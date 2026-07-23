"""项目级图斑自定义属性字段业务测试。"""

import asyncio
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openpyxl import load_workbook

from app.core.exceptions import ValidationException
from app.models.plot_attribute_field import ProjectPlotAttributeField
from app.schemas.plot_attribute_field import (
    PlotAttributeFieldCreateRequest,
    PlotAttributeFieldUpdateRequest,
)
from app.services.plot_attribute_field_service import PlotAttributeFieldService
from app.services.plot_attribute_workbook_parser import (
    SCHEMA_SHEET_NAME,
    PlotAttributeWorkbookParser,
)


def build_field(
    field_code: str,
    *,
    field_type: str = "text",
    required: bool = False,
    options: list[str] | None = None,
    status: str = "active",
    version: int = 1,
) -> ProjectPlotAttributeField:
    """构造带稳定审计信息的字段定义。

    Args:
        field_code: 稳定字段编码。
        field_type: 字段类型。
        required: 是否必填。
        options: 单选项。
        status: 启停状态。
        version: 定义版本。

    Returns:
        ProjectPlotAttributeField: 可用于服务测试的 ORM 对象。
    """
    now = datetime(2026, 7, 23, tzinfo=UTC)
    return ProjectPlotAttributeField(
        id=8,
        project_id=3,
        field_code=field_code,
        label="业务字段",
        field_type=field_type,
        required=required,
        options=options or [],
        display_order=10,
        status=status,
        version=version,
        created_by="赵志远",
        created_by_code="manager-zhao-zhiyuan",
        created_by_role="project_manager",
        updated_by="赵志远",
        updated_by_code="manager-zhao-zhiyuan",
        updated_by_role="project_manager",
        created_at=now,
        updated_at=now,
    )


def build_user_service() -> AsyncMock:
    """构造具备字段管理能力的稳定项目用户服务。

    Returns:
        AsyncMock: 权限校验替身。
    """
    service = AsyncMock()
    service.require_capability.return_value = SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )
    return service


def test_custom_attribute_validation_preserves_inactive_values() -> None:
    """验证停用字段历史值保留且不能由客户端继续编辑。"""
    active = build_field("soil_grade", required=True)
    inactive = build_field("legacy_code", status="inactive")

    values = PlotAttributeFieldService.validate_custom_attributes(
        [active, inactive],
        {"soil_grade": "  一级  "},
        existing={"legacy_code": "OLD-001"},
    )

    assert values == {"legacy_code": "OLD-001", "soil_grade": "一级"}
    with pytest.raises(ValidationException, match="未定义或已停用"):
        PlotAttributeFieldService.validate_custom_attributes(
            [active, inactive],
            {"soil_grade": "一级", "legacy_code": "NEW-001"},
            existing={"legacy_code": "OLD-001"},
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (build_field("sample_no", field_type="number"), True, "必须填写数值"),
        (build_field("survey_date", field_type="date"), "2026/07/23", "YYYY-MM-DD"),
        (build_field("verified", field_type="boolean"), "是", "必须填写是或否"),
        (
            build_field(
                "soil_type",
                field_type="single_select",
                options=["黑土", "白浆土"],
            ),
            "草甸土",
            "不在当前选项范围内",
        ),
    ],
)
def test_custom_attribute_type_validation(
    field: ProjectPlotAttributeField,
    value: object,
    message: str,
) -> None:
    """验证不同字段类型拒绝不兼容 JSON 值。"""
    with pytest.raises(ValidationException, match=message):
        PlotAttributeFieldService.validate_custom_attributes(
            [field],
            {field.field_code: value},
        )


def test_reactivating_field_revalidates_historical_values() -> None:
    """验证停用期间改变类型后重新启用仍会检查存量值。"""
    field = build_field("legacy_code", field_type="number", status="inactive")
    dao = AsyncMock()
    dao.get_project_by_code.return_value = SimpleNamespace(id=3)
    dao.get_field_for_update.return_value = field
    dao.active_field_count.return_value = 2
    dao.list_existing_values.return_value = ["OLD-001"]
    service = PlotAttributeFieldService(
        dao=dao,
        user_service=build_user_service(),
    )

    with pytest.raises(ValidationException, match="必须填写数值"):
        asyncio.run(
            service.update_field(
                AsyncMock(),
                "RS-2026",
                field.field_code,
                PlotAttributeFieldUpdateRequest(
                    status="active",
                    operator_code="manager-zhao-zhiyuan",
                ),
            )
        )

    dao.add_audit.assert_not_awaited()


