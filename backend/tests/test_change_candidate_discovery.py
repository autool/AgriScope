"""内置 RGB 差分候选发现与实体成果持久化测试。"""

import asyncio
import warnings
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile

from app.core.imagery_files import calculate_sha256
from app.schemas.change_detection import ChangeCandidateDiscoveryRequest
from app.services.change_candidate_discovery_engine import (
    ChangeCandidateDiscoveryEngine,
    ChangeCandidateDiscoveryResult,
    DiscoveredChangeGeometry,
)
from app.services.change_candidate_discovery_service import (
    ChangeCandidateDiscoveryService,
)


def make_rgba_png(rgb: np.ndarray) -> bytes:
    """将通道优先 RGB uint8 数组编码为全有效 RGBA PNG。"""
    rgba = np.zeros((4, rgb.shape[1], rgb.shape[2]), dtype="uint8")
    rgba[:3] = rgb
    rgba[3] = 255
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with MemoryFile() as memory:
            with memory.open(
                driver="PNG",
                width=rgb.shape[2],
                height=rgb.shape[1],
                count=4,
                dtype="uint8",
            ) as dataset:
                dataset.write(rgba)
            return memory.read()


def test_discovery_engine_vectorizes_single_change_component() -> None:
    """验证显著差分矩形被筛选并转换为一个 WGS84 Polygon。"""
    baseline = np.full((3, 40, 50), 80, dtype="uint8")
    target = baseline.copy()
    target[:, 10:25, 15:35] = 220
    result = ChangeCandidateDiscoveryEngine().discover(
        make_rgba_png(baseline),
        make_rgba_png(target),
        (126.0, 45.0, 127.0, 46.0),
        difference_threshold=0.2,
        min_component_pixels=9,
        max_candidates=20,
    )

    assert result.changed_pixel_count == 300
    assert result.valid_pixel_count == 2000
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.geometry["type"] == "Polygon"
    assert candidate.pixel_count == 300
    assert candidate.confidence > 0.5


def test_discovery_engine_returns_empty_for_unchanged_pair() -> None:
    """验证没有显著差分时返回真实空结果。"""
    image = np.full((3, 30, 30), 120, dtype="uint8")
    result = ChangeCandidateDiscoveryEngine().discover(
        make_rgba_png(image),
        make_rgba_png(image.copy()),
        (126.0, 45.0, 127.0, 46.0),
        difference_threshold=0.1,
        min_component_pixels=4,
        max_candidates=20,
    )

    assert result.candidates == ()
    assert result.changed_pixel_count == 0


def test_discovery_engine_splits_corner_touching_components() -> None:
    """验证角点相接像元不会生成 PostGIS 无法接收的自接触 Polygon。"""
    baseline = np.zeros((3, 12, 12), dtype="uint8")
    target = baseline.copy()
    target[:, 4, 4] = 255
    target[:, 5, 5] = 255

    result = ChangeCandidateDiscoveryEngine().discover(
        make_rgba_png(baseline),
        make_rgba_png(target),
        (126.0, 45.0, 127.0, 46.0),
        difference_threshold=0.5,
        min_component_pixels=1,
        max_candidates=10,
    )

    assert len(result.candidates) == 2
    for candidate in result.candidates:
        ring = candidate.geometry["coordinates"][0]
        assert candidate.pixel_count == 1
        assert ring[0] == ring[-1]
        assert len(set(map(tuple, ring[:-1]))) == len(ring) - 1


def test_discovery_engine_rejects_silent_candidate_truncation() -> None:
    """验证候选过多时要求调整阈值，而不是静默截断结果。"""
    baseline = np.zeros((3, 20, 20), dtype="uint8")
    target = baseline.copy()
    target[:, 2, 2] = 255
    target[:, 8, 8] = 255
    target[:, 15, 15] = 255

    with pytest.raises(ValueError, match="检测到 3 个候选"):
        ChangeCandidateDiscoveryEngine().discover(
            make_rgba_png(baseline),
            make_rgba_png(target),
            (126.0, 45.0, 127.0, 46.0),
            difference_threshold=0.5,
            min_component_pixels=1,
            max_candidates=2,
        )


