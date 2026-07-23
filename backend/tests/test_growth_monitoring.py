"""多时相 NDVI 长势监测引擎与服务门禁测试。"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.core.exceptions import ValidationException
from app.dao.growth_monitoring_dao import GrowthCoverageScope, GrowthTaskScope
from app.schemas.growth_monitoring import (
    GrowthMonitoringCreateRequest,
    GrowthMonitoringSourceResponse,
)
from app.services.delivery_service import DeliveryService
from app.services.growth_monitoring_engine import (
    GrowthExecutionResult,
    GrowthMonitoringEngine,
    GrowthRasterSource,
    RawGrowthZone,
)
from app.services.growth_monitoring_service import (
    GrowthMonitoringService,
    InspectedGrowthSource,
)


def write_ndvi_product(
    path: Path,
    ndvi: np.ndarray,
    nodata_mask: np.ndarray | None = None,
) -> tuple[int, str]:
    """写出包含唯一 NDVI 描述的七波段实体产品。

    Args:
        path: 输出 GeoTIFF 路径。
        ndvi: NDVI 二维数组。
        nodata_mask: 可选无效像元掩膜。

    Returns:
        tuple[int, str]: 文件大小和 SHA-256 占位值。
    """
    height, width = ndvi.shape
    data = np.full((7, height, width), 0.2, dtype="float32")
    data[6] = ndvi
    if nodata_mask is not None:
        data[:, nodata_mask] = np.nan
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=7,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(126.0, 46.0, 0.001, 0.001),
        nodata=np.nan,
    ) as dataset:
        dataset.write(data)
        for index, description in enumerate(
            ["red", "green", "blue", "nir", "true_color", "false_color", "NDVI"],
            start=1,
        ):
            dataset.set_band_description(index, description)
    return path.stat().st_size, "a" * 64


def build_source(path: Path, code: str) -> GrowthRasterSource:
    """构造已通过服务层实体校验的引擎来源。

    Args:
        path: NDVI 产品路径。
        code: 资产编号。

    Returns:
        GrowthRasterSource: 长势引擎输入。
    """
    return GrowthRasterSource(
        path=path,
        asset_code=code,
        source_uri=f"storage://imagery/{path.name}",
        source_size_bytes=path.stat().st_size,
        source_sha256="a" * 64,
        ndvi_band_index=7,
    )


def task_polygon() -> dict:
    """构造覆盖测试栅格的 WGS84 任务耕地范围。

    Returns:
        dict: GeoJSON Polygon。
    """
    return {
        "type": "Polygon",
        "coordinates": [[
            [126.0, 45.99],
            [126.01, 45.99],
            [126.01, 46.0],
            [126.0, 46.0],
            [126.0, 45.99],
        ]],
    }


def test_growth_engine_generates_real_classification_and_anomaly_zone(
    tmp_path: Path,
) -> None:
    """验证两期 NDVI 在任务掩膜内形成好、正常、差和物理 GeoTIFF。"""
    baseline_path = tmp_path / "baseline.tif"
    current_path = tmp_path / "current.tif"
    baseline = np.full((10, 10), 0.5, dtype="float32")
    current = np.full((10, 10), 0.52, dtype="float32")
    current[:, :3] = 0.35
    current[:, 7:] = 0.65
    write_ndvi_product(baseline_path, baseline)
    write_ndvi_product(current_path, current)
    output_path = tmp_path / "growth-class.tif"

    result = GrowthMonitoringEngine(max_output_pixels=1_000).execute(
        build_source(baseline_path, "BASELINE"),
        build_source(current_path, "CURRENT"),
        task_polygon(),
        output_path,
        -0.05,
        0.05,
        0.95,
        "GROWTH-TEST-001",
    )

    assert output_path.is_file()
    assert result.valid_pixel_count == 100
    assert result.poor_pixel_count == 30
    assert result.normal_pixel_count == 40
    assert result.good_pixel_count == 30
    assert result.valid_pixel_ratio == pytest.approx(1)
    assert len(result.raw_zones) == 1
    assert result.raw_zones[0].delta_mean == pytest.approx(-0.15, abs=1e-5)
    assert result.raw_zones[0].geometry["type"] == "Polygon"
    with rasterio.open(output_path) as dataset:
        classes = dataset.read(1)
        assert dataset.descriptions[0] == "growth_class"
        assert set(np.unique(classes)) == {1, 2, 3}
        assert dataset.tags()["BASELINE_ASSET"] == "BASELINE"


def test_growth_engine_rejects_insufficient_common_valid_coverage(
    tmp_path: Path,
) -> None:
    """验证监测期缺测超过门槛时不得发布部分长势成果。"""
    baseline_path = tmp_path / "baseline.tif"
    current_path = tmp_path / "current.tif"
    values = np.full((10, 10), 0.5, dtype="float32")
    nodata_mask = np.zeros((10, 10), dtype=bool)
    nodata_mask[:, :5] = True
    write_ndvi_product(baseline_path, values)
    write_ndvi_product(current_path, values, nodata_mask)
    output_path = tmp_path / "growth-class.tif"

    with pytest.raises(ValidationException, match="有效像元率"):
        GrowthMonitoringEngine(max_output_pixels=1_000).execute(
            build_source(baseline_path, "BASELINE"),
            build_source(current_path, "CURRENT"),
            task_polygon(),
            output_path,
            -0.05,
            0.05,
            0.8,
            "GROWTH-TEST-002",
        )

    assert not output_path.exists()


def test_growth_create_schema_rejects_same_temporal_asset() -> None:
    """验证 API 模型不允许同一影像冒充两个时相。"""
    from pydantic import ValidationError

    from app.schemas.growth_monitoring import GrowthMonitoringCreateRequest

    with pytest.raises(ValidationError, match="两个不同影像资产"):
        GrowthMonitoringCreateRequest.model_validate(
            {
                "run_code": "GROWTH-TEST-003",
                "run_name": "测试长势监测",
                "baseline_asset_code": "SAME",
                "current_asset_code": "SAME",
                "operator_code": "manager-zhao-zhiyuan",
                "comment": "验证相同时相资产必须被拒绝",
            }
        )


def test_growth_output_manifest_is_json_serializable(tmp_path: Path) -> None:
    """验证引擎证据清单可以稳定写入数据库 JSONB。"""
    baseline_path = tmp_path / "baseline.tif"
    current_path = tmp_path / "current.tif"
    values = np.full((4, 4), 0.5, dtype="float32")
    write_ndvi_product(baseline_path, values)
    write_ndvi_product(current_path, values + 0.1)
    result = GrowthMonitoringEngine(max_output_pixels=100).execute(
        build_source(baseline_path, "BASELINE"),
        build_source(current_path, "CURRENT"),
        task_polygon(),
        tmp_path / "growth.tif",
        -0.05,
        0.05,
        0.9,
        "GROWTH-TEST-004",
    )

    payload = json.dumps(result.manifest, sort_keys=True)
    assert "valid_pixel_ratio" in payload


def test_growth_service_persists_physical_artifacts_and_stable_audit(
    tmp_path: Path,
) -> None:
    """验证服务编排保存来源 SHA、PostGIS 异常区和用户角色审计。"""
    generated_at = datetime(2026, 7, 23, 2, tzinfo=UTC)
    baseline_asset = SimpleNamespace(
        id=11,
        asset_code="BASELINE",
        asset_name="基准期公开影像",
        acquired_at=datetime(2026, 6, 20, tzinfo=UTC),
    )
    current_asset = SimpleNamespace(
        id=12,
        asset_code="CURRENT",
        asset_name="监测期公开影像",
        acquired_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    baseline_row = SimpleNamespace(
        asset=baseline_asset,
        step=SimpleNamespace(id=21),
    )
    current_row = SimpleNamespace(
        asset=current_asset,
        step=SimpleNamespace(id=22),
    )
    dao = AsyncMock()
    dao.get_run.return_value = None
    dao.get_source_row.side_effect = [baseline_row, current_row]
    dao.get_task_scope.return_value = GrowthTaskScope(
        plot_count=2,
        task_updated_at=generated_at,
        farmland_area_ha=12.5,
        geometry_json=json.dumps(task_polygon()),
    )
    dao.get_coverage_scope.return_value = GrowthCoverageScope(
        task_farmland_area_ha=12.5,
        common_footprint_farmland_area_ha=10.0,
        spatial_coverage_ratio=0.8,
        geometry_json=json.dumps(task_polygon()),
    )
    dao.analyze_clipped_zone.return_value = {
        "geometry_json": json.dumps({
            "type": "MultiPolygon",
            "coordinates": [task_polygon()["coordinates"]],
        }),
        "area_ha": 0.6,
    }

    async def add_run(_db: object, run: object):
        run.id = 31
        run.created_at = generated_at
        return run

    dao.add_run.side_effect = add_run
    workbench_dao = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=9)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=3,
        project_id=9,
        task_code="RS-2026-045",
    )
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )
    engine = MagicMock()
    engine.max_output_pixels = 10_000
    engine.processor_version = "ndvi-delta-task-mask-v1"

    def execute(
        _baseline: object,
        _current: object,
        _geometry: object,
        output_path: Path,
        *_args: object,
    ) -> GrowthExecutionResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            width=2,
            height=2,
            count=1,
            dtype="uint8",
            crs="EPSG:4326",
            transform=from_origin(126, 46, 0.001, 0.001),
            nodata=0,
        ) as dataset:
            dataset.write(np.array([[1, 2], [3, 2]], dtype="uint8"), 1)
            dataset.set_band_description(1, "growth_class")
        return GrowthExecutionResult(
            width=2,
            height=2,
            crs="EPSG:4326",
            resolution_x=0.001,
            resolution_y=0.001,
            bounds_wgs84=[126, 45.998, 126.002, 46],
            common_footprint_mask_pixel_count=4,
            valid_pixel_count=4,
            valid_pixel_ratio=1,
            poor_pixel_count=1,
            normal_pixel_count=2,
            good_pixel_count=1,
            raw_zones=[
                RawGrowthZone(
                    geometry=task_polygon(),
                    baseline_mean=0.5,
                    current_mean=0.35,
                    delta_mean=-0.15,
                    pixel_count=1,
                )
            ],
            manifest={"processor_version": "ndvi-delta-task-mask-v1"},
        )

    engine.execute.side_effect = execute
    service = GrowthMonitoringService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        imagery_service=MagicMock(),
        engine=engine,
    )
    service.storage_root = tmp_path / "growth-monitoring"
    service._inspect_source = MagicMock(side_effect=[
        InspectedGrowthSource(
            response=GrowthMonitoringSourceResponse(
                asset_code="BASELINE",
                asset_name="基准期公开影像",
                acquired_at=baseline_asset.acquired_at,
                data_status="operational",
                source_uri="storage://baseline.tif",
                source_size_bytes=100,
                source_sha256="a" * 64,
                ndvi_band_index=7,
                eligible=True,
                unavailable_reason=None,
            ),
            engine_source=GrowthRasterSource(
                path=tmp_path / "baseline.tif",
                asset_code="BASELINE",
                source_uri="storage://baseline.tif",
                source_size_bytes=100,
                source_sha256="a" * 64,
                ndvi_band_index=7,
            ),
            step_id=21,
        ),
        InspectedGrowthSource(
            response=GrowthMonitoringSourceResponse(
                asset_code="CURRENT",
                asset_name="监测期公开影像",
                acquired_at=current_asset.acquired_at,
                data_status="operational",
                source_uri="storage://current.tif",
                source_size_bytes=120,
                source_sha256="b" * 64,
                ndvi_band_index=7,
                eligible=True,
                unavailable_reason=None,
            ),
            engine_source=GrowthRasterSource(
                path=tmp_path / "current.tif",
                asset_code="CURRENT",
                source_uri="storage://current.tif",
                source_size_bytes=120,
                source_sha256="b" * 64,
                ndvi_band_index=7,
            ),
            step_id=22,
        ),
    ])
    request = GrowthMonitoringCreateRequest.model_validate({
        "run_code": "GROWTH-SERVICE-001",
        "run_name": "服务编排测试",
        "baseline_asset_code": "BASELINE",
        "current_asset_code": "CURRENT",
        "poor_delta_threshold": -0.05,
        "good_delta_threshold": 0.05,
        "minimum_zone_area_ha": 0.1,
        "minimum_spatial_coverage_ratio": 0.8,
        "minimum_valid_pixel_ratio": 0.8,
        "operator_code": "manager-zhao-zhiyuan",
        "comment": "验证实体文件、异常区和稳定用户审计完整保存",
    })
    db = AsyncMock()

    response = asyncio.run(
        service.create_run(db, "RS-2026", "RS-2026-045", request)
    )

    assert response.anomaly_zone_count == 1
    assert response.anomaly_area_ha == pytest.approx(0.6)
    assert response.task_farmland_area_ha == pytest.approx(12.5)
    assert response.common_footprint_farmland_area_ha == pytest.approx(10)
    assert response.spatial_coverage_ratio == pytest.approx(0.8)
    assert response.valid_pixel_ratio == pytest.approx(1)
    assert response.classification_verified is True
    assert response.anomaly_verified is True
    dao.get_coverage_scope.assert_awaited_once_with(db, 3, 11, 12)
    dao.insert_zone.assert_awaited_once()
    event = dao.add_event.await_args.args[1]
    assert event.actor_code == "manager-zhao-zhiyuan"
    assert event.actor_role == "project_manager"
    db.commit.assert_awaited_once()


def test_growth_source_revalidation_rejects_changed_sha(tmp_path: Path) -> None:
    """验证下载和交付前来源步骤 SHA 变化会阻断旧长势成果。"""
    source_path = tmp_path / "source.tif"
    write_ndvi_product(
        source_path,
        np.full((2, 2), 0.5, dtype="float32"),
    )
    baseline_step = SimpleNamespace(
        id=21,
        status="completed",
        output_uri="storage://imagery/baseline.tif",
    )
    current_step = SimpleNamespace(
        id=22,
        status="completed",
        output_uri="storage://imagery/current.tif",
    )
    dao = AsyncMock()
    dao.get_source_steps.return_value = [baseline_step, current_step]
    imagery_service = MagicMock()
    imagery_service.resolve_verified_step_artifact_path.return_value = (
        source_path,
        {
            "file_size_bytes": source_path.stat().st_size,
            "checksum_sha256": "b" * 64,
        },
    )
    service = GrowthMonitoringService(
        dao=dao,
        imagery_service=imagery_service,
        engine=GrowthMonitoringEngine(max_output_pixels=100),
    )
    run = SimpleNamespace(
        baseline_step_id=21,
        current_step_id=22,
        baseline_source_uri=baseline_step.output_uri,
        current_source_uri=current_step.output_uri,
        baseline_source_size_bytes=source_path.stat().st_size,
        current_source_size_bytes=source_path.stat().st_size,
        baseline_source_sha256="a" * 64,
        current_source_sha256="b" * 64,
        manifest={
            "baseline": {"ndvi_band_index": 7},
            "current": {"ndvi_band_index": 7},
        },
    )

    with pytest.raises(ValidationException, match="基准期 NDVI 来源 SHA-256 已变化"):
        asyncio.run(service.verify_run_sources(AsyncMock(), run))


def test_delivery_loader_embeds_verified_growth_artifacts(tmp_path: Path) -> None:
    """验证最终成果归档会嵌入长势分级和异常区物理实体。"""
    classification_path = tmp_path / "growth.tif"
    classification_path.write_bytes(b"II*\x00verified-growth-raster")
    anomaly_path = tmp_path / "growth.geojson"
    anomaly_path.write_text(
        '{"type":"FeatureCollection","features":[]}',
        encoding="utf-8",
    )
    run = SimpleNamespace(
        run_code="GROWTH-DELIVERY-001",
        classification_filename="growth-class.tif",
        anomaly_filename="growth-anomalies.geojson",
        valid_pixel_count=128,
        anomaly_zone_count=0,
        anomaly_area_ha=0,
        baseline_asset_code="BASELINE",
        current_asset_code="CURRENT",
        task_updated_at=datetime(2026, 7, 23, tzinfo=UTC),
        classification_uri="storage://growth-monitoring/growth.tif",
        anomaly_uri="storage://growth-monitoring/growth.geojson",
    )
    growth_service = MagicMock()
    growth_service.verify_run_for_delivery = AsyncMock(return_value=(
        classification_path,
        anomaly_path,
    ))
    service = DeliveryService(growth_monitoring_service=growth_service)

    artifacts = asyncio.run(
        service._load_growth_monitoring_artifacts(
            AsyncMock(),
            [run],
            SimpleNamespace(updated_at=run.task_updated_at),
        )
    )

    assert len(artifacts) == 2
    assert artifacts[0]["path"].endswith("growth-class.tif")
    assert artifacts[1]["path"].endswith("growth-anomalies.geojson")
    assert artifacts[0]["content"] == classification_path.read_bytes()
