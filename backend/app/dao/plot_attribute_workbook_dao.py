"""地块属性 Excel 导入批次数据访问。"""

from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plot_attribute_workbook import PlotAttributeImportBatch
from app.models.workbench import PlotQualityCheck, QualityIssue


class PlotAttributeWorkbookDAO:
    """封装属性工作簿批次、质量门禁重置的数据访问。"""

    async def add_batch(
        self,
        db: AsyncSession,
        batch: PlotAttributeImportBatch,
    ) -> PlotAttributeImportBatch:
        """写入不可变导入批次。

        Args:
            db: 异步数据库会话。
            batch: 待持久化导入批次。

        Returns:
            PlotAttributeImportBatch: 已分配主键的导入批次。
        """
        db.add(batch)
        await db.flush()
        await db.refresh(batch)
        return batch

    async def list_batches(
        self,
        db: AsyncSession,
        task_id: int,
        limit: int = 20,
    ) -> Sequence[PlotAttributeImportBatch]:
        """查询任务最近的地块属性导入批次。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            limit: 最大返回数量。

        Returns:
            Sequence[PlotAttributeImportBatch]: 按导入时间倒序的批次。
        """
        result = await db.execute(
            select(PlotAttributeImportBatch)
            .where(PlotAttributeImportBatch.task_id == task_id)
            .order_by(
                PlotAttributeImportBatch.imported_at.desc(),
                PlotAttributeImportBatch.id.desc(),
            )
            .limit(limit)
        )
        return result.scalars().all()

    async def list_all_batches(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[PlotAttributeImportBatch]:
        """查询任务全部地块属性工作簿导入批次用于成果归档。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[PlotAttributeImportBatch]: 按导入时间正序的完整批次。
        """
        result = await db.execute(
            select(PlotAttributeImportBatch)
            .where(PlotAttributeImportBatch.task_id == task_id)
            .order_by(
                PlotAttributeImportBatch.imported_at,
                PlotAttributeImportBatch.id,
            )
        )
        return result.scalars().all()

    async def reset_quality_evidence(
        self,
        db: AsyncSession,
        task_id: int,
        plot_codes: list[str],
    ) -> None:
        """批量清除旧版本检查并关闭旧自动规则问题。

        仅处理本次实际变化图斑的派生质量证据；人工审核问题和外业问题保留。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            plot_codes: 本次产生新版本的图斑编号。

        Returns:
            None: 无返回值。
        """
        if not plot_codes:
            return
        await db.execute(
            delete(PlotQualityCheck).where(
                PlotQualityCheck.task_id == task_id,
                PlotQualityCheck.plot_code.in_(plot_codes),
            )
        )
        await db.execute(
            update(QualityIssue)
            .where(
                QualityIssue.task_id == task_id,
                QualityIssue.plot_code.in_(plot_codes),
                QualityIssue.source == "auto",
                QualityIssue.issue_type == "quality_rule",
                QualityIssue.status == "open",
            )
            .values(status="resolved", resolved_at=func.now())
        )
