"""遥感监测工作台业务单元测试。"""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import (
    NotFoundException,
    PermissionDeniedException,
    ValidationException,
)
from app.dao.workbench_dao import (
    MergeAnalysis,
    PlotQualityMetrics,
    QualityGateSummary,
    QualityIssueSummary,
    SplitAnalysis,
    SplitPiece,
)
from app.models.workbench import PlotEditOperation
from app.schemas.disaster import DisasterPatchUpdateRequest
from app.schemas.field_verification import (
    FieldResolutionRequest,
    FieldVerificationCreateRequest,
)
from app.schemas.imagery import ImageryStepRunRequest
from app.schemas.review import PlotRollbackRequest, ReviewActionRequest
from app.schemas.workbench import (
    BatchPlotAttributeUpdateRequest,
    LineStringGeometry,
    PlotAttributeMutationRequest,
    PlotAttributeUpdateRequest,
    PlotCreateRequest,
    PlotDeleteRequest,
    PlotGeometryUpdateRequest,
    PlotHistoryActionRequest,
    PlotMergeRequest,
    PlotQualityCheckRequest,
    PlotSplitRequest,
    PolygonGeometry,
    QualityIssueResolveRequest,
    TaskQualityCheckRequest,
    TaskSubmitRequest,
)
from app.services.disaster_service import DisasterService
from app.services.imagery_service import ImageryService
from app.services.plot_attribute_field_service import PlotAttributeFieldService
from app.services.project_user_service import ProjectUserService
from app.services.review_service import ReviewService
from app.services.statistics_service import StatisticsService
from app.services.workbench_service import WorkbenchService


def test_plot_attribute_request_accepts_farmland_crop() -> None:
    """验证耕地可关联作物类型。"""
    request = PlotAttributeUpdateRequest(
        land_class="耕地",
        crop_type="玉米",
        planting_mode="单季种植",
        irrigation_condition="良好",
        custom_attributes={},
    )

    assert request.crop_type == "玉米"


def test_plot_attribute_request_rejects_non_farmland_crop() -> None:
    """验证非耕地图斑不得填写作物类型。"""
    with pytest.raises(ValidationError):
        PlotAttributeUpdateRequest(land_class="园地", crop_type="玉米")


def test_get_plot_attributes_hides_plot_outside_task_scope() -> None:
    """验证工作台属性接口不能读取未分配到当前任务的图斑。"""
    dao = AsyncMock()
    dao.get_task_by_code.return_value = SimpleNamespace(id=1)
    dao.is_plot_assigned_to_task.return_value = False
    service = WorkbenchService(dao=dao)

    with pytest.raises(NotFoundException, match="当前任务未找到图斑"):
        asyncio.run(
            service.get_plot_attributes(
                AsyncMock(),
                "RS-2026-045",
                "OUTSIDE-001",
            )
        )

    dao.get_plot_by_code.assert_not_awaited()


