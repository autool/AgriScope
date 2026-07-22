"""平台内置影像预处理执行引擎测试。"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.transform import from_origin

from app.core.exceptions import ValidationException
from app.core.imagery_files import calculate_sha256
from app.schemas.imagery import (
    ImagerySourceLevelAcceptRequest,
    ImageryStepExecuteRequest,
)
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


def write_l2a_reflectance_raster(path: Path, *, scale_applied: bool = True) -> None:
    """写出带完整 Sentinel-2 L2A 源级承认证据的浮点反射率。"""
    rows, columns = 8, 10
    base = np.linspace(0.01, 0.8, rows * columns, dtype="float32").reshape(
        rows,
        columns,
    )
    data = np.stack([base, base * 0.9, base * 0.8, base * 1.2])
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=columns,
        height=rows,
        count=4,
        dtype="float32",
        crs="EPSG:32651",
        transform=from_origin(700000, 5080000, 10, 10),
    ) as output:
        output.write(data)
        output.descriptions = ("Blue", "Green", "Red", "NIR")
        output.update_tags(
            PLATFORM="Sentinel-2B",
            INSTRUMENT="MSI",
            PROCESSING_LEVEL="L2A",
            SOURCE_PROVIDER="AWS Open Data / Element 84 Earth Search",
            SOURCE_PRODUCT_URI="S2B_TEST.SAFE",
            SOURCE_PROCESSING_BASELINE="05.12",
            SOURCE_SCALE_APPLIED="true" if scale_applied else "false",
            REFLECTANCE_QUANTITY="BOA_REFLECTANCE",
            SECURITY_CLASSIFICATION="public",
            STAC_ITEM_ID="S2B_TEST_L2A",
            SOURCE_LICENSE_URL="https://example.test/sentinel-license",
        )


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
        ndvi = dataset.read(7, masked=True)
        assert ndvi.count() > 0
        assert float(ndvi.min()) >= -1
        assert float(ndvi.max()) <= 1


def test_engine_rejects_duplicate_band_product_mapping(tmp_path: Path) -> None:
    """验证真彩色、假彩色和 NDVI 不允许复用同一波段冒充不同光谱。"""
    source_path = tmp_path / "source.tif"
    write_four_band_raster(source_path)

    with pytest.raises(ValidationException, match="四个不同波段"):
        ImageryProcessingEngine().execute(
            "band_products",
            source_path,
            tmp_path / "invalid-products.tif",
            {"red_band": 1, "green_band": 1, "blue_band": 3, "nir_band": 4},
        )


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


def test_source_level_acceptance_requires_explicit_no_algorithm_confirmation() -> None:
    """验证源级承认必须明确确认不会执行或伪造重复算法。"""
    with pytest.raises(ValidationError, match="不执行重复算法"):
        ImagerySourceLevelAcceptRequest(
            operator_code="manager-zhao-zhiyuan",
            expected_processing_level="L2A",
            confirm_no_algorithm_execution=False,
            justification="已核对 Sentinel-2 L2A 官方产品级别",
        )


def test_service_accepts_verified_l2a_source_without_copying_or_processing(
    tmp_path: Path,
) -> None:
    """验证 L2A 源级承认复用同一实体、保存依据且不调用处理引擎。"""
    asset_dir = tmp_path / "assets" / "S2B-L2A"
    asset_dir.mkdir(parents=True)
    source_path = asset_dir / "source.tif"
    write_l2a_reflectance_raster(source_path)
    asset = SimpleNamespace(
        id=8,
        project_id=7,
        asset_code="S2B-L2A",
        asset_name="Sentinel-2B L2A 公开影像",
        sensor_type="Sentinel-2B MSI",
        acquired_at=datetime(2026, 7, 16, tzinfo=UTC),
        cloud_cover=4.04,
        resolution_m=10,
        processing_level="L2A",
        calibration_status="pending",
        correction_status="pending",
        file_uri="storage://imagery/assets/S2B-L2A/source.tif",
        file_size_bytes=source_path.stat().st_size,
        checksum_sha256=calculate_sha256(source_path),
    )
    radiometric_step = SimpleNamespace(
        step_code="radiometric",
        step_name="辐射定标",
        sequence=1,
        status="pending",
        progress=0,
        parameters={},
        output_uri=None,
        started_at=None,
        completed_at=None,
        updated_at=None,
    )
    atmospheric_step = SimpleNamespace(
        step_code="atmospheric",
        step_name="大气校正",
        sequence=2,
        status="pending",
        progress=0,
        parameters={},
        output_uri=None,
        started_at=None,
        completed_at=None,
        updated_at=None,
    )
    dao = AsyncMock()
    dao.get_asset_by_code_for_update.return_value = asset
    dao.get_asset_by_code.return_value = asset
    dao.get_step_for_update.return_value = radiometric_step
    dao.get_steps.return_value = [radiometric_step, atmospheric_step]
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=7,
    )
    project_user_service = AsyncMock()
    project_user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    processing_engine = MagicMock()
    service = ImageryService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
        processing_engine=processing_engine,
    )
    service.storage_dir = tmp_path
    db = AsyncMock()

    response = asyncio.run(
        service.accept_source_level_step(
            db,
            "S2B-L2A",
            "radiometric",
            "RS-2026-045",
            ImagerySourceLevelAcceptRequest(
                operator_code="manager-zhao-zhiyuan",
                expected_processing_level="L2A",
                confirm_no_algorithm_execution=True,
                justification="STAC 标度已在导入时应用，源文件为 L2A 地表反射率",
            ),
        )
    )

    evidence = radiometric_step.parameters["artifact_evidence"]
    assert evidence["execution_mode"] == "source_level_acceptance"
    assert evidence["algorithm_executed"] is False
    assert evidence["source_evidence"]["processing_level"] == "L2A"
    assert evidence["source_evidence"]["reflectance_quantity"] == (
        "BOA_REFLECTANCE"
    )
    assert evidence["relative_path"] == "assets/S2B-L2A/source.tif"
    assert evidence["checksum_sha256"] == calculate_sha256(source_path)
    assert response.completion_rate == 50
    assert asset.calibration_status == "completed"
    assert list(tmp_path.rglob("*.tif")) == [source_path]
    processing_engine.execute.assert_not_called()
    review_record = workbench_dao.add_review_record.await_args.args[1]
    assert review_record.action == "source_level_accepted"
    assert review_record.reviewer_code == "manager-zhao-zhiyuan"
    db.commit.assert_awaited_once()


def test_service_rejects_l2a_source_without_applied_stac_scale(
    tmp_path: Path,
) -> None:
    """验证仍为量化 DN 的 L2A 文件不能绕过辐射定标。"""
    source_path = tmp_path / "source.tif"
    write_l2a_reflectance_raster(source_path, scale_applied=False)
    asset = SimpleNamespace(
        id=8,
        project_id=7,
        asset_code="S2B-L2A",
        processing_level="L2A",
        file_uri="storage://imagery/source.tif",
        file_size_bytes=source_path.stat().st_size,
        checksum_sha256=calculate_sha256(source_path),
    )
    step = SimpleNamespace(
        step_code="radiometric",
        step_name="辐射定标",
        sequence=1,
        status="pending",
        progress=0,
        parameters={},
        output_uri=None,
        started_at=None,
        completed_at=None,
        updated_at=None,
    )
    dao = AsyncMock()
    dao.get_asset_by_code_for_update.return_value = asset
    dao.get_step_for_update.return_value = step
    dao.get_steps.return_value = [step]
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=7,
    )
    project_user_service = AsyncMock()
    project_user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    service = ImageryService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
    )
    service.storage_dir = tmp_path

    with pytest.raises(ValidationException, match="尚未应用 STAC 反射率标度"):
        asyncio.run(
            service.accept_source_level_step(
                AsyncMock(),
                "S2B-L2A",
                "radiometric",
                "RS-2026-045",
                ImagerySourceLevelAcceptRequest(
                    operator_code="manager-zhao-zhiyuan",
                    expected_processing_level="L2A",
                    confirm_no_algorithm_execution=True,
                    justification="准备核对源产品级别并承认定标要求已经满足",
                ),
            )
        )
