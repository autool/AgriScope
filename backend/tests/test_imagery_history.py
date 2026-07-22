"""历史影像覆盖矩阵与处理问题追溯服务测试。"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.core.exceptions import ValidationException
from app.core.imagery_files import calculate_sha256
from app.services.imagery_history_service import ImageryHistoryService


def test_history_overview_uses_real_coverage_and_artifact_gates(
    tmp_path: Path,
) -> None:
    """验证覆盖率、必选步骤、云量和历史替换证据均来自持久化事实。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    rule_dao = AsyncMock()
    asset_service = MagicMock()
    imagery_service = MagicMock()
    now = datetime.now(UTC)
    source_path = tmp_path / "source.tif"
    source_path.write_bytes(b"verified imagery source")
    source_sha = calculate_sha256(source_path)
    project = SimpleNamespace(id=1)
    asset = SimpleNamespace(
        id=10,
        project_id=1,
        asset_code="IMG-2026-07",
        asset_name="七月业务影像",
        sensor_type="Sentinel-2B MSI",
        acquired_at=now - timedelta(days=5),
        cloud_cover=Decimal("11.25"),
        resolution_m=Decimal("10"),
        processing_level="L2A",
        data_status="operational",
        checksum_sha256=source_sha,
        crs="EPSG:32651",
        file_uri="storage://imagery/assets/IMG-2026-07/source.tif",
        created_at=now - timedelta(days=4),
    )
    completed_step = SimpleNamespace(
        asset_id=10,
        step_code="radiometric",
        step_name="辐射定标",
        sequence=1,
        is_required=True,
        status="completed",
        parameters={
            "artifact_evidence": {
                "checksum_sha256": "a" * 64,
                "file_size_bytes": 1024,
                "processor_name": "受控源产品级别承认",
            },
            "artifact_history": [
                {
                    "registered_at": (now - timedelta(days=3)).isoformat(),
                    "checksum_sha256": "b" * 64,
                }
            ],
        },
        output_uri="storage://imagery/assets/IMG-2026-07/source.tif",
        completed_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=2),
    )
    pending_step = SimpleNamespace(
        asset_id=10,
        step_code="band_products",
        step_name="波段与指数产品",
        sequence=6,
        is_required=True,
        status="pending",
        parameters={},
        output_uri=None,
        completed_at=None,
        updated_at=now - timedelta(days=1),
    )
    workbench_dao.get_project_by_code.return_value = project
    dao.list_assets.return_value = [asset]
    dao.list_steps.return_value = [completed_step, pending_step]
    dao.list_boundaries.return_value = [
        {
            "boundary_code": "230100",
            "boundary_name": "哈尔滨市",
            "boundary_level": "city",
            "parent_code": "230000",
            "source_name": "真实行政区快照",
            "source_version": "2026-07",
            "source_updated_at": date(2026, 7, 21),
        },
        {
            "boundary_code": "230102",
            "boundary_name": "道里区",
            "boundary_level": "district",
            "parent_code": "230100",
            "source_name": "真实行政区快照",
            "source_version": "2026-07",
            "source_updated_at": date(2026, 7, 21),
        },
    ]
    dao.list_county_coverage.return_value = [
        {
            "asset_id": 10,
            "asset_code": "IMG-2026-07",
            "prefecture_code": "230100",
            "prefecture_name": "哈尔滨市",
            "county_code": "230102",
            "county_name": "道里区",
            "county_area_ha": Decimal("1000"),
            "covered_area_ha": Decimal("500"),
        }
    ]
    rule_dao.get_by_project_id.return_value = SimpleNamespace(
        max_cloud_cover_percent=Decimal("5")
    )
    asset_service.resolve_verified_asset_path.return_value = source_path

    def resolve_step(step: object) -> tuple[Path, dict]:
        if step is pending_step:
            raise ValidationException("尚未登记实体产物")
        return source_path, completed_step.parameters["artifact_evidence"]

    imagery_service.resolve_verified_step_artifact_path.side_effect = resolve_step
    service = ImageryHistoryService(
        dao=dao,
        workbench_dao=workbench_dao,
        rule_dao=rule_dao,
        asset_service=asset_service,
        imagery_service=imagery_service,
    )

    result = asyncio.run(service.get_overview(AsyncMock(), "RS-2026"))

    assert result.asset_count == 1
    assert result.verified_operational_asset_count == 1
    assert result.prefecture_count == 1
    assert result.county_count == 1
    assert result.coverage_cells[0].coverage_percent == 50
    assert result.coverage_cells[0].coverage_status == "partial"
    summary = result.assets[0]
    assert summary.processing_completion_rate == 50
    assert summary.covered_county_count == 1
    assert summary.province_coverage_percent == 50
    assert summary.issue_count == 2
    event_types = {event.event_type for event in result.trace_events}
    assert "cloud_threshold_exceeded" in event_types
    assert "required_step_pending" in event_types
    assert "step_completed" in event_types
    assert "artifact_superseded" in event_types


def test_history_overview_keeps_real_empty_asset_state() -> None:
    """验证无影像时仍返回真实行政区目录，不生成固定历史时相。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    rule_dao = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=1)
    dao.list_assets.return_value = []
    dao.list_steps.return_value = []
    dao.list_boundaries.return_value = [
        {
            "boundary_code": "230100",
            "boundary_name": "哈尔滨市",
            "boundary_level": "city",
            "parent_code": "230000",
            "source_name": "真实行政区快照",
            "source_version": "2026-07",
            "source_updated_at": date(2026, 7, 21),
        }
    ]
    dao.list_county_coverage.return_value = []
    rule_dao.get_by_project_id.return_value = None
    service = ImageryHistoryService(
        dao=dao,
        workbench_dao=workbench_dao,
        rule_dao=rule_dao,
        asset_service=MagicMock(),
        imagery_service=MagicMock(),
    )

    result = asyncio.run(service.get_overview(AsyncMock(), "RS-2026"))

    assert result.asset_count == 0
    assert result.assets == []
    assert result.coverage_cells == []
    assert result.trace_events == []
    assert result.prefecture_count == 1
    assert result.time_start is None
    assert result.time_end is None
