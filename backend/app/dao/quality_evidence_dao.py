"""项目任务当前质量证据统一失效数据访问。"""

from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workbench import (
    MonitoringTask,
    PlotQualityCheck,
    QualityIssue,
    ReviewRecord,
)


class QualityEvidenceDAO:
    """统一清理派生检查、关闭旧自动问题并写入重检审计。"""

    async def invalidate_project_quality_evidence(
        self,
        db: AsyncSession,
        project_id: int,
        *,
        reason: str,
        operator: str,
        operator_code: str,
        operator_role: str,
    ) -> int:
        """使项目全部任务当前质量证据失效并保留历史账本。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            reason: 触发重检的可审计业务原因。
            operator: 触发变更的用户显示名。
            operator_code: 稳定用户编码。
            operator_role: 执行时角色快照。

        Returns:
            int: 被重开并要求重新质检的任务数量。
        """
        task_ids = list(
            (
                await db.execute(
                    select(MonitoringTask.id)
                    .where(MonitoringTask.project_id == project_id)
                    .order_by(MonitoringTask.id)
                )
            )
            .scalars()
            .all()
        )
        if not task_ids:
            return 0
        invalidated_at = datetime.now(UTC)
        normalized_reason = reason.strip()[:1000]
        await db.execute(
            delete(PlotQualityCheck).where(PlotQualityCheck.task_id.in_(task_ids))
        )
        await db.execute(
            update(QualityIssue)
            .where(
                QualityIssue.task_id.in_(task_ids),
                QualityIssue.source == "auto",
                QualityIssue.issue_type == "quality_rule",
                QualityIssue.status == "open",
            )
            .values(
                status="resolved",
                resolved_at=invalidated_at,
                resolved_by=operator,
                resolved_by_code=operator_code,
                resolved_by_role=operator_role,
                resolution_comment=normalized_reason,
            )
        )
        await db.execute(
            update(MonitoringTask)
            .where(MonitoringTask.id.in_(task_ids))
            .values(
                status="interpreting",
                quality_score=None,
                updated_at=invalidated_at,
            )
        )
        db.add_all(
            [
                ReviewRecord(
                    task_id=task_id,
                    review_level="quality",
                    action="quality_evidence_invalidated",
                    reviewer=operator,
                    reviewer_code=operator_code,
                    reviewer_role=operator_role,
                    comment=normalized_reason,
                    created_at=invalidated_at,
                )
                for task_id in task_ids
            ]
        )
        await db.flush()
        return len(task_ids)