def test_create_field_versions_audit_and_invalidates_quality() -> None:
    """验证创建字段固化版本、稳定角色审计并重开质量门禁。"""
    dao = AsyncMock()
    dao.get_project_by_code.return_value = SimpleNamespace(id=3)
    dao.field_code_exists.return_value = False
    dao.active_field_count.return_value = 4

    async def add_field(_db: object, field: ProjectPlotAttributeField) -> object:
        field.id = 12
        return field

    dao.add_field.side_effect = add_field
    quality_evidence_dao = AsyncMock()
    service = PlotAttributeFieldService(
        dao=dao,
        user_service=build_user_service(),
        quality_evidence_dao=quality_evidence_dao,
    )
    db = AsyncMock()

    response = asyncio.run(
        service.create_field(
            db,
            "RS-2026",
            PlotAttributeFieldCreateRequest(
                field_code="soil_type",
                label="土壤类型",
                field_type="single_select",
                required=True,
                options=["黑土", "白浆土"],
                display_order=20,
                operator_code="manager-zhao-zhiyuan",
            ),
        )
    )

    audit = dao.add_audit.await_args.args[1]
    assert response.version == 1
    assert response.created_by_code == "manager-zhao-zhiyuan"
    assert audit.action == "created"
    assert audit.new_values["field_code"] == "soil_type"
    assert audit.operator_role == "project_manager"
    quality_evidence_dao.invalidate_project_quality_evidence.assert_awaited_once()
    invalidation = (
        quality_evidence_dao.invalidate_project_quality_evidence.await_args
    )
    assert invalidation.args == (db, 3)
    assert invalidation.kwargs["operator_code"] == "manager-zhao-zhiyuan"
    assert "soil_type" in invalidation.kwargs["reason"]
    db.commit.assert_awaited_once()


def test_dynamic_workbook_uses_named_range_and_rejects_stale_schema() -> None:
    """验证长单选项不受 Excel 255 字符限制且旧模式工作簿被拒绝。"""
    options = [f"选项-{index}-" + "甲" * 60 for index in range(5)]
    snapshot = [
        {
            "field_code": "soil_type",
            "label": "土壤类型",
            "field_type": "single_select",
            "required": True,
            "options": options,
            "display_order": 10,
            "version": 3,
        }
    ]
    plot = SimpleNamespace(
        plot_code="PLOT-001",
        version=7,
        owner_village="幸福村",
        land_class="耕地",
        crop_type="玉米",
        planting_mode="单季种植",
        irrigation_condition="良好",
        custom_attributes={"soil_type": options[2]},
    )
    content = PlotAttributeWorkbookParser.build_export([plot], snapshot)

    workbook = load_workbook(BytesIO(content), data_only=False)
    try:
        validation = next(iter(workbook["地块属性"].data_validations.dataValidation))
        custom_validation = next(
            item
            for item in workbook["地块属性"].data_validations.dataValidation
            if "H2" in str(item.sqref)
        )
        assert validation.type == "list"
        assert custom_validation.formula1 == "custom_options_8"
        assert workbook.defined_names["custom_options_8"].attr_text.startswith(
            f"'{SCHEMA_SHEET_NAME}'!$D$2:"
        )
        assert workbook[SCHEMA_SHEET_NAME].sheet_state == "veryHidden"
    finally:
        workbook.close()

    parsed = PlotAttributeWorkbookParser().parse(
        "plot-attributes.xlsx",
        content,
        expected_snapshot=snapshot,
        expected_digest=PlotAttributeWorkbookParser.schema_digest(snapshot),
    )
    assert parsed[0].custom_attributes == {"soil_type": options[2]}

    stale_snapshot = [{**snapshot[0], "version": 4}]
    with pytest.raises(ValidationException, match="字段定义已变化"):
        PlotAttributeWorkbookParser().parse(
            "plot-attributes.xlsx",
            content,
            expected_snapshot=stale_snapshot,
            expected_digest=PlotAttributeWorkbookParser.schema_digest(
                stale_snapshot
            ),
        )
