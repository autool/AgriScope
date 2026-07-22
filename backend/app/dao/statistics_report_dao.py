"""面积统计正式报告包数据访问对象。"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.statistics_report import StatisticsReport
from app.models.workbench import AreaStatisticsSnapshot


class StatisticsReportDAO:
    """封装统计报告版本、来源快照和状态变更。"""

    async def list_reports(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[StatisticsReport]:
        """查询任务全部统计报告版本。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[StatisticsReport]: 按版本倒序排列的报告。
        """
        result = await db.execute(
            select(StatisticsReport)
            .where(StatisticsReport.task_id == task_id)
            .order_by(StatisticsReport.version.desc())
        )
        return result.scalars().all()

    async def get_report_by_code(
        self,
        db: AsyncSession,
        report_code: str,
    ) -> StatisticsReport | None:
        """按业务编号查询统计报告。

        Args:
            db: 异步数据库会话。
            report_code: 报告业务编号。

        Returns:
            StatisticsReport | None: 报告实体，不存在时为空。
        """
        result = await db.execute(
            select(StatisticsReport).where(
                StatisticsReport.report_code == report_code
            )
        )
        return result.scalar_one_or_none()

    async def get_next_version(self, db: AsyncSession, task_id: int) -> int:
        """计算任务下一统计报告版本号。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            int: 从 1 开始递增的版本号。
        """
        result = await db.execute(
            select(func.coalesce(func.max(StatisticsReport.version), 0)).where(
                StatisticsReport.task_id == task_id
            )
        )
        return int(result.scalar_one()) + 1

    async def get_history_state(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> tuple[int, datetime | None]:
        """查询历史年度统计当前数量和最近更新时间。

        Args:
            db: 异步数据库会话。
            project_id: 监测项目主键。

        Returns:
            tuple[int, datetime | None]: 快照数量与最近更新时间。
        """
        result = await db.execute(
            select(
                func.count(AreaStatisticsSnapshot.id),
                func.max(AreaStatisticsSnapshot.updated_at),
            ).where(AreaStatisticsSnapshot.project_id == project_id)
        )
        count, latest_at = result.one()
        return int(count or 0), latest_at

    async def add_report(
        self,
        db: AsyncSession,
        report: StatisticsReport,
    ) -> StatisticsReport:
        """新增统计报告实体。

        Args:
            db: 异步数据库会话。
            report: 待写入报告模型。

        Returns:
            StatisticsReport: 已刷新主键的报告。
        """
        db.add(report)
        await db.flush()
        await db.refresh(report)
        return report

    async def supersede_completed_reports(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> int:
        """将任务已有当前报告标记为历史版本。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            int: 被替代报告数量。
        """
        result = await db.execute(
            update(StatisticsReport)
            .where(
                StatisticsReport.task_id == task_id,
                StatisticsReport.status == "completed",
            )
            .values(status="superseded")
        )
        return int(result.rowcount or 0)

    async def mark_invalid(
        self,
        db: AsyncSession,
        report_id: int,
    ) -> None:
        """把实体损坏的报告持久化标记为无效。

        Args:
            db: 异步数据库会话。
            report_id: 报告主键。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            update(StatisticsReport)
            .where(StatisticsReport.id == report_id)
            .values(status="invalid")
        )
