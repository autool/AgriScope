"""多时相变化检测任务、候选导入与人工判读业务测试。"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.schemas.change_detection import (
    ChangeCandidateGeoJsonImportRequest,
    ChangeCandidateReviewRequest,
    ChangeRunCreateRequest,
)
from app.services.change_detection_service import ChangeDetectionService


class StubOverviewChangeDetectionService(ChangeDetectionService):
    """为写操作测试提供固定提交后聚合结果。"""

    def __init__(self, overview: object, **kwargs: object) -> None:
        """初始化固定聚合结果服务。"""
        super().__init__(**kwargs)
        self.overview = overview

    async def get_overview(
        self,
        db: object,
        project_code: str,
        task_code: str,
    ) -> object:
        """返回测试预置的提交后聚合结果。"""
        return self.overview


def test_change_run_rejects_same_temporal_imagery() -> None:
    """验证变化检测任务不能绑定同一前后时相影像。"""
    with pytest.raises(ValidationError, match="前后时相影像不能相同"):
        ChangeRunCreateRequest(
            run_code="CD-2026-001",
            run_name="七月变化检测",
            baseline_asset_code="IMG-001",
            target_asset_code="IMG-001",
            alignment_method="同名点配准",
            alignment_offset_pixels=0.8,
            alignment_evidence_uri="storage://evidence/alignment.json",
            operator_code="manager-zhao-zhiyuan",
        )


def test_excluded_candidate_requires_reason() -> None:
    """验证人工排除变化候选必须给出可审计原因。"""
    with pytest.raises(ValidationError, match="排除变化候选必须填写排除原因"):
        ChangeCandidateReviewRequest(
            decision="excluded",
            evidence_comment="同期影像与外业证据一致",
            reviewer_code="quality-wang-min",
        )


def test_create_run_freezes_imagery_rules_and_task_scope() -> None:
    """验证检测任务固化影像校验值、规则版本和显式任务范围。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    rule_service = AsyncMock()
    imagery_service = MagicMock()
    now = datetime.now(UTC)
    project = SimpleNamespace(id=1)
    task = SimpleNamespace(
        id=2,
        project_id=1,
        status="interpreting",
        updated_at=now,
    )
    baseline = SimpleNamespace(
        id=10,
        asset_code="IMG-BASE",
        asset_name="前时相影像",
        acquired_at=datetime(2026, 5, 1, tzinfo=UTC),
        data_status="operational",
        checksum_sha256="a" * 64,
        calibration_status="completed",
        correction_status="completed",
        cloud_cover=Decimal("3.2"),
        processing_level="L2A",
        resolution_m=Decimal("1.0"),
        crs="EPSG:4490",
    )
    target = SimpleNamespace(
        id=11,
        asset_code="IMG-TARGET",
        asset_name="后时相影像",
        acquired_at=datetime(2026, 7, 1, tzinfo=UTC),
        data_status="operational",
        checksum_sha256="b" * 64,
        calibration_status="completed",
        correction_status="completed",
        cloud_cover=Decimal("2.5"),
        processing_level="L2A",
        resolution_m=Decimal("1.0"),
        crs="EPSG:4490",
    )
    config = SimpleNamespace(
        version=7,
        positional_accuracy_pixels=Decimal("2.0"),
        construction_min_area_sqm=Decimal("200"),
        other_agricultural_min_area_sqm=Decimal("400"),
        completeness_rate_min=Decimal("98"),
        boundary_agreement_rate_min=Decimal("90"),
        land_class_accuracy_min=Decimal("90"),
        key_field_accuracy_min=Decimal("95"),
        max_cloud_cover_percent=Decimal("10"),
        output_crs="EPSG:4490",
        output_projection="CGCS2000 高斯-克吕格",
    )
    workbench_dao.get_project_by_code.return_value = project
    workbench_dao.get_task_by_code.return_value = task
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    dao.get_run_by_code.return_value = None
    dao.get_imagery_asset.side_effect = [baseline, target]
    dao.analyze_asset_pair.return_value = {
        "has_extents": True,
        "intersects": True,
        "overlap_ratio": Decimal("0.9432"),
    }
    dao.count_task_plots.return_value = 35020
    imagery_service.verify_asset_file.return_value = (True, None)
    rule_service.ensure_for_project.return_value = config

    async def add_run(_: object, run: object) -> object:
        run.id = 20
        return run

    dao.add_run.side_effect = add_run
    response_run = SimpleNamespace(run_code="CD-2026-001")
    service = StubOverviewChangeDetectionService(
        SimpleNamespace(runs=[response_run]),
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        rule_service=rule_service,
        imagery_service=imagery_service,
    )

    result = asyncio.run(
        service.create_run(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            ChangeRunCreateRequest(
                run_code="CD-2026-001",
                run_name="七月变化检测",
                baseline_asset_code="IMG-BASE",
                target_asset_code="IMG-TARGET",
                alignment_method="同名点配准",
                alignment_offset_pixels=1.2,
                alignment_evidence_uri="storage://alignment/CD-2026-001.json",
                operator_code="manager-zhao-zhiyuan",
            ),
        )
    )

    assert result is response_run
    saved_run = dao.add_run.await_args.args[1]
    assert saved_run.rule_config_version == 7
    assert saved_run.task_plot_count == 35020
    assert saved_run.source_snapshot["baseline"]["checksum_sha256"] == "a" * 64
    assert saved_run.alignment_overlap_ratio == Decimal("0.9432")
    event = dao.add_event.await_args.args[1]
    assert event.event_type == "run_created"
    assert event.new_values["task_plot_count"] == 35020


