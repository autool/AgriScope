"""双时相真实栅格公共网格预览与缓存清单测试。"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from app.core.imagery_files import calculate_sha256
from app.services.change_comparison_renderer import (
    ChangeComparisonRenderer,
    ChangeComparisonRenderResult,
)
from app.services.change_comparison_service import ChangeComparisonService


def write_test_raster(
    path: Path,
    bounds: tuple[float, float, float, float],
    base_value: int,
    scale: int = 1,
) -> None:
    """写入带 CRS 和 RGB 波段描述的测试 GeoTIFF。"""
    width = 80
    height = 60
    data = np.zeros((3, height, width), dtype="uint16")
    x_gradient = np.arange(width, dtype="uint16")[None, :]
    y_gradient = np.arange(height, dtype="uint16")[:, None]
    data[0] = base_value + x_gradient * scale
    data[1] = base_value + y_gradient * scale
    data[2] = base_value + (x_gradient + y_gradient) * scale
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=3,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_bounds(*bounds, width, height),
    ) as dataset:
        dataset.write(data)
        dataset.set_band_description(1, "Red")
        dataset.set_band_description(2, "Green")
        dataset.set_band_description(3, "Blue")


def test_renderer_outputs_same_grid_and_shared_png_dimensions(tmp_path: Path) -> None:
    """验证两期栅格使用同一公共范围、尺寸和共同拉伸。"""
    baseline_path = tmp_path / "baseline.tif"
    target_path = tmp_path / "target.tif"
    write_test_raster(baseline_path, (126.0, 45.0, 127.0, 46.0), 100)
    write_test_raster(target_path, (126.4, 45.2, 127.4, 46.2), 300)

    result = ChangeComparisonRenderer().render_pair(
        baseline_path,
        target_path,
        512,
    )

    assert result.bounds_wgs84 == pytest.approx((126.4, 45.2, 127.0, 46.0))
    assert result.baseline_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert result.target_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert result.baseline_band_indexes == (1, 2, 3)
    assert result.target_band_indexes == (1, 2, 3)
    assert int.from_bytes(result.baseline_png[16:20], "big") == result.width
    assert int.from_bytes(result.baseline_png[20:24], "big") == result.height
    assert result.baseline_png[25] == 6
    assert int.from_bytes(result.target_png[16:20], "big") == result.width
    assert int.from_bytes(result.target_png[20:24], "big") == result.height
    assert result.target_png[25] == 6


def test_renderer_rejects_non_overlapping_rasters(tmp_path: Path) -> None:
    """验证无公共覆盖范围时不生成误导性对比图。"""
    baseline_path = tmp_path / "baseline.tif"
    target_path = tmp_path / "target.tif"
    write_test_raster(baseline_path, (126.0, 45.0, 126.2, 45.2), 100)
    write_test_raster(target_path, (127.0, 46.0, 127.2, 46.2), 300)

    with pytest.raises(ValueError, match="没有公共覆盖范围"):
        ChangeComparisonRenderer().render_pair(
            baseline_path,
            target_path,
            512,
        )


def test_renderer_rejects_incompatible_radiometric_scale(tmp_path: Path) -> None:
    """验证量纲差异过大的影像不会被共同拉伸成误导性黑图。"""
    baseline_path = tmp_path / "baseline.tif"
    target_path = tmp_path / "target.tif"
    write_test_raster(baseline_path, (126.0, 45.0, 127.0, 46.0), 10, 1)
    write_test_raster(target_path, (126.0, 45.0, 127.0, 46.0), 100, 200)

    with pytest.raises(ValueError, match="辐射量纲差异过大"):
        ChangeComparisonRenderer().render_pair(
            baseline_path,
            target_path,
            512,
        )


class CountingRenderer(ChangeComparisonRenderer):
    """记录实际栅格渲染次数的测试渲染器。"""

    def __init__(self) -> None:
        """初始化渲染计数器。"""
        self.render_count = 0

    def render_pair(
        self,
        baseline_path: Path,
        target_path: Path,
        max_dimension: int,
    ) -> ChangeComparisonRenderResult:
        """计数后调用真实公共网格渲染。"""
        self.render_count += 1
        return super().render_pair(baseline_path, target_path, max_dimension)


def test_comparison_service_persists_manifest_and_reuses_cache(
    tmp_path: Path,
) -> None:
    """验证来源 SHA、预览 SHA、公共网格清单和缓存复用。"""
    baseline_path = tmp_path / "baseline.tif"
    target_path = tmp_path / "target.tif"
    write_test_raster(baseline_path, (126.0, 45.0, 127.0, 46.0), 100)
    write_test_raster(target_path, (126.4, 45.2, 127.4, 46.2), 300)
    baseline_checksum = calculate_sha256(baseline_path)
    target_checksum = calculate_sha256(target_path)
    baseline = SimpleNamespace(
        id=10,
        project_id=1,
        asset_code="IMG-BASE",
        asset_name="前时相影像",
        acquired_at=datetime(2026, 5, 1, tzinfo=UTC),
        data_status="operational",
        checksum_sha256=baseline_checksum,
        file_size_bytes=baseline_path.stat().st_size,
        calibration_status="completed",
        correction_status="completed",
    )
    target = SimpleNamespace(
        id=11,
        project_id=1,
        asset_code="IMG-TARGET",
        asset_name="后时相影像",
        acquired_at=datetime(2026, 7, 1, tzinfo=UTC),
        data_status="operational",
        checksum_sha256=target_checksum,
        file_size_bytes=target_path.stat().st_size,
        calibration_status="completed",
        correction_status="completed",
    )
    run = SimpleNamespace(
        id=20,
        project_id=1,
        task_id=2,
        run_code="CD-2026-001",
        baseline_asset_id=10,
        target_asset_id=11,
        registration_job_id=30,
        rule_config_version=3,
        alignment_offset_pixels=Decimal("1.2"),
        source_snapshot={
            "baseline": {"checksum_sha256": baseline_checksum},
            "target": {"checksum_sha256": target_checksum},
            "registration": {"output_sha256": target_checksum},
        },
    )
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    imagery_service = MagicMock()
    registration_service = AsyncMock()
    renderer = CountingRenderer()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=1)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=2,
        project_id=1,
    )
    dao.get_run_by_code.return_value = run
    dao.get_imagery_assets_by_ids.return_value = [baseline, target]
    imagery_service.resolve_verified_asset_path.return_value = baseline_path
    registration_service.resolve_verified_job_by_id.return_value = (
        SimpleNamespace(
            id=30,
            task_id=2,
            reference_asset_id=10,
            moving_asset_id=11,
            checksum_sha256=target_checksum,
        ),
        target_path,
    )
    service = ChangeComparisonService(
        dao=dao,
        workbench_dao=workbench_dao,
        imagery_service=imagery_service,
        registration_service=registration_service,
        renderer=renderer,
    )
    service.preview_root = tmp_path / "cache"

    first = asyncio.run(
        service.get_metadata(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            "CD-2026-001",
        )
    )
    second = asyncio.run(
        service.get_metadata(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            "CD-2026-001",
        )
    )
    image, etag = asyncio.run(
        service.get_image(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            "CD-2026-001",
            "baseline",
        )
    )

    assert renderer.render_count == 1
    assert first == second
    assert first.baseline_url.startswith(
        "/api/v1/change-detection/runs/CD-2026-001/comparison/baseline.png"
    )
    assert first.baseline_preview_sha256 == etag
    assert calculate_sha256(next(service.preview_root.rglob("baseline.png"))) == etag
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    manifest_path = next(service.preview_root.rglob("manifest.json"))
    manifest = manifest_path.read_text(encoding="utf-8")
    assert baseline_checksum in manifest
    assert target_checksum in manifest
