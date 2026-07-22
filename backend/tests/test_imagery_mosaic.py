"""多景影像匀色、镶嵌、覆盖率验收和实体成果测试。"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.transform import from_origin

from app.core.exceptions import ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.imagery_mosaic_dao import MosaicSourceRecord
from app.schemas.imagery_mosaic import (
    ImageryMosaicCreateRequest,
    ImageryMosaicSourceRequest,
)
from app.services.imagery_mosaic_engine import ImageryMosaicEngine, MosaicSource
from app.services.imagery_mosaic_service import ImageryMosaicService
from app.services.imagery_service import ImageryService


def write_mosaic_source(path: Path, *, left: float, offset: float) -> None:
    """写出带重叠范围和不同亮度偏移的两波段影像。"""
    rows, columns = 50, 60
    gradient = np.linspace(0, 100, rows * columns, dtype="float32").reshape(
        rows,
        columns,
    )
    data = np.stack([gradient + offset, gradient * 0.8 + offset])
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=columns,
        height=rows,
        count=2,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(left, 1.0, 0.01, 0.01),
        nodata=np.nan,
    ) as output:
        output.write(data)
        output.descriptions = ("red", "nir")


def mosaic_boundary(right: float = 0.9) -> dict:
    """构造覆盖测试镶嵌范围的 WGS84 行政区多边形。"""
    return {
        "type": "Polygon",
        "coordinates": [[
            [0.1, 0.55],
            [right, 0.55],
            [right, 0.95],
            [0.1, 0.95],
            [0.1, 0.55],
        ]],
    }


def engine_sources(tmp_path: Path) -> list[MosaicSource]:
    """写出并返回两个已校验引擎来源。"""
    first = tmp_path / "first.tif"
    second = tmp_path / "second.tif"
    write_mosaic_source(first, left=0.0, offset=0)
    write_mosaic_source(second, left=0.4, offset=40)
    return [
        MosaicSource(
            asset_code="SOURCE-A",
            asset_name="来源 A",
            step_code="clip",
            step_name="行政区裁剪",
            path=first,
            source_uri="storage://imagery/first.tif",
            source_size_bytes=first.stat().st_size,
            source_sha256=calculate_sha256(first),
        ),
        MosaicSource(
            asset_code="SOURCE-B",
            asset_name="来源 B",
            step_code="clip",
            step_name="行政区裁剪",
            path=second,
            source_uri="storage://imagery/second.tif",
            source_size_bytes=second.stat().st_size,
            source_sha256=calculate_sha256(second),
        ),
    ]


def test_mosaic_engine_balances_merges_and_accepts_real_coverage(
    tmp_path: Path,
) -> None:
    """验证多景重投影、均值标准差匀色、均值合成和覆盖验收。"""
    output_path = tmp_path / "mosaic.tif"

    result = ImageryMosaicEngine(max_output_pixels=100_000).execute(
        engine_sources(tmp_path),
        output_path,
        mosaic_boundary(),
        "EPSG:4326",
        0.01,
        "mean_std",
        "mean",
        "bilinear",
        98,
        "MOSAIC-TEST-001",
    )

    assert output_path.is_file()
    assert result.width == 100
    assert result.height == 50
    assert result.band_count == 2
    assert result.coverage_ratio == 100
    assert result.inputs[1].balance_statistics["transforms"][0]["offset"] < 0
    with rasterio.open(output_path) as output:
        assert output.crs.to_string() == "EPSG:4326"
        assert output.tags()["COLOR_BALANCE_METHOD"] == "mean_std"
        assert output.tags()["BLEND_METHOD"] == "mean"
        assert output.read(1, masked=True).count() > 0


def test_mosaic_engine_rejects_low_coverage_and_oversized_grid(
    tmp_path: Path,
) -> None:
    """验证覆盖不足和预计像元超限时不生成部分镶嵌成果。"""
    sources = engine_sources(tmp_path)
    low_coverage_path = tmp_path / "low-coverage.tif"
    with pytest.raises(ValidationException, match="覆盖率"):
        ImageryMosaicEngine(max_output_pixels=100_000).execute(
            sources,
            low_coverage_path,
            mosaic_boundary(right=1.2),
            "EPSG:4326",
            0.01,
            "none",
            "first",
            "nearest",
            98,
            "MOSAIC-LOW",
        )
    assert not low_coverage_path.exists()

    with pytest.raises(ValidationException, match="超过上限"):
        ImageryMosaicEngine(max_output_pixels=10_000).execute(
            sources,
            tmp_path / "oversized.tif",
            mosaic_boundary(),
            "EPSG:4326",
            0.001,
            "none",
            "first",
            "nearest",
            90,
            "MOSAIC-LARGE",
        )


def test_mosaic_schema_rejects_duplicate_source() -> None:
    """验证同一资产步骤不能重复计入镶嵌输入。"""
    source = ImageryMosaicSourceRequest(asset_code="A", step_code="clip")
    with pytest.raises(ValidationError, match="不能重复"):
        ImageryMosaicCreateRequest(
            job_code="MOSAIC-001",
            job_name="重复来源测试",
            boundary_code="230000",
            target_crs="EPSG:4326",
            target_resolution=0.01,
            sources=[source, source],
            operator_code="manager-zhao-zhiyuan",
            comment="验证服务端拒绝重复选择同一影像来源",
        )


def test_mosaic_schema_rejects_multiple_steps_from_same_asset() -> None:
    """验证同一景影像不能用两个步骤产物伪装成多景输入。"""
    with pytest.raises(ValidationError, match="同一影像资产只能选择一个"):
        ImageryMosaicCreateRequest(
            job_code="MOSAIC-002",
            job_name="同景重复步骤测试",
            boundary_code="230000",
            target_crs="EPSG:4326",
            target_resolution=0.01,
            sources=[
                ImageryMosaicSourceRequest(
                    asset_code="SOURCE-A",
                    step_code="geometric",
                ),
                ImageryMosaicSourceRequest(
                    asset_code="SOURCE-A",
                    step_code="clip",
                ),
            ],
            operator_code="manager-zhao-zhiyuan",
            comment="验证一个影像资产不能重复充当两景镶嵌输入",
        )


def test_mosaic_engine_rejects_incompatible_or_constant_bands(
    tmp_path: Path,
) -> None:
    """验证波段语义不一致和常量波段不会生成伪匀色成果。"""
    mismatched_sources = engine_sources(tmp_path)
    with rasterio.open(mismatched_sources[1].path, "r+") as output:
        output.descriptions = ("green", "nir")
    mismatch_output = tmp_path / "mismatch.tif"
    with pytest.raises(ValidationException, match="波段描述不一致"):
        ImageryMosaicEngine(max_output_pixels=100_000).execute(
            mismatched_sources,
            mismatch_output,
            mosaic_boundary(),
            "EPSG:4326",
            0.01,
            "none",
            "first",
            "nearest",
            90,
            "MOSAIC-MISMATCH",
        )
    assert not mismatch_output.exists()

    constant_path = tmp_path / "constant.tif"
    with rasterio.open(
        constant_path,
        "w",
        driver="GTiff",
        width=60,
        height=50,
        count=2,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0.4, 1.0, 0.01, 0.01),
        nodata=np.nan,
    ) as output:
        output.write(np.full((2, 50, 60), 5, dtype="float32"))
        output.descriptions = ("red", "nir")
    normal_source = engine_sources(tmp_path)[0]
    constant_source = MosaicSource(
        asset_code="SOURCE-CONSTANT",
        asset_name="常量来源",
        step_code="clip",
        step_name="行政区裁剪",
        path=constant_path,
        source_uri="storage://imagery/constant.tif",
        source_size_bytes=constant_path.stat().st_size,
        source_sha256=calculate_sha256(constant_path),
    )
    constant_output = tmp_path / "constant-output.tif"
    with pytest.raises(ValidationException, match="动态范围不足"):
        ImageryMosaicEngine(max_output_pixels=100_000).execute(
            [normal_source, constant_source],
            constant_output,
            mosaic_boundary(),
            "EPSG:4326",
            0.01,
            "mean_std",
            "mean",
            "bilinear",
            90,
            "MOSAIC-CONSTANT",
        )
    assert not constant_output.exists()


def test_mosaic_service_persists_lineage_checksum_and_role(
    tmp_path: Path,
) -> None:
    """验证业务服务保存显式输入、实体校验值和稳定用户角色。"""
    sources = engine_sources(tmp_path)
    records = []
    for index, source in enumerate(sources, start=1):
        records.append(MosaicSourceRecord(
            asset=SimpleNamespace(
                id=index,
                asset_code=source.asset_code,
                asset_name=source.asset_name,
                acquired_at=datetime.now(UTC),
            ),
            step=SimpleNamespace(
                step_code="clip",
                step_name="行政区裁剪",
                output_uri=source.source_uri,
                parameters={
                    "artifact_evidence": {
                        "relative_path": source.path.name,
                        "file_size_bytes": source.source_size_bytes,
                        "checksum_sha256": source.source_sha256,
                    }
                },
            ),
        ))
    dao = AsyncMock()
    dao.get_job_by_code.return_value = None
    dao.get_boundary_geojson.return_value = (
        "测试行政区",
        __import__("json").dumps(mosaic_boundary()),
    )
    dao.list_source_records.return_value = records
    stored_inputs = []

    async def add_job(_: object, job: object) -> object:
        job.id = 9
        job.created_at = datetime.now(UTC)
        return job

    async def add_inputs(_: object, items: list[object]) -> None:
        stored_inputs.extend(items)

    dao.add_job.side_effect = add_job
    dao.add_inputs.side_effect = add_inputs
    dao.list_inputs.side_effect = lambda _db, _job_id: stored_inputs
    workbench_dao = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=7)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(id=3, project_id=7)
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )
    imagery_service = ImageryService()
    imagery_service.storage_dir = tmp_path
    service = ImageryMosaicService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
        imagery_service=imagery_service,
        engine=ImageryMosaicEngine(max_output_pixels=100_000),
    )
    service.storage_root = tmp_path / "mosaics"
    db = AsyncMock()

    response = asyncio.run(service.create_job(
        db,
        "RS-2026",
        "RS-2026-045",
        ImageryMosaicCreateRequest(
            job_code="MOSAIC-SERVICE-001",
            job_name="服务层镶嵌测试",
            boundary_code="230000",
            target_crs="EPSG:4326",
            target_resolution=0.01,
            coverage_threshold=98,
            sources=[
                ImageryMosaicSourceRequest(
                    asset_code=source.asset_code,
                    step_code="clip",
                )
                for source in sources
            ],
            operator_code="manager-zhao-zhiyuan",
            comment="使用两景已裁剪影像执行全局匀色和覆盖验收",
        ),
    ))

    assert response.meets_coverage is True
    assert response.source_count == 2
    assert len(response.checksum_sha256) == 64
    assert response.created_by_code == "manager-zhao-zhiyuan"
    assert response.created_by_role == "project_manager"
    assert len(stored_inputs) == 2
    assert stored_inputs[0].source_sha256 == sources[0].source_sha256
    dao.add_event.assert_awaited_once()
    db.commit.assert_awaited_once()