def build_import_request(
    change_class: str = "farmland_outflow",
) -> ChangeCandidateGeoJsonImportRequest:
    """构造单候选 GeoJSON 导入请求。"""
    return ChangeCandidateGeoJsonImportRequest.model_validate(
        {
            "type": "FeatureCollection",
            "source_name": "外部变化检测模型",
            "source_uri": "storage://change/model-output.geojson",
            "source_version": "model-v2.1",
            "operator_code": "manager-zhao-zhiyuan",
            "comment": "导入模型候选供人工判读",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [126.6, 45.8],
                                [126.601, 45.8],
                                [126.601, 45.801],
                                [126.6, 45.801],
                                [126.6, 45.8],
                            ]
                        ],
                    },
                    "properties": {
                        "candidate_code": "CDC-001",
                        "source_feature_id": "model-feature-1",
                        "change_class": change_class,
                        "confidence": 0.91,
                        "evidence_uri": "storage://change/evidence/CDC-001.png",
                    },
                }
            ],
        }
    )


def test_candidate_import_uses_frozen_run_minimum_area() -> None:
    """验证候选阈值读取检测任务规则快照，而不是当前可变规则。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=1)
    task_updated_at = datetime.now(UTC)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=2,
        project_id=1,
        status="interpreting",
        updated_at=task_updated_at,
    )
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    dao.get_run_by_code_for_update.return_value = SimpleNamespace(
        id=3,
        status="active",
        task_plot_count=10,
        task_updated_at_snapshot=task_updated_at,
        rule_profile_snapshot={
            "construction_min_area_sqm": 200,
            "other_agricultural_min_area_sqm": 400,
        },
    )
    dao.get_conflicting_candidates_for_update.return_value = []
    dao.count_task_plots.return_value = 10
    dao.analyze_import_geometry.return_value = {
        "geometry_valid": True,
        "within_project": True,
        "area_ha": Decimal("0.0100"),
    }
    service = ChangeDetectionService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        rule_service=AsyncMock(),
        imagery_service=AsyncMock(),
    )

    with pytest.raises(ValidationException, match="400 平方米"):
        asyncio.run(
            service.import_candidates(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                "CD-2026-001",
                build_import_request(),
            )
        )
    dao.insert_candidate.assert_not_awaited()
    service.rule_service.ensure_for_project.assert_not_awaited()


def test_candidate_import_rejects_stale_task_snapshot() -> None:
    """验证任务图斑或数据版本变化后必须重新建立检测任务。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    original_time = datetime(2026, 7, 1, tzinfo=UTC)
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=1)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=2,
        project_id=1,
        status="interpreting",
        updated_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    dao.get_run_by_code_for_update.return_value = SimpleNamespace(
        id=3,
        status="active",
        task_plot_count=35020,
        task_updated_at_snapshot=original_time,
    )
    dao.count_task_plots.return_value = 35021
    service = ChangeDetectionService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        rule_service=AsyncMock(),
        imagery_service=AsyncMock(),
    )

    with pytest.raises(ValidationException, match="数据版本已变化"):
        asyncio.run(
            service.import_candidates(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                "CD-2026-001",
                build_import_request(),
            )
        )
    dao.analyze_import_geometry.assert_not_awaited()


