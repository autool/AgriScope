"""项目级业务规则配置数据访问对象。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workbench import ProjectRuleConfig, ProjectRuleConfigAudit


class RuleConfigDAO:
    """封装项目规则配置和修改审计持久化。"""

    async def get_by_project_id(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> ProjectRuleConfig | None:
        """按项目主键查询规则配置。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            ProjectRuleConfig | None: 已保存配置，不存在时返回 None。
        """
        result = await db.execute(
            select(ProjectRuleConfig).where(
                ProjectRuleConfig.project_id == project_id
            )
        )
        return result.scalar_one_or_none()

    async def add_config(
        self,
        db: AsyncSession,
        config: ProjectRuleConfig,
    ) -> ProjectRuleConfig:
        """新增项目规则配置。

        Args:
            db: 异步数据库会话。
            config: 待保存配置。

        Returns:
            ProjectRuleConfig: 已加入会话的配置。
        """
        db.add(config)
        await db.flush()
        return config

    async def get_by_project_id_for_update(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> ProjectRuleConfig | None:
        """锁定并查询待修改的项目规则配置。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            ProjectRuleConfig | None: 已锁定配置；不存在时返回 None。
        """
        result = await db.execute(
            select(ProjectRuleConfig)
            .where(ProjectRuleConfig.project_id == project_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def add_audit(
        self,
        db: AsyncSession,
        audit: ProjectRuleConfigAudit,
    ) -> ProjectRuleConfigAudit:
        """写入项目规则配置修改审计。

        Args:
            db: 异步数据库会话。
            audit: 修改前后值和操作人。

        Returns:
            ProjectRuleConfigAudit: 已写入审计记录。
        """
        db.add(audit)
        await db.flush()
        return audit
