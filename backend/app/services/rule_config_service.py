"""项目级质量和内外业校核规则配置业务服务。"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.rule_defaults import (
    DEFAULT_BOUNDARY_AGREEMENT_RATE_MIN,
    DEFAULT_COMPLETENESS_RATE_MIN,
    DEFAULT_CONSTRUCTION_MIN_AREA_SQM,
    DEFAULT_FIELD_OFFSET_THRESHOLD_M,
    DEFAULT_FIELD_SEARCH_RADIUS_M,
    DEFAULT_KEY_FIELD_ACCURACY_MIN,
    DEFAULT_LAND_CLASS_ACCURACY_MIN,
    DEFAULT_MAX_CAPTURE_IMAGE_DAYS,
    DEFAULT_MAX_CLOUD_COVER_PERCENT,
    DEFAULT_OTHER_AGRICULTURAL_MIN_AREA_SQM,
    DEFAULT_OUTPUT_CRS,
    DEFAULT_OUTPUT_PROJECTION,
    DEFAULT_POSITIONAL_ACCURACY_PIXELS,
    DEFAULT_RULE_OPERATOR,
)
from app.dao.rule_config_dao import RuleConfigDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.workbench import ProjectRuleConfig, ProjectRuleConfigAudit
from app.schemas.rule_config import RuleConfigResponse, RuleConfigUpdateRequest
from app.services.project_user_service import ProjectUserService


class RuleConfigService:
    """管理项目规则默认值、持久化配置和修改审计。"""

    def __init__(
        self,
        dao: RuleConfigDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
    ) -> None:
        """初始化项目规则配置服务。

        Args:
            dao: 规则配置 DAO。
            workbench_dao: 项目查询 DAO。
            project_user_service: 项目用户与角色校验服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or RuleConfigDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()

    async def ensure_for_project(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> ProjectRuleConfig:
        """查询项目配置，不存在时写入受控默认值。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            ProjectRuleConfig: 当前项目生效配置。
        """
        config = await self.dao.get_by_project_id(db, project_id)
        if config is not None:
            return config
        return await self.dao.add_config(
            db,
            ProjectRuleConfig(
                project_id=project_id,
                field_offset_threshold_m=DEFAULT_FIELD_OFFSET_THRESHOLD_M,
                field_search_radius_m=DEFAULT_FIELD_SEARCH_RADIUS_M,
                positional_accuracy_pixels=DEFAULT_POSITIONAL_ACCURACY_PIXELS,
                max_capture_image_days=DEFAULT_MAX_CAPTURE_IMAGE_DAYS,
                construction_min_area_sqm=DEFAULT_CONSTRUCTION_MIN_AREA_SQM,
                other_agricultural_min_area_sqm=(
                    DEFAULT_OTHER_AGRICULTURAL_MIN_AREA_SQM
                ),
                completeness_rate_min=DEFAULT_COMPLETENESS_RATE_MIN,
                boundary_agreement_rate_min=DEFAULT_BOUNDARY_AGREEMENT_RATE_MIN,
                land_class_accuracy_min=DEFAULT_LAND_CLASS_ACCURACY_MIN,
                key_field_accuracy_min=DEFAULT_KEY_FIELD_ACCURACY_MIN,
                max_cloud_cover_percent=DEFAULT_MAX_CLOUD_COVER_PERCENT,
                output_crs=DEFAULT_OUTPUT_CRS,
                output_projection=DEFAULT_OUTPUT_PROJECTION,
                version=1,
                updated_by=DEFAULT_RULE_OPERATOR,
                updated_by_code=None,
                updated_by_role=None,
            ),
        )

    @staticmethod
    def _to_response(
        project_code: str,
        config: ProjectRuleConfig,
    ) -> RuleConfigResponse:
        """将 ORM 配置转换为 API 响应。

        Args:
            project_code: 项目编号。
            config: 项目规则 ORM 对象。

        Returns:
            RuleConfigResponse: 当前规则配置响应。
        """
        return RuleConfigResponse(
            project_code=project_code,
            field_offset_threshold_m=float(config.field_offset_threshold_m),
            field_search_radius_m=float(config.field_search_radius_m),
            positional_accuracy_pixels=float(config.positional_accuracy_pixels),
            max_capture_image_days=config.max_capture_image_days,
            construction_min_area_sqm=float(config.construction_min_area_sqm),
            other_agricultural_min_area_sqm=float(
                config.other_agricultural_min_area_sqm
            ),
            completeness_rate_min=float(config.completeness_rate_min),
            boundary_agreement_rate_min=float(config.boundary_agreement_rate_min),
            land_class_accuracy_min=float(config.land_class_accuracy_min),
            key_field_accuracy_min=float(config.key_field_accuracy_min),
            max_cloud_cover_percent=(
                float(config.max_cloud_cover_percent)
                if config.max_cloud_cover_percent is not None
                else None
            ),
            output_crs=config.output_crs,
            output_projection=config.output_projection,
            version=config.version,
            updated_by=config.updated_by,
            updated_by_code=config.updated_by_code,
            updated_by_role=config.updated_by_role,
            updated_at=config.updated_at,
        )

    @staticmethod
    def _audit_values(
        config: ProjectRuleConfig,
    ) -> dict[str, float | int | str | None]:
        """提取适合写入 JSON 审计的规则值。

        Args:
            config: 项目规则 ORM 对象。

        Returns:
            dict[str, float | int]: 不包含 ORM 状态的业务规则值。
        """
        return {
            "field_offset_threshold_m": float(config.field_offset_threshold_m),
            "field_search_radius_m": float(config.field_search_radius_m),
            "positional_accuracy_pixels": float(config.positional_accuracy_pixels),
            "max_capture_image_days": config.max_capture_image_days,
            "construction_min_area_sqm": float(config.construction_min_area_sqm),
            "other_agricultural_min_area_sqm": float(
                config.other_agricultural_min_area_sqm
            ),
            "completeness_rate_min": float(config.completeness_rate_min),
            "boundary_agreement_rate_min": float(
                config.boundary_agreement_rate_min
            ),
            "land_class_accuracy_min": float(config.land_class_accuracy_min),
            "key_field_accuracy_min": float(config.key_field_accuracy_min),
            "max_cloud_cover_percent": (
                float(config.max_cloud_cover_percent)
                if config.max_cloud_cover_percent is not None
                else None
            ),
            "output_crs": config.output_crs,
            "output_projection": config.output_projection,
            "version": config.version,
        }

    async def get_config(
        self,
        db: AsyncSession,
        project_code: str,
    ) -> RuleConfigResponse:
        """查询项目当前生效规则配置。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。

        Returns:
            RuleConfigResponse: 当前生效规则。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        config = await self.ensure_for_project(db, project.id)
        await db.commit()
        await db.refresh(config)
        return self._to_response(project_code, config)

    async def update_config(
        self,
        db: AsyncSession,
        project_code: str,
        request: RuleConfigUpdateRequest,
    ) -> RuleConfigResponse:
        """更新项目规则并写入修改前后值审计。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            request: 新规则和操作人。

        Returns:
            RuleConfigResponse: 更新后的当前规则。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        operator = await self.project_user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_rules",
        )
        config = await self.dao.get_by_project_id_for_update(db, project.id)
        if config is None:
            config = await self.ensure_for_project(db, project.id)
        previous_values = self._audit_values(config)
        config.field_offset_threshold_m = request.field_offset_threshold_m
        config.field_search_radius_m = request.field_search_radius_m
        config.positional_accuracy_pixels = request.positional_accuracy_pixels
        config.max_capture_image_days = request.max_capture_image_days
        config.construction_min_area_sqm = request.construction_min_area_sqm
        config.other_agricultural_min_area_sqm = (
            request.other_agricultural_min_area_sqm
        )
        config.completeness_rate_min = request.completeness_rate_min
        config.boundary_agreement_rate_min = request.boundary_agreement_rate_min
        config.land_class_accuracy_min = request.land_class_accuracy_min
        config.key_field_accuracy_min = request.key_field_accuracy_min
        config.max_cloud_cover_percent = request.max_cloud_cover_percent
        config.output_crs = request.output_crs
        config.output_projection = request.output_projection
        config.version += 1
        config.updated_by = operator.display_name
        config.updated_by_code = operator.user_code
        config.updated_by_role = operator.role_code
        config.updated_at = datetime.now(UTC)
        new_values = self._audit_values(config)
        await self.dao.add_audit(
            db,
            ProjectRuleConfigAudit(
                project_id=project.id,
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
                previous_values=previous_values,
                new_values=new_values,
            ),
        )
        await self.dao.invalidate_project_quality_evidence(db, project.id)
        await db.commit()
        await db.refresh(config)
        return self._to_response(project_code, config)