def test_review_candidate_appends_history_and_completes_run() -> None:
    """验证最后一个待判候选确认后追加历史并完成检测任务。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    project = SimpleNamespace(id=1)
    task = SimpleNamespace(
        id=2,
        project_id=1,
        status="interpreting",
        updated_at=datetime.now(UTC),
    )
    run = SimpleNamespace(
        id=3,
        status="reviewing",
        rule_profile_snapshot={
            "construction_min_area_sqm": 200,
            "other_agricultural_min_area_sqm": 400,
        },
        updated_at=datetime.now(UTC),
    )
    candidate = SimpleNamespace(
        id=4,
        status="pending",
        change_class="farmland_outflow",
        area_ha=Decimal("1.2500"),
        exclusion_reason=None,
        review_comment=None,
        reviewed_by=None,
        reviewed_by_code=None,
        reviewed_by_role=None,
        reviewed_at=None,
        updated_at=datetime.now(UTC),
    )
    response_candidate = SimpleNamespace(candidate_code="CDC-001")
    workbench_dao.get_project_by_code.return_value = project
    workbench_dao.get_task_by_code.return_value = task
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="quality-wang-min",
        display_name="王敏",
        role_code="quality_inspector",
    )
    dao.get_run_by_code_for_update.return_value = run
    dao.get_candidate_for_update.return_value = candidate
    dao.count_candidate_statuses.return_value = {"confirmed": 1}
    service = StubOverviewChangeDetectionService(
        SimpleNamespace(
            runs=[
                SimpleNamespace(
                    run_code="CD-2026-001",
                    candidates=[response_candidate],
                )
            ]
        ),
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        rule_service=AsyncMock(),
        imagery_service=AsyncMock(),
    )

    result = asyncio.run(
        service.review_candidate(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            "CD-2026-001",
            "CDC-001",
            ChangeCandidateReviewRequest(
                decision="confirmed",
                change_class="farmland_outflow",
                evidence_comment="同期影像纹理和任务底图均显示耕地转出",
                reviewer_code="quality-wang-min",
            ),
        )
    )

    assert result is response_candidate
    assert candidate.status == "confirmed"
    assert candidate.reviewed_by_code == "quality-wang-min"
    assert run.status == "completed"
    event = dao.add_event.await_args.args[1]
    assert event.event_type == "candidate_reviewed"
    assert event.previous_values["status"] == "pending"
    assert event.new_values["status"] == "confirmed"


def test_review_rejects_confirming_unclassified_auto_candidate() -> None:
    """验证自动候选未人工归入六类变化前不能确认。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=1)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=2,
        project_id=1,
        status="interpreting",
    )
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="quality-wang-min",
        display_name="王敏",
        role_code="quality_inspector",
    )
    dao.get_run_by_code_for_update.return_value = SimpleNamespace(
        id=3,
        status="reviewing",
        rule_profile_snapshot={
            "construction_min_area_sqm": 200,
            "other_agricultural_min_area_sqm": 400,
        },
    )
    dao.get_candidate_for_update.return_value = SimpleNamespace(
        id=4,
        status="pending",
        change_class="unclassified",
        area_ha=Decimal("1.0000"),
        exclusion_reason=None,
        review_comment=None,
        reviewed_by_code=None,
    )
    service = ChangeDetectionService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        rule_service=AsyncMock(),
        imagery_service=AsyncMock(),
    )

    with pytest.raises(ValidationException, match="必须归入六类变化"):
        asyncio.run(
            service.review_candidate(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                "CD-2026-001",
                "AUTO-001",
                ChangeCandidateReviewRequest(
                    decision="confirmed",
                    evidence_comment="发现明显变化，但尚未完成业务分类",
                    reviewer_code="quality-wang-min",
                ),
            )
        )
    dao.add_event.assert_not_awaited()
