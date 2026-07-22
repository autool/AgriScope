"""独立监理抽样、过程检查、整改复检、县区评价和报告业务服务。"""

import asyncio
import json
import math
import os
import secrets
from collections import defaultdict
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.supervision_dao import SupervisionDAO
from app.dao.workbench_dao import WorkbenchDAO
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
from app.schemas.supervision import (
    SupervisionCountyEvaluationRequest,
    SupervisionCountyEvaluationResponse,
    SupervisionEventResponse,
    SupervisionFindingCreateRequest,
    SupervisionFindingResponse,
    SupervisionInspectionCreateRequest,
    SupervisionInspectionResponse,
    SupervisionMetricsResponse,
    SupervisionOverviewResponse,
    SupervisionPlanCreateRequest,
    SupervisionPlanResponse,
    SupervisionRectificationRequest,
    SupervisionReinspectionRequest,
    SupervisionReinspectionResponse,
    SupervisionReportGenerateRequest,
    SupervisionReportResponse,
    SupervisionSamplePageResponse,
    SupervisionSampleResponse,
    SupervisionWorkAreaResponse,
)
from app.services.project_user_service import ProjectUserService

MAX_PLAN_SAMPLES = 5000


class SupervisionService:
    """编排与质检、三级审核相互独立的项目监理闭环。"""

    def __init__(
        self,
        dao: SupervisionDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        user_service: ProjectUserService | None = None,
    ) -> None:
        """初始化独立监理服务。

        Args:
            dao: 监理数据访问对象。
            workbench_dao: 项目任务公共数据访问对象。
            user_service: 项目用户能力服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or SupervisionDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.user_service = user_service or ProjectUserService()
        self.storage_root = (
            Path(__file__).resolve().parents[2] / "storage" / "supervision"
        )

    async def _resolve_context(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
    ) -> tuple[object, object]:
        """解析项目任务并验证归属关系。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。

        Returns:
            tuple[object, object]: 项目和任务 ORM 对象。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None or task.project_id != project.id:
            raise NotFoundException(f"项目内未找到任务 {task_code}")
        return project, task

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        """临时写入后原子替换不可变监理报告。

        Args:
            path: 最终报告路径。
            content: 报告字节。

        Returns:
            None: 无返回值。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.part")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _select_region_candidates(
        candidates: list[object],
        plan_code: str,
        sampling_method: str,
        target_count: int,
    ) -> list[object]:
        """按县区执行可复现的系统抽样或分层随机抽样。

        Args:
            candidates: 同一县区候选图斑身份行。
            plan_code: 作为随机化盐值的计划编号。
            sampling_method: 系统抽样或分层随机抽样。
            target_count: 该县区需要抽取的数量。

        Returns:
            list[object]: 按选择顺序排列的候选行。
        """
        if target_count >= len(candidates):
            return list(candidates)
        if sampling_method == "stratified_random":
            ranked = sorted(
                candidates,
                key=lambda row: sha256(
                    f"{plan_code}:{row['plot_code']}".encode()
                ).hexdigest(),
            )
            return ranked[:target_count]
        interval = len(candidates) / target_count
        indexes = [
            min(len(candidates) - 1, math.floor((index + 0.5) * interval))
            for index in range(target_count)
        ]
        return [candidates[index] for index in indexes]

    @staticmethod
    def _grade(overall_score: float) -> str:
        """按量化总分计算县区监理等级。

        Args:
            overall_score: 0–100 综合得分。

        Returns:
            str: A、B、C 或 D 等级。
        """
        if overall_score >= 90:
            return "A"
        if overall_score >= 80:
            return "B"
        if overall_score >= 70:
            return "C"
        return "D"

    @staticmethod
    def _event_response(event: SupervisionEvent) -> SupervisionEventResponse:
        """转换监理事件响应。

        Args:
            event: 事件 ORM 对象。

        Returns:
            SupervisionEventResponse: 类型化事件响应。
        """
        return SupervisionEventResponse(
            entity_type=event.entity_type,
            entity_code=event.entity_code,
            action=event.action,
            previous_values=event.previous_values or {},
            new_values=event.new_values or {},
            comment=event.comment,
            operator=event.operator,
            operator_code=event.operator_code,
            operator_role=event.operator_role,
            created_at=event.created_at,
        )

    @staticmethod
    def _report_response(report: SupervisionReport) -> SupervisionReportResponse:
        """转换不可变监理报告响应。

        Args:
            report: 报告 ORM 对象。

        Returns:
            SupervisionReportResponse: 报告证据和下载地址。
        """
        return SupervisionReportResponse(
            report_code=report.report_code,
            file_uri=report.file_uri,
            file_size_bytes=report.file_size_bytes,
            checksum_sha256=report.checksum_sha256,
            evidence_manifest=report.evidence_manifest or {},
            generated_by=report.generated_by,
            generated_by_code=report.generated_by_code,
            generated_by_role=report.generated_by_role,
            generated_at=report.generated_at,
            download_url=(
                f"/api/v1/supervision/reports/{report.report_code}/download"
            ),
        )

    async def _build_plan_response(
        self,
        db: AsyncSession,
        plan: SupervisionPlan,
        *,
        complete_events: bool = False,
    ) -> SupervisionPlanResponse:
        """聚合计划样本、检查、问题、复检、评价和报告。

        Args:
            db: 异步数据库会话。
            plan: 监理计划。
            complete_events: 是否读取完整事件用于实体报告。

        Returns:
            SupervisionPlanResponse: 计划聚合响应。
        """
        samples = await self.dao.list_samples(db, plan.id)
        inspections = await self.dao.list_inspections(db, plan.id)
        findings = await self.dao.list_findings(db, plan.id)
        reinspections = await self.dao.list_reinspections(
            db,
            [finding.id for finding in findings],
        )
        evaluations = await self.dao.list_evaluations(db, plan.id)
        report = await self.dao.get_report(db, plan.id)
        events = (
            await self.dao.list_all_events(db, plan.id)
            if complete_events
            else await self.dao.list_recent_events(db, plan.id)
        )

        sample_by_id = {sample.id: sample for sample in samples}
        region_sample_counts: dict[str, int] = defaultdict(int)
        for sample in samples:
            region_sample_counts[sample.region_code] += 1
        reinspections_by_finding: dict[int, list[SupervisionReinspectionResponse]] = (
            defaultdict(list)
        )
        for item in reinspections:
            reinspections_by_finding[item.finding_id].append(
                SupervisionReinspectionResponse(
                    round_no=item.round_no,
                    result=item.result,
                    comment=item.comment,
                    evidence_uri=item.evidence_uri,
                    inspector=item.inspector,
                    inspector_code=item.inspector_code,
                    inspector_role=item.inspector_role,
                    created_at=item.created_at,
                )
            )
        findings_by_inspection: dict[int, list[SupervisionFindingResponse]] = (
            defaultdict(list)
        )
        today = date.today()
        for finding in findings:
            sample = sample_by_id.get(finding.sample_id) if finding.sample_id else None
            findings_by_inspection[finding.inspection_id].append(
                SupervisionFindingResponse(
                    finding_code=finding.finding_code,
                    plot_code=sample.plot_code if sample else None,
                    region_code=finding.region_code,
                    region_name=finding.region_name,
                    issue_type=finding.issue_type,
                    severity=finding.severity,
                    description=finding.description,
                    evidence_uri=finding.evidence_uri,
                    rework_deadline=finding.rework_deadline,
                    overdue=(
                        finding.status != "closed"
                        and finding.rework_deadline < today
                    ),
                    status=finding.status,
                    rectification_comment=finding.rectification_comment,
                    rectification_evidence_uri=(
                        finding.rectification_evidence_uri
                    ),
                    rectified_by=finding.rectified_by,
                    rectified_by_code=finding.rectified_by_code,
                    rectified_by_role=finding.rectified_by_role,
                    rectified_at=finding.rectified_at,
                    created_by=finding.created_by,
                    created_by_code=finding.created_by_code,
                    created_by_role=finding.created_by_role,
                    created_at=finding.created_at,
                    reinspections=reinspections_by_finding.get(finding.id, []),
                )
            )
        inspection_responses = [
            SupervisionInspectionResponse(
                inspection_code=inspection.inspection_code,
                inspection_stage=inspection.inspection_stage,
                inspected_at=inspection.inspected_at,
                conclusion=inspection.conclusion,
                evidence_uri=inspection.evidence_uri,
                summary=inspection.summary,
                inspector=inspection.inspector,
                inspector_code=inspection.inspector_code,
                inspector_role=inspection.inspector_role,
                created_at=inspection.created_at,
                findings=findings_by_inspection.get(inspection.id, []),
            )
            for inspection in inspections
        ]
        evaluation_responses = [
            SupervisionCountyEvaluationResponse(
                region_code=item.region_code,
                region_name=item.region_name,
                quality_score=float(item.quality_score),
                timeliness_score=float(item.timeliness_score),
                compliance_score=float(item.compliance_score),
                overall_score=float(item.overall_score),
                grade=item.grade,
                comment=item.comment,
                evaluated_by=item.evaluated_by,
                evaluated_by_code=item.evaluated_by_code,
                evaluated_by_role=item.evaluated_by_role,
                evaluated_at=item.evaluated_at,
            )
            for item in evaluations
        ]
        open_findings = [item for item in findings if item.status != "closed"]
        overdue_count = sum(
            1 for item in open_findings if item.rework_deadline < today
        )
        return SupervisionPlanResponse(
            plan_code=plan.plan_code,
            plan_name=plan.plan_name,
            sampling_method=plan.sampling_method,
            sample_ratio=float(plan.sample_ratio),
            minimum_per_region=plan.minimum_per_region,
            region_codes=plan.region_codes or [],
            region_sample_counts=dict(region_sample_counts),
            sample_count=len(samples),
            task_plot_count_snapshot=plan.task_plot_count_snapshot,
            task_updated_at_snapshot=plan.task_updated_at_snapshot,
            planned_start_date=plan.planned_start_date,
            planned_end_date=plan.planned_end_date,
            status=plan.status,
            inspection_count=len(inspections),
            finding_count=len(findings),
            open_finding_count=len(open_findings),
            overdue_finding_count=overdue_count,
            evaluation_count=len(evaluations),
            created_by=plan.created_by,
            created_by_code=plan.created_by_code,
            created_by_role=plan.created_by_role,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            inspections=inspection_responses,
            county_evaluations=evaluation_responses,
            report=self._report_response(report) if report else None,
            recent_events=[self._event_response(event) for event in events],
        )

    async def _require_current_plan_snapshot(
        self,
        db: AsyncSession,
        task: object,
        plan: SupervisionPlan,
    ) -> None:
        """阻止基础任务范围变化后继续追加旧计划证据。

        Args:
            db: 异步数据库会话。
            task: 当前任务 ORM 对象。
            plan: 监理计划。

        Returns:
            None: 快照一致时无返回值。
        """
        current_count = await self.dao.count_task_plots(db, task.id)
        if (
            current_count != plan.task_plot_count_snapshot
            or task.updated_at != plan.task_updated_at_snapshot
        ):
            raise ValidationException(
                "任务图斑范围或数据版本已变化，请创建新的独立监理计划"
            )

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
    ) -> SupervisionOverviewResponse:
        """查询独立监理真实工作区、计划和闭环证据。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。

        Returns:
            SupervisionOverviewResponse: 独立监理工作台状态。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        work_area_rows = await self.dao.list_work_areas(db, project.id, task.id)
        work_areas = [
            SupervisionWorkAreaResponse(
                city_code=row["city_code"],
                city_name=row["city_name"],
                region_code=row["region_code"],
                region_name=row["region_name"],
                plot_count=int(row["plot_count"] or 0),
                area_ha=float(row["area_ha"] or 0),
            )
            for row in work_area_rows
        ]
        plans = [
            await self._build_plan_response(db, plan)
            for plan in await self.dao.list_plans(db, task.id)
        ]
        blockers: list[str] = []
        if not any(item.plot_count > 0 for item in work_areas):
            blockers.append("当前任务没有可供独立监理抽样的真实图斑")
        if not plans:
            blockers.append("尚未创建独立监理抽样计划")
        return SupervisionOverviewResponse(
            project_code=project_code,
            task_code=task_code,
            blockers=blockers,
            metrics=SupervisionMetricsResponse(
                plan_count=len(plans),
                active_plan_count=sum(
                    1 for plan in plans if plan.status == "active"
                ),
                sampled_plot_count=sum(plan.sample_count for plan in plans),
                inspection_count=sum(plan.inspection_count for plan in plans),
                open_finding_count=sum(
                    plan.open_finding_count for plan in plans
                ),
                overdue_finding_count=sum(
                    plan.overdue_finding_count for plan in plans
                ),
                completed_report_count=sum(
                    1 for plan in plans if plan.report is not None
                ),
            ),
            work_areas=work_areas,
            plans=plans,
        )

    async def create_plan(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: SupervisionPlanCreateRequest,
    ) -> SupervisionPlanResponse:
        """按县区从任务真实图斑创建可复现抽样计划。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            request: 抽样方法、比例、县区和操作审计。

        Returns:
            SupervisionPlanResponse: 新建计划及显式样本统计。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        supervisor = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "supervise_project",
        )
        existing = await self.dao.get_plan_by_code(
            db,
            task.id,
            request.plan_code,
        )
        if existing is not None:
            raise ValidationException(f"监理计划编号 {request.plan_code} 已存在")
        work_area_rows = await self.dao.list_work_areas(db, project.id, task.id)
        work_area_by_code = {row["region_code"]: row for row in work_area_rows}
        invalid_regions = [
            code
            for code in request.region_codes
            if code not in work_area_by_code
            or int(work_area_by_code[code]["plot_count"] or 0) <= 0
        ]
        if invalid_regions:
            raise ValidationException(
                f"所选县区没有任务真实图斑：{', '.join(invalid_regions)}"
            )
        candidates = await self.dao.list_candidate_plots(
            db,
            task.id,
            request.region_codes,
        )
        candidates_by_region: dict[str, list[object]] = defaultdict(list)
        for row in candidates:
            candidates_by_region[row["region_code"]].append(row)
        selected_rows: list[tuple[object, int]] = []
        for region_code in request.region_codes:
            region_candidates = candidates_by_region[region_code]
            target_count = min(
                len(region_candidates),
                max(
                    request.minimum_per_region,
                    math.ceil(len(region_candidates) * request.sample_ratio / 100),
                ),
            )
            selected = self._select_region_candidates(
                region_candidates,
                request.plan_code,
                request.sampling_method,
                target_count,
            )
            selected_rows.extend(
                (row, rank) for rank, row in enumerate(selected, start=1)
            )
        if not selected_rows:
            raise ValidationException("当前范围未抽取到真实图斑样本")
        if len(selected_rows) > MAX_PLAN_SAMPLES:
            raise ValidationException(
                f"本次将抽取 {len(selected_rows)} 个样本，超过上限 "
                f"{MAX_PLAN_SAMPLES}，请降低抽样比例或减少县区"
            )
        task_plot_count = await self.dao.count_task_plots(db, task.id)
        now = datetime.now(UTC)
        plan = SupervisionPlan(
            project_id=project.id,
            task_id=task.id,
            plan_code=request.plan_code,
            plan_name=request.plan_name,
            sampling_method=request.sampling_method,
            sample_ratio=request.sample_ratio,
            minimum_per_region=request.minimum_per_region,
            region_codes=request.region_codes,
            task_plot_count_snapshot=task_plot_count,
            task_updated_at_snapshot=task.updated_at,
            planned_start_date=request.planned_start_date,
            planned_end_date=request.planned_end_date,
            status="active",
            created_by=supervisor.display_name,
            created_by_code=supervisor.user_code,
            created_by_role=supervisor.role_code,
            created_at=now,
            updated_at=now,
        )
        try:
            await self.dao.add_plan(db, plan)
            samples = [
                SupervisionSample(
                    plan_id=plan.id,
                    plot_code=row["plot_code"],
                    region_code=row["region_code"],
                    region_name=(
                        row["region_name"]
                        or work_area_by_code[row["region_code"]]["region_name"]
                    ),
                    plot_version_snapshot=int(row["plot_version"]),
                    selection_rank=rank,
                    selected_at=now,
                )
                for row, rank in selected_rows
            ]
            await self.dao.add_samples(db, samples)
            await self.dao.add_event(
                db,
                SupervisionEvent(
                    plan_id=plan.id,
                    entity_type="plan",
                    entity_code=plan.plan_code,
                    action="created",
                    previous_values={},
                    new_values={
                        "sampling_method": request.sampling_method,
                        "sample_ratio": request.sample_ratio,
                        "minimum_per_region": request.minimum_per_region,
                        "region_codes": request.region_codes,
                        "sample_count": len(samples),
                        "task_plot_count_snapshot": task_plot_count,
                        "task_updated_at_snapshot": task.updated_at.isoformat(),
                    },
                    comment=request.comment,
                    operator=supervisor.display_name,
                    operator_code=supervisor.user_code,
                    operator_role=supervisor.role_code,
                    created_at=now,
                ),
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException("监理计划编号或抽样图斑发生冲突") from exc
        return await self._build_plan_response(db, plan)

    async def list_samples(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        plan_code: str,
        page: int,
        page_size: int,
        region_code: str | None,
    ) -> SupervisionSamplePageResponse:
        """分页查询监理计划显式样本。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            plan_code: 计划编号。
            page: 页码。
            page_size: 每页数量。
            region_code: 可选县区编码。

        Returns:
            SupervisionSamplePageResponse: 完整计数和当前页样本。
        """
        _, task = await self._resolve_context(db, project_code, task_code)
        plan = await self.dao.get_plan_by_code(db, task.id, plan_code)
        if plan is None:
            raise NotFoundException(f"未找到监理计划 {plan_code}")
        if region_code and region_code not in (plan.region_codes or []):
            raise ValidationException("县区不属于当前监理计划")
        total, samples = await self.dao.list_samples_page(
            db,
            plan.id,
            page,
            page_size,
            region_code,
        )
        return SupervisionSamplePageResponse(
            plan_code=plan_code,
            total=total,
            page=page,
            page_size=page_size,
            items=[
                SupervisionSampleResponse(
                    plot_code=sample.plot_code,
                    region_code=sample.region_code,
                    region_name=sample.region_name,
                    plot_version_snapshot=sample.plot_version_snapshot,
                    selection_rank=sample.selection_rank,
                    selected_at=sample.selected_at,
                )
                for sample in samples
            ],
        )

    async def create_inspection(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        plan_code: str,
        request: SupervisionInspectionCreateRequest,
    ) -> SupervisionPlanResponse:
        """为当前计划登记独立过程检查。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            plan_code: 监理计划编号。
            request: 检查环节、结论、时间和证据。

        Returns:
            SupervisionPlanResponse: 更新后的计划。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        supervisor = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "supervise_project",
        )
        plan = await self.dao.get_plan_by_code(
            db,
            task.id,
            plan_code,
            for_update=True,
        )
        if plan is None:
            raise NotFoundException(f"未找到监理计划 {plan_code}")
        if plan.status != "active":
            raise ValidationException("已完成或取消的监理计划不能新增检查")
        await self._require_current_plan_snapshot(db, task, plan)
        if not (
            plan.planned_start_date
            <= request.inspected_at.date()
            <= plan.planned_end_date
        ):
            raise ValidationException("检查时间必须位于监理计划周期内")
        if await self.dao.get_inspection_by_code(
            db,
            plan.id,
            request.inspection_code,
        ):
            raise ValidationException("当前计划内检查编号已存在")
        inspection = SupervisionInspection(
            plan_id=plan.id,
            inspection_code=request.inspection_code,
            inspection_stage=request.inspection_stage,
            inspected_at=request.inspected_at,
            conclusion=request.conclusion,
            evidence_uri=request.evidence_uri,
            summary=request.summary,
            inspector=supervisor.display_name,
            inspector_code=supervisor.user_code,
            inspector_role=supervisor.role_code,
        )
        try:
            await self.dao.add_inspection(db, inspection)
            await self.dao.add_event(
                db,
                SupervisionEvent(
                    plan_id=plan.id,
                    entity_type="inspection",
                    entity_code=inspection.inspection_code,
                    action="created",
                    previous_values={},
                    new_values={
                        "inspection_stage": inspection.inspection_stage,
                        "inspected_at": inspection.inspected_at.isoformat(),
                        "conclusion": inspection.conclusion,
                        "evidence_uri": inspection.evidence_uri,
                    },
                    comment=inspection.summary,
                    operator=supervisor.display_name,
                    operator_code=supervisor.user_code,
                    operator_role=supervisor.role_code,
                ),
            )
            plan.updated_at = datetime.now(UTC)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException("当前计划内检查编号已存在") from exc
        return await self._build_plan_response(db, plan)

    async def create_finding(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        plan_code: str,
        inspection_code: str,
        request: SupervisionFindingCreateRequest,
    ) -> SupervisionPlanResponse:
        """在独立检查下登记问题证据和整改期限。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            plan_code: 监理计划编号。
            inspection_code: 过程检查编号。
            request: 问题、严重度、证据和期限。

        Returns:
            SupervisionPlanResponse: 更新后的计划。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        supervisor = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "supervise_project",
        )
        plan = await self.dao.get_plan_by_code(
            db,
            task.id,
            plan_code,
            for_update=True,
        )
        if plan is None:
            raise NotFoundException(f"未找到监理计划 {plan_code}")
        if plan.status != "active":
            raise ValidationException("已完成或取消的监理计划不能新增问题")
        await self._require_current_plan_snapshot(db, task, plan)
        inspection = await self.dao.get_inspection_by_code(
            db,
            plan.id,
            inspection_code,
        )
        if inspection is None:
            raise NotFoundException(f"未找到监理检查 {inspection_code}")
        if request.region_code not in (plan.region_codes or []):
            raise ValidationException("问题县区不属于当前监理计划")
        sample = None
        if request.plot_code:
            sample = await self.dao.get_sample_by_plot_code(
                db,
                plan.id,
                request.plot_code,
            )
            if sample is None:
                raise ValidationException("问题图斑不属于当前监理抽样")
            if sample.region_code != request.region_code:
                raise ValidationException("问题图斑与县区编码不一致")
        if request.rework_deadline < date.today():
            raise ValidationException("整改期限不得早于今天")
        work_areas = await self.dao.list_work_areas(db, project.id, task.id)
        region_names = {
            row["region_code"]: row["region_name"] for row in work_areas
        }
        region_name = region_names.get(request.region_code)
        if not region_name:
            raise ValidationException("未找到问题县区真实行政区信息")
        finding = SupervisionFinding(
            inspection_id=inspection.id,
            sample_id=sample.id if sample else None,
            finding_code=request.finding_code,
            region_code=request.region_code,
            region_name=region_name,
            issue_type=request.issue_type,
            severity=request.severity,
            description=request.description,
            evidence_uri=request.evidence_uri,
            rework_deadline=request.rework_deadline,
            status="open",
            created_by=supervisor.display_name,
            created_by_code=supervisor.user_code,
            created_by_role=supervisor.role_code,
        )
        try:
            await self.dao.add_finding(db, finding)
            await self.dao.add_event(
                db,
                SupervisionEvent(
                    plan_id=plan.id,
                    entity_type="finding",
                    entity_code=finding.finding_code,
                    action="created",
                    previous_values={},
                    new_values={
                        "inspection_code": inspection.inspection_code,
                        "plot_code": request.plot_code,
                        "region_code": finding.region_code,
                        "severity": finding.severity,
                        "status": finding.status,
                        "rework_deadline": finding.rework_deadline.isoformat(),
                        "evidence_uri": finding.evidence_uri,
                    },
                    comment=finding.description,
                    operator=supervisor.display_name,
                    operator_code=supervisor.user_code,
                    operator_role=supervisor.role_code,
                ),
            )
            plan.updated_at = datetime.now(UTC)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException("当前检查内问题编号已存在") from exc
        return await self._build_plan_response(db, plan)

    async def submit_rectification(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        plan_code: str,
        finding_code: str,
        request: SupervisionRectificationRequest,
    ) -> SupervisionPlanResponse:
        """由生产团队提交整改证据并等待独立复检。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            plan_code: 监理计划编号。
            finding_code: 问题编号。
            request: 整改说明、实体证据和操作人。

        Returns:
            SupervisionPlanResponse: 更新后的计划。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "rectify_supervision_finding",
        )
        plan = await self.dao.get_plan_by_code(
            db,
            task.id,
            plan_code,
            for_update=True,
        )
        if plan is None:
            raise NotFoundException(f"未找到监理计划 {plan_code}")
        if plan.status != "active":
            raise ValidationException("已完成或取消的监理计划不能提交整改")
        finding = await self.dao.get_finding_by_code_for_update(
            db,
            plan.id,
            finding_code,
        )
        if finding is None:
            raise NotFoundException(f"未找到监理问题 {finding_code}")
        if finding.status not in {"open", "rework_required"}:
            raise ValidationException("当前问题状态不允许重复提交整改")
        previous = {
            "status": finding.status,
            "rectification_comment": finding.rectification_comment,
            "rectification_evidence_uri": finding.rectification_evidence_uri,
        }
        now = datetime.now(UTC)
        finding.status = "rectification_submitted"
        finding.rectification_comment = request.rectification_comment
        finding.rectification_evidence_uri = request.rectification_evidence_uri
        finding.rectified_by = operator.display_name
        finding.rectified_by_code = operator.user_code
        finding.rectified_by_role = operator.role_code
        finding.rectified_at = now
        finding.updated_at = now
        await self.dao.add_event(
            db,
            SupervisionEvent(
                plan_id=plan.id,
                entity_type="finding",
                entity_code=finding.finding_code,
                action="rectification_submitted",
                previous_values=previous,
                new_values={
                    "status": finding.status,
                    "rectification_comment": finding.rectification_comment,
                    "rectification_evidence_uri": (
                        finding.rectification_evidence_uri
                    ),
                },
                comment=request.rectification_comment,
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
            ),
        )
        plan.updated_at = now
        await db.commit()
        return await self._build_plan_response(db, plan)

    async def reinspect_finding(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        plan_code: str,
        finding_code: str,
        request: SupervisionReinspectionRequest,
    ) -> SupervisionPlanResponse:
        """独立监理复检整改证据并形成不可覆盖轮次。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            plan_code: 监理计划编号。
            finding_code: 问题编号。
            request: 复检结论、证据和操作人。

        Returns:
            SupervisionPlanResponse: 更新后的计划。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        supervisor = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "supervise_project",
        )
        plan = await self.dao.get_plan_by_code(
            db,
            task.id,
            plan_code,
            for_update=True,
        )
        if plan is None:
            raise NotFoundException(f"未找到监理计划 {plan_code}")
        if plan.status != "active":
            raise ValidationException("已完成或取消的监理计划不能复检")
        finding = await self.dao.get_finding_by_code_for_update(
            db,
            plan.id,
            finding_code,
        )
        if finding is None:
            raise NotFoundException(f"未找到监理问题 {finding_code}")
        if finding.status != "rectification_submitted":
            raise ValidationException("仅已提交整改证据的问题允许复检")
        round_no = await self.dao.count_reinspections(db, finding.id) + 1
        previous_status = finding.status
        new_status = "closed" if request.result == "passed" else "rework_required"
        reinspection = SupervisionReinspection(
            finding_id=finding.id,
            round_no=round_no,
            result=request.result,
            comment=request.comment,
            evidence_uri=request.evidence_uri,
            inspector=supervisor.display_name,
            inspector_code=supervisor.user_code,
            inspector_role=supervisor.role_code,
        )
        await self.dao.add_reinspection(db, reinspection)
        finding.status = new_status
        finding.updated_at = datetime.now(UTC)
        await self.dao.add_event(
            db,
            SupervisionEvent(
                plan_id=plan.id,
                entity_type="finding",
                entity_code=finding.finding_code,
                action="reinspected",
                previous_values={"status": previous_status},
                new_values={
                    "status": new_status,
                    "round_no": round_no,
                    "result": request.result,
                    "evidence_uri": request.evidence_uri,
                },
                comment=request.comment,
                operator=supervisor.display_name,
                operator_code=supervisor.user_code,
                operator_role=supervisor.role_code,
            ),
        )
        plan.updated_at = datetime.now(UTC)
        await db.commit()
        return await self._build_plan_response(db, plan)

    async def evaluate_county(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        plan_code: str,
        region_code: str,
        request: SupervisionCountyEvaluationRequest,
    ) -> SupervisionPlanResponse:
        """新增或显式更新计划县区量化评价并保留修改前后值。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            plan_code: 监理计划编号。
            region_code: 县区编码。
            request: 三项评分、说明和操作人。

        Returns:
            SupervisionPlanResponse: 更新后的计划。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        supervisor = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "supervise_project",
        )
        plan = await self.dao.get_plan_by_code(
            db,
            task.id,
            plan_code,
            for_update=True,
        )
        if plan is None:
            raise NotFoundException(f"未找到监理计划 {plan_code}")
        if plan.status != "active":
            raise ValidationException("已完成或取消的监理计划不能修改评价")
        if region_code not in (plan.region_codes or []):
            raise ValidationException("县区不属于当前监理计划")
        work_areas = await self.dao.list_work_areas(db, project.id, task.id)
        region_names = {
            row["region_code"]: row["region_name"] for row in work_areas
        }
        region_name = region_names.get(region_code)
        if not region_name:
            raise ValidationException("未找到县区真实行政区信息")
        overall_score = round(
            request.quality_score * 0.5
            + request.timeliness_score * 0.25
            + request.compliance_score * 0.25,
            2,
        )
        grade = self._grade(overall_score)
        now = datetime.now(UTC)
        evaluation = await self.dao.get_evaluation_for_update(
            db,
            plan.id,
            region_code,
        )
        previous_values: dict = {}
        action = "created"
        if evaluation is None:
            evaluation = SupervisionCountyEvaluation(
                plan_id=plan.id,
                region_code=region_code,
                region_name=region_name,
                quality_score=request.quality_score,
                timeliness_score=request.timeliness_score,
                compliance_score=request.compliance_score,
                overall_score=overall_score,
                grade=grade,
                comment=request.comment,
                evaluated_by=supervisor.display_name,
                evaluated_by_code=supervisor.user_code,
                evaluated_by_role=supervisor.role_code,
                evaluated_at=now,
            )
            await self.dao.add_evaluation(db, evaluation)
        else:
            action = "updated"
            previous_values = {
                "quality_score": float(evaluation.quality_score),
                "timeliness_score": float(evaluation.timeliness_score),
                "compliance_score": float(evaluation.compliance_score),
                "overall_score": float(evaluation.overall_score),
                "grade": evaluation.grade,
                "comment": evaluation.comment,
            }
            evaluation.quality_score = request.quality_score
            evaluation.timeliness_score = request.timeliness_score
            evaluation.compliance_score = request.compliance_score
            evaluation.overall_score = overall_score
            evaluation.grade = grade
            evaluation.comment = request.comment
            evaluation.evaluated_by = supervisor.display_name
            evaluation.evaluated_by_code = supervisor.user_code
            evaluation.evaluated_by_role = supervisor.role_code
            evaluation.evaluated_at = now
        new_values = {
            "quality_score": request.quality_score,
            "timeliness_score": request.timeliness_score,
            "compliance_score": request.compliance_score,
            "overall_score": overall_score,
            "grade": grade,
            "comment": request.comment,
        }
        await self.dao.add_event(
            db,
            SupervisionEvent(
                plan_id=plan.id,
                entity_type="county_evaluation",
                entity_code=region_code,
                action=action,
                previous_values=previous_values,
                new_values=new_values,
                comment=request.comment,
                operator=supervisor.display_name,
                operator_code=supervisor.user_code,
                operator_role=supervisor.role_code,
            ),
        )
        plan.updated_at = now
        await db.commit()
        return await self._build_plan_response(db, plan)

    async def generate_report(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        plan_code: str,
        request: SupervisionReportGenerateRequest,
    ) -> SupervisionReportResponse:
        """通过闭环门禁后生成校验值固定的实体监理报告。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            plan_code: 监理计划编号。
            request: 生成操作人和说明。

        Returns:
            SupervisionReportResponse: 不可变报告证据。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        supervisor = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "supervise_project",
        )
        plan = await self.dao.get_plan_by_code(
            db,
            task.id,
            plan_code,
            for_update=True,
        )
        if plan is None:
            raise NotFoundException(f"未找到监理计划 {plan_code}")
        if plan.status != "active":
            raise ValidationException("监理计划已生成报告或不可用")
        if await self.dao.get_report(db, plan.id):
            raise ValidationException("每个监理计划只能生成一份不可变报告")
        await self._require_current_plan_snapshot(db, task, plan)
        plan_response = await self._build_plan_response(
            db,
            plan,
            complete_events=True,
        )
        if plan_response.inspection_count == 0:
            raise ValidationException("至少完成一次独立过程检查后才能生成报告")
        if plan_response.open_finding_count > 0:
            raise ValidationException(
                f"仍有 {plan_response.open_finding_count} 个监理问题未闭环"
            )
        sampled_regions = set(plan_response.region_sample_counts)
        evaluated_regions = {
            item.region_code for item in plan_response.county_evaluations
        }
        missing_evaluations = sorted(sampled_regions - evaluated_regions)
        if missing_evaluations:
            raise ValidationException(
                "以下抽样县区尚未完成评价：" + ", ".join(missing_evaluations)
            )
        generated_at = datetime.now(UTC)
        report_code = (
            f"SVR-{plan.plan_code[:55]}-{generated_at:%Y%m%dT%H%M%S}-"
            f"{secrets.token_hex(3)}"
        )
        report_payload = {
            "schema_version": "1.0",
            "report_code": report_code,
            "generated_at": generated_at.isoformat(),
            "project_code": project_code,
            "task_code": task_code,
            "task_data_snapshot": {
                "plot_count": plan.task_plot_count_snapshot,
                "task_updated_at": plan.task_updated_at_snapshot.isoformat(),
            },
            "plan": plan_response.model_dump(mode="json"),
        }
        report_bytes = json.dumps(
            report_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        checksum = sha256(report_bytes).hexdigest()
        relative_path = Path(str(plan.id)) / f"{report_code}.json"
        file_path = self.storage_root / relative_path
        file_uri = f"storage://supervision/{relative_path.as_posix()}"
        await asyncio.to_thread(self._write_atomic, file_path, report_bytes)
        manifest = {
            "schema_version": "1.0",
            "task_plot_count_snapshot": plan.task_plot_count_snapshot,
            "task_updated_at_snapshot": plan.task_updated_at_snapshot.isoformat(),
            "sample_count": plan_response.sample_count,
            "inspection_count": plan_response.inspection_count,
            "finding_count": plan_response.finding_count,
            "county_evaluation_count": plan_response.evaluation_count,
            "event_count": len(plan_response.recent_events),
        }
        report = SupervisionReport(
            plan_id=plan.id,
            report_code=report_code,
            file_uri=file_uri,
            file_size_bytes=len(report_bytes),
            checksum_sha256=checksum,
            evidence_manifest=manifest,
            generated_by=supervisor.display_name,
            generated_by_code=supervisor.user_code,
            generated_by_role=supervisor.role_code,
            generated_at=generated_at,
        )
        try:
            await self.dao.add_report(db, report)
            plan.status = "completed"
            plan.updated_at = generated_at
            await self.dao.add_event(
                db,
                SupervisionEvent(
                    plan_id=plan.id,
                    entity_type="report",
                    entity_code=report_code,
                    action="generated",
                    previous_values={"plan_status": "active"},
                    new_values={
                        "plan_status": "completed",
                        "file_uri": file_uri,
                        "file_size_bytes": len(report_bytes),
                        "checksum_sha256": checksum,
                        "evidence_manifest": manifest,
                    },
                    comment=request.comment,
                    operator=supervisor.display_name,
                    operator_code=supervisor.user_code,
                    operator_role=supervisor.role_code,
                    created_at=generated_at,
                ),
            )
            await db.commit()
        except (IntegrityError, SQLAlchemyError, OSError):
            await db.rollback()
            file_path.unlink(missing_ok=True)
            raise
        return self._report_response(report)

    async def get_report_file(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        report_code: str,
        user_code: str,
    ) -> tuple[bytes, str, str]:
        """鉴权并重新校验监理实体报告后返回文件。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            report_code: 报告编号。
            user_code: 下载用户稳定编码。

        Returns:
            tuple[bytes, str, str]: 文件内容、下载文件名和 SHA256。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        await self.user_service.require_capability(
            db,
            project.id,
            user_code,
            "download_supervision_report",
        )
        report = await self.dao.get_report_by_code(db, task.id, report_code)
        if report is None:
            raise NotFoundException(f"未找到监理报告 {report_code}")
        file_path = await asyncio.to_thread(self.verify_report_file, report)
        actual_checksum = report.checksum_sha256
        content = await asyncio.to_thread(file_path.read_bytes)
        return content, f"{report.report_code}.json", actual_checksum

    def verify_report_file(self, report: SupervisionReport) -> Path:
        """重新校验监理报告受控路径、大小和 SHA-256。

        Args:
            report: 待纳入归档或下载的监理报告。

        Returns:
            Path: 已通过完整性校验的实体文件路径。
        """
        if not report.file_uri.startswith("storage://supervision/"):
            raise ValidationException("监理报告存储地址不受控")
        relative_path = report.file_uri.removeprefix("storage://supervision/")
        file_path = (self.storage_root / relative_path).resolve()
        if (
            not file_path.is_relative_to(self.storage_root.resolve())
            or not file_path.is_file()
        ):
            raise NotFoundException("监理报告实体文件不存在")
        if file_path.stat().st_size != report.file_size_bytes:
            raise ValidationException("监理报告文件大小与记录不一致")
        if calculate_sha256(file_path) != report.checksum_sha256:
            raise ValidationException("监理报告 SHA-256 校验失败")
        return file_path
