"""平台内置影像预处理执行引擎测试。"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.core.imagery_files import calculate_sha256
from app.schemas.imagery import ImageryStepExecuteRequest
from app.services.imagery_processing_engine import ImageryProcessingEngine
from app.services.imagery_service import ImageryService


def write_four_band_raster(path: Path) -> None:
    """写出具有 WGS84 空间参考的四波段测试影像。"""
    rows, columns = 8, 10
    base = np.arange(rows * columns, dtype="uint16").reshape(rows, columns)
    data = np.stack([base + 100, base + 200, base + 300, base + 500])
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=columns,
        height=rows,
        count=4,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(126.5, 45.9, 0.01, 0.01),
    ) as output:
        output.write(data)


def test_engine_executes_complete_parameterized_raster_chain(
    tmp_path: Path,
) -> None:
    """验证五个步骤均生成可读取且具有真实处理结果的 GeoTIFF。"""
    engine = ImageryProcessingEngine()
    source_path = tmp_path / "source.tif"
    radiometric_path = tmp_path / "radiometric.tif"
    atmospheric_path = tmp_path / "atmospheric.tif"
    geometric_path = tmp_path / "geometric.tif"
    clipped_path = tmp_path / "clipped.tif"
    products_path = tmp_path / "products.tif"
    write_four_band_raster(source_path)

    radiometric = engine.execute(
        "radiometric",
        source_path,
        radiometric_path,
        {"scale_factor": 0.0001, "add_offset": 0},
    )
    atmospheric = engine.execute(
        "atmospheric",
        radiometric_path,
        atmospheric_path,
        {"dark_percentile": 1},
    )
    geometric = engine.execute(
        "geometric",
        atmospheric_path,
        geometric_path,
        {"target_crs": "EPSG:4490"},
    )
    clipped = engine.execute(
        "clip",
        geometric_path,
        clipped_path,
        {"boundary_code": "230000"},
        {
            "type": "Polygon",
            "coordinates": [[
                [126.52, 45.83],
                [126.58, 45.83],
                [126.58, 45.88],
                [126.52, 45.88],
                [126.52, 45.83],
            ]],
        },
    )
    products = engine.execute(
        "band_products",
        clipped_path,
        products_path,
        {"red_band": 1, "green_band": 2, "blue_band": 3, "nir_band": 4},
    )

    assert radiometric.dtype == "float32"
    assert radiometric.parameters["scale_factor"] == 0.0001
    assert atmospheric.parameters["model"] == "DOS1"
    assert len(atmospheric.parameters["dark_values"]) == 4
    assert geometric.crs == "EPSG:4490"
    assert clipped.width < geometric.width
    assert clipped.height < geometric.height
    assert products.band_count == 7
    with rasterio.open(products_path) as dataset:
        assert dataset.descriptions[-1] == "ndvi"
        ndvi = dataset.read()[6]
        assert float(ndvi.min()) >= -1
        assert float(ndvi.max()) <= 1


def test_service_executes_step_and_persists_checksum_evidence(
    tmp_path: Path,
) -> None:
    """验证业务服务使用稳定用户编码执行并保存完整产物证据。"""
    asset_dir = tmp_path / "assets" / "DEMO-RASTER"
    asset_dir.mkdir(parents=True)
    source_path = asset_dir / "source.tif"
    write_four_band_raster(source_path)
    asset = SimpleNamespace(
        id=3,
        project_id=7,
        asset_code="DEMO-RASTER",
        asset_name="测试四波段影像",
        sensor_type="TEST-MSI",
        acquired_at=datetime(2026, 6, 18, tzinfo=UTC),
        cloud_cover=0,
        resolution_m=1000,
        processing_level="L1A",
        calibration_status="pending",
        correction_status="pending",
        file_uri="storage://imagery/assets/DEMO-RASTER/source.tif",
        file_size_bytes=source_path.stat().st_size,
        checksum_sha256=calculate_sha256(source_path),
    )
    step = SimpleNamespace(
        step_code="radiometric",
        step_name="辐射定标",
        sequence=1,
        status="pending",
        progress=0,
        parameters={"output": "TOA reflectance"},
        output_uri=None,
        started_at=None,
        completed_at=None,
        updated_at=None,
    )
    downstream_step = SimpleNamespace(
        step_code="atmospheric",
        step_name="大气校正",
        sequence=2,
        status="completed",
        progress=100,
        parameters={
            "model": "DOS1",
            "artifact_evidence": {
                "relative_path": "processed/DEMO-RASTER/old-atmospheric.tif",
                "checksum_sha256": "old-checksum",
            },
        },
        output_uri="storage://imagery/processed/DEMO-RASTER/old-atmospheric.tif",
        started_at=datetime(2026, 7, 21, tzinfo=UTC),
        completed_at=datetime(2026, 7, 21, tzinfo=UTC),
        updated_at=datetime(2026, 7, 21, tzinfo=UTC),
    )
    dao = AsyncMock()
    dao.get_asset_by_code_for_update.return_value = asset
    dao.get_asset_by_code.return_value = asset
    dao.get_step_for_update.return_value = step
    dao.get_steps.return_value = [step, downstream_step]
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=7,
    )
    project_user_service = AsyncMock()
    project_user_service.require_capability.return_value = SimpleNamespace(
        user_code="interp-li-jing",
        display_name="李静",
        role_code="interpreter",
    )
    service = ImageryService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
    )
    service.storage_dir = tmp_path
    db = AsyncMock()

    response = asyncio.run(
        service.execute_step(
            db,
            "DEMO-RASTER",
            "radiometric",
            "RS-2026-045",
            ImageryStepExecuteRequest(
                operator_code="interp-li-jing",
                parameters={"scale_factor": 0.0001, "add_offset": 0},
                comment="使用公开定标比例系数执行",
            ),
        )
    )

    evidence = step.parameters["artifact_evidence"]
    output_path = tmp_path / evidence["relative_path"]
    assert output_path.is_file()
    assert evidence["execution_mode"] == "built_in"
    assert evidence["execution_parameters"]["scale_factor"] == 0.0001
    assert evidence["output_band_count"] == 4
    assert evidence["checksum_sha256"] == calculate_sha256(output_path)
    assert response.steps[0].output_verified is True
    assert response.completion_rate == 50
    assert asset.calibration_status == "completed"
    assert asset.correction_status == "pending"
    assert downstream_step.status == "pending"
    assert downstream_step.output_uri is None
    assert "artifact_evidence" not in downstream_step.parameters
    assert downstream_step.parameters["artifact_history"][0][
        "superseded_by_step"
    ] == "radiometric"
    project_user_service.require_capability.assert_awaited_once_with(
        db,
        7,
        "interp-li-jing",
        "process_imagery",
    )
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()
