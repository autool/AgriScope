"""项目级地块自定义属性字段数据访问。"""

from collections.abc import Sequence

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plot_attribute_field import (
    ProjectPlotAttributeField,
    ProjectPlotAttributeFieldAudit,
)
from app.models.workbench import MonitoringProject


class PlotAttributeFieldDAO:
    """封装项目字段定义、审计和存量值查询。"""

    async def get_project_by_code(
        self,
        db: AsyncSession,
        project_code: str,
    ) -> MonitoringProject | None:
        """按项目编号查询项目。

        Args:
            db: 异步数据库会话。
            project_code: 项目业务编号。

        Returns:
            MonitoringProject | None: 项目或空值。
        """
        result = await db.execute(
            select(MonitoringProject).where(
                MonitoringProject.project_code == project_code
            )
        )
        return result.scalar_one_or_none()

    async def list_fields(
        self,
        db: AsyncSession,
        project_id: int,
        *,
        include_inactive: bool = False,
    ) -> Sequence[ProjectPlotAttributeField]:
        """查询项目字段定义。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            include_inactive: 是否包含已停用字段。

        Returns:
            Sequence[ProjectPlotAttributeField]: 排序后的字段定义。
        """
        statement = select(ProjectPlotAttributeField).where(
            ProjectPlotAttributeField.project_id == project_id
        )
        if not include_inactive:
            statement = statement.where(ProjectPlotAttributeField.status == "active")
        result = await db.execute(
            statement.order_by(
                ProjectPlotAttributeField.display_order,
                ProjectPlotAttributeField.id,
            )
        )
        return result.scalars().all()

    async def get_field_for_update(
        self,
        db: AsyncSession,
        project_id: int,
        field_code: str,
    ) -> ProjectPlotAttributeField | None:
        """锁定一个项目字段定义。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            field_code: 稳定字段编码。

        Returns:
            ProjectPlotAttributeField | None: 已锁定字段或空值。
        """
        result = await db.execute(
            select(ProjectPlotAttributeField)
            .where(
                ProjectPlotAttributeField.project_id == project_id,
                ProjectPlotAttributeField.field_code == field_code,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def field_code_exists(
        self,
        db: AsyncSession,
        project_id: int,
        field_code: str,
    ) -> bool:
        """判断项目字段编码是否已存在。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            field_code: 待检查字段编码。

        Returns:
            bool: 已存在时为 True。
        """
        result = await db.execute(
            select(ProjectPlotAttributeField.id).where(
                ProjectPlotAttributeField.project_id == project_id,
                ProjectPlotAttributeField.field_code == field_code,
            )
        )
        return result.scalar_one_or_none() is not None

    async def active_field_count(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> int:
        """统计项目活动字段数量。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            int: 活动字段数量。
        """
        result = await db.execute(
            select(func.count(ProjectPlotAttributeField.id)).where(
                ProjectPlotAttributeField.project_id == project_id,
                ProjectPlotAttributeField.status == "active",
            )
        )
        return int(result.scalar_one())

    async def add_field(
        self,
        db: AsyncSession,
        field: ProjectPlotAttributeField,
    ) -> ProjectPlotAttributeField:
        """写入字段定义。

        Args:
            db: 异步数据库会话。
            field: 待写入字段。

        Returns:
            ProjectPlotAttributeField: 已分配主键的字段。
        """
        db.add(field)
        await db.flush()
        await db.refresh(field)
        return field

    async def add_audit(
        self,
        db: AsyncSession,
        audit: ProjectPlotAttributeFieldAudit,
    ) -> None:
        """写入不可变字段定义审计。

        Args:
            db: 异步数据库会话。
            audit: 待写入审计。

        Returns:
            None: 无返回值。
        """
        db.add(audit)
        await db.flush()

    async def list_existing_values(
        self,
        db: AsyncSession,
        project_id: int,
        field_code: str,
    ) -> list[object]:
        """查询项目任务图斑内某字段的不同非空 JSON 值。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            field_code: 字段编码。

        Returns:
            list[object]: 最多 101 个不同非空值。
        """
        result = await db.execute(
            text(
                """
                SELECT DISTINCT plot.custom_attributes -> :field_code AS value
                FROM farmland_plots AS plot
                JOIN task_plots AS task_plot
                  ON task_plot.plot_code = plot.plot_code
                JOIN monitoring_tasks AS task
                  ON task.id = task_plot.task_id
                WHERE task.project_id = :project_id
                  AND plot.custom_attributes -> :field_code IS NOT NULL
                  AND plot.custom_attributes -> :field_code <> 'null'::jsonb
                LIMIT 101
                """
            ),
            {"project_id": project_id, "field_code": field_code},
        )
        return [row.value for row in result]