def test_list_plot_versions_hides_plot_outside_task_scope() -> None:
    """验证历史版本查询不能绕过任务图斑分配关系。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(id=1)
    workbench_dao.is_plot_assigned_to_task.return_value = False
    service = ReviewService(dao=dao, workbench_dao=workbench_dao)

    with pytest.raises(NotFoundException, match="当前任务未找到图斑"):
        asyncio.run(
            service.list_plot_versions(
                AsyncMock(),
                "RS-2026-045",
                "OUTSIDE-001",
            )
        )

    dao.get_versions.assert_not_awaited()


def build_editable_plot(
    *,
    plot_code: str = "USR-HLJ-001",
    version: int = 1,
    status: str = "interpreting",
    area_ha: Decimal = Decimal("1.2500"),
) -> SimpleNamespace:
    """构造满足图斑编辑响应的测试对象。"""
    return SimpleNamespace(
        plot_code=plot_code,
        owner_village="测试村",
        area_ha=area_ha,
        land_class="耕地",
        crop_type="玉米",
        planting_mode="单季种植",
        irrigation_condition="良好",
        custom_attributes={},
        interpretation_status=status,
        version=version,
        geom="polygon-geometry",
        updated_at=datetime.now(UTC),
    )


def build_polygon_geometry() -> PolygonGeometry:
    """构造闭合的 WGS84 测试多边形。"""
    return PolygonGeometry(
        coordinates=[
            [
                (126.70, 45.70),
                (126.71, 45.70),
                (126.71, 45.71),
                (126.70, 45.70),
            ]
        ]
    )


def build_split_line() -> LineStringGeometry:
    """构造完整穿过测试多边形的 WGS84 分割线。"""
    return LineStringGeometry(
        coordinates=[
            (126.695, 45.705),
            (126.715, 45.705),
        ]
    )


def build_user_service(
    *,
    user_code: str = "interp-li-jing",
    display_name: str = "李静",
    role_code: str = "interpreter",
) -> AsyncMock:
    """构造已通过项目能力校验的用户服务。"""
    service = AsyncMock()
    service.require_capability.return_value = SimpleNamespace(
        user_code=user_code,
        display_name=display_name,
        role_code=role_code,
    )
    return service


def build_plot_attribute_field_service() -> MagicMock:
    """构造没有活动自定义字段的项目字段服务。"""
    service = MagicMock()
    service.get_all_fields_by_project_id = AsyncMock(return_value=[])
    service.get_active_fields_by_project_id = AsyncMock(return_value=[])
    service.build_schema_snapshot.side_effect = (
        PlotAttributeFieldService.build_schema_snapshot
    )
    service.schema_digest.side_effect = PlotAttributeFieldService.schema_digest
    service.validate_custom_attributes.side_effect = (
        lambda _fields, submitted, existing=None: {
            **(existing or {}),
            **(submitted or {}),
        }
    )
    return service


def test_polygon_geometry_rejects_unclosed_ring() -> None:
    """验证绘制几何必须闭合。"""
    with pytest.raises(ValidationError, match="必须闭合"):
        PolygonGeometry(
            coordinates=[
                [
                    (126.70, 45.70),
                    (126.71, 45.70),
                    (126.71, 45.71),
                    (126.70, 45.71),
                ]
            ]
        )


def test_create_plot_generates_version_audit_and_task_progress() -> None:
    """验证新建图斑生成编号、版本、审计并重开任务。"""
    task = build_task("interpreting")
    plot = build_editable_plot()
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.analyze_polygon.return_value = (True, 1.25)
    dao.get_next_plot_code.return_value = "USR-HLJ-001"
    dao.create_plot.return_value = plot
    dao.count_plot_progress.return_value = (216, 0)
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
        plot_attribute_field_service=build_plot_attribute_field_service(),
    )
    db = AsyncMock()

    response = asyncio.run(
        service.create_plot(
            db,
            "RS-2026-045",
            PlotCreateRequest(
                owner_village="测试村",
                geometry=build_polygon_geometry(),
                land_class="耕地",
                crop_type="玉米",
                planting_mode="单季种植",
                irrigation_condition="良好",
                operator_code="interp-li-jing",
                comment="补绘漏判地块",
            ),
        )
    )

    assert response.plot_code == "USR-HLJ-001"
    assert task.status == "interpreting"
    assert task.total_plots == 216
    saved_version = dao.add_plot_version.await_args.args[1]
    assert saved_version.version == 1
    assert saved_version.change_summary == "补绘漏判地块"
    assert saved_version.created_by_code == "interp-li-jing"
    assert saved_version.created_by_role == "interpreter"
    dao.assign_plot_to_task.assert_awaited_once_with(
        db,
        task.id,
        "USR-HLJ-001",
        "李静",
        "interp-li-jing",
        "interpreter",
    )
    dao.count_plot_progress.assert_awaited_once_with(db, task.id)
    dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_update_plot_attributes_uses_stable_user_audit() -> None:
    """验证单图属性修改保存用户编码、角色快照和不可变版本。"""
    task = build_task("interpreting")
    plot = build_editable_plot()
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_plot_by_code_for_update.return_value = plot
    dao.is_plot_assigned_to_task.return_value = True
    dao.count_plot_progress.return_value = (1, 1)
    user_service = build_user_service()
    service = WorkbenchService(
        dao=dao,
        project_user_service=user_service,
        plot_attribute_field_service=build_plot_attribute_field_service(),
    )
    db = AsyncMock()

    response = asyncio.run(
        service.update_plot_attributes(
            db,
            "RS-2026-045",
            plot.plot_code,
            PlotAttributeMutationRequest(
                land_class="耕地",
                crop_type="大豆",
                planting_mode="轮作",
                irrigation_condition="良好",
                operator_code="interp-li-jing",
                comment="依据影像纹理修改为大豆",
            ),
        )
    )

    assert response.crop_type == "大豆"
    assert response.version == 2
    version = dao.add_plot_version.await_args.args[1]
    assert version.created_by == "李静"
    assert version.created_by_code == "interp-li-jing"
    assert version.created_by_role == "interpreter"
    record = dao.add_review_record.await_args.args[1]
    assert record.reviewer_code == "interp-li-jing"
    assert record.reviewer_role == "interpreter"
    user_service.require_capability.assert_awaited_once_with(
        db,
        task.project_id,
        "interp-li-jing",
        "edit_plots",
    )
    dao.supersede_reverted_plot_operations.assert_awaited_once_with(db, task.id)
    db.commit.assert_awaited_once()


def test_plot_create_rejects_user_without_edit_capability() -> None:
    """验证后端拒绝无地块编辑能力的项目身份。"""
    task = build_task("interpreting")
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    user_service = AsyncMock()
    user_service.require_capability.side_effect = PermissionDeniedException(
        "外业核查员无权执行当前业务节点"
    )
    service = WorkbenchService(
        dao=dao,
        project_user_service=user_service,
    )

    with pytest.raises(PermissionDeniedException, match="外业核查员"):
        asyncio.run(
            service.create_plot(
                AsyncMock(),
                "RS-2026-045",
                PlotCreateRequest(
                    owner_village="测试村",
                    geometry=build_polygon_geometry(),
                    land_class="耕地",
                    crop_type="玉米",
                    operator_code="field-zhang-qiang",
                ),
            )
        )

    dao.analyze_polygon.assert_not_awaited()


def test_plot_edit_rejects_task_in_review() -> None:
    """验证进入审核流程后任何图斑属性修改均被阻止。"""
    task = build_task("quality_review")
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    user_service = build_user_service()

    with pytest.raises(ValidationException, match="仅解译中的任务"):
        asyncio.run(
            WorkbenchService(
                dao=dao,
                project_user_service=user_service,
            ).update_plot_attributes(
                AsyncMock(),
                "RS-2026-045",
                "OSM-HLJ-100",
                PlotAttributeMutationRequest(
                    land_class="耕地",
                    crop_type="玉米",
                    operator_code="interp-li-jing",
                ),
            )
        )

    user_service.require_capability.assert_not_awaited()


def test_update_plot_geometry_recalculates_area_and_creates_version() -> None:
    """验证节点编辑后重算面积并创建不可变版本。"""
    task = build_task("interpreting")
    current_plot = build_editable_plot()
    updated_plot = build_editable_plot(version=2, area_ha=Decimal("2.5000"))
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_plot_by_code_for_update.return_value = current_plot
    dao.is_plot_assigned_to_task.return_value = True
    dao.analyze_polygon.return_value = (True, 2.5)
    dao.update_plot_geometry.return_value = updated_plot
    dao.count_plot_progress.return_value = (215, 0)
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
        plot_attribute_field_service=build_plot_attribute_field_service(),
    )
    db = AsyncMock()

    response = asyncio.run(
        service.update_plot_geometry(
            db,
            "RS-2026-045",
            current_plot.plot_code,
            PlotGeometryUpdateRequest(
                geometry=build_polygon_geometry(),
                operator_code="interp-li-jing",
                comment="沿影像纹理修正东侧节点",
            ),
        )
    )

    assert response.area_ha == 2.5
    assert response.version == 2
    assert task.status == "interpreting"
    saved_version = dao.add_plot_version.await_args.args[1]
    assert saved_version.version == 2
    assert saved_version.change_summary == "沿影像纹理修正东侧节点"
    db.commit.assert_awaited_once()


def test_delete_plot_is_soft_delete_with_audit_cleanup() -> None:
    """验证删除工具执行软删除、版本审计和关联清理。"""
    task = build_task("interpreting")
    current_plot = build_editable_plot()
    deleted_plot = build_editable_plot(version=2, status="deleted")
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_plot_by_code_for_update.return_value = current_plot
    dao.soft_delete_plot.return_value = deleted_plot
    dao.count_plot_progress.return_value = (214, 0)
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
        plot_attribute_field_service=build_plot_attribute_field_service(),
    )
    db = AsyncMock()

    response = asyncio.run(
        service.delete_plot(
            db,
            "RS-2026-045",
            current_plot.plot_code,
            PlotDeleteRequest(
                operator_code="interp-li-jing",
                comment="影像判读确认重复图斑",
            ),
        )
    )

    assert response.interpretation_status == "deleted"
    assert response.version == 2
    assert task.total_plots == 214
    dao.close_plot_issues.assert_awaited_once_with(db, current_plot.plot_code)
    dao.detach_field_verifications.assert_awaited_once_with(
        db,
        current_plot.plot_code,
    )
    dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_split_plot_creates_two_children_versions_and_operation_audit() -> None:
    """验证分割事务生成两个子图斑、三份版本和稳定用户操作日志。"""
    task = build_task("interpreting")
    source_plot = build_editable_plot(area_ha=Decimal("1.2500"))
    source_plot.custom_attributes = {"soil_type": "黑土"}
    deleted_source = build_editable_plot(
        version=2,
        status="deleted",
        area_ha=Decimal("1.2500"),
    )
    deleted_source.custom_attributes = {"soil_type": "黑土"}
    first_child = build_editable_plot(
        plot_code="SPL-HLJ-001",
        area_ha=Decimal("0.7000"),
    )
    first_child.custom_attributes = {"soil_type": "黑土"}
    second_child = build_editable_plot(
        plot_code="SPL-HLJ-002",
        area_ha=Decimal("0.5500"),
    )
    second_child.custom_attributes = {"soil_type": "黑土"}
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_plot_by_code_for_update.return_value = source_plot
    dao.is_plot_assigned_to_task.return_value = True
    dao.analyze_plot_split.return_value = SplitAnalysis(
        cutter_simple=True,
        source_area_ha=1.25,
        pieces=[
            SplitPiece('{"type":"Polygon"}', 0.7),
            SplitPiece('{"type":"Polygon"}', 0.55),
        ],
    )
    dao.get_next_plot_code.side_effect = ["SPL-HLJ-001", "SPL-HLJ-002"]
    dao.create_split_child.side_effect = [first_child, second_child]
    dao.soft_delete_plot.return_value = deleted_source
    dao.count_plot_progress.return_value = (216, 0)
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
        plot_attribute_field_service=build_plot_attribute_field_service(),
    )
    db = AsyncMock()

    response = asyncio.run(
        service.split_plot(
            db,
            "RS-2026-045",
            source_plot.plot_code,
            PlotSplitRequest(
                cutter=build_split_line(),
                operator_code="interp-li-jing",
                comment="沿影像可见田埂执行分割",
            ),
        )
    )

    assert [item.plot_code for item in response.result_plots] == [
        "SPL-HLJ-001",
        "SPL-HLJ-002",
    ]
    assert response.area_difference_ha == pytest.approx(0)
    assert response.total_plot_count == 216
    assert dao.assign_plot_to_task.await_count == 2
    versions = dao.add_plot_versions.await_args.args[1]
    assert len(versions) == 3
    assert versions[0].interpretation_status == "deleted"
    assert {item.plot_code for item in versions[1:]} == {
        "SPL-HLJ-001",
        "SPL-HLJ-002",
    }
    assert all(
        item.custom_attributes == {"soil_type": "黑土"} for item in versions
    )
    operation = dao.add_plot_edit_operation.await_args.args[1]
    assert operation.operation_type == "split"
    assert operation.source_plot_codes == [source_plot.plot_code]
    assert operation.result_plot_codes == ["SPL-HLJ-001", "SPL-HLJ-002"]
    assert operation.operator_code == "interp-li-jing"
    assert operation.applied_versions == {
        source_plot.plot_code: 2,
        "SPL-HLJ-001": 1,
        "SPL-HLJ-002": 1,
    }
    dao.rematch_split_field_verifications.assert_awaited_once_with(
        db,
        source_plot.plot_code,
        ["SPL-HLJ-001", "SPL-HLJ-002"],
    )
    db.commit.assert_awaited_once()


def test_split_plot_rejects_line_that_does_not_create_two_pieces() -> None:
    """验证未完整穿过图斑的分割线不会产生伪子图斑。"""
    task = build_task("interpreting")
    source_plot = build_editable_plot()
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_plot_by_code_for_update.return_value = source_plot
    dao.is_plot_assigned_to_task.return_value = True
    dao.analyze_plot_split.return_value = SplitAnalysis(
        cutter_simple=True,
        source_area_ha=1.25,
        pieces=[SplitPiece('{"type":"Polygon"}', 1.25)],
    )
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
    )

    with pytest.raises(ValidationException, match="仅生成两个子图斑"):
        asyncio.run(
            service.split_plot(
                AsyncMock(),
                "RS-2026-045",
                source_plot.plot_code,
                PlotSplitRequest(
                    cutter=build_split_line(),
                    operator_code="interp-li-jing",
                    comment="尝试沿田埂分割",
                ),
            )
        )

    dao.create_split_child.assert_not_awaited()


def test_merge_plots_creates_result_versions_and_operation_audit() -> None:
    """验证相邻图斑合并生成结果、源版本和冲突属性操作日志。"""
    task = build_task("interpreting")
    first = build_editable_plot(
        plot_code="USR-HLJ-001",
        area_ha=Decimal("1.2500"),
    )
    second = build_editable_plot(
        plot_code="USR-HLJ-002",
        area_ha=Decimal("0.7500"),
    )
    second.owner_village = "相邻村"
    merged = build_editable_plot(
        plot_code="MRG-HLJ-001",
        area_ha=Decimal("2.0000"),
    )
    first_deleted = build_editable_plot(
        plot_code=first.plot_code,
        version=2,
        status="deleted",
        area_ha=first.area_ha,
    )
    second_deleted = build_editable_plot(
        plot_code=second.plot_code,
        version=2,
        status="deleted",
        area_ha=second.area_ha,
    )
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_task_plots_by_codes_for_update.return_value = [first, second]
    dao.analyze_plot_merge.return_value = MergeAnalysis(
        source_count=2,
        district_count=1,
        geometry_type="ST_Polygon",
        component_count=1,
        geometry_valid=True,
        source_area_ha=2.0,
        result_area_ha=2.0,
        overlap_area_ha=0,
        geometry_json='{"type":"Polygon"}',
    )
    dao.get_next_plot_code.return_value = "MRG-HLJ-001"
    dao.create_merged_plot.return_value = merged
    dao.soft_delete_plot.side_effect = [first_deleted, second_deleted]
    dao.count_plot_progress.return_value = (214, 0)
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
        plot_attribute_field_service=build_plot_attribute_field_service(),
    )
    db = AsyncMock()

    response = asyncio.run(
        service.merge_plots(
            db,
            "RS-2026-045",
            PlotMergeRequest(
                plot_codes=[first.plot_code, second.plot_code],
                owner_village="合并确认村",
                land_class="耕地",
                crop_type="玉米",
                planting_mode="单季种植",
                irrigation_condition="良好",
                operator_code="interp-li-jing",
                comment="依据连续田埂和权属调查合并",
            ),
        )
    )

    assert response.result_plot.plot_code == "MRG-HLJ-001"
    assert response.area_difference_ha == pytest.approx(0)
    assert response.total_plot_count == 214
    versions = dao.add_plot_versions.await_args.args[1]
    assert len(versions) == 3
    assert {item.plot_code for item in versions[:2]} == {
        first.plot_code,
        second.plot_code,
    }
    assert versions[2].plot_code == "MRG-HLJ-001"
    operation = dao.add_plot_edit_operation.await_args.args[1]
    assert operation.operation_type == "merge"
    assert operation.source_plot_codes == [first.plot_code, second.plot_code]
    assert operation.result_plot_codes == ["MRG-HLJ-001"]
    assert operation.applied_versions == {
        first.plot_code: 2,
        second.plot_code: 2,
        "MRG-HLJ-001": 1,
    }
    dao.rematch_merged_field_verifications.assert_awaited_once_with(
        db,
        [first.plot_code, second.plot_code],
        "MRG-HLJ-001",
    )
    assert dao.close_plot_issues.await_count == 2
    db.commit.assert_awaited_once()


def test_merge_rejects_unresolved_custom_attribute_conflict() -> None:
    """验证活动自定义字段冲突必须由用户显式确认最终值。"""
    task = build_task("interpreting")
    first = build_editable_plot(plot_code="USR-HLJ-001")
    second = build_editable_plot(plot_code="USR-HLJ-002")
    first.custom_attributes = {"soil_type": "黑土"}
    second.custom_attributes = {"soil_type": "白浆土"}
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_task_plots_by_codes_for_update.return_value = [first, second]
    dao.analyze_plot_merge.return_value = MergeAnalysis(
        source_count=2,
        district_count=1,
        geometry_type="ST_Polygon",
        component_count=1,
        geometry_valid=True,
        source_area_ha=2.5,
        result_area_ha=2.5,
        overlap_area_ha=0,
        geometry_json='{"type":"Polygon"}',
    )
    field_service = build_plot_attribute_field_service()
    field_service.get_all_fields_by_project_id.return_value = [
        SimpleNamespace(
            field_code="soil_type",
            label="土壤类型",
            field_type="single_select",
            required=False,
            options=["黑土", "白浆土"],
            display_order=10,
            status="active",
            version=1,
        )
    ]
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
        plot_attribute_field_service=field_service,
    )

    with pytest.raises(ValidationException, match="人工确认自定义冲突字段.*土壤类型"):
        asyncio.run(
            service.merge_plots(
                AsyncMock(),
                "RS-2026-045",
                PlotMergeRequest(
                    plot_codes=[first.plot_code, second.plot_code],
                    owner_village="合并确认村",
                    land_class="耕地",
                    crop_type="玉米",
                    planting_mode="单季种植",
                    irrigation_condition="良好",
                    operator_code="interp-li-jing",
                    comment="验证自定义属性冲突门禁",
                ),
            )
        )

    dao.create_merged_plot.assert_not_awaited()


def test_merge_plots_rejects_disconnected_sources() -> None:
    """验证不连续图斑不能合并成 MultiPolygon 冒充单一地块。"""
    task = build_task("interpreting")
    first = build_editable_plot(plot_code="USR-HLJ-001")
    second = build_editable_plot(plot_code="USR-HLJ-002")
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_task_plots_by_codes_for_update.return_value = [first, second]
    dao.analyze_plot_merge.return_value = MergeAnalysis(
        source_count=2,
        district_count=1,
        geometry_type="ST_MultiPolygon",
        component_count=2,
        geometry_valid=True,
        source_area_ha=2.5,
        result_area_ha=2.5,
        overlap_area_ha=0,
        geometry_json='{"type":"MultiPolygon"}',
    )
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
    )

    with pytest.raises(ValidationException, match="所选图斑不连续"):
        asyncio.run(
            service.merge_plots(
                AsyncMock(),
                "RS-2026-045",
                PlotMergeRequest(
                    plot_codes=[first.plot_code, second.plot_code],
                    owner_village="测试村",
                    land_class="耕地",
                    crop_type="玉米",
                    operator_code="interp-li-jing",
                    comment="尝试合并不连续图斑",
                ),
            )
        )

    dao.create_merged_plot.assert_not_awaited()


def test_undo_split_restores_source_and_deactivates_children() -> None:
    """验证撤销分割恢复源图斑、停用子图斑并保存版本状态。"""
    task = build_task("interpreting")
    source_deleted = build_editable_plot(
        plot_code="USR-HLJ-001",
        version=2,
        status="deleted",
    )
    first_child = build_editable_plot(plot_code="SPL-HLJ-001", version=1)
    second_child = build_editable_plot(plot_code="SPL-HLJ-002", version=1)
    source_restored = build_editable_plot(
        plot_code=source_deleted.plot_code,
        version=3,
        status="interpreting",
    )
    first_deleted = build_editable_plot(
        plot_code=first_child.plot_code,
        version=2,
        status="deleted",
    )
    second_deleted = build_editable_plot(
        plot_code=second_child.plot_code,
        version=2,
        status="deleted",
    )
    operation = PlotEditOperation(
        id=1,
        operation_code="PEO-SPLIT-001",
        task_id=task.id,
        operation_type="split",
        source_plot_codes=[source_deleted.plot_code],
        result_plot_codes=[first_child.plot_code, second_child.plot_code],
        applied_versions={
            source_deleted.plot_code: 2,
            first_child.plot_code: 1,
            second_child.plot_code: 1,
        },
        reverted_versions={},
        status="applied",
        operator="李静",
        operator_code="interp-li-jing",
        operator_role="interpreter",
        comment="初始分割",
    )
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_latest_undoable_plot_operation.return_value = operation
    dao.get_plots_by_codes_for_update_any_status.return_value = [
        source_deleted,
        first_child,
        second_child,
    ]
    dao.restore_plot_from_latest_active_version.return_value = source_restored
    dao.soft_delete_plot.side_effect = [first_deleted, second_deleted]
    dao.count_plot_progress.return_value = (215, 0)
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
    )
    db = AsyncMock()

    response = asyncio.run(
        service.undo_plot_operation(
            db,
            "RS-2026-045",
            PlotHistoryActionRequest(
                operator_code="interp-li-jing",
                comment="误将同一经营地块分割，撤销恢复",
            ),
        )
    )

    assert response.action == "undo"
    assert response.active_plot_codes == [source_deleted.plot_code]
    assert operation.status == "reverted"
    assert operation.reverted_versions == {
        source_deleted.plot_code: 3,
        first_child.plot_code: 2,
        second_child.plot_code: 2,
    }
    dao.rematch_merged_field_verifications.assert_awaited_once_with(
        db,
        [first_child.plot_code, second_child.plot_code],
        source_deleted.plot_code,
    )
    assert dao.add_plot_versions.await_args.args[1][0].version == 3
    event = dao.add_plot_edit_operation_event.await_args.args[1]
    assert event.action == "undo"
    db.commit.assert_awaited_once()


def test_redo_merge_deactivates_sources_and_restores_result() -> None:
    """验证重做合并停用源图斑、恢复结果并更新生效版本快照。"""
    task = build_task("interpreting")
    first_source = build_editable_plot(plot_code="USR-HLJ-001", version=3)
    second_source = build_editable_plot(plot_code="USR-HLJ-002", version=3)
    result_deleted = build_editable_plot(
        plot_code="MRG-HLJ-001",
        version=2,
        status="deleted",
    )
    first_deleted = build_editable_plot(
        plot_code=first_source.plot_code,
        version=4,
        status="deleted",
    )
    second_deleted = build_editable_plot(
        plot_code=second_source.plot_code,
        version=4,
        status="deleted",
    )
    result_restored = build_editable_plot(
        plot_code=result_deleted.plot_code,
        version=3,
    )
    operation = PlotEditOperation(
        id=2,
        operation_code="PEO-MERGE-001",
        task_id=task.id,
        operation_type="merge",
        source_plot_codes=[first_source.plot_code, second_source.plot_code],
        result_plot_codes=[result_deleted.plot_code],
        applied_versions={},
        reverted_versions={
            first_source.plot_code: 3,
            second_source.plot_code: 3,
            result_deleted.plot_code: 2,
        },
        status="reverted",
        operator="李静",
        operator_code="interp-li-jing",
        operator_role="interpreter",
        comment="初始合并",
        reverted_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_latest_redoable_plot_operation.return_value = operation
    dao.get_plots_by_codes_for_update_any_status.return_value = [
        first_source,
        second_source,
        result_deleted,
    ]
    dao.restore_plot_from_latest_active_version.return_value = result_restored
    dao.soft_delete_plot.side_effect = [first_deleted, second_deleted]
    dao.count_plot_progress.return_value = (214, 0)
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
    )
    db = AsyncMock()

    response = asyncio.run(
        service.redo_plot_operation(
            db,
            "RS-2026-045",
            PlotHistoryActionRequest(
                operator_code="interp-li-jing",
                comment="复核确认仍应保持合并结果",
            ),
        )
    )

    assert response.action == "redo"
    assert response.active_plot_codes == [result_deleted.plot_code]
    assert operation.status == "applied"
    assert operation.reverted_at is None
    assert operation.applied_versions == {
        first_source.plot_code: 4,
        second_source.plot_code: 4,
        result_deleted.plot_code: 3,
    }
    dao.rematch_merged_field_verifications.assert_awaited_once_with(
        db,
        [first_source.plot_code, second_source.plot_code],
        result_deleted.plot_code,
    )
    event = dao.add_plot_edit_operation_event.await_args.args[1]
    assert event.action == "redo"
    db.commit.assert_awaited_once()


def test_undo_rejects_operation_when_plot_version_changed() -> None:
    """验证关联图斑产生新版本后撤销不会覆盖后续编辑。"""
    task = build_task("interpreting")
    source = build_editable_plot(
        plot_code="USR-HLJ-001",
        version=3,
        status="deleted",
    )
    child = build_editable_plot(plot_code="SPL-HLJ-001", version=1)
    operation = PlotEditOperation(
        id=3,
        operation_code="PEO-SPLIT-CHANGED",
        task_id=task.id,
        operation_type="split",
        source_plot_codes=[source.plot_code],
        result_plot_codes=[child.plot_code],
        applied_versions={source.plot_code: 2, child.plot_code: 1},
        reverted_versions={},
        status="applied",
        operator="李静",
        operator_code="interp-li-jing",
        operator_role="interpreter",
        comment="初始分割",
    )
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_latest_undoable_plot_operation.return_value = operation
    dao.get_plots_by_codes_for_update_any_status.return_value = [source, child]
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
    )

    with pytest.raises(ValidationException, match="不能覆盖新编辑"):
        asyncio.run(
            service.undo_plot_operation(
                AsyncMock(),
                "RS-2026-045",
                PlotHistoryActionRequest(
                    operator_code="interp-li-jing",
                    comment="尝试撤销旧操作",
                ),
            )
        )

    dao.restore_plot_from_latest_active_version.assert_not_awaited()


def test_geometry_edit_rejects_postgis_invalid_polygon() -> None:
    """验证 PostGIS 判定自相交时拒绝保存边界。"""
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = build_task("interpreting")
    dao.get_plot_by_code_for_update.return_value = build_editable_plot()
    dao.analyze_polygon.return_value = (False, 0.0)
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
    )

    with pytest.raises(ValidationException, match="无效几何"):
        asyncio.run(
            service.update_plot_geometry(
                AsyncMock(),
                "RS-2026-045",
                "USR-HLJ-001",
                PlotGeometryUpdateRequest(
                    geometry=build_polygon_geometry(),
                    operator_code="interp-li-jing",
                ),
            )
        )


def build_quality_plot(**overrides: object) -> SimpleNamespace:
    """构造来源和行政层级完整的质量检查图斑。"""
    values = {
        "plot_code": "OSM-HLJ-100",
        "owner_village": "测试村",
        "area_ha": Decimal("12.5000"),
        "land_class": "耕地",
        "crop_type": "玉米",
        "planting_mode": "单季种植",
        "irrigation_condition": "良好",
        "custom_attributes": {},
        "interpretation_status": "interpreted",
        "source_name": "OpenStreetMap",
        "source_feature_id": "way/100",
        "source_uri": "https://www.openstreetmap.org/way/100",
        "source_version": "2",
        "source_updated_at": datetime.now(UTC),
        "province_name": "黑龙江省",
        "city_name": "哈尔滨市",
        "district_name": "道外区",
        "district_code": "230104",
        "version": 2,
        "geom": "polygon-geometry",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def build_quality_metrics(**overrides: object) -> PlotQualityMetrics:
    """构造通过 PostGIS 核心规则的质量指标。"""
    values = {
        "geometry_valid": True,
        "ring_closed": True,
        "calculated_area_ha": 12.5,
        "overlap_count": 0,
        "overlap_area_ha": 0.0,
        "within_district": True,
        "has_imagery": True,
        "covered_by_imagery": True,
        "imagery_resolution_m": 0.8,
    }
    values.update(overrides)
    return PlotQualityMetrics(**values)


def build_quality_dao(
    plot: SimpleNamespace,
    metrics: PlotQualityMetrics,
) -> AsyncMock:
    """构造包含持久化门禁汇总的质量检查 DAO。"""
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = SimpleNamespace(
        id=1,
        project_id=9,
        assignee="李静",
        quality_score=None,
        status="interpreting",
    )
    dao.get_plot_by_code.return_value = plot
    dao.is_plot_assigned_to_task.return_value = True
    dao.get_plot_quality_metrics.return_value = metrics
    dao.get_quality_gate_summary.return_value = QualityGateSummary(
        total_count=809,
        checked_count=1,
        passing_count=1,
        average_score=97.0,
    )
    return dao


def build_quality_service(dao: AsyncMock) -> WorkbenchService:
    """构造使用 2 像元项目规则的质量检查服务。"""
    rule_config_service = AsyncMock()
    rule_config_service.ensure_for_project.return_value = SimpleNamespace(
        positional_accuracy_pixels=Decimal("2.00")
    )
    return WorkbenchService(
        dao=dao,
        rule_config_service=rule_config_service,
        project_user_service=build_user_service(
            user_code="quality-wang-haifeng",
            display_name="王海峰",
            role_code="quality_inspector",
        ),
        plot_attribute_field_service=build_plot_attribute_field_service(),
    )


def test_quality_check_uses_real_metrics_and_marks_position_pending() -> None:
    """验证真实规则通过时只保留位置精度待配置警告。"""
    dao = build_quality_dao(build_quality_plot(), build_quality_metrics())
    service = build_quality_service(dao)
    db = AsyncMock()

    response = asyncio.run(
        service.check_plot_quality(
            db,
            "RS-2026-045",
            "OSM-HLJ-100",
            PlotQualityCheckRequest(operator_code="quality-wang-haifeng"),
        )
    )

    assert response.score == 97
    assert response.can_submit is True
    assert response.checked_plot_count == 1
    assert response.total_plot_count == 809
    assert response.rules[-1].status == "warning"
    assert response.rules[-1].blocking is False
    assert "不生成虚假偏移数值" in response.rules[-1].detail
    dao.get_plot_quality_metrics.assert_awaited_once_with(
        db,
        "OSM-HLJ-100",
        9,
    )
    dao.upsert_plot_quality_check.assert_awaited_once()
    dao.add_quality_issues.assert_awaited_once()


def test_quality_check_missing_crop_blocks_submission() -> None:
    """验证耕地缺少作物类型时生成阻断问题。"""
    dao = build_quality_dao(
        build_quality_plot(crop_type=None),
        build_quality_metrics(),
    )
    dao.get_quality_gate_summary.return_value = QualityGateSummary(
        total_count=809,
        checked_count=1,
        passing_count=0,
        average_score=87.0,
    )

    response = asyncio.run(
        build_quality_service(dao).check_plot_quality(
            AsyncMock(),
            "RS-2026-045",
            "OSM-HLJ-100",
            PlotQualityCheckRequest(operator_code="quality-wang-haifeng"),
        )
    )

    crop_rule = next(
        rule for rule in response.rules if rule.rule_code == "LAND_CROP_LOGIC"
    )
    assert response.score == 87
    assert response.can_submit is False
    assert crop_rule.status == "fail"
    assert crop_rule.blocking is True


def test_task_quality_check_batches_all_scoped_plots() -> None:
    """验证任务级质检一次处理全部作用域图斑并汇总规则。"""
    task = build_task("interpreting")
    task.id = 1
    task.project_id = 9
    task.assignee = "李静"
    passing_plot = build_quality_plot(plot_code="OSM-HLJ-100")
    failing_plot = build_quality_plot(
        plot_code="OSM-HLJ-101",
        crop_type=None,
    )
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_task_plots.return_value = [passing_plot, failing_plot]
    dao.get_task_quality_metrics.return_value = {
        passing_plot.plot_code: build_quality_metrics(),
        failing_plot.plot_code: build_quality_metrics(),
    }
    dao.get_quality_gate_summary.return_value = QualityGateSummary(
        total_count=2,
        checked_count=2,
        passing_count=1,
        average_score=92.0,
    )
    service = build_quality_service(dao)
    db = AsyncMock()

    response = asyncio.run(
        service.run_task_quality_checks(
            db,
            "RS-2026-045",
            TaskQualityCheckRequest(
                operator_code="quality-wang-haifeng",
                comment="全量质检单元测试",
            ),
        )
    )

    assert response.total_plot_count == 2
    assert response.run_code.startswith("QCR-")
    assert response.checked_plot_count == 2
    assert response.passing_plot_count == 1
    assert response.failed_plot_count == 1
    assert response.issue_count == 3
    assert response.can_submit is False
    assert response.rule_config_version == 1
    assert len(response.custom_field_schema_digest) == 64
    crop_summary = next(
        item for item in response.rule_summaries if item.rule_code == "LAND_CROP_LOGIC"
    )
    assert crop_summary.pass_count == 1
    assert crop_summary.fail_count == 1
    assert crop_summary.blocking_issue_count == 1
    checks = dao.upsert_plot_quality_checks.await_args.args[1]
    assert len(checks) == 2
    dao.clear_task_quality_issues.assert_awaited_once_with(db, task.id)
    dao.add_quality_issues.assert_awaited_once()
    dao.add_task_quality_run.assert_awaited_once()
    quality_run = dao.add_task_quality_run.await_args.args[1]
    assert quality_run.run_code == response.run_code
    assert quality_run.task_plot_count == 2
    assert quality_run.checked_plot_count == 2
    assert quality_run.passing_plot_count == 1
    assert quality_run.failed_plot_count == 1
    assert quality_run.issue_count == 3
    assert quality_run.operator_code == "quality-wang-haifeng"
    assert len(quality_run.custom_field_schema_digest) == 64
    dao.add_review_record.assert_awaited_once()
    record = dao.add_review_record.await_args.args[1]
    assert record.reviewer_code == "quality-wang-haifeng"
    assert record.reviewer_role == "quality_inspector"
    assert response.run_code in record.comment
    assert "覆盖 2/2 个图斑" in record.comment
    assert "全量质检单元测试" in record.comment
    db.commit.assert_awaited_once()


def test_task_quality_check_request_limits_audit_comment() -> None:
    """验证全量质检说明不会超过审核记录安全长度。"""
    with pytest.raises(ValidationError):
        TaskQualityCheckRequest(
            operator_code="quality-wang-haifeng",
            comment="质" * 501,
        )


def test_task_quality_run_history_returns_immutable_snapshots() -> None:
    """验证任务质检历史返回规则、自定义字段和稳定用户快照。"""
    created_at = datetime.now(UTC)
    dao = AsyncMock()
    dao.get_task_by_code.return_value = SimpleNamespace(id=1)
    dao.list_task_quality_runs.return_value = (
        [
            SimpleNamespace(
                run_code="QCR-TEST-001",
                task_plot_count=35020,
                task_updated_at_snapshot=created_at,
                rule_config_version=3,
                rule_config_snapshot={"positional_accuracy_pixels": "2.00"},
                custom_field_schema_digest="a" * 64,
                custom_field_snapshot=[
                    {
                        "field_code": "soil_type",
                        "label": "土壤类型",
                        "field_type": "single_select",
                        "required": True,
                        "options": ["黑土"],
                        "display_order": 10,
                        "version": 1,
                    }
                ],
                checked_plot_count=35020,
                passing_plot_count=0,
                failed_plot_count=35020,
                average_score=Decimal("58.80"),
                issue_count=110806,
                can_submit=False,
                duration_ms=37462,
                rule_summaries=[
                    {
                        "rule_code": "IMAGERY_COVERAGE",
                        "label": "影像覆盖检查",
                        "pass_count": 461,
                        "warning_count": 0,
                        "fail_count": 34559,
                        "blocking_issue_count": 34559,
                    }
                ],
                operator="赵志远",
                operator_code="manager-zhao-zhiyuan",
                operator_role="project_manager",
                comment="全省真实图斑质量门禁验证",
                created_at=created_at,
            )
        ],
        4,
    )

    db = AsyncMock()
    response = asyncio.run(
        WorkbenchService(dao=dao).list_task_quality_runs(
            db,
            "RS-2026-045",
            10,
        )
    )

    assert response.total_count == 4
    assert response.items[0].run_code == "QCR-TEST-001"
    assert response.items[0].rule_config_version == 3
    assert response.items[0].average_score == 58.8
    assert response.items[0].rule_summaries[0].fail_count == 34559
    dao.list_task_quality_runs.assert_awaited_once_with(db, 1, 10)


def test_task_quality_check_rejects_submitted_task() -> None:
    """验证已进入审核流程的任务不能覆盖原质检结果。"""
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = build_task("quality_review")

    with pytest.raises(ValidationException, match="仅解译中的任务"):
        asyncio.run(
            WorkbenchService(dao=dao).run_task_quality_checks(
                AsyncMock(),
                "RS-2026-045",
                TaskQualityCheckRequest(operator_code="quality-wang-haifeng"),
            )
        )

    dao.get_task_plots.assert_not_awaited()


def test_task_quality_check_rejects_user_without_quality_capability() -> None:
    """验证全量质检不能由内业解译员越权执行。"""
    task = build_task("interpreting")
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    user_service = AsyncMock()
    user_service.require_capability.side_effect = PermissionDeniedException(
        "内业解译员无权执行当前业务节点"
    )

    with pytest.raises(PermissionDeniedException, match="内业解译员"):
        asyncio.run(
            WorkbenchService(
                dao=dao,
                project_user_service=user_service,
            ).run_task_quality_checks(
                AsyncMock(),
                "RS-2026-045",
                TaskQualityCheckRequest(operator_code="interp-li-jing"),
            )
        )

    dao.get_task_plots.assert_not_awaited()


def test_quality_issue_queue_returns_plot_context_and_rule_counts() -> None:
    """验证问题队列返回可定位图斑上下文和规则汇总。"""
    dao = AsyncMock()
    dao.get_task_by_code.return_value = SimpleNamespace(id=1)
    created_at = datetime.now(UTC)
    dao.get_quality_issue_page.return_value = (
        [
            {
                "id": 10,
                "plot_code": "OSM-HLJ-100",
                "rule_code": "LAND_CROP_LOGIC",
                "issue_type": "quality_rule",
                "severity": "medium",
                "description": "耕地必须填写作物类型",
                "status": "open",
                "source": "auto",
                "assignee": "李静",
                "resolved_by": None,
                "resolved_by_code": None,
                "resolved_by_role": None,
                "resolution_comment": None,
                "created_at": created_at,
                "resolved_at": None,
                "plot_version": 2,
                "city_name": "哈尔滨市",
                "district_name": "道外区",
                "owner_village": "测试村",
                "land_class": "耕地",
                "crop_type": None,
                "area_ha": Decimal("12.5000"),
            }
        ],
        809,
    )
    dao.get_quality_issue_summary.return_value = (
        QualityIssueSummary(
            total_count=2458,
            open_count=2458,
            resolved_count=0,
            high_count=840,
            medium_count=809,
            low_count=809,
        ),
        [
            {
                "rule_code": "LAND_CROP_LOGIC",
                "total_count": 809,
                "open_count": 809,
            }
        ],
    )

    response = asyncio.run(
        WorkbenchService(dao=dao).get_task_quality_issues(
            AsyncMock(),
            "RS-2026-045",
            status="open",
            rule_code="LAND_CROP_LOGIC",
            severity=None,
            issue_type="quality_rule",
            keyword="哈尔滨",
            page=1,
            page_size=20,
        )
    )

    assert response.total_count == 809
    assert response.open_count == 2458
    assert response.items[0].plot_code == "OSM-HLJ-100"
    assert response.items[0].rule_label == "地类与作物逻辑"
    assert response.items[0].area_ha == 12.5
    assert response.rule_counts[0].open_count == 809
    dao.get_quality_issue_page.assert_awaited_once()
    dao.get_quality_issue_summary.assert_awaited_once()


def test_batch_plot_attributes_updates_versions_and_audit() -> None:
    """验证显式选择图斑批量赋值后生成独立版本和任务审计。"""
    task = build_task("interpreting")
    task.id = 1
    first_plot = build_quality_plot(plot_code="OSM-HLJ-100", crop_type=None)
    second_plot = build_quality_plot(plot_code="OSM-HLJ-101", crop_type=None)
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_task_plots_by_codes_for_update.return_value = [
        first_plot,
        second_plot,
    ]
    dao.count_plot_progress.return_value = (809, 2)
    service = WorkbenchService(
        dao=dao,
        project_user_service=build_user_service(),
        plot_attribute_field_service=build_plot_attribute_field_service(),
    )
    db = AsyncMock()

    response = asyncio.run(
        service.batch_update_plot_attributes(
            db,
            "RS-2026-045",
            BatchPlotAttributeUpdateRequest(
                plot_codes=[first_plot.plot_code, second_plot.plot_code],
                attributes=PlotAttributeUpdateRequest(
                    land_class="耕地",
                    crop_type="大豆",
                    planting_mode="轮作",
                    irrigation_condition="良好",
                ),
                operator_code="interp-li-jing",
                comment="依据同期影像统一判读为大豆",
            ),
        )
    )

    assert response.updated_count == 2
    assert response.completed_plot_count == 2
    assert response.quality_recheck_required is True
    assert first_plot.crop_type == "大豆"
    assert first_plot.version == 3
    assert second_plot.version == 3
    versions = dao.add_plot_versions.await_args.args[1]
    assert len(versions) == 2
    assert all(
        version.change_summary == "依据同期影像统一判读为大豆" for version in versions
    )
    dao.resolve_plot_quality_rules.assert_awaited_once_with(
        db,
        task.id,
        [first_plot.plot_code, second_plot.plot_code],
        ["LAND_CROP_LOGIC"],
    )
    dao.add_review_record.assert_awaited_once()
    dao.count_plot_progress.assert_awaited_once_with(db, task.id)
    db.commit.assert_awaited_once()


def test_batch_plot_attributes_rejects_out_of_scope_plot() -> None:
    """验证批量赋值不能越过任务图斑作用域。"""
    task = build_task("interpreting")
    task.id = 1
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_task_plots_by_codes_for_update.return_value = []

    with pytest.raises(ValidationException, match="不属于任务或已删除"):
        asyncio.run(
            WorkbenchService(
                dao=dao,
                project_user_service=build_user_service(),
            ).batch_update_plot_attributes(
                AsyncMock(),
                "RS-2026-045",
                BatchPlotAttributeUpdateRequest(
                    plot_codes=["OUTSIDE-001"],
                    attributes=PlotAttributeUpdateRequest(
                        land_class="耕地",
                        crop_type="玉米",
                    ),
                    operator_code="interp-li-jing",
                    comment="验证越权图斑不能批量赋值",
                ),
            )
        )

    dao.add_plot_versions.assert_not_awaited()


@pytest.mark.parametrize(
    ("plot", "metrics", "rule_code"),
    [
        (
            build_quality_plot(),
            build_quality_metrics(calculated_area_ha=13.0),
            "AREA_CONSISTENCY",
        ),
        (
            build_quality_plot(),
            build_quality_metrics(overlap_count=2, overlap_area_ha=0.35),
            "TOPOLOGY_OVERLAP",
        ),
        (
            build_quality_plot(),
            build_quality_metrics(covered_by_imagery=False),
            "IMAGERY_COVERAGE",
        ),
    ],
)
def test_quality_check_real_spatial_failures_are_blocking(
    plot: SimpleNamespace,
    metrics: PlotQualityMetrics,
    rule_code: str,
) -> None:
    """验证面积、重叠和影像覆盖异常均形成阻断规则。"""
    dao = build_quality_dao(plot, metrics)

    response = asyncio.run(
        build_quality_service(dao).check_plot_quality(
            AsyncMock(),
            "RS-2026-045",
            plot.plot_code,
            PlotQualityCheckRequest(operator_code="quality-wang-haifeng"),
        )
    )

    failed_rule = next(rule for rule in response.rules if rule.rule_code == rule_code)
    assert response.can_submit is False
    assert failed_rule.status == "fail"
    assert failed_rule.blocking is True


def test_task_submit_rejects_incomplete_quality_coverage() -> None:
    """验证未覆盖全部有效图斑时不能提交内业自检。"""
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = build_task("interpreting")
    dao.get_quality_gate_summary.return_value = QualityGateSummary(
        total_count=809,
        checked_count=808,
        passing_count=808,
        average_score=96.0,
    )

    user_service = AsyncMock()
    user_service.require_capability.return_value = build_project_user()

    with pytest.raises(ValidationException, match="已检查 808/809"):
        asyncio.run(
            WorkbenchService(
                dao=dao,
                project_user_service=user_service,
            ).submit_task_for_self_check(
                AsyncMock(),
                "RS-2026-045",
                TaskSubmitRequest(reviewer_code="interp-li-jing"),
            )
        )


def test_task_submit_rejects_non_passing_plots() -> None:
    """验证仍有阻断图斑时不能提交内业自检。"""
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = build_task("interpreting")
    dao.get_quality_gate_summary.return_value = QualityGateSummary(
        total_count=809,
        checked_count=809,
        passing_count=808,
        average_score=96.0,
    )

    user_service = AsyncMock()
    user_service.require_capability.return_value = build_project_user()

    with pytest.raises(ValidationException, match="通过 808/809"):
        asyncio.run(
            WorkbenchService(
                dao=dao,
                project_user_service=user_service,
            ).submit_task_for_self_check(
                AsyncMock(),
                "RS-2026-045",
                TaskSubmitRequest(reviewer_code="interp-li-jing"),
            )
        )


def test_task_submit_succeeds_only_after_all_plots_pass() -> None:
    """验证全量检查通过且平均分达标后进入内业自检。"""
    task = build_task("interpreting")
    dao = AsyncMock()
    dao.get_task_by_code_for_update.return_value = task
    dao.get_quality_gate_summary.return_value = QualityGateSummary(
        total_count=809,
        checked_count=809,
        passing_count=809,
        average_score=96.5,
    )
    db = AsyncMock()
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_project_user()

    response = asyncio.run(
        WorkbenchService(
            dao=dao,
            project_user_service=user_service,
        ).submit_task_for_self_check(
            db,
            "RS-2026-045",
            TaskSubmitRequest(
                reviewer_code="interp-li-jing",
                comment="全量质量检查完成",
            ),
        )
    )

    assert response.status == "self_check"
    assert response.quality_score == 96.5
    dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_field_verification_rejects_invalid_coordinate() -> None:
    """验证外业核查点必须使用合法 WGS84 坐标。"""
    with pytest.raises(ValidationError):
        FieldVerificationCreateRequest(
            verification_code="FV-TEST-001",
            investigator_code="field-zhang-qiang",
            lon=200,
            lat=45.8,
            captured_at="2026-07-21T10:00:00+08:00",
        )


def test_field_resolution_rejects_unknown_decision() -> None:
    """验证外业疑点仅允许预定义处置决策。"""
    with pytest.raises(ValidationError):
        FieldResolutionRequest(
            decision="unknown",
            reviewer_code="quality-wang-haifeng",
            comment="测试非法处置决策",
        )


def build_task(status: str = "self_check") -> SimpleNamespace:
    """构造满足任务响应模型的审核测试对象。"""
    return SimpleNamespace(
        id=1,
        project_id=9,
        task_code="RS-2026-045",
        task_name="松北区第 06 作业单元",
        administrative_region="哈尔滨市松北区",
        assignee="李静",
        status=status,
        total_plots=128,
        completed_plots=105,
        quality_score=Decimal("92.00"),
        deadline=date(2026, 7, 28),
        updated_at=datetime.now(UTC),
    )


def build_project_user(
    *,
    user_code: str = "interp-li-jing",
    display_name: str = "李静",
    role_code: str = "interpreter",
    role_name: str = "内业解译员",
) -> SimpleNamespace:
    """构造项目用户角色测试对象。"""
    return SimpleNamespace(
        user_code=user_code,
        display_name=display_name,
        role_code=role_code,
        role_name=role_name,
        status="active",
        is_default=False,
    )


def test_manual_review_issue_can_be_resolved_with_audit() -> None:
    """验证质检员确认整改后可关闭人工审核问题并记录审计。"""
    task = build_task("interpreting")
    issue = SimpleNamespace(
        id=31,
        source="manual",
        rule_code="REVIEW_9",
        status="open",
        resolved_at=None,
        resolved_by=None,
        resolved_by_code=None,
        resolved_by_role=None,
        resolution_comment=None,
    )
    dao = AsyncMock()
    dao.get_task_by_code.return_value = task
    dao.get_quality_issue_for_update.return_value = issue
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_project_user(
        user_code="quality-wang-haifeng",
        display_name="王海峰",
        role_code="quality_inspector",
        role_name="质检员",
    )
    service = WorkbenchService(
        dao=dao,
        project_user_service=user_service,
    )
    db = AsyncMock()

    response = asyncio.run(
        service.resolve_review_issue(
            db,
            "RS-2026-045",
            31,
            QualityIssueResolveRequest(
                operator_code="quality-wang-haifeng",
                comment="复核边界和属性均已整改",
            ),
        )
    )

    assert response.status == "resolved"
    assert response.resolved_by_code == "quality-wang-haifeng"
    assert issue.resolution_comment == "复核边界和属性均已整改"
    dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_automatic_quality_issue_cannot_be_closed_manually() -> None:
    """验证自动规则问题必须通过重新质检关闭，防止人工绕过门禁。"""
    dao = AsyncMock()
    dao.get_task_by_code.return_value = build_task("interpreting")
    dao.get_quality_issue_for_update.return_value = SimpleNamespace(
        id=32,
        source="auto",
        rule_code="LAND_CROP_LOGIC",
        status="open",
    )
    service = WorkbenchService(
        dao=dao,
        project_user_service=AsyncMock(),
    )

    with pytest.raises(ValidationException, match="必须通过对应业务流程"):
        asyncio.run(
            service.resolve_review_issue(
                AsyncMock(),
                "RS-2026-045",
                32,
                QualityIssueResolveRequest(
                    operator_code="quality-wang-haifeng",
                    comment="尝试手工关闭自动规则",
                ),
            )
        )


def test_review_pass_advances_to_quality_review() -> None:
    """验证内业自检通过后进入质检审核节点。"""
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = build_task()
    workbench_dao.add_review_record.return_value = SimpleNamespace(id=9)
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_project_user()
    service = ReviewService(
        dao=AsyncMock(),
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )
    db = AsyncMock()

    response = asyncio.run(
        service.execute_task_action(
            db,
            "RS-2026-045",
            ReviewActionRequest(
                action="pass",
                reviewer_code="interp-li-jing",
                comment="自检资料完整，同意进入质检审核",
            ),
        )
    )

    assert response.previous_status == "self_check"
    assert response.current_status == "quality_review"
    assert response.record_id == 9
    assert response.reviewer_code == "interp-li-jing"
    workbench_dao.add_review_record.assert_awaited_once()
    workbench_dao.add_quality_issues.assert_not_awaited()
    db.commit.assert_awaited_once()


def test_review_return_requires_comment() -> None:
    """验证退回整改必须填写可追踪的审核意见。"""
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = build_task(
        "quality_review"
    )
    service = ReviewService(
        dao=AsyncMock(),
        workbench_dao=workbench_dao,
        project_user_service=AsyncMock(),
    )

    with pytest.raises(ValidationException, match="退回整改必须填写审核意见"):
        asyncio.run(
            service.execute_task_action(
                AsyncMock(),
                "RS-2026-045",
                ReviewActionRequest(
                    action="return",
                    reviewer_code="quality-wang-haifeng",
                ),
            )
        )


def test_quality_review_rejects_interpreter_role() -> None:
    """验证内业解译员不能越权执行质检审核节点。"""
    task = build_task("quality_review")
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = task
    user_dao = AsyncMock()
    user_dao.get_active_user.return_value = build_project_user()
    service = ReviewService(
        dao=AsyncMock(),
        workbench_dao=workbench_dao,
        project_user_service=ProjectUserService(dao=user_dao),
    )

    with pytest.raises(PermissionDeniedException, match="无权执行当前业务节点"):
        asyncio.run(
            service.execute_task_action(
                AsyncMock(),
                "RS-2026-045",
                ReviewActionRequest(
                    action="pass",
                    reviewer_code="interp-li-jing",
                    comment="尝试越权审核",
                ),
            )
        )

    assert task.status == "quality_review"
    workbench_dao.add_review_record.assert_not_awaited()


def test_quality_review_blocks_unresolved_issues() -> None:
    """验证质检审核不能绕过任务未关闭问题。"""
    task = build_task("quality_review")
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = task
    workbench_dao.count_open_issues.return_value = 3
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_project_user(
        user_code="quality-wang-haifeng",
        display_name="王海峰",
        role_code="quality_inspector",
        role_name="质检员",
    )
    service = ReviewService(
        dao=AsyncMock(),
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )

    with pytest.raises(ValidationException, match="仍有 3 条问题未关闭"):
        asyncio.run(
            service.execute_task_action(
                AsyncMock(),
                "RS-2026-045",
                ReviewActionRequest(
                    action="pass",
                    reviewer_code="quality-wang-haifeng",
                    comment="尝试忽略问题通过",
                ),
            )
        )

    assert task.status == "quality_review"


def test_client_review_blocks_pending_field_verifications() -> None:
    """验证甲方复核完成前必须处置全部外业疑点。"""
    task = build_task("client_review")
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = task
    workbench_dao.count_open_issues.return_value = 0
    workbench_dao.count_pending_field_verifications.return_value = 2
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_project_user(
        user_code="client-agri-dept",
        display_name="农业农村厅审核代表",
        role_code="client_reviewer",
        role_name="甲方（监管方）",
    )
    service = ReviewService(
        dao=AsyncMock(),
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )

    with pytest.raises(ValidationException, match="仍有 2 条外业疑点未处置"):
        asyncio.run(
            service.execute_task_action(
                AsyncMock(),
                "RS-2026-045",
                ReviewActionRequest(
                    action="pass",
                    reviewer_code="client-agri-dept",
                    comment="甲方复核",
                ),
            )
        )

    assert task.status == "client_review"


def test_plot_rollback_creates_new_version_and_reopens_task() -> None:
    """验证历史回退不会覆盖旧版本，并将任务重新打开整改。"""
    task = build_task("quality_review")
    plot = SimpleNamespace(
        plot_code="HLJ-001",
        owner_village="幸福村",
        area_ha=Decimal("12.5000"),
        land_class="耕地",
        crop_type="玉米",
        planting_mode="轮作",
        irrigation_condition="一般",
        custom_attributes={"soil_type": "白浆土"},
        interpretation_status="interpreted",
        geom="current-geometry",
        version=3,
        updated_at=datetime.now(UTC),
    )
    target = SimpleNamespace(
        land_class="耕地",
        crop_type="大豆",
        planting_mode="单季种植",
        irrigation_condition="良好",
        custom_attributes={"soil_type": "黑土", "legacy_code": "OLD-001"},
        geom="version-1-geometry",
    )
    review_dao = AsyncMock()
    review_dao.get_version.return_value = target
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = task
    workbench_dao.get_plot_by_code.return_value = plot
    workbench_dao.is_plot_assigned_to_task.return_value = True
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_project_user(
        user_code="quality-wang-haifeng",
        display_name="王海峰",
        role_code="quality_inspector",
        role_name="质检员",
    )
    service = ReviewService(
        dao=review_dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )
    db = AsyncMock()

    response = asyncio.run(
        service.rollback_plot(
            db,
            "RS-2026-045",
            "HLJ-001",
            PlotRollbackRequest(
                target_version=1,
                operator_code="quality-wang-haifeng",
                comment="恢复经确认的首版边界",
            ),
        )
    )

    assert response.version == 4
    assert response.crop_type == "大豆"
    assert response.interpretation_status == "interpreting"
    assert response.custom_attributes == {
        "soil_type": "黑土",
        "legacy_code": "OLD-001",
    }
    assert plot.geom == "version-1-geometry"
    assert task.status == "interpreting"
    saved_version = review_dao.add_version.await_args.args[1]
    assert saved_version.version == 4
    assert saved_version.change_summary == "恢复经确认的首版边界"
    assert saved_version.custom_attributes == response.custom_attributes
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_workbench_overview_allows_missing_operational_imagery() -> None:
    """验证未上传业务影像时工作台返回明确空值而不是依赖占位记录。"""
    dao = AsyncMock()
    dao.get_project_by_code.return_value = SimpleNamespace(
        id=1,
        project_code="RS-2026",
        project_name="省级农作物种植监测",
        province="黑龙江省",
        monitor_year=2026,
        status="active",
        progress=Decimal("46.00"),
        deadline=date(2026, 7, 28),
    )
    dao.get_task_by_code.return_value = SimpleNamespace(
        id=2,
        project_id=1,
        task_code="RS-2026-045",
        task_name="全域地块解译",
        administrative_region="黑龙江省",
        assignee="李静",
        status="interpreting",
        total_plots=22092,
        completed_plots=0,
        quality_score=None,
        deadline=date(2026, 7, 28),
    )
    dao.get_latest_imagery.return_value = None
    dao.get_reviews.return_value = []
    dao.count_reviews.side_effect = [27, 4]
    dao.count_open_issues.return_value = 0
    dao.get_quality_gate_summary.return_value = QualityGateSummary(
        total_count=22092,
        checked_count=0,
        passing_count=0,
        average_score=None,
    )
    dao.get_navigation_counts.return_value = SimpleNamespace(
        operational_imagery_count=0,
        pending_disaster_count=0,
        total_field_verification_count=0,
        pending_field_verification_count=0,
        current_delivery_package_count=0,
    )
    service = WorkbenchService(dao=dao)

    response = asyncio.run(
        service.get_overview(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
        )
    )

    assert response.imagery is None
    assert response.statistics.plot_count == 22092
    assert response.statistics.operational_imagery_count == 0
    assert response.statistics.pending_disaster_count == 0
    assert response.statistics.pending_field_verification_count == 0
    assert response.statistics.review_record_count == 27
    assert response.statistics.current_cycle_review_count == 4
    assert dao.get_reviews.await_args.kwargs["limit"] == 20
    assert dao.get_reviews.await_args.kwargs["current_cycle"] is True
    assert response.project.progress == 0
    assert response.workflow.current_stage == "影像预处理"
    assert response.workflow.stages[0].status == "blocked"
    assert response.workflow.stages[1].status == "active"


def test_workbench_overview_completes_only_with_full_evidence() -> None:
    """验证总览只有在六阶段证据完整时才显示全流程完成。"""
    dao = AsyncMock()
    dao.get_project_by_code.return_value = SimpleNamespace(
        id=1,
        project_code="RS-2026",
        project_name="省级农作物种植监测",
        province="黑龙江省",
        monitor_year=2026,
        status="active",
        progress=Decimal("46.00"),
        deadline=date(2026, 8, 8),
    )
    dao.get_task_by_code.return_value = SimpleNamespace(
        id=2,
        project_id=1,
        task_code="RS-2026-045",
        task_name="全域地块解译",
        administrative_region="黑龙江省",
        assignee="李静",
        status="completed",
        total_plots=2,
        completed_plots=2,
        quality_score=Decimal("96.50"),
        deadline=date(2026, 7, 28),
    )
    dao.get_latest_imagery.return_value = SimpleNamespace(
        asset_code="GF-REAL-001",
        asset_name="业务遥感影像",
        sensor_type="GF2-PMS",
        acquired_at=datetime.now(UTC),
        cloud_cover=Decimal("2.00"),
        resolution_m=Decimal("0.80"),
        processing_level="L2A",
        calibration_status="completed",
        correction_status="completed",
    )
    dao.get_reviews.return_value = []
    dao.count_reviews.return_value = 0
    dao.count_open_issues.return_value = 0
    dao.get_quality_gate_summary.return_value = QualityGateSummary(
        total_count=2,
        checked_count=2,
        passing_count=2,
        average_score=96.5,
    )
    dao.get_navigation_counts.return_value = SimpleNamespace(
        operational_imagery_count=1,
        pending_disaster_count=0,
        total_field_verification_count=2,
        pending_field_verification_count=0,
        current_delivery_package_count=1,
    )

    response = asyncio.run(
        WorkbenchService(dao=dao).get_overview(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
        )
    )

    assert response.project.progress == 100
    assert response.workflow.current_stage == "全流程完成"
    assert all(stage.status == "completed" for stage in response.workflow.stages)


def test_plot_rollback_rejects_interpreter_role() -> None:
    """验证图斑版本回退仅允许质检员或项目负责人。"""
    task = build_task("quality_review")
    plot = SimpleNamespace(version=3)
    review_dao = AsyncMock()
    review_dao.get_version.return_value = SimpleNamespace()
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = task
    workbench_dao.get_plot_by_code.return_value = plot
    workbench_dao.is_plot_assigned_to_task.return_value = True
    user_dao = AsyncMock()
    user_dao.get_active_user.return_value = build_project_user()
    service = ReviewService(
        dao=review_dao,
        workbench_dao=workbench_dao,
        project_user_service=ProjectUserService(dao=user_dao),
    )

    with pytest.raises(PermissionDeniedException, match="无权执行当前业务节点"):
        asyncio.run(
            service.rollback_plot(
                AsyncMock(),
                "RS-2026-045",
                "HLJ-001",
                PlotRollbackRequest(
                    target_version=1,
                    operator_code="interp-li-jing",
                ),
            )
        )

    review_dao.add_version.assert_not_awaited()


def test_area_statistics_aggregates_groups_and_trend() -> None:
    """验证面积统计可生成地类占比、亩数和年度同比。"""
    dao = AsyncMock()
    dao.get_totals.return_value = (2, Decimal("20.0000"))
    dao.get_land_class_groups.return_value = [
        SimpleNamespace(label="耕地", plot_count=1, area_ha=Decimal("12.0000")),
        SimpleNamespace(label="园地", plot_count=1, area_ha=Decimal("8.0000")),
    ]
    dao.get_crop_type_groups.return_value = [
        SimpleNamespace(label="玉米", plot_count=1, area_ha=Decimal("12.0000")),
        SimpleNamespace(label="作物未录入", plot_count=1, area_ha=Decimal("8.0000")),
    ]
    dao.get_planting_mode_groups.return_value = [
        SimpleNamespace(label="单季", plot_count=2, area_ha=Decimal("20.0000"))
    ]
    dao.get_city_groups.return_value = [
        SimpleNamespace(label="哈尔滨市", plot_count=2, area_ha=Decimal("20.0000"))
    ]
    dao.get_district_groups.return_value = [
        SimpleNamespace(
            code="230109",
            label="松北区",
            parent_label="哈尔滨市",
            plot_count=2,
            area_ha=Decimal("20.0000"),
        )
    ]
    dao.get_village_groups.return_value = [
        SimpleNamespace(label="幸福村", plot_count=2, area_ha=Decimal("20.0000"))
    ]
    dao.get_crop_assignment_counts.return_value = (1, 1)
    dao.get_project_monitor_year.return_value = 2026
    dao.get_annual_trend.return_value = [
        SimpleNamespace(monitor_year=2025, total_area_ha=Decimal("18.0000")),
        SimpleNamespace(monitor_year=2026, total_area_ha=Decimal("20.0000")),
    ]
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(id=7, project_id=1)
    service = StatisticsService(dao=dao, workbench_dao=workbench_dao)

    response = asyncio.run(service.get_area_statistics(AsyncMock(), "RS-2026-045"))

    assert response.total_area_ha == 20
    assert response.total_area_mu == 300
    assert response.average_plot_area_ha == 10
    assert response.farmland_area_ha == 12
    assert response.crop_assignment_rate == 100
    assert response.by_district[0].code == "230109"
    assert response.by_land_class[0].percentage == 60
    assert response.annual_trend[-1].year_over_year == 11.11
    assert dao.get_totals.await_args.args[1] == 7


def test_disaster_summary_builds_area_groups_and_geojson() -> None:
    """验证灾害斑块可汇总受灾面积并生成专题 GeoJSON。"""
    dao = AsyncMock()
    dao.get_patches.return_value = [
        (
            SimpleNamespace(
                patch_code="DS-001",
                disaster_type="洪涝",
                severity="重度",
                affected_area_ha=Decimal("4.2000"),
                crop_type="水稻",
                detected_at=date(2026, 6, 22),
                ndvi_change=Decimal("-0.310"),
                status="pending",
                source="测试模型",
                reviewed_by=None,
                reviewed_by_code=None,
                reviewed_by_role=None,
                review_comment=None,
                reviewed_at=None,
            ),
            '{"type":"Polygon","coordinates":[[[126,45],[127,45],[127,46],[126,45]]]}',
        ),
        (
            SimpleNamespace(
                patch_code="DS-002",
                disaster_type="干旱",
                severity="中度",
                affected_area_ha=Decimal("2.8000"),
                crop_type="玉米",
                detected_at=date(2026, 6, 24),
                ndvi_change=Decimal("-0.180"),
                status="confirmed",
                source="测试模型",
                reviewed_by="王海峰",
                reviewed_by_code="quality-wang-haifeng",
                reviewed_by_role="quality_inspector",
                review_comment="确认旱情等级",
                reviewed_at=datetime(2026, 7, 21, tzinfo=UTC),
            ),
            '{"type":"Polygon","coordinates":[[[126,45],[127,45],[127,46],[126,45]]]}',
        ),
    ]
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(id=1)
    service = DisasterService(dao=dao, workbench_dao=workbench_dao)

    response = asyncio.run(service.get_summary(AsyncMock(), "RS-2026-045"))

    assert response.total_patches == 2
    assert response.affected_area_ha == 7
    assert response.pending_count == 1
    assert response.by_severity[0].label == "重度"
    assert len(response.feature_collection["features"]) == 2


def test_disaster_update_rejects_unknown_severity() -> None:
    """验证灾害人工修正仅接受业务定义的等级。"""
    with pytest.raises(ValidationError):
        DisasterPatchUpdateRequest(
            severity="灾难级",
            status="confirmed",
            reviewer_code="quality-wang-haifeng",
        )


def test_imagery_processing_does_not_count_missing_artifacts() -> None:
    """验证数据库完成状态没有实体产物时不得计入完成率。"""
    dao = AsyncMock()
    dao.get_asset_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=7,
        asset_code="GF2-TEST",
        asset_name="GF2 测试影像",
        sensor_type="高分二号 PMS1",
        acquired_at=datetime(2026, 6, 18, tzinfo=UTC),
        cloud_cover=Decimal("2.30"),
        resolution_m=Decimal("0.80"),
        processing_level="L2A",
    )
    dao.get_steps.return_value = [
        SimpleNamespace(
            step_code="radiometric",
            step_name="辐射定标",
            sequence=1,
            status="completed",
            progress=100,
            parameters={"method": "absolute"},
            output_uri="/output/radiometric.tif",
            started_at=datetime(2026, 7, 20, tzinfo=UTC),
            completed_at=datetime(2026, 7, 20, 1, tzinfo=UTC),
        ),
        SimpleNamespace(
            step_code="clip",
            step_name="行政区裁剪",
            sequence=2,
            status="running",
            progress=60,
            parameters={"boundary": "松北区"},
            output_uri=None,
            started_at=datetime(2026, 7, 21, tzinfo=UTC),
            completed_at=None,
        ),
    ]
    service = ImageryService(dao=dao, workbench_dao=AsyncMock())

    response = asyncio.run(service.get_processing(AsyncMock(), "GF2-TEST"))

    assert response.completion_rate == 0
    assert response.completed_steps == 0
    assert response.total_steps == 2
    assert response.resolution_m == 0.8
    assert response.steps[0].status == "artifact_missing"
    assert response.steps[0].output_verified is False
    assert response.steps[0].artifact_error == "尚未登记实体产物"


def test_imagery_step_registers_verified_physical_artifact(tmp_path: Path) -> None:
    """验证实体文件存在时登记大小、SHA256 和处理器证据。"""
    storage_path = tmp_path / "GF2-TEST"
    storage_path.mkdir()
    artifact_path = storage_path / "radiometric-result.tif"
    artifact_path.write_bytes(b"II*\x00" + b"real-raster-artifact-evidence")
    asset = SimpleNamespace(
        id=1,
        project_id=7,
        asset_code="GF2-TEST",
        asset_name="GF2 测试影像",
        sensor_type="高分二号 PMS1",
        acquired_at=datetime(2026, 6, 18, tzinfo=UTC),
        cloud_cover=Decimal("2.30"),
        resolution_m=Decimal("0.80"),
        processing_level="L2A",
        calibration_status="pending",
        correction_status="pending",
    )
    step = SimpleNamespace(
        step_code="radiometric",
        step_name="辐射定标",
        sequence=1,
        status="pending",
        progress=0,
        parameters={"method": "absolute"},
        output_uri=None,
        started_at=None,
        completed_at=None,
        updated_at=None,
    )
    dao = AsyncMock()
    dao.get_asset_by_code_for_update.return_value = asset
    dao.get_asset_by_code.return_value = asset
    dao.get_step_for_update.return_value = step
    dao.get_steps.return_value = [step]
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
        service.run_step(
            db,
            "GF2-TEST",
            "radiometric",
            "RS-2026-045",
            ImageryStepRunRequest(
                operator_code="interp-li-jing",
                output_relative_path="GF2-TEST/radiometric-result.tif",
                processor_name="6S 批处理工具",
                processor_version="2.1",
                comment="定标参数复核完成",
            ),
        )
    )

    assert response.completion_rate == 100
    assert response.completed_steps == 1
    assert response.steps[0].output_verified is True
    assert response.steps[0].output_size_bytes == artifact_path.stat().st_size
    assert len(response.steps[0].output_checksum_sha256 or "") == 64
    assert response.steps[0].processor_name == "6S 批处理工具"
    assert asset.calibration_status == "completed"
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()