def test_discovery_service_writes_artifact_and_unclassified_candidates(
    tmp_path: Path,
) -> None:
    """验证自动发现保存实体 GeoJSON、面积过滤和未分类人工门禁。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    comparison_service = AsyncMock()
    engine = MagicMock()
    now = datetime.now(UTC)
    project = SimpleNamespace(id=1)
    task = SimpleNamespace(
        id=2,
        project_id=1,
        status="interpreting",
        updated_at=now,
    )
    run = SimpleNamespace(
        id=3,
        project_id=1,
        task_id=2,
        run_code="CD-2026-001",
        status="active",
        task_plot_count=35020,
        task_updated_at_snapshot=now,
        rule_profile_snapshot={"other_agricultural_min_area_sqm": 400},
        updated_at=now,
    )
    workbench_dao.get_project_by_code.return_value = project
    workbench_dao.get_task_by_code_for_update.return_value = task
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    dao.get_run_by_code_for_update.return_value = run
    dao.count_task_plots.return_value = 35020
    comparison_service.get_metadata.return_value = SimpleNamespace(
        bounds_wgs84=(126.0, 45.0, 127.0, 46.0),
        baseline_preview_sha256="a" * 64,
        target_preview_sha256="b" * 64,
    )
    comparison_service.get_image.side_effect = [
        (b"baseline", "a" * 64),
        (b"target", "b" * 64),
    ]
    engine.algorithm_code = "rgb_absolute_difference"
    engine.algorithm_version = "1.0.0"
    engine.discover.return_value = ChangeCandidateDiscoveryResult(
        candidates=(
            DiscoveredChangeGeometry(
                geometry={
                    "type": "Polygon",
                    "coordinates": [
                        [[126.1, 45.1], [126.2, 45.1], [126.2, 45.2], [126.1, 45.1]]
                    ],
                },
                confidence=0.82,
                pixel_count=120,
            ),
            DiscoveredChangeGeometry(
                geometry={
                    "type": "Polygon",
                    "coordinates": [
                        [[126.3, 45.3], [126.4, 45.3], [126.4, 45.4], [126.3, 45.3]]
                    ],
                },
                confidence=0.61,
                pixel_count=40,
            ),
        ),
        changed_pixel_count=160,
        valid_pixel_count=10000,
    )
    dao.analyze_import_geometry.side_effect = [
        {"geometry_valid": True, "within_project": True, "area_ha": 0.08},
        {"geometry_valid": True, "within_project": True, "area_ha": 0.02},
    ]

    async def insert_candidate(_: object, values: dict[str, object]) -> object:
        return SimpleNamespace(
            id=10,
            confidence=values["confidence"],
            area_ha=values["area_ha"],
        )

    dao.insert_candidate.side_effect = insert_candidate
    service = ChangeCandidateDiscoveryService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        comparison_service=comparison_service,
        engine=engine,
    )
    service.storage_root = tmp_path / "discovery"

    result = asyncio.run(
        service.discover_candidates(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            "CD-2026-001",
            ChangeCandidateDiscoveryRequest(
                difference_threshold=0.2,
                min_component_pixels=9,
                max_candidates=100,
                operator_code="manager-zhao-zhiyuan",
                comment="使用共同网格执行首轮自动变化筛查",
            ),
        )
    )

    assert result.detected_count == 2
    assert result.imported_count == 1
    assert result.filtered_below_area_count == 1
    artifact_path = next(service.storage_root.rglob("candidates.geojson"))
    assert calculate_sha256(artifact_path) == result.artifact_sha256
    inserted = dao.insert_candidate.await_args.args[1]
    assert inserted["change_class"] == "unclassified"
    assert inserted["source_checksum_sha256"] == result.artifact_sha256
    assert run.status == "reviewing"
