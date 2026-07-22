"""遥感监测工作台数据访问对象。"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import case, func, or_, select, text, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.plot import FarmlandPlot
from app.models.workbench import (
    DeliveryPackage,
    DisasterPatch,
    FieldVerification,
    ImageryAsset,
    MonitoringProject,
    MonitoringTask,
    PlotEditOperation,
    PlotEditOperationEvent,
    PlotVersion,
    QualityIssue,
    ReviewRecord,
    TaskPlot,
)

REVIEW_CYCLE_RESET_ACTIONS = {
    "plot_source_imported",
    "return",
    "reject",
    "rollback",
    "field_records_imported",
}


@dataclass(frozen=True)
class PlotQualityMetrics:
    """PostGIS 计算得到的单图斑质量指标。"""

    geometry_valid: bool
    ring_closed: bool
    calculated_area_ha: float
    overlap_count: int
    overlap_area_ha: float
    within_district: bool
    has_imagery: bool
    covered_by_imagery: bool
    imagery_resolution_m: float | None


@dataclass(frozen=True)
class SplitPiece:
    """PostGIS 分割生成的单个有效子面。"""

    geometry_json: str
    area_ha: float


@dataclass(frozen=True)
class SplitAnalysis:
    """分割线与源图斑的空间分析结果。"""

    cutter_simple: bool
    source_area_ha: float
    pieces: list[SplitPiece]


@dataclass(frozen=True)
class MergeAnalysis:
    """多个任务图斑的 PostGIS 合并分析结果。"""

    source_count: int
    district_count: int
    geometry_type: str
    component_count: int
    geometry_valid: bool
    source_area_ha: float
    result_area_ha: float
    overlap_area_ha: float
    geometry_json: str


@dataclass(frozen=True)
class QualityGateSummary:
    """任务当前有效图斑的质量门禁汇总。"""

    total_count: int
    checked_count: int
    passing_count: int
    average_score: float | None


@dataclass(frozen=True)
class QualityIssueSummary:
    """任务质量问题队列汇总。"""

    total_count: int
    open_count: int
    resolved_count: int
    high_count: int
    medium_count: int
    low_count: int


@dataclass(frozen=True)
class WorkbenchNavigationCounts:
    """工作台导航所需的实时业务数量。"""

    operational_imagery_count: int
    pending_disaster_count: int
    total_field_verification_count: int
    pending_field_verification_count: int
    current_delivery_package_count: int


class WorkbenchDAO:
    """封装工作台项目、任务、图斑和审核数据访问。"""

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
            MonitoringProject | None: 项目对象，不存在时返回 None。
        """
        result = await db.execute(
            select(MonitoringProject).where(
                MonitoringProject.project_code == project_code
            )
        )
        return result.scalar_one_or_none()

    async def get_task_by_code(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> MonitoringTask | None:
        """按任务编号查询作业任务。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            MonitoringTask | None: 任务对象，不存在时返回 None。
        """
        result = await db.execute(
            select(MonitoringTask).where(MonitoringTask.task_code == task_code)
        )
        return result.scalar_one_or_none()

    async def get_task_by_code_for_update(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> MonitoringTask | None:
        """锁定并查询待执行状态流转的任务。

        Args:
            db: 异步数据库会话。
            task_code: 任务编号。

        Returns:
            MonitoringTask | None: 已加行锁的任务；不存在时返回 None。
        """
        result = await db.execute(
            select(MonitoringTask)
            .where(MonitoringTask.task_code == task_code)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_task_by_id(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> MonitoringTask | None:
        """按主键查询作业任务。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            MonitoringTask | None: 作业任务；不存在时返回 None。
        """
        result = await db.execute(
            select(MonitoringTask).where(MonitoringTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_imagery(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> ImageryAsset | None:
        """查询项目最新遥感影像。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            ImageryAsset | None: 最新影像资产，不存在时返回 None。
        """
        result = await db.execute(
            select(ImageryAsset)
            .where(
                ImageryAsset.project_id == project_id,
                ImageryAsset.data_status == "operational",
                ImageryAsset.file_uri.is_not(None),
                ImageryAsset.file_size_bytes.is_not(None),
                ImageryAsset.checksum_sha256.is_not(None),
            )
            .order_by(ImageryAsset.acquired_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _review_conditions(
        task_id: int,
        *,
        current_cycle: bool,
    ) -> list[object]:
        """构造完整历史或当前整改周期的审核查询条件。

        Args:
            task_id: 任务主键。
            current_cycle: 是否仅保留最近数据重载、退回、驳回或回退后的记录。

        Returns:
            list[object]: 可用于审核记录查询和计数的条件。
        """
        conditions: list[object] = [ReviewRecord.task_id == task_id]
        if not current_cycle:
            return conditions
        cycle_record = aliased(ReviewRecord)
        cycle_started_at = (
            select(func.max(cycle_record.created_at))
            .where(
                cycle_record.task_id == task_id,
                cycle_record.action.in_(REVIEW_CYCLE_RESET_ACTIONS),
            )
            .scalar_subquery()
        )
        conditions.append(
            ReviewRecord.created_at
            >= func.coalesce(cycle_started_at, ReviewRecord.created_at)
        )
        return conditions

    async def get_reviews(
        self,
        db: AsyncSession,
        task_id: int,
        limit: int | None = None,
        *,
        current_cycle: bool = False,
    ) -> Sequence[ReviewRecord]:
        """查询任务审核与操作历史。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            limit: 可选的最大返回数量；为空时返回完整交付审计。
            current_cycle: 是否仅返回当前整改周期证据。

        Returns:
            Sequence[ReviewRecord]: 按时间倒序排列的记录。
        """
        statement = (
            select(ReviewRecord)
            .where(
                *self._review_conditions(
                    task_id,
                    current_cycle=current_cycle,
                )
            )
            .order_by(ReviewRecord.created_at.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        result = await db.execute(statement)
        return result.scalars().all()

    async def count_reviews(
        self,
        db: AsyncSession,
        task_id: int,
        *,
        current_cycle: bool = False,
    ) -> int:
        """统计任务完整审核及操作审计数量。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            current_cycle: 是否只统计当前整改周期。

        Returns:
            int: 当前任务审计记录总数。
        """
        result = await db.execute(
            select(func.count(ReviewRecord.id)).where(
                *self._review_conditions(
                    task_id,
                    current_cycle=current_cycle,
                )
            )
        )
        return int(result.scalar_one())

    async def count_open_issues(self, db: AsyncSession, task_id: int) -> int:
        """统计任务未关闭质量问题数量。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            int: 未关闭质量问题数量。
        """
        result = await db.execute(
            select(func.count(QualityIssue.id)).where(
                QualityIssue.task_id == task_id,
                QualityIssue.status == "open",
            )
        )
        return int(result.scalar_one())

    async def count_pending_field_verifications(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> int:
        """统计尚未完成疑点处置的外业核查记录。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            int: 处置状态仍为 pending 的外业记录数量。
        """
        result = await db.execute(
            select(func.count(FieldVerification.id)).where(
                FieldVerification.task_id == task_id,
                FieldVerification.resolution_status == "pending",
            )
        )
        return int(result.scalar_one())

    async def get_navigation_counts(
        self,
        db: AsyncSession,
        project_id: int,
        task_id: int,
    ) -> WorkbenchNavigationCounts:
        """一次查询工作台导航中的真实业务数量。

        影像数量只统计具备实体 URI、文件大小和 SHA256 证据的业务资产；
        灾害与外业数量统计当前任务仍待人工处置的工作项。

        Args:
            db: 异步数据库会话。
            project_id: 当前监测项目主键。
            task_id: 当前作业任务主键。

        Returns:
            WorkbenchNavigationCounts: 影像资产和待办工作项数量。
        """
        operational_imagery_count = (
            select(func.count(ImageryAsset.id))
            .where(
                ImageryAsset.project_id == project_id,
                ImageryAsset.data_status == "operational",
                ImageryAsset.file_uri.is_not(None),
                ImageryAsset.file_size_bytes.is_not(None),
                ImageryAsset.file_size_bytes > 0,
                ImageryAsset.checksum_sha256.is_not(None),
            )
            .scalar_subquery()
        )
        pending_disaster_count = (
            select(func.count(DisasterPatch.id))
            .where(
                DisasterPatch.task_id == task_id,
                DisasterPatch.status == "pending",
            )
            .scalar_subquery()
        )
        pending_field_count = (
            select(func.count(FieldVerification.id))
            .where(
                FieldVerification.task_id == task_id,
                FieldVerification.resolution_status == "pending",
            )
            .scalar_subquery()
        )
        total_field_count = (
            select(func.count(FieldVerification.id))
            .where(FieldVerification.task_id == task_id)
            .scalar_subquery()
        )
        current_delivery_count = (
            select(func.count(DeliveryPackage.id))
            .join(
                MonitoringTask,
                MonitoringTask.id == DeliveryPackage.task_id,
            )
            .where(
                DeliveryPackage.task_id == task_id,
                DeliveryPackage.status == "completed",
                DeliveryPackage.file_uri.is_not(None),
                DeliveryPackage.file_size_bytes.is_not(None),
                DeliveryPackage.file_size_bytes > 0,
                DeliveryPackage.checksum_sha256.is_not(None),
                DeliveryPackage.completed_at.is_not(None),
                DeliveryPackage.completed_at >= MonitoringTask.updated_at,
            )
            .scalar_subquery()
        )
        row = (
            (
                await db.execute(
                    select(
                        operational_imagery_count.label("operational_imagery_count"),
                        pending_disaster_count.label("pending_disaster_count"),
                        total_field_count.label("total_field_verification_count"),
                        pending_field_count.label("pending_field_verification_count"),
                        current_delivery_count.label("current_delivery_package_count"),
                    )
                )
            )
            .mappings()
            .one()
        )
        return WorkbenchNavigationCounts(
            operational_imagery_count=int(row["operational_imagery_count"]),
            pending_disaster_count=int(row["pending_disaster_count"]),
            total_field_verification_count=int(row["total_field_verification_count"]),
            pending_field_verification_count=int(
                row["pending_field_verification_count"]
            ),
            current_delivery_package_count=int(row["current_delivery_package_count"]),
        )

    async def get_quality_issue_for_update(
        self,
        db: AsyncSession,
        task_id: int,
        issue_id: int,
    ) -> QualityIssue | None:
        """锁定并查询任务内指定质量问题。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            issue_id: 问题主键。

        Returns:
            QualityIssue | None: 已锁定问题；不存在时返回 None。
        """
        result = await db.execute(
            select(QualityIssue)
            .where(
                QualityIssue.id == issue_id,
                QualityIssue.task_id == task_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _quality_issue_conditions(
        task_id: int,
        *,
        status: str,
        rule_code: str | None,
        severity: str | None,
        issue_type: str | None,
        keyword: str | None,
    ) -> list[object]:
        """构造质量问题队列的参数化筛选条件。

        Args:
            task_id: 作业任务主键。
            status: 问题状态或 all。
            rule_code: 可选规则编码。
            severity: 可选严重度。
            issue_type: 可选问题类型。
            keyword: 可选图斑或行政区关键词。

        Returns:
            list[object]: SQLAlchemy 查询条件列表。
        """
        conditions: list[object] = [QualityIssue.task_id == task_id]
        if status != "all":
            conditions.append(QualityIssue.status == status)
        if rule_code:
            conditions.append(QualityIssue.rule_code == rule_code)
        if severity:
            conditions.append(QualityIssue.severity == severity)
        if issue_type:
            conditions.append(QualityIssue.issue_type == issue_type)
        if keyword:
            pattern = f"%{keyword}%"
            conditions.append(
                or_(
                    QualityIssue.plot_code.ilike(pattern),
                    FarmlandPlot.city_name.ilike(pattern),
                    FarmlandPlot.district_name.ilike(pattern),
                    FarmlandPlot.owner_village.ilike(pattern),
                )
            )
        return conditions

    async def get_quality_issue_page(
        self,
        db: AsyncSession,
        task_id: int,
        *,
        status: str,
        rule_code: str | None,
        severity: str | None,
        issue_type: str | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[RowMapping], int]:
        """分页查询任务质量问题及图斑上下文。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            status: 问题状态或 all。
            rule_code: 可选规则编码。
            severity: 可选严重度。
            issue_type: 可选问题类型。
            keyword: 可选图斑或行政区关键词。
            page: 页码。
            page_size: 每页条数。

        Returns:
            tuple[list[RowMapping], int]: 当前页数据和总条数。
        """
        conditions = self._quality_issue_conditions(
            task_id,
            status=status,
            rule_code=rule_code,
            severity=severity,
            issue_type=issue_type,
            keyword=keyword,
        )
        base_from = (
            select(QualityIssue.id)
            .select_from(QualityIssue)
            .outerjoin(
                FarmlandPlot,
                FarmlandPlot.plot_code == QualityIssue.plot_code,
            )
            .where(*conditions)
        )
        total = int(
            (
                await db.execute(select(func.count()).select_from(base_from.subquery()))
            ).scalar_one()
        )
        severity_order = case(
            (QualityIssue.severity == "high", 1),
            (QualityIssue.severity == "medium", 2),
            else_=3,
        )
        statement = (
            select(
                QualityIssue.id,
                QualityIssue.plot_code,
                QualityIssue.rule_code,
                QualityIssue.issue_type,
                QualityIssue.severity,
                QualityIssue.description,
                QualityIssue.status,
                QualityIssue.source,
                QualityIssue.assignee,
                QualityIssue.resolved_by,
                QualityIssue.resolved_by_code,
                QualityIssue.resolved_by_role,
                QualityIssue.resolution_comment,
                QualityIssue.created_at,
                QualityIssue.resolved_at,
                FarmlandPlot.version.label("plot_version"),
                FarmlandPlot.city_name,
                FarmlandPlot.district_name,
                FarmlandPlot.owner_village,
                FarmlandPlot.land_class,
                FarmlandPlot.crop_type,
                FarmlandPlot.area_ha,
            )
            .select_from(QualityIssue)
            .outerjoin(
                FarmlandPlot,
                FarmlandPlot.plot_code == QualityIssue.plot_code,
            )
            .where(*conditions)
            .order_by(severity_order, QualityIssue.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await db.execute(statement)).mappings().all()
        return list(rows), total

    async def get_quality_issue_summary(
        self,
        db: AsyncSession,
        task_id: int,
        *,
        issue_type: str | None,
        keyword: str | None,
    ) -> tuple[QualityIssueSummary, list[RowMapping]]:
        """汇总任务质量问题状态、严重度和规则数量。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            issue_type: 可选问题类型。
            keyword: 可选图斑或行政区关键词。

        Returns:
            tuple[QualityIssueSummary, list[RowMapping]]: 汇总指标和规则计数。
        """
        conditions = self._quality_issue_conditions(
            task_id,
            status="all",
            rule_code=None,
            severity=None,
            issue_type=issue_type,
            keyword=keyword,
        )
        summary_statement = (
            select(
                func.count(QualityIssue.id).label("total_count"),
                func.count(QualityIssue.id)
                .filter(QualityIssue.status == "open")
                .label("open_count"),
                func.count(QualityIssue.id)
                .filter(QualityIssue.status != "open")
                .label("resolved_count"),
                func.count(QualityIssue.id)
                .filter(
                    QualityIssue.severity == "high",
                    QualityIssue.status == "open",
                )
                .label("high_count"),
                func.count(QualityIssue.id)
                .filter(
                    QualityIssue.severity == "medium",
                    QualityIssue.status == "open",
                )
                .label("medium_count"),
                func.count(QualityIssue.id)
                .filter(
                    QualityIssue.severity == "low",
                    QualityIssue.status == "open",
                )
                .label("low_count"),
            )
            .select_from(QualityIssue)
            .outerjoin(
                FarmlandPlot,
                FarmlandPlot.plot_code == QualityIssue.plot_code,
            )
            .where(*conditions)
        )
        summary_row = (await db.execute(summary_statement)).mappings().one()
        rule_statement = (
            select(
                QualityIssue.rule_code,
                func.count(QualityIssue.id).label("total_count"),
                func.count(QualityIssue.id)
                .filter(QualityIssue.status == "open")
                .label("open_count"),
            )
            .select_from(QualityIssue)
            .outerjoin(
                FarmlandPlot,
                FarmlandPlot.plot_code == QualityIssue.plot_code,
            )
            .where(*conditions)
            .group_by(QualityIssue.rule_code)
            .order_by(func.count(QualityIssue.id).desc())
        )
        rule_rows = (await db.execute(rule_statement)).mappings().all()
        return (
            QualityIssueSummary(
                total_count=int(summary_row["total_count"]),
                open_count=int(summary_row["open_count"]),
                resolved_count=int(summary_row["resolved_count"]),
                high_count=int(summary_row["high_count"]),
                medium_count=int(summary_row["medium_count"]),
                low_count=int(summary_row["low_count"]),
            ),
            list(rule_rows),
        )

    async def get_plot_by_code(
        self,
        db: AsyncSession,
        plot_code: str,
    ) -> FarmlandPlot | None:
        """按编号查询解译图斑。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑编号。

        Returns:
            FarmlandPlot | None: 图斑对象，不存在时返回 None。
        """
        result = await db.execute(
            select(FarmlandPlot).where(FarmlandPlot.plot_code == plot_code)
        )
        return result.scalar_one_or_none()

    async def get_plot_by_code_for_update(
        self,
        db: AsyncSession,
        plot_code: str,
    ) -> FarmlandPlot | None:
        """锁定并查询待修改图斑。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑编号。

        Returns:
            FarmlandPlot | None: 已锁定图斑；不存在时返回 None。
        """
        result = await db.execute(
            select(FarmlandPlot)
            .where(FarmlandPlot.plot_code == plot_code)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_task_plots(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[FarmlandPlot]:
        """查询任务当前纳入质量检查范围的有效图斑。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[FarmlandPlot]: 按图斑编号排序的任务图斑。
        """
        result = await db.execute(
            select(FarmlandPlot)
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .where(
                TaskPlot.task_id == task_id,
                FarmlandPlot.interpretation_status != "deleted",
            )
            .order_by(FarmlandPlot.plot_code)
        )
        return result.scalars().all()

    async def get_task_plots_by_codes(
        self,
        db: AsyncSession,
        task_id: int,
        plot_codes: list[str],
    ) -> Sequence[FarmlandPlot]:
        """查询任务内显式选择的有效图斑。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            plot_codes: 用户显式选择的图斑编号。

        Returns:
            Sequence[FarmlandPlot]: 属于任务且未删除的图斑。
        """
        result = await db.execute(
            select(FarmlandPlot)
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .where(
                TaskPlot.task_id == task_id,
                FarmlandPlot.plot_code.in_(plot_codes),
                FarmlandPlot.interpretation_status != "deleted",
            )
            .order_by(FarmlandPlot.plot_code)
        )
        return result.scalars().all()

    async def get_task_plots_by_codes_for_update(
        self,
        db: AsyncSession,
        task_id: int,
        plot_codes: list[str],
    ) -> Sequence[FarmlandPlot]:
        """锁定任务内显式选择的有效图斑。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            plot_codes: 用户显式选择的图斑编号。

        Returns:
            Sequence[FarmlandPlot]: 已锁定且属于任务的有效图斑。
        """
        result = await db.execute(
            select(FarmlandPlot)
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .where(
                TaskPlot.task_id == task_id,
                FarmlandPlot.plot_code.in_(plot_codes),
                FarmlandPlot.interpretation_status != "deleted",
            )
            .order_by(FarmlandPlot.plot_code)
            .with_for_update()
        )
        return result.scalars().all()

    async def get_plots_by_codes_for_update_any_status(
        self,
        db: AsyncSession,
        plot_codes: list[str],
    ) -> Sequence[FarmlandPlot]:
        """锁定并查询指定编号图斑，包含已软删除记录。

        Args:
            db: 异步数据库会话。
            plot_codes: 需要恢复或再次停用的图斑编号。

        Returns:
            Sequence[FarmlandPlot]: 已锁定图斑列表。
        """
        result = await db.execute(
            select(FarmlandPlot)
            .where(FarmlandPlot.plot_code.in_(plot_codes))
            .order_by(FarmlandPlot.plot_code)
            .with_for_update()
        )
        return result.scalars().all()

    async def is_plot_assigned_to_task(
        self,
        db: AsyncSession,
        task_id: int,
        plot_code: str,
    ) -> bool:
        """判断图斑是否属于指定任务作用域。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            plot_code: 图斑编号。

        Returns:
            bool: 已分配到任务时返回 True。
        """
        result = await db.execute(
            select(func.count(TaskPlot.id)).where(
                TaskPlot.task_id == task_id,
                TaskPlot.plot_code == plot_code,
            )
        )
        return int(result.scalar_one()) > 0

    async def assign_plot_to_task(
        self,
        db: AsyncSession,
        task_id: int,
        plot_code: str,
        assigned_by: str,
        assigned_by_code: str | None = None,
        assigned_by_role: str | None = None,
    ) -> None:
        """将新建图斑加入任务作用域。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            plot_code: 图斑编号。
            assigned_by: 分配操作人。
            assigned_by_code: 分配操作人稳定编码。
            assigned_by_role: 分配时角色快照。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            text(
                """
                INSERT INTO task_plots (
                    task_id, plot_code, assigned_by,
                    assigned_by_code, assigned_by_role
                )
                VALUES (
                    :task_id, :plot_code, :assigned_by,
                    :assigned_by_code, :assigned_by_role
                )
                ON CONFLICT (task_id, plot_code) DO NOTHING
                """
            ),
            {
                "task_id": task_id,
                "plot_code": plot_code,
                "assigned_by": assigned_by,
                "assigned_by_code": assigned_by_code,
                "assigned_by_role": assigned_by_role,
            },
        )

    async def analyze_polygon(
        self,
        db: AsyncSession,
        geometry_json: str,
    ) -> tuple[bool, float]:
        """校验候选多边形并计算椭球面积。

        Args:
            db: 异步数据库会话。
            geometry_json: WGS84 GeoJSON Polygon 字符串。

        Returns:
            tuple[bool, float]: 几何是否有效及面积公顷数。
        """
        # 候选几何只通过绑定参数进入 PostGIS，避免把坐标拼接进 SQL。
        statement = text(
            """
            WITH candidate AS (
                SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326) AS geom
            )
            SELECT
                ST_IsValid(geom) AS is_valid,
                ST_Area(geom::geography) / 10000.0 AS area_ha
            FROM candidate
            """
        )
        result = await db.execute(statement, {"geometry": geometry_json})
        row = result.mappings().one()
        return bool(row["is_valid"]), float(row["area_ha"])

    async def analyze_plot_split(
        self,
        db: AsyncSession,
        plot_code: str,
        cutter_json: str,
    ) -> SplitAnalysis:
        """使用 PostGIS 分析分割线并返回有效子面。

        Args:
            db: 异步数据库会话。
            plot_code: 待分割图斑编号。
            cutter_json: WGS84 GeoJSON LineString 字符串。

        Returns:
            SplitAnalysis: 分割线有效性、源面积和子面列表。
        """
        # ST_Split 在数据库内执行真实拓扑分割，所有几何均显式设置为 EPSG:4326。
        statement = text(
            """
            WITH target AS (
                SELECT geom
                FROM farmland_plots
                WHERE plot_code = :plot_code
                  AND interpretation_status != 'deleted'
            ), cutter AS (
                SELECT ST_SetSRID(
                    ST_GeomFromGeoJSON(:cutter),
                    4326
                ) AS geom
            ), split_result AS (
                SELECT
                    ST_IsSimple(cutter.geom) AS cutter_simple,
                    ST_Area(target.geom::geography) / 10000.0
                        AS source_area_ha,
                    ST_Split(target.geom, cutter.geom) AS geom
                FROM target
                CROSS JOIN cutter
            ), pieces AS (
                SELECT
                    split_result.cutter_simple,
                    split_result.source_area_ha,
                    (ST_Dump(
                        ST_CollectionExtract(split_result.geom, 3)
                    )).geom AS geom
                FROM split_result
            )
            SELECT
                cutter_simple,
                source_area_ha,
                ST_AsGeoJSON(geom) AS geometry_json,
                ST_Area(geom::geography) / 10000.0 AS area_ha
            FROM pieces
            WHERE NOT ST_IsEmpty(geom)
              AND ST_IsValid(geom)
            ORDER BY area_ha DESC
            """
        )
        rows = (
            (
                await db.execute(
                    statement,
                    {"plot_code": plot_code, "cutter": cutter_json},
                )
            )
            .mappings()
            .all()
        )
        if not rows:
            return SplitAnalysis(
                cutter_simple=False,
                source_area_ha=0,
                pieces=[],
            )
        return SplitAnalysis(
            cutter_simple=bool(rows[0]["cutter_simple"]),
            source_area_ha=float(rows[0]["source_area_ha"]),
            pieces=[
                SplitPiece(
                    geometry_json=str(row["geometry_json"]),
                    area_ha=float(row["area_ha"]),
                )
                for row in rows
            ],
        )

    async def analyze_plot_merge(
        self,
        db: AsyncSession,
        task_id: int,
        plot_codes: list[str],
    ) -> MergeAnalysis:
        """分析任务内多个图斑是否可合并为单一有效 Polygon。

        Args:
            db: 异步数据库会话。
            task_id: 当前任务主键。
            plot_codes: 用户显式选择的图斑编号。

        Returns:
            MergeAnalysis: 行政区、重叠、连通性、面积和结果几何。
        """
        # 先限定任务作用域，再以 ST_UnaryUnion 生成真实拓扑合并结果。
        statement = text(
            """
            WITH sources AS (
                SELECT plot.plot_code, plot.district_code, plot.geom
                FROM task_plots AS scope
                JOIN farmland_plots AS plot
                  ON plot.plot_code = scope.plot_code
                WHERE scope.task_id = :task_id
                  AND plot.plot_code = ANY(CAST(:plot_codes AS VARCHAR[]))
                  AND plot.interpretation_status != 'deleted'
            ), merged AS (
                SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
                FROM sources
            ), overlap_summary AS (
                SELECT COALESCE(SUM(
                    ST_Area(ST_Intersection(left_plot.geom, right_plot.geom)::geography)
                    / 10000.0
                ), 0) AS area_ha
                FROM sources AS left_plot
                JOIN sources AS right_plot
                  ON left_plot.plot_code < right_plot.plot_code
                 AND left_plot.geom && right_plot.geom
                 AND ST_Intersects(left_plot.geom, right_plot.geom)
                 AND NOT ST_Touches(left_plot.geom, right_plot.geom)
            )
            SELECT
                (SELECT COUNT(*) FROM sources) AS source_count,
                (SELECT COUNT(DISTINCT district_code) FROM sources)
                    AS district_count,
                ST_GeometryType(merged.geom) AS geometry_type,
                ST_NumGeometries(merged.geom) AS component_count,
                ST_IsValid(merged.geom) AS geometry_valid,
                COALESCE((
                    SELECT SUM(ST_Area(geom::geography) / 10000.0)
                    FROM sources
                ), 0) AS source_area_ha,
                ST_Area(merged.geom::geography) / 10000.0 AS result_area_ha,
                overlap_summary.area_ha AS overlap_area_ha,
                ST_AsGeoJSON(merged.geom) AS geometry_json
            FROM merged
            CROSS JOIN overlap_summary
            """
        )
        row = (
            (
                await db.execute(
                    statement,
                    {"task_id": task_id, "plot_codes": plot_codes},
                )
            )
            .mappings()
            .one()
        )
        return MergeAnalysis(
            source_count=int(row["source_count"]),
            district_count=int(row["district_count"]),
            geometry_type=str(row["geometry_type"] or ""),
            component_count=int(row["component_count"] or 0),
            geometry_valid=bool(row["geometry_valid"]),
            source_area_ha=float(row["source_area_ha"] or 0),
            result_area_ha=float(row["result_area_ha"] or 0),
            overlap_area_ha=float(row["overlap_area_ha"] or 0),
            geometry_json=str(row["geometry_json"] or ""),
        )

    async def get_next_plot_code(
        self,
        db: AsyncSession,
        prefix: str = "USR-HLJ",
    ) -> str:
        """生成当前编号序列的下一个图斑编号。

        Args:
            db: 异步数据库会话。
            prefix: 图斑编号前缀。

        Returns:
            str: 形如 USR-HLJ-006 的下一个编号。
        """
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:prefix))"),
            {"prefix": prefix},
        )
        statement = text(
            """
            SELECT COALESCE(
                MAX(CAST(SUBSTRING(plot_code FROM :pattern) AS INTEGER)),
                0
            ) + 1
            FROM farmland_plots
            WHERE plot_code ~ :filter_pattern
            """
        )
        result = await db.execute(
            statement,
            {
                "pattern": f"^{prefix}-(\\d+)$",
                "filter_pattern": f"^{prefix}-[0-9]+$",
            },
        )
        sequence = int(result.scalar_one())
        return f"{prefix}-{sequence:03d}"

    async def create_plot(
        self,
        db: AsyncSession,
        *,
        plot_code: str,
        owner_village: str,
        area_ha: float,
        geometry_json: str,
        land_class: str,
        crop_type: str | None,
        planting_mode: str | None,
        irrigation_condition: str | None,
    ) -> FarmlandPlot | None:
        """写入新解译图斑和 PostGIS 几何。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑编号。
            owner_village: 权属村。
            area_ha: 椭球面积，单位公顷。
            geometry_json: WGS84 GeoJSON Polygon。
            land_class: 一级地类。
            crop_type: 作物类型。
            planting_mode: 种植模式。
            irrigation_condition: 灌排条件。

        Returns:
            FarmlandPlot | None: 新建图斑；范围不在行政区内时返回 None。
        """
        statement = text(
            """
            WITH candidate AS (
                SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326) AS geom
            ), district_match AS (
                SELECT boundary_code, boundary_name, parent_code
                FROM administrative_boundaries AS boundary, candidate
                WHERE boundary.boundary_level = 'district'
                  AND ST_Covers(
                      boundary.geom,
                      ST_PointOnSurface(candidate.geom)
                  )
                ORDER BY ST_Area(boundary.geom::geography)
                LIMIT 1
            ), city_match AS (
                SELECT boundary_name
                FROM administrative_boundaries
                WHERE boundary_code = (SELECT parent_code FROM district_match)
            )
            INSERT INTO farmland_plots (
                plot_code, owner_village, area_ha, geom, land_class,
                crop_type, planting_mode, irrigation_condition,
                interpretation_status, version, updated_at, source_name,
                source_feature_id, source_version, source_updated_at,
                province_name, city_name, district_name, district_code
            )
            SELECT
                :plot_code, :owner_village, :area_ha,
                candidate.geom,
                :land_class, :crop_type, :planting_mode,
                :irrigation_condition, 'interpreting', 1, NOW(),
                '内业人工解译', :plot_code, '1', NOW(), '黑龙江省',
                city_match.boundary_name, district_match.boundary_name,
                district_match.boundary_code
            FROM candidate
            JOIN district_match ON TRUE
            JOIN city_match ON TRUE
            """
        )
        result = await db.execute(
            statement,
            {
                "plot_code": plot_code,
                "owner_village": owner_village,
                "area_ha": area_ha,
                "geometry": geometry_json,
                "land_class": land_class,
                "crop_type": crop_type,
                "planting_mode": planting_mode,
                "irrigation_condition": irrigation_condition,
            },
        )
        if result.rowcount == 0:
            return None
        plot = await self.get_plot_by_code(db, plot_code)
        return plot

    async def create_split_child(
        self,
        db: AsyncSession,
        *,
        source_plot_code: str,
        child_plot_code: str,
        geometry_json: str,
        area_ha: float,
    ) -> FarmlandPlot | None:
        """继承源图斑属性并写入一个分割子图斑。

        Args:
            db: 异步数据库会话。
            source_plot_code: 被分割的源图斑编号。
            child_plot_code: 新子图斑编号。
            geometry_json: WGS84 子面 GeoJSON。
            area_ha: PostGIS 计算的子面公顷面积。

        Returns:
            FarmlandPlot | None: 新建子图斑；源图斑不存在时返回 None。
        """
        statement = text(
            """
            WITH child AS (
                SELECT ST_SetSRID(
                    ST_GeomFromGeoJSON(:geometry),
                    4326
                ) AS geom
            )
            INSERT INTO farmland_plots (
                plot_code, owner_village, area_ha, geom, land_class,
                crop_type, planting_mode, irrigation_condition,
                interpretation_status, version, updated_at, source_name,
                source_feature_id, source_version, source_updated_at,
                province_name, city_name, district_name, district_code
            )
            SELECT
                :child_plot_code, source.owner_village, :area_ha,
                child.geom, source.land_class, source.crop_type,
                source.planting_mode, source.irrigation_condition,
                'interpreting', 1, NOW(), '内业图斑分割',
                :child_plot_code, '1', NOW(), source.province_name,
                source.city_name, source.district_name, source.district_code
            FROM farmland_plots AS source
            CROSS JOIN child
            WHERE source.plot_code = :source_plot_code
            """
        )
        result = await db.execute(
            statement,
            {
                "source_plot_code": source_plot_code,
                "child_plot_code": child_plot_code,
                "geometry": geometry_json,
                "area_ha": area_ha,
            },
        )
        if result.rowcount == 0:
            return None
        return await self.get_plot_by_code(db, child_plot_code)

    async def create_merged_plot(
        self,
        db: AsyncSession,
        *,
        source_plot_code: str,
        merged_plot_code: str,
        geometry_json: str,
        area_ha: float,
        owner_village: str,
        land_class: str,
        crop_type: str | None,
        planting_mode: str | None,
        irrigation_condition: str | None,
    ) -> FarmlandPlot | None:
        """继承行政层级并写入人工确认属性的合并结果图斑。

        Args:
            db: 异步数据库会话。
            source_plot_code: 用于继承行政层级的任一源图斑编号。
            merged_plot_code: 新合并图斑编号。
            geometry_json: PostGIS 合并结果 GeoJSON。
            area_ha: 合并结果公顷面积。
            owner_village: 人工确认权属村。
            land_class: 人工确认一级地类。
            crop_type: 人工确认作物类型。
            planting_mode: 人工确认种植模式。
            irrigation_condition: 人工确认灌排条件。

        Returns:
            FarmlandPlot | None: 合并结果图斑；源图斑不存在时返回 None。
        """
        statement = text(
            """
            WITH merged AS (
                SELECT ST_SetSRID(
                    ST_GeomFromGeoJSON(:geometry),
                    4326
                ) AS geom
            )
            INSERT INTO farmland_plots (
                plot_code, owner_village, area_ha, geom, land_class,
                crop_type, planting_mode, irrigation_condition,
                interpretation_status, version, updated_at, source_name,
                source_feature_id, source_version, source_updated_at,
                province_name, city_name, district_name, district_code
            )
            SELECT
                :merged_plot_code, :owner_village, :area_ha,
                merged.geom, :land_class, :crop_type,
                :planting_mode, :irrigation_condition,
                'interpreting', 1, NOW(), '内业图斑合并',
                :merged_plot_code, '1', NOW(), source.province_name,
                source.city_name, source.district_name, source.district_code
            FROM farmland_plots AS source
            CROSS JOIN merged
            WHERE source.plot_code = :source_plot_code
            """
        )
        result = await db.execute(
            statement,
            {
                "source_plot_code": source_plot_code,
                "merged_plot_code": merged_plot_code,
                "geometry": geometry_json,
                "area_ha": area_ha,
                "owner_village": owner_village,
                "land_class": land_class,
                "crop_type": crop_type,
                "planting_mode": planting_mode,
                "irrigation_condition": irrigation_condition,
            },
        )
        if result.rowcount == 0:
            return None
        return await self.get_plot_by_code(db, merged_plot_code)

    async def update_plot_geometry(
        self,
        db: AsyncSession,
        plot_code: str,
        geometry_json: str,
        area_ha: float,
    ) -> FarmlandPlot | None:
        """更新图斑边界和椭球面积。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑编号。
            geometry_json: WGS84 GeoJSON Polygon。
            area_ha: 新边界对应公顷面积。

        Returns:
            FarmlandPlot | None: 更新后的图斑，不存在时返回 None。
        """
        statement = text(
            """
            UPDATE farmland_plots
            SET
                geom = ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326),
                area_ha = :area_ha,
                interpretation_status = 'interpreting',
                version = version + 1,
                updated_at = NOW()
            WHERE plot_code = :plot_code
              AND interpretation_status != 'deleted'
            """
        )
        result = await db.execute(
            statement,
            {
                "plot_code": plot_code,
                "geometry": geometry_json,
                "area_ha": area_ha,
            },
        )
        if result.rowcount == 0:
            return None
        plot = await self.get_plot_by_code(db, plot_code)
        if plot is not None:
            await db.refresh(plot)
        return plot

    async def restore_plot_from_latest_active_version(
        self,
        db: AsyncSession,
        plot_code: str,
    ) -> FarmlandPlot | None:
        """从最近非删除版本恢复图斑并创建新的当前版本号。

        Args:
            db: 异步数据库会话。
            plot_code: 待恢复图斑编号。

        Returns:
            FarmlandPlot | None: 已恢复图斑；缺少有效历史版本时返回 None。
        """
        statement = text(
            """
            WITH restore_version AS (
                SELECT land_class, crop_type, planting_mode,
                       irrigation_condition, interpretation_status, geom
                FROM plot_versions
                WHERE plot_code = :plot_code
                  AND interpretation_status != 'deleted'
                ORDER BY version DESC
                LIMIT 1
            )
            UPDATE farmland_plots AS plot
            SET land_class = restore_version.land_class,
                crop_type = restore_version.crop_type,
                planting_mode = restore_version.planting_mode,
                irrigation_condition = restore_version.irrigation_condition,
                interpretation_status = restore_version.interpretation_status,
                geom = restore_version.geom,
                area_ha = ROUND((
                    ST_Area(restore_version.geom::geography) / 10000.0
                )::numeric, 4),
                version = plot.version + 1,
                updated_at = NOW()
            FROM restore_version
            WHERE plot.plot_code = :plot_code
            """
        )
        result = await db.execute(statement, {"plot_code": plot_code})
        if result.rowcount == 0:
            return None
        plot = await self.get_plot_by_code(db, plot_code)
        if plot is not None:
            await db.refresh(plot)
        return plot

    async def soft_delete_plot(
        self,
        db: AsyncSession,
        plot_code: str,
    ) -> FarmlandPlot | None:
        """将图斑标记为已删除并递增版本号。

        Args:
            db: 异步数据库会话。
            plot_code: 待软删除图斑编号。

        Returns:
            FarmlandPlot | None: 已删除图斑；不存在或已删除时返回 None。
        """
        result = await db.execute(
            text(
                """
                UPDATE farmland_plots
                SET interpretation_status = 'deleted',
                    version = version + 1,
                    updated_at = NOW()
                WHERE plot_code = :plot_code
                  AND interpretation_status != 'deleted'
                """
            ),
            {"plot_code": plot_code},
        )
        if result.rowcount == 0:
            return None
        plot = await self.get_plot_by_code(db, plot_code)
        if plot is not None:
            await db.refresh(plot)
        return plot

    async def close_plot_issues(
        self,
        db: AsyncSession,
        plot_code: str,
    ) -> None:
        """关闭已删除图斑的未解决质量问题。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑编号。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            text(
                """
                UPDATE quality_issues
                SET status = 'resolved', resolved_at = NOW()
                WHERE plot_code = :plot_code AND status = 'open'
                """
            ),
            {"plot_code": plot_code},
        )

    async def detach_field_verifications(
        self,
        db: AsyncSession,
        plot_code: str,
    ) -> None:
        """解除外业记录与已删除图斑的空间匹配。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑编号。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            text(
                """
                UPDATE field_verifications
                SET matched_plot_code = NULL,
                    offset_distance_m = NULL,
                    match_status = 'pending',
                    updated_at = NOW()
                WHERE matched_plot_code = :plot_code
                """
            ),
            {"plot_code": plot_code},
        )

    async def rematch_split_field_verifications(
        self,
        db: AsyncSession,
        source_plot_code: str,
        child_plot_codes: list[str],
    ) -> None:
        """将源图斑外业点重关联到实际覆盖它的分割子图斑。

        Args:
            db: 异步数据库会话。
            source_plot_code: 被分割的源图斑编号。
            child_plot_codes: 两个分割子图斑编号。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            text(
                """
                WITH rematch AS (
                    SELECT
                        verification.id,
                        (
                        SELECT child.plot_code
                        FROM farmland_plots AS child
                        WHERE child.plot_code = ANY(
                            CAST(:child_plot_codes AS VARCHAR[])
                        )
                          AND ST_Covers(child.geom, verification.location)
                        ORDER BY child.plot_code
                        LIMIT 1
                        ) AS child_plot_code
                    FROM field_verifications AS verification
                    WHERE verification.matched_plot_code = :source_plot_code
                )
                UPDATE field_verifications AS verification
                SET matched_plot_code = rematch.child_plot_code,
                    offset_distance_m = CASE
                        WHEN rematch.child_plot_code IS NULL THEN NULL
                        ELSE verification.offset_distance_m
                    END,
                    match_status = CASE
                        WHEN rematch.child_plot_code IS NULL THEN 'pending'
                        ELSE verification.match_status
                    END,
                    updated_at = NOW()
                FROM rematch
                WHERE verification.id = rematch.id
                """
            ),
            {
                "source_plot_code": source_plot_code,
                "child_plot_codes": child_plot_codes,
            },
        )

    async def rematch_merged_field_verifications(
        self,
        db: AsyncSession,
        source_plot_codes: list[str],
        merged_plot_code: str,
    ) -> None:
        """将所有源图斑外业点关联到合并结果图斑。

        Args:
            db: 异步数据库会话。
            source_plot_codes: 被合并的源图斑编号。
            merged_plot_code: 合并结果图斑编号。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            text(
                """
                UPDATE field_verifications
                SET matched_plot_code = :merged_plot_code,
                    updated_at = NOW()
                WHERE matched_plot_code = ANY(
                    CAST(:source_plot_codes AS VARCHAR[])
                )
                """
            ),
            {
                "source_plot_codes": source_plot_codes,
                "merged_plot_code": merged_plot_code,
            },
        )

    async def count_plot_progress(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> tuple[int, int]:
        """统计指定任务有效图斑总数和已解译数量。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            tuple[int, int]: 有效图斑总数和已解译数量。
        """
        result = await db.execute(
            select(
                func.count(FarmlandPlot.id).filter(
                    FarmlandPlot.interpretation_status != "deleted"
                ),
                func.count(FarmlandPlot.id).filter(
                    FarmlandPlot.interpretation_status == "interpreted"
                ),
            )
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .where(TaskPlot.task_id == task_id)
        )
        total, completed = result.one()
        return int(total), int(completed)

    async def add_plot_version(
        self,
        db: AsyncSession,
        version: PlotVersion,
    ) -> PlotVersion:
        """写入不可变图斑版本记录。

        Args:
            db: 异步数据库会话。
            version: 待写入版本。

        Returns:
            PlotVersion: 已持久化版本。
        """
        db.add(version)
        await db.flush()
        await db.refresh(version)
        return version

    async def add_plot_versions(
        self,
        db: AsyncSession,
        versions: list[PlotVersion],
    ) -> None:
        """一次写入多个不可变图斑版本。

        Args:
            db: 异步数据库会话。
            versions: 待写入的图斑版本列表。

        Returns:
            None: 无返回值。
        """
        if not versions:
            return
        db.add_all(versions)
        await db.flush()

    async def add_plot_edit_operation(
        self,
        db: AsyncSession,
        operation: PlotEditOperation,
    ) -> PlotEditOperation:
        """写入不可变地块编辑操作日志。

        Args:
            db: 异步数据库会话。
            operation: 分割、合并或恢复操作对象。

        Returns:
            PlotEditOperation: 已持久化操作日志。
        """
        db.add(operation)
        await db.flush()
        await db.refresh(operation)
        return operation

    async def get_latest_undoable_plot_operation(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> PlotEditOperation | None:
        """锁定任务最近一个仍生效的分割或合并操作。

        Args:
            db: 异步数据库会话。
            task_id: 当前任务主键。

        Returns:
            PlotEditOperation | None: 可撤销操作；不存在时返回 None。
        """
        result = await db.execute(
            select(PlotEditOperation)
            .where(
                PlotEditOperation.task_id == task_id,
                PlotEditOperation.status == "applied",
            )
            .order_by(
                PlotEditOperation.created_at.desc(),
                PlotEditOperation.id.desc(),
            )
            .limit(1)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_latest_redoable_plot_operation(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> PlotEditOperation | None:
        """锁定任务最近一次被撤销且尚未失效的操作。

        Args:
            db: 异步数据库会话。
            task_id: 当前任务主键。

        Returns:
            PlotEditOperation | None: 可重做操作；不存在时返回 None。
        """
        result = await db.execute(
            select(PlotEditOperation)
            .where(
                PlotEditOperation.task_id == task_id,
                PlotEditOperation.status == "reverted",
            )
            .order_by(
                PlotEditOperation.reverted_at.desc(),
                PlotEditOperation.id.desc(),
            )
            .limit(1)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def supersede_reverted_plot_operations(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> None:
        """新编辑发生时使当前任务全部重做分支失效。

        Args:
            db: 异步数据库会话。
            task_id: 当前任务主键。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            update(PlotEditOperation)
            .where(
                PlotEditOperation.task_id == task_id,
                PlotEditOperation.status == "reverted",
            )
            .values(status="superseded")
        )

    async def add_plot_edit_operation_event(
        self,
        db: AsyncSession,
        event: PlotEditOperationEvent,
    ) -> PlotEditOperationEvent:
        """写入撤销或重做不可变事件。

        Args:
            db: 异步数据库会话。
            event: 操作事件对象。

        Returns:
            PlotEditOperationEvent: 已持久化事件。
        """
        db.add(event)
        await db.flush()
        await db.refresh(event)
        return event

    async def get_plot_geometry_validity(
        self,
        db: AsyncSession,
        plot_code: str,
    ) -> bool:
        """检查图斑几何有效性。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑编号。

        Returns:
            bool: 几何是否有效。
        """
        result = await db.execute(
            select(func.ST_IsValid(FarmlandPlot.geom)).where(
                FarmlandPlot.plot_code == plot_code
            )
        )
        return bool(result.scalar_one())

    async def get_plot_quality_metrics(
        self,
        db: AsyncSession,
        plot_code: str,
        project_id: int,
    ) -> PlotQualityMetrics:
        """计算几何、面积、拓扑、行政区和影像覆盖指标。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑编号。
            project_id: 当前监测项目主键。

        Returns:
            PlotQualityMetrics: PostGIS 计算的真实质量指标。
        """
        # 相交面积阈值为 1 平方米，排除仅边界接触和浮点微小误差。
        statement = text(
            """
            WITH target AS (
                SELECT *
                FROM farmland_plots
                WHERE plot_code = :plot_code
                  AND interpretation_status != 'deleted'
            ), overlap_rows AS (
                SELECT
                    ST_Area(
                        ST_Intersection(target.geom, other.geom)::geography
                    ) / 10000.0 AS overlap_area_ha
                FROM target
                JOIN farmland_plots AS other
                  ON other.plot_code != target.plot_code
                 AND other.interpretation_status != 'deleted'
                 AND target.geom && other.geom
                 AND ST_Intersects(target.geom, other.geom)
                 AND NOT ST_Touches(target.geom, other.geom)
            ), imagery AS (
                SELECT spatial_extent, resolution_m
                FROM imagery_assets
                WHERE project_id = :project_id
                  AND data_status = 'operational'
                  AND file_uri IS NOT NULL
                  AND checksum_sha256 IS NOT NULL
                ORDER BY acquired_at DESC
                LIMIT 1
            )
            SELECT
                ST_IsValid(target.geom) AS geometry_valid,
                ST_IsClosed(ST_ExteriorRing(target.geom)) AS ring_closed,
                ST_Area(target.geom::geography) / 10000.0 AS calculated_area_ha,
                (
                    SELECT COUNT(*) FROM overlap_rows
                    WHERE overlap_area_ha > 0.0001
                ) AS overlap_count,
                COALESCE((
                    SELECT SUM(overlap_area_ha) FROM overlap_rows
                    WHERE overlap_area_ha > 0.0001
                ), 0) AS overlap_area_ha,
                EXISTS (
                    SELECT 1
                    FROM administrative_boundaries AS boundary
                    WHERE boundary.boundary_code = target.district_code
                      AND ST_Covers(boundary.geom, target.geom)
                ) AS within_district,
                EXISTS (SELECT 1 FROM imagery) AS has_imagery,
                COALESCE((
                    SELECT ST_Covers(imagery.spatial_extent, target.geom)
                    FROM imagery
                    WHERE imagery.spatial_extent IS NOT NULL
                ), FALSE) AS covered_by_imagery,
                (SELECT resolution_m FROM imagery) AS imagery_resolution_m
            FROM target
            """
        )
        row = (
            (
                await db.execute(
                    statement,
                    {"plot_code": plot_code, "project_id": project_id},
                )
            )
            .mappings()
            .one()
        )
        return PlotQualityMetrics(
            geometry_valid=bool(row["geometry_valid"]),
            ring_closed=bool(row["ring_closed"]),
            calculated_area_ha=float(row["calculated_area_ha"]),
            overlap_count=int(row["overlap_count"]),
            overlap_area_ha=float(row["overlap_area_ha"]),
            within_district=bool(row["within_district"]),
            has_imagery=bool(row["has_imagery"]),
            covered_by_imagery=bool(row["covered_by_imagery"]),
            imagery_resolution_m=(
                float(row["imagery_resolution_m"])
                if row["imagery_resolution_m"] is not None
                else None
            ),
        )

    async def get_task_quality_metrics(
        self,
        db: AsyncSession,
        task_id: int,
        project_id: int,
    ) -> dict[str, PlotQualityMetrics]:
        """批量计算任务全部图斑的空间质量指标。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            project_id: 当前监测项目主键。

        Returns:
            dict[str, PlotQualityMetrics]: 以图斑编号索引的质量指标。
        """
        # 先按任务作用域筛选目标图斑，再利用 GIST 包围盒条件计算真实重叠。
        statement = text(
            """
            WITH scoped AS (
                SELECT plot.*
                FROM task_plots AS scope
                JOIN farmland_plots AS plot
                  ON plot.plot_code = scope.plot_code
                WHERE scope.task_id = :task_id
                  AND plot.interpretation_status != 'deleted'
            ), overlap_rows AS (
                SELECT
                    target.plot_code,
                    ST_Area(
                        ST_Intersection(target.geom, other.geom)::geography
                    ) / 10000.0 AS overlap_area_ha
                FROM scoped AS target
                JOIN farmland_plots AS other
                  ON other.plot_code != target.plot_code
                 AND other.interpretation_status != 'deleted'
                 AND target.geom && other.geom
                 AND ST_Intersects(target.geom, other.geom)
                 AND NOT ST_Touches(target.geom, other.geom)
            ), overlap_summary AS (
                SELECT
                    plot_code,
                    COUNT(*) FILTER (
                        WHERE overlap_area_ha > 0.0001
                    ) AS overlap_count,
                    COALESCE(SUM(overlap_area_ha) FILTER (
                        WHERE overlap_area_ha > 0.0001
                    ), 0) AS overlap_area_ha
                FROM overlap_rows
                GROUP BY plot_code
            ), imagery AS (
                SELECT spatial_extent, resolution_m
                FROM imagery_assets
                WHERE project_id = :project_id
                  AND data_status = 'operational'
                  AND file_uri IS NOT NULL
                  AND checksum_sha256 IS NOT NULL
                ORDER BY acquired_at DESC
                LIMIT 1
            )
            SELECT
                scoped.plot_code,
                ST_IsValid(scoped.geom) AS geometry_valid,
                ST_IsClosed(ST_ExteriorRing(scoped.geom)) AS ring_closed,
                ST_Area(scoped.geom::geography) / 10000.0 AS calculated_area_ha,
                COALESCE(overlap_summary.overlap_count, 0) AS overlap_count,
                COALESCE(overlap_summary.overlap_area_ha, 0) AS overlap_area_ha,
                EXISTS (
                    SELECT 1
                    FROM administrative_boundaries AS boundary
                    WHERE boundary.boundary_code = scoped.district_code
                      AND ST_Covers(boundary.geom, scoped.geom)
                ) AS within_district,
                EXISTS (SELECT 1 FROM imagery) AS has_imagery,
                COALESCE((
                    SELECT ST_Covers(imagery.spatial_extent, scoped.geom)
                    FROM imagery
                    WHERE imagery.spatial_extent IS NOT NULL
                ), FALSE) AS covered_by_imagery,
                (SELECT resolution_m FROM imagery) AS imagery_resolution_m
            FROM scoped
            LEFT JOIN overlap_summary
              ON overlap_summary.plot_code = scoped.plot_code
            ORDER BY scoped.plot_code
            """
        )
        rows = (
            (
                await db.execute(
                    statement,
                    {"task_id": task_id, "project_id": project_id},
                )
            )
            .mappings()
            .all()
        )
        return {
            str(row["plot_code"]): PlotQualityMetrics(
                geometry_valid=bool(row["geometry_valid"]),
                ring_closed=bool(row["ring_closed"]),
                calculated_area_ha=float(row["calculated_area_ha"]),
                overlap_count=int(row["overlap_count"]),
                overlap_area_ha=float(row["overlap_area_ha"]),
                within_district=bool(row["within_district"]),
                has_imagery=bool(row["has_imagery"]),
                covered_by_imagery=bool(row["covered_by_imagery"]),
                imagery_resolution_m=(
                    float(row["imagery_resolution_m"])
                    if row["imagery_resolution_m"] is not None
                    else None
                ),
            )
            for row in rows
        }

    async def upsert_plot_quality_check(
        self,
        db: AsyncSession,
        *,
        task_id: int,
        plot_code: str,
        plot_version: int,
        score: int,
        can_submit: bool,
        rules: list[dict[str, object]],
    ) -> None:
        """保存指定图斑版本的最近一次质量检查结果。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            plot_code: 图斑编号。
            plot_version: 接受检查的图斑版本。
            score: 质量得分。
            can_submit: 当前图斑是否通过质量门禁。
            rules: 结构化规则结果。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            text(
                """
                INSERT INTO plot_quality_checks (
                    task_id, plot_code, plot_version, score,
                    can_submit, rules, checked_at
                ) VALUES (
                    :task_id, :plot_code, :plot_version, :score,
                    :can_submit, CAST(:rules AS JSONB), NOW()
                )
                ON CONFLICT (task_id, plot_code) DO UPDATE SET
                    plot_version = EXCLUDED.plot_version,
                    score = EXCLUDED.score,
                    can_submit = EXCLUDED.can_submit,
                    rules = EXCLUDED.rules,
                    checked_at = NOW()
                """
            ),
            {
                "task_id": task_id,
                "plot_code": plot_code,
                "plot_version": plot_version,
                "score": score,
                "can_submit": can_submit,
                "rules": json.dumps(rules, ensure_ascii=False),
            },
        )

    async def upsert_plot_quality_checks(
        self,
        db: AsyncSession,
        checks: list[dict[str, object]],
    ) -> None:
        """批量保存任务图斑最近一次质量检查结果。

        Args:
            db: 异步数据库会话。
            checks: 已序列化的图斑检查结果。

        Returns:
            None: 无返回值。
        """
        if not checks:
            return
        statement = text(
            """
            INSERT INTO plot_quality_checks (
                task_id, plot_code, plot_version, score,
                can_submit, rules, checked_at
            ) VALUES (
                :task_id, :plot_code, :plot_version, :score,
                :can_submit, CAST(:rules AS JSONB), NOW()
            )
            ON CONFLICT (task_id, plot_code) DO UPDATE SET
                plot_version = EXCLUDED.plot_version,
                score = EXCLUDED.score,
                can_submit = EXCLUDED.can_submit,
                rules = EXCLUDED.rules,
                checked_at = NOW()
            """
        )
        parameters = [
            {
                **check,
                "rules": json.dumps(check["rules"], ensure_ascii=False),
            }
            for check in checks
        ]
        await db.execute(statement, parameters)

    async def get_quality_gate_summary(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> QualityGateSummary:
        """汇总当前有效图斑版本的质量检查覆盖率和通过率。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            QualityGateSummary: 总数、已检查数、通过数和平均分。
        """
        statement = text(
            """
            SELECT
                COUNT(plot.id) AS total_count,
                COUNT(check_result.id) AS checked_count,
                COUNT(check_result.id) FILTER (
                    WHERE check_result.can_submit
                ) AS passing_count,
                AVG(check_result.score) AS average_score
            FROM farmland_plots AS plot
            JOIN task_plots AS scope
              ON scope.plot_code = plot.plot_code
             AND scope.task_id = :task_id
            LEFT JOIN plot_quality_checks AS check_result
              ON check_result.task_id = :task_id
             AND check_result.plot_code = plot.plot_code
             AND check_result.plot_version = plot.version
            WHERE plot.interpretation_status != 'deleted'
            """
        )
        row = (await db.execute(statement, {"task_id": task_id})).mappings().one()
        return QualityGateSummary(
            total_count=int(row["total_count"]),
            checked_count=int(row["checked_count"]),
            passing_count=int(row["passing_count"]),
            average_score=(
                float(row["average_score"])
                if row["average_score"] is not None
                else None
            ),
        )

    async def clear_auto_issues(
        self,
        db: AsyncSession,
        task_id: int,
        plot_code: str,
    ) -> None:
        """将图斑上一次自动检查产生的未关闭问题标记为已解决。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            plot_code: 图斑编号。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            update(QualityIssue)
            .where(
                QualityIssue.task_id == task_id,
                QualityIssue.plot_code == plot_code,
                QualityIssue.source == "auto",
                QualityIssue.issue_type == "quality_rule",
                QualityIssue.status == "open",
            )
            .values(status="resolved", resolved_at=func.now())
        )

    async def clear_task_quality_issues(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> None:
        """关闭任务上一次全量质检产生的未解决规则问题。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            update(QualityIssue)
            .where(
                QualityIssue.task_id == task_id,
                QualityIssue.source == "auto",
                QualityIssue.issue_type == "quality_rule",
                QualityIssue.status == "open",
            )
            .values(status="resolved", resolved_at=func.now())
        )

    async def resolve_plot_quality_rules(
        self,
        db: AsyncSession,
        task_id: int,
        plot_codes: list[str],
        rule_codes: list[str],
    ) -> None:
        """关闭显式属性整改已确定修复的自动规则问题。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            plot_codes: 已完成属性整改的图斑编号。
            rule_codes: 可由本次属性赋值确定修复的规则编码。

        Returns:
            None: 无返回值。
        """
        if not plot_codes or not rule_codes:
            return
        await db.execute(
            update(QualityIssue)
            .where(
                QualityIssue.task_id == task_id,
                QualityIssue.plot_code.in_(plot_codes),
                QualityIssue.rule_code.in_(rule_codes),
                QualityIssue.issue_type == "quality_rule",
                QualityIssue.source == "auto",
                QualityIssue.status == "open",
            )
            .values(status="resolved", resolved_at=func.now())
        )

    async def add_quality_issues(
        self,
        db: AsyncSession,
        issues: list[QualityIssue],
    ) -> None:
        """批量写入质量问题。

        Args:
            db: 异步数据库会话。
            issues: 待写入问题列表。

        Returns:
            None: 无返回值。
        """
        db.add_all(issues)
        await db.flush()

    async def add_review_record(
        self,
        db: AsyncSession,
        record: ReviewRecord,
    ) -> ReviewRecord:
        """写入审核操作记录。

        Args:
            db: 异步数据库会话。
            record: 审核操作记录。

        Returns:
            ReviewRecord: 已写入记录。
        """
        db.add(record)
        await db.flush()
        await db.refresh(record)
        return record
