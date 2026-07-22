"""独立监理计划、抽样、检查、整改复检和报告数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.plot import FarmlandPlot
from app.models.supervision import (
    SupervisionCountyEvaluation,
    SupervisionEvent,
    SupervisionFinding,
    SupervisionInspection,
    SupervisionPlan,
    SupervisionReinspection,
    SupervisionReport,
    SupervisionSample,
)
from app.models.workbench import AdministrativeBoundary, TaskPlot


class SupervisionDAO:
    """封装独立监理任务作用域查询和持久化操作。"""

    async def list_work_areas(
        self,
        db: AsyncSession,
        project_id: int,
        task_id: int,
    ) -> list[RowMapping]:
        """按真实县区统计任务图斑数量和面积。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            task_id: 任务主键。

        Returns:
            list[RowMapping]: 地级区域、县区和任务图斑统计。
        """
        city = aliased(AdministrativeBoundary)
        district = aliased(AdministrativeBoundary)
        task_scope = (
            select(
                FarmlandPlot.district_code.label("region_code"),
                func.count(FarmlandPlot.plot_code).label("plot_count"),
                func.coalesce(func.sum(FarmlandPlot.area_ha), 0).label("area_ha"),
            )
            .join(
                TaskPlot,
                (TaskPlot.plot_code == FarmlandPlot.plot_code)
                & (TaskPlot.task_id == task_id),
            )
            .where(FarmlandPlot.interpretation_status != "deleted")
            .group_by(FarmlandPlot.district_code)
            .subquery()
        )
        result = await db.execute(
            select(
                city.boundary_code.label("city_code"),
                city.boundary_name.label("city_name"),
                district.boundary_code.label("region_code"),
                district.boundary_name.label("region_name"),
                func.coalesce(task_scope.c.plot_count, 0).label("plot_count"),
                func.coalesce(task_scope.c.area_ha, 0).label("area_ha"),
            )
            .join(city, city.boundary_code == district.parent_code)
            .outerjoin(
                task_scope,
                task_scope.c.region_code == district.boundary_code,
            )
            .where(
                district.project_id == project_id,
                district.boundary_level == "district",
                city.project_id == project_id,
                city.boundary_level == "city",
            )
            .order_by(city.boundary_code, district.boundary_code)
        )
        return list(result.mappings().all())

    async def list_candidate_plots(
        self,
        db: AsyncSession,
        task_id: int,
        region_codes: list[str],
    ) -> list[RowMapping]:
        """读取所选县区内任务真实图斑身份和版本，不加载完整几何。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            region_codes: 明确选择的县区编码。

        Returns:
            list[RowMapping]: 图斑编号、县区和版本快照候选。
        """
        result = await db.execute(
            select(
                FarmlandPlot.plot_code,
                FarmlandPlot.district_code.label("region_code"),
                FarmlandPlot.district_name.label("region_name"),
                FarmlandPlot.version.label("plot_version"),
            )
            .join(
                TaskPlot,
                (TaskPlot.plot_code == FarmlandPlot.plot_code)
                & (TaskPlot.task_id == task_id),
            )
            .where(
                FarmlandPlot.interpretation_status != "deleted",
                FarmlandPlot.district_code.in_(region_codes),
            )
            .order_by(FarmlandPlot.district_code, FarmlandPlot.plot_code)
        )
        return list(result.mappings().all())

    async def count_task_plots(self, db: AsyncSession, task_id: int) -> int:
        """统计任务显式图斑数量。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            int: 任务图斑数。
        """
        result = await db.execute(
            select(func.count(TaskPlot.id)).where(TaskPlot.task_id == task_id)
        )
        return int(result.scalar_one())

    async def get_plan_by_code(
        self,
        db: AsyncSession,
        task_id: int,
        plan_code: str,
        *,
        for_update: bool = False,
    ) -> SupervisionPlan | None:
        """按任务和计划编号查询监理计划。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            plan_code: 监理计划编号。
            for_update: 是否锁定计划行。

        Returns:
            SupervisionPlan | None: 未找到时返回 None。
        """
        statement = select(SupervisionPlan).where(
            SupervisionPlan.task_id == task_id,
            SupervisionPlan.plan_code == plan_code,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def list_plans(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[SupervisionPlan]:
        """查询任务全部监理计划。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            Sequence[SupervisionPlan]: 按创建时间倒序的计划。
        """
        result = await db.execute(
            select(SupervisionPlan)
            .where(SupervisionPlan.task_id == task_id)
            .order_by(SupervisionPlan.created_at.desc())
        )
        return result.scalars().all()

    async def add_plan(
        self,
        db: AsyncSession,
        plan: SupervisionPlan,
    ) -> SupervisionPlan:
        """新增监理计划。

        Args:
            db: 异步数据库会话。
            plan: 待写入计划。

        Returns:
            SupervisionPlan: 已刷新主键的计划。
        """
        db.add(plan)
        await db.flush()
        return plan

    async def add_samples(
        self,
        db: AsyncSession,
        samples: list[SupervisionSample],
    ) -> None:
        """批量写入显式监理样本。

        Args:
            db: 异步数据库会话。
            samples: 样本模型列表。

        Returns:
            None: 无返回值。
        """
        db.add_all(samples)
        await db.flush()

    async def list_sample_counts(
        self,
        db: AsyncSession,
        plan_id: int,
    ) -> list[RowMapping]:
        """按县区聚合计划样本数。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。

        Returns:
            list[RowMapping]: 县区编码和样本数。
        """
        result = await db.execute(
            select(
                SupervisionSample.region_code,
                func.count(SupervisionSample.id).label("sample_count"),
            )
            .where(SupervisionSample.plan_id == plan_id)
            .group_by(SupervisionSample.region_code)
        )
        return list(result.mappings().all())

    async def list_samples(
        self,
        db: AsyncSession,
        plan_id: int,
    ) -> Sequence[SupervisionSample]:
        """读取计划完整样本身份用于问题关联和报告，不返回完整几何。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。

        Returns:
            Sequence[SupervisionSample]: 显式样本身份列表。
        """
        result = await db.execute(
            select(SupervisionSample)
            .where(SupervisionSample.plan_id == plan_id)
            .order_by(
                SupervisionSample.region_code,
                SupervisionSample.selection_rank,
            )
        )
        return result.scalars().all()

    async def list_samples_page(
        self,
        db: AsyncSession,
        plan_id: int,
        page: int,
        page_size: int,
        region_code: str | None,
    ) -> tuple[int, Sequence[SupervisionSample]]:
        """分页查询显式监理样本，禁止概览静默截断。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。
            page: 页码。
            page_size: 每页数量。
            region_code: 可选县区筛选。

        Returns:
            tuple[int, Sequence[SupervisionSample]]: 总数和当前页样本。
        """
        conditions = [SupervisionSample.plan_id == plan_id]
        if region_code:
            conditions.append(SupervisionSample.region_code == region_code)
        total_result = await db.execute(
            select(func.count(SupervisionSample.id)).where(*conditions)
        )
        result = await db.execute(
            select(SupervisionSample)
            .where(*conditions)
            .order_by(
                SupervisionSample.region_code,
                SupervisionSample.selection_rank,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return int(total_result.scalar_one()), result.scalars().all()

    async def get_sample_by_plot_code(
        self,
        db: AsyncSession,
        plan_id: int,
        plot_code: str,
    ) -> SupervisionSample | None:
        """校验问题关联图斑属于当前监理抽样。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。
            plot_code: 图斑编号。

        Returns:
            SupervisionSample | None: 未抽样时返回 None。
        """
        result = await db.execute(
            select(SupervisionSample).where(
                SupervisionSample.plan_id == plan_id,
                SupervisionSample.plot_code == plot_code,
            )
        )
        return result.scalar_one_or_none()

    async def add_inspection(
        self,
        db: AsyncSession,
        inspection: SupervisionInspection,
    ) -> SupervisionInspection:
        """新增过程检查。

        Args:
            db: 异步数据库会话。
            inspection: 检查模型。

        Returns:
            SupervisionInspection: 已写入检查。
        """
        db.add(inspection)
        await db.flush()
        return inspection

    async def get_inspection_by_code(
        self,
        db: AsyncSession,
        plan_id: int,
        inspection_code: str,
    ) -> SupervisionInspection | None:
        """按计划查询过程检查。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。
            inspection_code: 检查编号。

        Returns:
            SupervisionInspection | None: 未找到时返回 None。
        """
        result = await db.execute(
            select(SupervisionInspection).where(
                SupervisionInspection.plan_id == plan_id,
                SupervisionInspection.inspection_code == inspection_code,
            )
        )
        return result.scalar_one_or_none()

    async def list_inspections(
        self,
        db: AsyncSession,
        plan_id: int,
    ) -> Sequence[SupervisionInspection]:
        """查询计划全部过程检查。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。

        Returns:
            Sequence[SupervisionInspection]: 检查列表。
        """
        result = await db.execute(
            select(SupervisionInspection)
            .where(SupervisionInspection.plan_id == plan_id)
            .order_by(SupervisionInspection.inspected_at.desc())
        )
        return result.scalars().all()

    async def add_finding(
        self,
        db: AsyncSession,
        finding: SupervisionFinding,
    ) -> SupervisionFinding:
        """新增监理问题。

        Args:
            db: 异步数据库会话。
            finding: 问题模型。

        Returns:
            SupervisionFinding: 已写入问题。
        """
        db.add(finding)
        await db.flush()
        return finding

    async def list_findings(
        self,
        db: AsyncSession,
        plan_id: int,
    ) -> Sequence[SupervisionFinding]:
        """查询计划全部监理问题。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。

        Returns:
            Sequence[SupervisionFinding]: 问题列表。
        """
        result = await db.execute(
            select(SupervisionFinding)
            .join(
                SupervisionInspection,
                SupervisionInspection.id == SupervisionFinding.inspection_id,
            )
            .where(SupervisionInspection.plan_id == plan_id)
            .order_by(SupervisionFinding.created_at.desc())
        )
        return result.scalars().all()

    async def get_finding_by_code_for_update(
        self,
        db: AsyncSession,
        plan_id: int,
        finding_code: str,
    ) -> SupervisionFinding | None:
        """锁定当前计划下的监理问题。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。
            finding_code: 问题编号。

        Returns:
            SupervisionFinding | None: 未找到时返回 None。
        """
        result = await db.execute(
            select(SupervisionFinding)
            .join(
                SupervisionInspection,
                SupervisionInspection.id == SupervisionFinding.inspection_id,
            )
            .where(
                SupervisionInspection.plan_id == plan_id,
                SupervisionFinding.finding_code == finding_code,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def add_reinspection(
        self,
        db: AsyncSession,
        reinspection: SupervisionReinspection,
    ) -> SupervisionReinspection:
        """新增不可变复检轮次。

        Args:
            db: 异步数据库会话。
            reinspection: 复检模型。

        Returns:
            SupervisionReinspection: 已写入复检记录。
        """
        db.add(reinspection)
        await db.flush()
        return reinspection

    async def list_reinspections(
        self,
        db: AsyncSession,
        finding_ids: list[int],
    ) -> Sequence[SupervisionReinspection]:
        """批量查询问题复检历史。

        Args:
            db: 异步数据库会话。
            finding_ids: 问题主键列表。

        Returns:
            Sequence[SupervisionReinspection]: 全部复检轮次。
        """
        if not finding_ids:
            return []
        result = await db.execute(
            select(SupervisionReinspection)
            .where(SupervisionReinspection.finding_id.in_(finding_ids))
            .order_by(
                SupervisionReinspection.finding_id,
                SupervisionReinspection.round_no,
            )
        )
        return result.scalars().all()

    async def count_reinspections(
        self,
        db: AsyncSession,
        finding_id: int,
    ) -> int:
        """统计问题已有复检轮次。

        Args:
            db: 异步数据库会话。
            finding_id: 问题主键。

        Returns:
            int: 已有复检轮次。
        """
        result = await db.execute(
            select(func.count(SupervisionReinspection.id)).where(
                SupervisionReinspection.finding_id == finding_id
            )
        )
        return int(result.scalar_one())

    async def get_evaluation_for_update(
        self,
        db: AsyncSession,
        plan_id: int,
        region_code: str,
    ) -> SupervisionCountyEvaluation | None:
        """锁定县区监理评价以支持显式更新审计。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。
            region_code: 县区编码。

        Returns:
            SupervisionCountyEvaluation | None: 尚未评价时返回 None。
        """
        result = await db.execute(
            select(SupervisionCountyEvaluation)
            .where(
                SupervisionCountyEvaluation.plan_id == plan_id,
                SupervisionCountyEvaluation.region_code == region_code,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def add_evaluation(
        self,
        db: AsyncSession,
        evaluation: SupervisionCountyEvaluation,
    ) -> SupervisionCountyEvaluation:
        """新增县区监理评价。

        Args:
            db: 异步数据库会话。
            evaluation: 县区评价模型。

        Returns:
            SupervisionCountyEvaluation: 已写入评价。
        """
        db.add(evaluation)
        await db.flush()
        return evaluation

    async def list_evaluations(
        self,
        db: AsyncSession,
        plan_id: int,
    ) -> Sequence[SupervisionCountyEvaluation]:
        """查询计划县区评价。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。

        Returns:
            Sequence[SupervisionCountyEvaluation]: 县区评价列表。
        """
        result = await db.execute(
            select(SupervisionCountyEvaluation)
            .where(SupervisionCountyEvaluation.plan_id == plan_id)
            .order_by(SupervisionCountyEvaluation.region_code)
        )
        return result.scalars().all()

    async def get_report(
        self,
        db: AsyncSession,
        plan_id: int,
    ) -> SupervisionReport | None:
        """查询计划不可变报告。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。

        Returns:
            SupervisionReport | None: 未生成时返回 None。
        """
        result = await db.execute(
            select(SupervisionReport).where(SupervisionReport.plan_id == plan_id)
        )
        return result.scalar_one_or_none()

    async def get_report_by_code(
        self,
        db: AsyncSession,
        task_id: int,
        report_code: str,
    ) -> SupervisionReport | None:
        """按任务和报告编号查询实体报告。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            report_code: 报告编号。

        Returns:
            SupervisionReport | None: 未找到时返回 None。
        """
        result = await db.execute(
            select(SupervisionReport)
            .join(SupervisionPlan, SupervisionPlan.id == SupervisionReport.plan_id)
            .where(
                SupervisionPlan.task_id == task_id,
                SupervisionReport.report_code == report_code,
            )
        )
        return result.scalar_one_or_none()

    async def add_report(
        self,
        db: AsyncSession,
        report: SupervisionReport,
    ) -> SupervisionReport:
        """新增不可变监理报告记录。

        Args:
            db: 异步数据库会话。
            report: 报告模型。

        Returns:
            SupervisionReport: 已写入报告。
        """
        db.add(report)
        await db.flush()
        return report

    async def add_event(
        self,
        db: AsyncSession,
        event: SupervisionEvent,
    ) -> SupervisionEvent:
        """写入监理不可变事件。

        Args:
            db: 异步数据库会话。
            event: 事件模型。

        Returns:
            SupervisionEvent: 已写入事件。
        """
        db.add(event)
        await db.flush()
        return event

    async def list_recent_events(
        self,
        db: AsyncSession,
        plan_id: int,
        limit: int = 100,
    ) -> Sequence[SupervisionEvent]:
        """查询工作台最近事件，完整历史由报告清单保留。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。
            limit: 工作台最大事件数。

        Returns:
            Sequence[SupervisionEvent]: 最近事件。
        """
        result = await db.execute(
            select(SupervisionEvent)
            .where(SupervisionEvent.plan_id == plan_id)
            .order_by(SupervisionEvent.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def list_all_events(
        self,
        db: AsyncSession,
        plan_id: int,
    ) -> Sequence[SupervisionEvent]:
        """为不可变报告读取完整监理事件历史。

        Args:
            db: 异步数据库会话。
            plan_id: 计划主键。

        Returns:
            Sequence[SupervisionEvent]: 全部事件。
        """
        result = await db.execute(
            select(SupervisionEvent)
            .where(SupervisionEvent.plan_id == plan_id)
            .order_by(SupervisionEvent.created_at)
        )
        return result.scalars().all()
