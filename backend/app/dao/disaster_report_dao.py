"""灾害监测专题报告数据访问层。"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.disaster_report import DisasterReport


class DisasterReportDAO:
    """封装灾害专题报告查询、写入和替代操作。"""

    async def list_reports(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> list[DisasterReport]:
        """查询任务全部灾害专题报告。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            list[DisasterReport]: 按生成时间倒序排列的报告。
        """
        result = await db.execute(
            select(DisasterReport)
            .where(DisasterReport.task_id == task_id)
            .order_by(DisasterReport.generated_at.desc())
        )
        return list(result.scalars().all())

    async def get_report_by_code(
        self,
        db: AsyncSession,
        report_code: str,
    ) -> DisasterReport | None:
        """按业务编号查询灾害专题报告。

        Args:
            db: 异步数据库会话。
            report_code: 报告业务编号。

        Returns:
            DisasterReport | None: 报告或 None。
        """
        result = await db.execute(
            select(DisasterReport).where(
                DisasterReport.report_code == report_code
            )
        )
        return result.scalar_one_or_none()

    async def add_report(
        self,
        db: AsyncSession,
        report: DisasterReport,
    ) -> DisasterReport:
        """新增灾害专题报告记录。

        Args:
            db: 异步数据库会话。
            report: 待保存报告。

        Returns:
            DisasterReport: 已刷新报告。
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
        """把任务已有当前报告标记为被替代。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            int: 被替代报告数量。
        """
        result = await db.execute(
            update(DisasterReport)
            .where(
                DisasterReport.task_id == task_id,
                DisasterReport.status == "completed",
            )
            .values(status="superseded")
        )
        return int(result.rowcount or 0)
