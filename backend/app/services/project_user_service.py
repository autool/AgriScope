"""项目用户、角色和业务能力服务。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, PermissionDeniedException
from app.dao.project_user_dao import ProjectUserDAO
from app.models.workbench import ProjectUser
from app.schemas.project_user import (
    ProjectUserListResponse,
    ProjectUserResponse,
)

ROLE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "interpreter": (
        "edit_plots",
        "manage_imagery",
        "process_imagery",
        "import_disaster",
        "run_plot_quality_check",
        "submit_self_check",
        "review_self_check",
    ),
    "field_inspector": ("upload_field_data",),
    "quality_inspector": (
        "run_quality_check",
        "run_plot_quality_check",
        "review_quality",
        "resolve_review_issue",
        "rematch_field_data",
        "resolve_field_issue",
        "review_disaster",
        "rollback_plot",
    ),
    "project_manager": (
        "manage_project",
        "manage_production",
        "manage_datasets",
        "run_change_detection",
        "manage_services",
        "manage_devices",
        "review_model_output",
        "edit_plots",
        "manage_imagery",
        "process_imagery",
        "import_disaster",
        "run_quality_check",
        "run_plot_quality_check",
        "generate_delivery",
        "download_delivery",
        "export_statistics",
        "import_statistics_history",
        "resolve_review_issue",
        "manage_rules",
        "rematch_field_data",
        "resolve_field_issue",
        "review_disaster",
        "rollback_plot",
    ),
    "client_reviewer": (
        "review_client",
        "download_delivery",
        "resolve_review_issue",
    ),
    "independent_supervisor": (
        "supervise_project",
        "view_production",
        "view_datasets",
    ),
}


class ProjectUserService:
    """解析项目身份并执行服务端角色能力校验。"""

    def __init__(self, dao: ProjectUserDAO | None = None) -> None:
        """初始化项目用户服务。

        Args:
            dao: 项目用户 DAO。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ProjectUserDAO()

    @staticmethod
    def get_capabilities(role_code: str) -> list[str]:
        """获取角色对应的业务能力。

        Args:
            role_code: 角色编码。

        Returns:
            list[str]: 角色能力编码列表。
        """
        return list(ROLE_CAPABILITIES.get(role_code, ()))

    def to_response(self, user: ProjectUser) -> ProjectUserResponse:
        """将数据库用户转换为包含能力的响应。

        Args:
            user: 项目成员模型。

        Returns:
            ProjectUserResponse: 可供前端权限控制的用户信息。
        """
        return ProjectUserResponse(
            user_code=user.user_code,
            display_name=user.display_name,
            role_code=user.role_code,
            role_name=user.role_name,
            status=user.status,
            is_default=user.is_default,
            capabilities=self.get_capabilities(user.role_code),
        )

    async def list_project_users(
        self,
        db: AsyncSession,
        project_code: str,
    ) -> ProjectUserListResponse:
        """查询项目启用用户与能力。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。

        Returns:
            ProjectUserListResponse: 项目成员列表。
        """
        project = await self.dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        users = await self.dao.list_active_users(db, project.id)
        return ProjectUserListResponse(
            project_code=project_code,
            users=[self.to_response(user) for user in users],
        )

    async def require_capability(
        self,
        db: AsyncSession,
        project_id: int,
        user_code: str,
        capability: str,
    ) -> ProjectUser:
        """校验项目用户是否具备指定业务能力。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            user_code: 稳定用户编码。
            capability: 目标业务能力编码。

        Returns:
            ProjectUser: 已通过校验的启用项目用户。
        """
        user = await self.dao.get_active_user(db, project_id, user_code)
        if user is None:
            raise PermissionDeniedException("当前用户不属于该项目或账号已停用")
        if capability not in ROLE_CAPABILITIES.get(user.role_code, ()):
            raise PermissionDeniedException(
                f"{user.role_name}无权执行当前业务节点"
            )
        return user
