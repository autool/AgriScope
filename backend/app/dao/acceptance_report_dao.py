"""成果验收正式报告数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.acceptance_report import AcceptanceReport


class AcceptanceReportDAO:
    """封装验收报告版本和持久化查询。"""

    async def get_reports(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[AcceptanceReport]:
        """查询任务全部验收报告版本。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[AcceptanceReport]: 按版本倒序排列的报告。
        """
        result = await db.execute(
            select(AcceptanceReport)
            .where(AcceptanceReport.task_id == task_id)
            .order_by(AcceptanceReport.version.desc())
        )
        return result.scalars().all()

    async def get_report_by_code(
        self,
        db: AsyncSession,
        report_code: str,
    ) -> AcceptanceReport | None:
        """按业务编号查询验收报告。

        Args:
            db: 异步数据库会话。
            report_code: 验收报告编号。

        Returns:
            AcceptanceReport | None: 报告模型或空。
        """
        result = await db.execute(
            select(AcceptanceReport).where(AcceptanceReport.report_code == report_code)
        )
        return result.scalar_one_or_none()

    async def get_next_version(self, db: AsyncSession, task_id: int) -> int:
        """计算任务下一报告版本号。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            int: 下一版本号。
        """
        result = await db.execute(
            select(func.coalesce(func.max(AcceptanceReport.version), 0)).where(
                AcceptanceReport.task_id == task_id
            )
        )
        return int(result.scalar_one()) + 1

    async def supersede_completed_reports(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> int:
        """将当前完成报告转为历史版本。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            int: 被替代报告数量。
        """
        result = await db.execute(
            update(AcceptanceReport)
            .where(
                AcceptanceReport.task_id == task_id,
                AcceptanceReport.status == "completed",
            )
            .values(status="superseded")
        )
        return int(result.rowcount or 0)

    async def add_report(
        self,
        db: AsyncSession,
        report: AcceptanceReport,
    ) -> AcceptanceReport:
        """新增验收报告实体。

        Args:
            db: 异步数据库会话。
            report: 待持久化报告。

        Returns:
            AcceptanceReport: 已写入会话的报告。
        """
        db.add(report)
        await db.flush()
        return report
