"""项目级地块自定义属性字段业务服务。"""

import json
import math
from datetime import UTC, date, datetime
from hashlib import sha256

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.plot_attribute_field_dao import PlotAttributeFieldDAO
from app.models.plot_attribute_field import (
    ProjectPlotAttributeField,
    ProjectPlotAttributeFieldAudit,
)
from app.schemas.plot_attribute_field import (
    CustomAttributeScalar,
    PlotAttributeFieldCreateRequest,
    PlotAttributeFieldDefinition,
    PlotAttributeFieldListResponse,
    PlotAttributeFieldResponse,
    PlotAttributeFieldUpdateRequest,
)
from app.services.project_user_service import ProjectUserService

MAX_ACTIVE_CUSTOM_FIELDS = 50


class PlotAttributeFieldService:
    """管理项目字段定义、值校验、模式摘要和质量证据失效。"""

    def __init__(
        self,
        dao: PlotAttributeFieldDAO | None = None,
        user_service: ProjectUserService | None = None,
    ) -> None:
        """初始化项目字段服务。

        Args:
            dao: 字段定义 DAO。
            user_service: 稳定项目用户权限服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or PlotAttributeFieldDAO()
        self.user_service = user_service or ProjectUserService()

    @staticmethod
    def definition_snapshot(
        field: ProjectPlotAttributeField,
    ) -> dict[str, object]:
        """构建单个字段的完整审计快照。

        Args:
            field: ORM 字段定义。

        Returns:
            dict[str, object]: 可写入 JSON 审计的字段状态。
        """
        return {
            "field_code": field.field_code,
            "label": field.label,
            "field_type": field.field_type,
            "required": field.required,
            "options": list(field.options or []),
            "display_order": field.display_order,
            "status": field.status,
            "version": field.version,
        }

    @staticmethod
    def build_schema_snapshot(
        fields: list[ProjectPlotAttributeField],
    ) -> list[dict]:
        """构建活动字段的稳定模式快照。

        Args:
            fields: 已按展示顺序排列的活动字段。

        Returns:
            list[dict]: 可固化进 Excel、导入批次和成果清单的快照。
        """
        return [
            PlotAttributeFieldDefinition(
                field_code=field.field_code,
                label=field.label,
                field_type=field.field_type,
                required=field.required,
                options=list(field.options or []),
                display_order=field.display_order,
                version=field.version,
            ).model_dump(mode="json")
            for field in fields
            if field.status == "active"
        ]

    @staticmethod
    def schema_digest(snapshot: list[dict]) -> str:
        """计算字段模式的规范化 SHA-256。

        Args:
            snapshot: 活动字段模式快照。

        Returns:
            str: 64 位十六进制 SHA-256。
        """
        canonical = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(canonical).hexdigest()

    @staticmethod
    def _to_response(
        field: ProjectPlotAttributeField,
    ) -> PlotAttributeFieldResponse:
        """将 ORM 字段转换为 API 响应。

        Args:
            field: ORM 字段定义。

        Returns:
            PlotAttributeFieldResponse: API 字段响应。
        """
        return PlotAttributeFieldResponse(
            field_code=field.field_code,
            label=field.label,
            field_type=field.field_type,
            required=field.required,
            options=list(field.options or []),
            display_order=field.display_order,
            version=field.version,
            status=field.status,
            created_by=field.created_by,
            created_by_code=field.created_by_code,
            created_by_role=field.created_by_role,
            updated_by=field.updated_by,
            updated_by_code=field.updated_by_code,
            updated_by_role=field.updated_by_role,
            created_at=field.created_at,
            updated_at=field.updated_at,
        )

    @staticmethod
    def _normalize_value(
        definition: ProjectPlotAttributeField | PlotAttributeFieldDefinition,
        value: object,
    ) -> CustomAttributeScalar:
        """按字段定义校验并标准化一个 JSON 标量值。

        Args:
            definition: 字段定义。
            value: 待校验原始值。

        Returns:
            CustomAttributeScalar: 标准化标量或空值。
        """
        label = definition.label
        if value is None:
            return None
        if definition.field_type == "text":
            if not isinstance(value, str):
                raise ValidationException(f"自定义字段“{label}”必须填写文本")
            normalized = value.strip()
            if len(normalized) > 500:
                raise ValidationException(f"自定义字段“{label}”不得超过 500 个字符")
            return normalized or None
        if definition.field_type == "number":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValidationException(f"自定义字段“{label}”必须填写数值")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValidationException(f"自定义字段“{label}”必须为有限数值")
            return value
        if definition.field_type == "date":
            if not isinstance(value, str):
                raise ValidationException(f"自定义字段“{label}”必须填写日期")
            try:
                parsed = date.fromisoformat(value.strip())
            except ValueError as exc:
                raise ValidationException(
                    f"自定义字段“{label}”必须使用 YYYY-MM-DD 日期格式"
                ) from exc
            return parsed.isoformat()
        if definition.field_type == "boolean":
            if not isinstance(value, bool):
                raise ValidationException(f"自定义字段“{label}”必须填写是或否")
            return value
        if not isinstance(value, str):
            raise ValidationException(f"自定义字段“{label}”必须选择一个选项")
        normalized = value.strip()
        if normalized not in definition.options:
            raise ValidationException(f"自定义字段“{label}”的值不在当前选项范围内")
        return normalized

    @classmethod
    def validate_custom_attributes(
        cls,
        fields: list[ProjectPlotAttributeField],
        submitted: dict[str, object] | None,
        *,
        existing: dict[str, object] | None = None,
    ) -> dict[str, CustomAttributeScalar]:
        """校验活动字段值并保留不可编辑的停用字段值。

        Args:
            fields: 项目全部字段定义，含停用字段。
            submitted: 客户端提交的活动字段值；空值表示沿用当前值。
            existing: 图斑当前完整自定义属性。

        Returns:
            dict[str, CustomAttributeScalar]: 可安全持久化的完整属性对象。
        """
        active_fields = [field for field in fields if field.status == "active"]
        active_by_code = {field.field_code: field for field in active_fields}
        existing_values = dict(existing or {})
        submitted_values = dict(submitted or {})
        unknown = sorted(set(submitted_values) - set(active_by_code))
        if unknown:
            raise ValidationException(
                "存在未定义或已停用的自定义字段：" + "、".join(unknown[:5])
            )

        result: dict[str, CustomAttributeScalar] = {
            key: value
            for key, value in existing_values.items()
            if key not in active_by_code
            and isinstance(value, str | int | float | bool | type(None))
        }
        for field in active_fields:
            raw_value = (
                submitted_values[field.field_code]
                if field.field_code in submitted_values
                else existing_values.get(field.field_code)
            )
            normalized = cls._normalize_value(field, raw_value)
            if field.required and normalized is None:
                raise ValidationException(f"自定义字段“{field.label}”为必填项")
            result[field.field_code] = normalized
        return result

    async def get_all_fields_by_project_id(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[ProjectPlotAttributeField]:
        """查询项目全部字段定义供业务链路校验。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[ProjectPlotAttributeField]: 包含停用字段的定义。
        """
        return list(
            await self.dao.list_fields(
                db,
                project_id,
                include_inactive=True,
            )
        )

    async def get_active_fields_by_project_id(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[ProjectPlotAttributeField]:
        """查询项目活动字段定义。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[ProjectPlotAttributeField]: 活动字段定义。
        """
        return list(await self.dao.list_fields(db, project_id))

    async def list_fields(
        self,
        db: AsyncSession,
        project_code: str,
        *,
        include_inactive: bool,
    ) -> PlotAttributeFieldListResponse:
        """查询项目字段列表和活动模式摘要。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            include_inactive: 是否展示停用字段。

        Returns:
            PlotAttributeFieldListResponse: 字段列表与模式摘要。
        """
        project = await self.dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        fields = list(
            await self.dao.list_fields(
                db,
                project.id,
                include_inactive=include_inactive,
            )
        )
        active_fields = [field for field in fields if field.status == "active"]
        if include_inactive:
            active_fields = list(await self.dao.list_fields(db, project.id))
        snapshot = self.build_schema_snapshot(active_fields)
        return PlotAttributeFieldListResponse(
            project_code=project_code,
            schema_digest=self.schema_digest(snapshot),
            active_count=len(active_fields),
            items=[self._to_response(field) for field in fields],
        )

    async def create_field(
        self,
        db: AsyncSession,
        project_code: str,
        request: PlotAttributeFieldCreateRequest,
    ) -> PlotAttributeFieldResponse:
        """创建字段定义并失效受影响任务的质量证据。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            request: 字段语义和稳定操作人编码。

        Returns:
            PlotAttributeFieldResponse: 新建字段定义。
        """
        project = await self.dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_plot_attribute_fields",
        )
        if await self.dao.field_code_exists(db, project.id, request.field_code):
            raise ValidationException(f"字段编码 {request.field_code} 已存在")
        if (
            await self.dao.active_field_count(db, project.id)
            >= MAX_ACTIVE_CUSTOM_FIELDS
        ):
            raise ValidationException("每个项目最多启用 50 个自定义地块属性字段")
        now = datetime.now(UTC)
        field = ProjectPlotAttributeField(
            project_id=project.id,
            field_code=request.field_code,
            label=request.label,
            field_type=request.field_type,
            required=request.required,
            options=request.options,
            display_order=request.display_order,
            status="active",
            version=1,
            created_by=operator.display_name,
            created_by_code=operator.user_code,
            created_by_role=operator.role_code,
            updated_by=operator.display_name,
            updated_by_code=operator.user_code,
            updated_by_role=operator.role_code,
            created_at=now,
            updated_at=now,
        )
        await self.dao.add_field(db, field)
        current = self.definition_snapshot(field)
        await self.dao.add_audit(
            db,
            ProjectPlotAttributeFieldAudit(
                project_id=project.id,
                field_id=field.id,
                action="created",
                previous_values={},
                new_values=current,
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
            ),
        )
        await self.dao.invalidate_project_quality_evidence(db, project.id)
        await db.commit()
        await db.refresh(field)
        return self._to_response(field)

    async def update_field(
        self,
        db: AsyncSession,
        project_code: str,
        field_code: str,
        request: PlotAttributeFieldUpdateRequest,
    ) -> PlotAttributeFieldResponse:
        """更新字段语义、版本和审计并失效旧质量证据。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            field_code: 不可变字段编码。
            request: 新字段语义和操作人。

        Returns:
            PlotAttributeFieldResponse: 更新后的字段定义。
        """
        project = await self.dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_plot_attribute_fields",
        )
        field = await self.dao.get_field_for_update(db, project.id, field_code)
        if field is None:
            raise NotFoundException(f"未找到自定义字段 {field_code}")
        previous = self.definition_snapshot(field)
        target_type = request.field_type or field.field_type
        target_options = (
            request.options
            if request.options is not None
            else list(field.options or [])
        )
        target_status = request.status or field.status
        if target_type == "single_select" and not target_options:
            raise ValidationException("单选字段至少配置一个选项")
        if target_type != "single_select" and target_options:
            raise ValidationException("只有单选字段可以配置选项")
        if field.status == "inactive" and target_status == "active":
            if (
                await self.dao.active_field_count(db, project.id)
                >= MAX_ACTIVE_CUSTOM_FIELDS
            ):
                raise ValidationException("每个项目最多启用 50 个自定义地块属性字段")

        probe = PlotAttributeFieldDefinition(
            field_code=field.field_code,
            label=request.label or field.label,
            field_type=target_type,
            required=(
                request.required if request.required is not None else field.required
            ),
            options=target_options,
            display_order=(
                request.display_order
                if request.display_order is not None
                else field.display_order
            ),
            version=field.version + 1,
        )
        if target_status == "active" and (
            field.status != "active"
            or target_type != field.field_type
            or target_options != list(field.options or [])
        ):
            existing_values = await self.dao.list_existing_values(
                db,
                project.id,
                field.field_code,
            )
            for value in existing_values:
                self._normalize_value(probe, value)

        target_snapshot = {
            "field_code": field.field_code,
            "label": probe.label,
            "field_type": probe.field_type,
            "required": probe.required,
            "options": list(probe.options),
            "display_order": probe.display_order,
            "status": target_status,
            "version": field.version,
        }
        if target_snapshot == previous:
            raise ValidationException("字段定义没有发生变化")

        field.label = probe.label
        field.field_type = probe.field_type
        field.required = probe.required
        field.options = probe.options
        field.display_order = probe.display_order
        field.status = target_status
        field.version += 1
        field.updated_by = operator.display_name
        field.updated_by_code = operator.user_code
        field.updated_by_role = operator.role_code
        field.updated_at = datetime.now(UTC)
        current = self.definition_snapshot(field)
        await self.dao.add_audit(
            db,
            ProjectPlotAttributeFieldAudit(
                project_id=project.id,
                field_id=field.id,
                action="updated",
                previous_values=previous,
                new_values=current,
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
            ),
        )
        await self.dao.invalidate_project_quality_evidence(db, project.id)
        await db.commit()
        await db.refresh(field)
        return self._to_response(field)
