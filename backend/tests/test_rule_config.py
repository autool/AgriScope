"""项目规则配置和外业动态阈值业务测试。"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import PermissionDeniedException
from app.models.workbench import ProjectRuleConfig
from app.schemas.field_verification import FieldResolutionRequest
from app.schemas.rule_config import RuleConfigUpdateRequest
from app.services.field_verification_service import FieldVerificationService
from app.services.project_user_service import ProjectUserService
from app.services.rule_config_service import RuleConfigService


def build_config(
    *,
    offset_m: Decimal = Decimal("5.00"),
    search_radius_m: Decimal = Decimal("1000.00"),
    positional_pixels: Decimal = Decimal("2.00"),
    max_days: int = 15,
) -> SimpleNamespace:
    """构造可供业务服务读取的项目规则配置。"""
    return SimpleNamespace(
        id=1,
        project_id=7,
        field_offset_threshold_m=offset_m,
        field_search_radius_m=search_radius_m,
        positional_accuracy_pixels=positional_pixels,
        max_capture_image_days=max_days,
        construction_min_area_sqm=Decimal("200.00"),
        other_agricultural_min_area_sqm=Decimal("400.00"),
        completeness_rate_min=Decimal("98.00"),
        boundary_agreement_rate_min=Decimal("90.00"),
        land_class_accuracy_min=Decimal("90.00"),
        key_field_accuracy_min=Decimal("95.00"),
        max_cloud_cover_percent=None,
        output_crs="EPSG:4490",
        output_projection="CGCS2000 高斯-克吕格（按成果分幅配置中央经线）",
        version=1,
        updated_by="系统默认配置",
        updated_by_code=None,
        updated_by_role=None,
        updated_at=datetime.now(UTC),
    )


def build_field_record() -> SimpleNamespace:
    """构造外业空间匹配记录。"""
    return SimpleNamespace(
        id=3,
        verification_code="FV-TEST-001",
        captured_at=datetime(2026, 6, 20, tzinfo=UTC),
        matched_plot_code=None,
        offset_distance_m=None,
        match_status="pending",
        resolution_status="pending",
    )


def build_rule_update(**overrides: object) -> RuleConfigUpdateRequest:
    """构造包含采购量化基线的完整规则更新请求。"""
    values: dict[str, object] = {
        "field_offset_threshold_m": 8,
        "field_search_radius_m": 1500,
        "positional_accuracy_pixels": 1.5,
        "max_capture_image_days": 10,
        "construction_min_area_sqm": 200,
        "other_agricultural_min_area_sqm": 400,
        "completeness_rate_min": 98,
        "boundary_agreement_rate_min": 90,
        "land_class_accuracy_min": 90,
        "key_field_accuracy_min": 95,
        "max_cloud_cover_percent": None,
        "output_crs": "EPSG:4490",
        "output_projection": "CGCS2000 高斯-克吕格（按成果分幅配置中央经线）",
        "operator_code": "manager-zhao-zhiyuan",
    }
    values.update(overrides)
    return RuleConfigUpdateRequest(**values)


def test_rule_config_rejects_search_radius_not_larger_than_offset() -> None:
    """验证最近邻搜索半径必须严格大于偏移阈值。"""
    with pytest.raises(ValidationError, match="搜索半径"):
        build_rule_update(
            field_offset_threshold_m=10,
            field_search_radius_m=10,
        )


def test_rule_config_update_persists_values_and_audit() -> None:
    """验证规则更新写入当前值和修改前后值审计。"""
    config = ProjectRuleConfig(
        id=1,
        project_id=7,
        field_offset_threshold_m=Decimal("5.00"),
        field_search_radius_m=Decimal("1000.00"),
        positional_accuracy_pixels=Decimal("2.00"),
        max_capture_image_days=15,
        construction_min_area_sqm=Decimal("200.00"),
        other_agricultural_min_area_sqm=Decimal("400.00"),
        completeness_rate_min=Decimal("98.00"),
        boundary_agreement_rate_min=Decimal("90.00"),
        land_class_accuracy_min=Decimal("90.00"),
        key_field_accuracy_min=Decimal("95.00"),
        max_cloud_cover_percent=None,
        output_crs="EPSG:4490",
        output_projection="CGCS2000 高斯-克吕格（按成果分幅配置中央经线）",
        version=1,
        updated_by="系统默认配置",
        updated_by_code=None,
        updated_by_role=None,
        updated_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.get_by_project_id_for_update.return_value = config
    workbench_dao = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=7)
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    db = AsyncMock()
    service = RuleConfigService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )

    response = asyncio.run(
        service.update_config(
            db,
            "RS-2026",
                build_rule_update(),
        )
    )

    assert response.field_offset_threshold_m == 8
    assert response.field_search_radius_m == 1500
    assert response.positional_accuracy_pixels == 1.5
    assert response.max_capture_image_days == 10
    assert response.construction_min_area_sqm == 200
    assert response.other_agricultural_min_area_sqm == 400
    assert response.completeness_rate_min == 98
    assert response.version == 2
    assert response.updated_by == "赵志远"
    assert response.updated_by_code == "manager-zhao-zhiyuan"
    audit = dao.add_audit.await_args.args[1]
    assert audit.previous_values["field_offset_threshold_m"] == 5
    assert audit.new_values["field_offset_threshold_m"] == 8
    assert audit.operator == "赵志远"
    assert audit.operator_code == "manager-zhao-zhiyuan"
    dao.invalidate_project_quality_evidence.assert_awaited_once_with(db, 7)
    db.commit.assert_awaited_once()


def test_rule_config_update_rejects_quality_inspector_role() -> None:
    """验证质检员不能越权修改项目级判定阈值。"""
    workbench_dao = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=7)
    user_dao = AsyncMock()
    user_dao.get_active_user.return_value = SimpleNamespace(
        user_code="quality-wang-haifeng",
        display_name="王海峰",
        role_code="quality_inspector",
        role_name="质检员",
    )
    service = RuleConfigService(
        dao=AsyncMock(),
        workbench_dao=workbench_dao,
        project_user_service=ProjectUserService(dao=user_dao),
    )

    with pytest.raises(PermissionDeniedException, match="无权执行当前业务节点"):
        asyncio.run(
            service.update_config(
                AsyncMock(),
                "RS-2026",
                    build_rule_update(
                        operator_code="quality-wang-haifeng",
                    ),
            )
        )


def test_field_match_uses_configured_offset_threshold() -> None:
    """验证外业点在自定义偏移阈值内判定为一致。"""
    dao = AsyncMock()
    dao.find_nearest_plot.return_value = ("OSM-HLJ-100", 8.0, False)
    workbench_dao = AsyncMock()
    service = FieldVerificationService(
        dao=dao,
        workbench_dao=workbench_dao,
        rule_config_service=AsyncMock(),
    )
    record = build_field_record()
    task = SimpleNamespace(id=1, assignee="李静")
    imagery = SimpleNamespace(acquired_at=datetime(2026, 6, 18, tzinfo=UTC))

    has_issue = asyncio.run(
        service._match_record(
            AsyncMock(),
            task,
            record,
            build_config(offset_m=Decimal("10.00")),
            imagery,
        )
    )

    assert has_issue is False
    assert record.match_status == "consistent"
    assert record.resolution_status == "not_required"
    dao.find_nearest_plot.assert_awaited_once()
    assert dao.find_nearest_plot.await_args.args[3] == 1000.0
    workbench_dao.add_quality_issues.assert_not_awaited()


def test_field_match_creates_offset_issue_with_dynamic_threshold() -> None:
    """验证超过自定义偏移阈值时问题描述使用实际配置值。"""
    dao = AsyncMock()
    dao.find_nearest_plot.return_value = ("OSM-HLJ-100", 8.0, False)
    workbench_dao = AsyncMock()
    service = FieldVerificationService(
        dao=dao,
        workbench_dao=workbench_dao,
        rule_config_service=AsyncMock(),
    )
    record = build_field_record()
    task = SimpleNamespace(id=1, assignee="李静")
    imagery = SimpleNamespace(acquired_at=datetime(2026, 6, 18, tzinfo=UTC))

    has_issue = asyncio.run(
        service._match_record(
            AsyncMock(),
            task,
            record,
            build_config(offset_m=Decimal("5.00")),
            imagery,
        )
    )

    assert has_issue is True
    assert record.match_status == "offset"
    issue = workbench_dao.add_quality_issues.await_args.args[1][0]
    assert "超过 5 米阈值" in issue.description
    assert issue.assignee == "李静"


def test_field_match_detects_imagery_time_mismatch() -> None:
    """验证空间一致但采集时间超限时生成时间一致性疑点。"""
    dao = AsyncMock()
    dao.find_nearest_plot.return_value = ("OSM-HLJ-100", 0.0, True)
    workbench_dao = AsyncMock()
    service = FieldVerificationService(
        dao=dao,
        workbench_dao=workbench_dao,
        rule_config_service=AsyncMock(),
    )
    record = build_field_record()
    task = SimpleNamespace(id=1, assignee="李静")
    imagery = SimpleNamespace(
        acquired_at=record.captured_at - timedelta(days=20),
    )

    has_issue = asyncio.run(
        service._match_record(
            AsyncMock(),
            task,
            record,
            build_config(max_days=15),
            imagery,
        )
    )

    assert has_issue is True
    assert record.match_status == "time_mismatch"
    issue = workbench_dao.add_quality_issues.await_args.args[1][0]
    assert "相差 20.0 天" in issue.description
    assert "超过 15 天阈值" in issue.description


def test_use_field_resolution_creates_immutable_plot_version() -> None:
    """验证采用外业结论时更新属性并生成不可变图斑版本。"""
    record = SimpleNamespace(
        id=3,
        task_id=1,
        verification_code="FV-TEST-001",
        match_status="offset",
        matched_plot_code="OSM-HLJ-100",
        observed_land_class="耕地",
        observed_crop_type="大豆",
        resolution_status="pending",
        resolution_decision=None,
        resolution_comment=None,
        resolved_by=None,
        resolved_by_code=None,
        resolved_by_role=None,
        updated_at=datetime.now(UTC),
        investigator="外业员",
        investigator_code="field-zhang-qiang",
        photo_urls=[],
        voice_url=None,
        remark=None,
        captured_at=datetime.now(UTC),
        offset_distance_m=Decimal("8.00"),
    )
    plot = SimpleNamespace(
        plot_code="OSM-HLJ-100",
        land_class="耕地",
        crop_type="玉米",
        planting_mode="单季种植",
        irrigation_condition="良好",
        interpretation_status="interpreted",
        geom="plot-geometry",
        version=1,
        updated_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.get_by_code_for_update.return_value = record
    dao.get_coordinates.return_value = (126.8, 45.8)
    workbench_dao = AsyncMock()
    workbench_dao.get_plot_by_code.return_value = plot
    workbench_dao.get_task_by_id_for_update.return_value = SimpleNamespace(
        id=1,
        project_id=7,
        status="quality_review",
        quality_score=Decimal("92.00"),
        updated_at=datetime.now(UTC),
    )
    workbench_dao.is_plot_assigned_to_task.return_value = True
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="quality-wang-haifeng",
        display_name="王海峰",
        role_code="quality_inspector",
    )
    artifact_dao = AsyncMock()
    artifact_dao.count_by_record_type.return_value = 1
    artifact_dao.list_by_verification_ids.return_value = []
    service = FieldVerificationService(
        dao=dao,
        workbench_dao=workbench_dao,
        rule_config_service=AsyncMock(),
        project_user_service=user_service,
        artifact_dao=artifact_dao,
    )
    db = AsyncMock()

    response = asyncio.run(
        service.resolve_record(
            db,
            record.verification_code,
            FieldResolutionRequest(
                decision="use_field",
                reviewer_code="quality-wang-haifeng",
                comment="现场确认种植大豆",
            ),
        )
    )

    assert response.resolution_status == "resolved"
    assert plot.crop_type == "大豆"
    assert plot.version == 2
    version = workbench_dao.add_plot_version.await_args.args[1]
    assert version.version == 2
    assert version.crop_type == "大豆"
    assert version.created_by == "王海峰"
    assert record.resolved_by_code == "quality-wang-haifeng"
    db.commit.assert_awaited_once()
