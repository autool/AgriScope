"""外业疑点四类决策与重新打开业务测试。"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.schemas.field_verification import (
    FieldReopenRequest,
    FieldResolutionRequest,
)
from app.services.field_verification_service import FieldVerificationService


def build_record(
    *,
    resolution_status: str = "pending",
    matched_plot_code: str | None = "PLOT-001",
) -> SimpleNamespace:
    """构造具有响应所需字段的外业疑点记录。

    Args:
        resolution_status: 当前处置状态。
        matched_plot_code: 可选匹配图斑编号。

    Returns:
        SimpleNamespace: 外业记录替身。
    """
    return SimpleNamespace(
        id=5,
        task_id=3,
        verification_code="FV-RESOLUTION-001",
        investigator="张强",
        investigator_code="field-zhang-qiang",
        observed_land_class="耕地",
        observed_crop_type="玉米",
        photo_urls=["https://legacy.example/photo.jpg"],
        voice_url=None,
        remark="现场核查",
        captured_at=datetime(2026, 7, 23, 3, 30, tzinfo=UTC),
        source_name="省级外业采集 App",
        source_uri="field-app://record/001",
        source_version="v1",
        source_record_id="mobile-001",
        source_checksum_sha256="a" * 64,
        source_file_uri=None,
        source_file_size_bytes=None,
        import_batch_code="FIELD-BATCH-001",
        imported_by="张强",
        imported_by_code="field-zhang-qiang",
        imported_by_role="field_inspector",
        matched_plot_code=matched_plot_code,
        offset_distance_m=Decimal("8.50"),
        match_status="offset",
        resolution_status=resolution_status,
        resolution_decision=(
            "use_field" if resolution_status == "resolved" else None
        ),
        resolution_comment=(
            "首次采用外业结论" if resolution_status == "resolved" else None
        ),
        resolved_by="王海峰" if resolution_status == "resolved" else None,
        resolved_by_code=(
            "quality-wang-haifeng" if resolution_status == "resolved" else None
        ),
        resolved_by_role=(
            "quality_inspector" if resolution_status == "resolved" else None
        ),
        updated_at=datetime.now(UTC),
    )


def build_service(
    record: SimpleNamespace,
) -> tuple[FieldVerificationService, AsyncMock, AsyncMock, SimpleNamespace]:
    """构造具备照片证据和质检员权限的处置服务。

    Args:
        record: 当前外业记录。

    Returns:
        tuple: 服务、外业 DAO、工作台 DAO 和任务替身。
    """
    dao = AsyncMock()
    dao.get_by_code_for_update.return_value = record
    dao.get_coordinates.return_value = (126.6103, 45.8057)
    dao.reopen_quality_issue.return_value = True
    task = SimpleNamespace(
        id=3,
        project_id=9,
        status="quality_review",
        quality_score=Decimal("92.00"),
        assignee="李静",
        updated_at=datetime.now(UTC),
    )
    plot = SimpleNamespace(
        plot_code="PLOT-001",
        land_class="耕地",
        crop_type="水稻",
        planting_mode="单季种植",
        irrigation_condition="良好",
        interpretation_status="interpreted",
        geom="plot-geometry",
        version=2,
        updated_at=datetime.now(UTC),
    )
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_id_for_update.return_value = task
    workbench_dao.is_plot_assigned_to_task.return_value = True
    workbench_dao.get_plot_by_code.return_value = plot
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="王海峰",
        user_code="quality-wang-haifeng",
        role_code="quality_inspector",
    )
    artifact_dao = AsyncMock()
    artifact_dao.count_by_record_type.return_value = 1
    artifact_dao.list_by_verification_ids.return_value = []
    service = FieldVerificationService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
        artifact_dao=artifact_dao,
    )
    return service, dao, workbench_dao, task


def test_compromise_request_requires_explicit_valid_target() -> None:
    """验证折中方案不能静默沿用内业属性或产生地类作物矛盾。"""
    with pytest.raises(ValidationError, match="最终地类"):
        FieldResolutionRequest(
            decision="compromise",
            reviewer_code="quality-wang-haifeng",
            comment="人工综合现场和影像",
        )
    with pytest.raises(ValidationError, match="必须填写作物"):
        FieldResolutionRequest(
            decision="compromise",
            reviewer_code="quality-wang-haifeng",
            comment="人工综合现场和影像",
            target_land_class="耕地",
        )
    with pytest.raises(ValidationError, match="仅折中处置"):
        FieldResolutionRequest(
            decision="keep_internal",
            reviewer_code="quality-wang-haifeng",
            comment="保持原判读",
            target_land_class="耕地",
            target_crop_type="大豆",
        )


def test_compromise_resolution_uses_explicit_target_and_versions_plot() -> None:
    """验证折中处置使用人工最终属性并生成不可变图斑版本。"""
    record = build_record()
    service, _, workbench_dao, task = build_service(record)

    response = asyncio.run(
        service.resolve_record(
            AsyncMock(),
            record.verification_code,
            FieldResolutionRequest(
                decision="compromise",
                reviewer_code="quality-wang-haifeng",
                comment="影像纹理与现场调查综合确认种植大豆",
                target_land_class="耕地",
                target_crop_type="大豆",
            ),
        )
    )

    plot = workbench_dao.get_plot_by_code.return_value
    assert plot.crop_type == "大豆"
    assert plot.version == 3
    version = workbench_dao.add_plot_version.await_args.args[1]
    assert "人工折中方案" in version.change_summary
    assert "大豆" in version.change_summary
    assert response.resolution_decision == "compromise"
    assert task.status == "interpreting"
    assert task.quality_score is None


def test_use_field_audit_records_observed_final_attributes() -> None:
    """验证采用外业结论时审核记录保存实际落地属性而非空请求字段。"""
    record = build_record()
    service, _, workbench_dao, _ = build_service(record)

    asyncio.run(
        service.resolve_record(
            AsyncMock(),
            record.verification_code,
            FieldResolutionRequest(
                decision="use_field",
                reviewer_code="quality-wang-haifeng",
                comment="现场照片和调查表共同证明当前种植玉米",
            ),
        )
    )

    review = workbench_dao.add_review_record.await_args.args[1]
    assert "最终地类 耕地" in review.comment
    assert "最终作物 玉米" in review.comment


def test_unmatched_record_cannot_modify_nonexistent_plot() -> None:
    """验证未匹配记录不能用采用外业或折中路径虚构内业修改。"""
    record = build_record(matched_plot_code=None)
    service, _, workbench_dao, _ = build_service(record)

    with pytest.raises(ValidationException, match="先重新匹配或驳回"):
        asyncio.run(
            service.resolve_record(
                AsyncMock(),
                record.verification_code,
                FieldResolutionRequest(
                    decision="use_field",
                    reviewer_code="quality-wang-haifeng",
                    comment="尝试采用现场结论",
                ),
            )
        )

    workbench_dao.get_plot_by_code.assert_not_awaited()


def test_reject_field_closes_issue_without_mutating_plot() -> None:
    """验证驳回外业结论只关闭本次疑点，不改写内业图斑。"""
    record = build_record()
    service, dao, workbench_dao, task = build_service(record)
    original_status = task.status

    response = asyncio.run(
        service.resolve_record(
            AsyncMock(),
            record.verification_code,
            FieldResolutionRequest(
                decision="reject_field",
                reviewer_code="quality-wang-haifeng",
                comment="现场照片定位错误，与目标图斑无关",
            ),
        )
    )

    assert response.resolution_decision == "reject_field"
    workbench_dao.get_plot_by_code.assert_not_awaited()
    workbench_dao.add_plot_version.assert_not_awaited()
    dao.resolve_quality_issue.assert_awaited_once()
    assert task.status == original_status


def test_reopen_resolved_issue_restores_quality_gate_and_task() -> None:
    """验证重新打开会清除当前结论、恢复问题并退回解译阶段。"""
    record = build_record(resolution_status="resolved")
    service, dao, workbench_dao, task = build_service(record)
    task.status = "completed"
    task.quality_score = Decimal("96.00")

    response = asyncio.run(
        service.reopen_record(
            AsyncMock(),
            record.verification_code,
            FieldReopenRequest(
                operator_code="quality-wang-haifeng",
                comment="新增现场照片表明上次处置依据不足",
            ),
        )
    )

    assert response.resolution_status == "pending"
    assert response.resolution_decision is None
    assert record.resolved_by_code is None
    assert task.status == "interpreting"
    assert task.quality_score is None
    dao.reopen_quality_issue.assert_awaited_once()
    review = workbench_dao.add_review_record.await_args.args[1]
    assert review.action == "field_issue_reopened"
    assert "上次决策 采用外业结论" in review.comment
