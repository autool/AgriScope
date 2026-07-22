"""项目用户与角色数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workbench import MonitoringProject, ProjectUser


class ProjectUserDAO:
    """封装项目成员、角色和启用状态查询。"""

    async def get_project_by_code(
        self,
        db: AsyncSession,
        project_code: str,
    ) -> MonitoringProject | None:
        """按项目编号查询项目。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。

        Returns:
            MonitoringProject | None: 项目对象；不存在时返回 None。
        """
        result = await db.execute(
            select(MonitoringProject).where(
                MonitoringProject.project_code == project_code
            )
        )
        return result.scalar_one_or_none()

    async def get_active_user(
        self,
        db: AsyncSession,
        project_id: int,
        user_code: str,
    ) -> ProjectUser | None:
        """查询项目内启用的指定用户。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            user_code: 稳定用户编码。

        Returns:
            ProjectUser | None: 启用用户；不存在或停用时返回 None。
        """
        result = await db.execute(
            select(ProjectUser).where(
                ProjectUser.project_id == project_id,
                ProjectUser.user_code == user_code,
                ProjectUser.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def list_active_users(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[ProjectUser]:
        """查询项目当前启用成员。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[ProjectUser]: 默认身份优先的项目成员列表。
        """
        result = await db.execute(
            select(ProjectUser)
            .where(
                ProjectUser.project_id == project_id,
                ProjectUser.status == "active",
            )
            .order_by(
                ProjectUser.is_default.desc(),
                ProjectUser.id.asc(),
            )
        )
        return result.scalars().all()
