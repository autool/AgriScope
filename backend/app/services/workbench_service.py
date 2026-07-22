"""遥感监测工作台业务服务。"""

import json
import logging
from collections import Counter
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.workbench_dao import (
    PlotQualityMetrics,
    QualityGateSummary,
    WorkbenchDAO,
    WorkbenchNavigationCounts,
)
from app.models.plot import FarmlandPlot
from app.models.workbench import (
    MonitoringTask,
    PlotEditOperation,
    PlotEditOperationEvent,
    PlotVersion,
    QualityIssue,
    ReviewRecord,
)
from app.schemas.workbench import (
    BatchPlotAttributeUpdateRequest,
    BatchPlotAttributeUpdateResponse,
    ImagerySummary,
    PlotAttributeMutationRequest,
    PlotAttributesResponse,
    PlotCreateRequest,
    PlotDeleteRequest,
    PlotGeometryUpdateRequest,
    PlotHistoryActionRequest,
    PlotHistoryActionResponse,
    PlotMergeRequest,
    PlotMergeResponse,
    PlotOperationHistoryStateResponse,
    PlotOperationSummary,
    PlotQualityCheckRequest,
    PlotSplitRequest,
    PlotSplitResponse,
    PolygonGeometry,
    ProjectSummary,
    QualityCheckResponse,
    QualityIssueItem,
    QualityIssueListResponse,
    QualityIssueResolveRequest,
    QualityIssueResolveResponse,
    QualityIssueRuleCount,
    QualityRuleResult,
    QualityRuleSummary,
    ReviewRecordResponse,
    TaskQualityCheckRequest,
    TaskQualityCheckResponse,
    TaskSubmitRequest,
    TaskSummary,
    WorkbenchOverviewResponse,
    WorkbenchStatistics,
    WorkbenchWorkflowResponse,
    WorkflowStageResponse,
)
from app.services.project_user_service import ProjectUserService
from app.services.rule_config_service import RuleConfigService

logger = logging.getLogger(__name__)

QUALITY_RULE_LABELS = {
    "GEOMETRY_VALID": "几何闭合与有效性",
    "AREA_POSITIVE": "面积有效性",
    "AREA_CONSISTENCY": "面积计算一致性",
    "REQUIRED_ATTRIBUTES": "必填属性完整性",
    "LAND_CROP_LOGIC": "地类与作物逻辑",
    "TOPOLOGY_OVERLAP": "图斑重叠检查",
    "ADMIN_CONTAINMENT": "行政区归属检查",
    "SOURCE_TRACEABLE": "来源可追溯性",
    "IMAGERY_COVERAGE": "影像覆盖检查",
    "POSITIONAL_ACCURACY_CONFIG": "位置精度检测配置",
}
MIN_SPLIT_PIECE_AREA_HA = 0.01
MAX_MERGE_OVERLAP_AREA_HA = 0.0001


class WorkbenchService:
    """处理遥感监测工作台聚合、质检和审核业务。"""

    def __init__(
        self,
        dao: WorkbenchDAO | None = None,
        rule_config_service: RuleConfigService | None = None,
        project_user_service: ProjectUserService | None = None,
    ) -> None:
        """初始化工作台服务。

        Args:
            dao: 可选工作台 DAO，便于单元测试替换。
            rule_config_service: 项目规则配置服务。
            project_user_service: 项目用户与角色校验服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or WorkbenchDAO()
        self.rule_config_service = rule_config_service or RuleConfigService()
        self.project_user_service = project_user_service or ProjectUserService()

    @staticmethod
    def _geometry_json(request_geometry: PolygonGeometry) -> str:
        """将 Pydantic GeoJSON 几何序列化为数据库绑定参数。

        Args:
            request_geometry: 已通过请求模型校验的 PolygonGeometry。

        Returns:
            str: 紧凑 GeoJSON 字符串。
        """
        return json.dumps(
            request_geometry.model_dump(),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    async def _validate_geometry(
        self,
        db: AsyncSession,
        request_geometry: PolygonGeometry,
    ) -> tuple[str, float]:
        """执行 PostGIS 几何有效性和椭球面积校验。

        Args:
            db: 异步数据库会话。
            request_geometry: 已通过基础结构校验的 PolygonGeometry。

        Returns:
            tuple[str, float]: GeoJSON 字符串和公顷面积。
        """
        geometry_json = self._geometry_json(request_geometry)
        is_valid, area_ha = await self.dao.analyze_polygon(db, geometry_json)
        if not is_valid:
            raise ValidationException("图斑边界存在自相交或其他无效几何")
        if area_ha <= 0:
            raise ValidationException("图斑面积必须大于 0")
        return geometry_json, area_ha

    async def _reopen_task(
        self,
        db: AsyncSession,
        task: MonitoringTask,
    ) -> None:
        """编辑图斑后重新打开任务并刷新进度统计。

        Args:
            db: 异步数据库会话。
            task: 当前作业任务。

        Returns:
            None: 无返回值。
        """
        total_plots, completed_plots = await self.dao.count_plot_progress(
            db,
            task.id,
        )
        task.status = "interpreting"
        task.total_plots = total_plots
        task.completed_plots = completed_plots
        task.quality_score = None
        task.updated_at = datetime.now(UTC)

    @staticmethod
    def _build_plot_version(
        plot: FarmlandPlot,
        created_by: str,
        change_summary: str,
        created_by_code: str | None = None,
        created_by_role: str | None = None,
    ) -> PlotVersion:
        """根据图斑当前状态创建不可变版本对象。

        Args:
            plot: 当前图斑。
            created_by: 操作人。
            change_summary: 变更摘要。
            created_by_code: 操作人稳定编码。
            created_by_role: 执行时角色快照。

        Returns:
            PlotVersion: 待持久化版本。
        """
        return PlotVersion(
            plot_code=plot.plot_code,
            version=plot.version,
            land_class=plot.land_class,
            crop_type=plot.crop_type,
            planting_mode=plot.planting_mode,
            irrigation_condition=plot.irrigation_condition,
            interpretation_status=plot.interpretation_status,
            geom=plot.geom,
            change_summary=change_summary,
            created_by=created_by,
            created_by_code=created_by_code,
            created_by_role=created_by_role,
        )

    @staticmethod
    def _to_operation_summary(
        operation: PlotEditOperation,
    ) -> PlotOperationSummary:
        """将操作模型转换为工具栏历史摘要。

        Args:
            operation: 分割或合并操作模型。

        Returns:
            PlotOperationSummary: 可撤销/重做摘要。
        """
        return PlotOperationSummary(
            operation_code=operation.operation_code,
            operation_type=operation.operation_type,
            source_plot_codes=list(operation.source_plot_codes),
            result_plot_codes=list(operation.result_plot_codes),
        )

    @staticmethod
    def _validate_operation_versions(
        operation: PlotEditOperation,
        plots: list[FarmlandPlot],
        expected_versions: dict[str, int],
    ) -> None:
        """防止撤销或重做覆盖操作后产生的新版本。

        Args:
            operation: 待执行历史动作的编辑操作。
            plots: 已锁定的源和结果图斑。
            expected_versions: 操作日志记录的预期版本。

        Returns:
            None: 版本一致时无返回值。
        """
        actual = {plot.plot_code: plot.version for plot in plots}
        expected = {code: int(version) for code, version in expected_versions.items()}
        if set(actual) != set(expected) or actual != expected:
            raise ValidationException(
                f"操作 {operation.operation_code} 关联图斑已产生后续版本，"
                "不能覆盖新编辑"
            )

    @staticmethod
    def _build_quality_rules(
        plot: FarmlandPlot,
        metrics: PlotQualityMetrics,
        positional_accuracy_pixels: float,
    ) -> list[QualityRuleResult]:
        """根据数据库指标和图斑属性生成可解释质量规则。

        Args:
            plot: 当前图斑。
            metrics: PostGIS 计算的几何与空间指标。
            positional_accuracy_pixels: 当前项目允许的位置偏差像元数。

        Returns:
            list[QualityRuleResult]: 带阻断标记的规则结果。
        """
        stored_area = float(plot.area_ha or 0)
        area_difference = abs(metrics.calculated_area_ha - stored_area)
        area_tolerance = max(0.01, metrics.calculated_area_ha * 0.005)
        area_consistent = area_difference <= area_tolerance
        geometry_valid = metrics.geometry_valid and metrics.ring_closed
        required_valid = (
            bool(plot.owner_village and plot.land_class) and stored_area > 0
        )
        crop_logic_valid = (plot.land_class == "耕地" and bool(plot.crop_type)) or (
            plot.land_class != "耕地" and not plot.crop_type
        )
        source_traceable = bool(
            plot.source_name
            and plot.source_feature_id
            and plot.source_version
            and plot.source_updated_at
            and (plot.source_name == "内业人工解译" or plot.source_uri)
        )
        hierarchy_complete = bool(
            plot.province_name
            and plot.city_name
            and plot.district_name
            and plot.district_code
        )
        if not metrics.has_imagery:
            imagery_status = "warning"
            imagery_detail = "项目尚未配置可用于覆盖校验的影像资产"
        elif metrics.covered_by_imagery:
            imagery_status = "pass"
            resolution = (
                f"，影像分辨率 {metrics.imagery_resolution_m:.2f} 米"
                if metrics.imagery_resolution_m is not None
                else ""
            )
            imagery_detail = f"图斑位于当前影像覆盖范围内{resolution}"
        else:
            imagery_status = "fail"
            imagery_detail = "图斑超出当前项目最新影像的空间覆盖范围"

        return [
            QualityRuleResult(
                rule_code="GEOMETRY_VALID",
                label="几何闭合与有效性",
                status="pass" if geometry_valid else "fail",
                severity="high",
                detail=(
                    "Polygon 几何有效且外环闭合"
                    if geometry_valid
                    else "图斑存在无效几何或外环未闭合"
                ),
                blocking=True,
            ),
            QualityRuleResult(
                rule_code="AREA_POSITIVE",
                label="面积有效性",
                status="pass" if stored_area > 0 else "fail",
                severity="high",
                detail=(
                    f"数据库面积为 {stored_area:.4f} 公顷"
                    if stored_area > 0
                    else "面积必须大于 0"
                ),
                blocking=True,
            ),
            QualityRuleResult(
                rule_code="AREA_CONSISTENCY",
                label="面积计算一致性",
                status="pass" if area_consistent else "fail",
                severity="high",
                detail=(
                    f"存储面积与椭球重算面积差 {area_difference:.4f} 公顷，"
                    f"容差 {area_tolerance:.4f} 公顷"
                ),
                blocking=True,
            ),
            QualityRuleResult(
                rule_code="REQUIRED_ATTRIBUTES",
                label="必填属性完整性",
                status="pass" if required_valid else "fail",
                severity="high",
                detail=(
                    "权属村、地类和面积字段完整"
                    if required_valid
                    else "权属村、地类或面积字段缺失"
                ),
                blocking=True,
            ),
            QualityRuleResult(
                rule_code="LAND_CROP_LOGIC",
                label="地类与作物逻辑",
                status="pass" if crop_logic_valid else "fail",
                severity="medium",
                detail=(
                    "地类与作物类型逻辑一致"
                    if crop_logic_valid
                    else "耕地必须填写作物，非耕地不得保留作物类型"
                ),
                blocking=True,
            ),
            QualityRuleResult(
                rule_code="TOPOLOGY_OVERLAP",
                label="图斑重叠检查",
                status="pass" if metrics.overlap_count == 0 else "fail",
                severity="high",
                detail=(
                    "未发现与其他有效图斑发生面积重叠"
                    if metrics.overlap_count == 0
                    else (
                        f"与 {metrics.overlap_count} 个图斑重叠，"
                        f"重叠面积合计 {metrics.overlap_area_ha:.4f} 公顷"
                    )
                ),
                blocking=True,
            ),
            QualityRuleResult(
                rule_code="ADMIN_CONTAINMENT",
                label="行政区归属检查",
                status=(
                    "pass" if hierarchy_complete and metrics.within_district else "fail"
                ),
                severity="high",
                detail=(
                    f"图斑完整位于 {plot.city_name} / {plot.district_name} 内"
                    if hierarchy_complete and metrics.within_district
                    else "行政层级缺失或图斑跨出归属县区边界"
                ),
                blocking=True,
            ),
            QualityRuleResult(
                rule_code="SOURCE_TRACEABLE",
                label="来源可追溯性",
                status="pass" if source_traceable else "fail",
                severity="medium",
                detail=(
                    f"来源 {plot.source_name}，要素 {plot.source_feature_id}，"
                    f"版本 {plot.source_version}"
                    if source_traceable
                    else "缺少来源名称、要素 ID、版本、更新时间或原始链接"
                ),
                blocking=True,
            ),
            QualityRuleResult(
                rule_code="IMAGERY_COVERAGE",
                label="影像覆盖检查",
                status=imagery_status,
                severity="high",
                detail=imagery_detail,
                blocking=True,
            ),
            QualityRuleResult(
                rule_code="POSITIONAL_ACCURACY_CONFIG",
                label="位置精度检测配置",
                status="warning",
                severity="low",
                detail=(
                    "尚未配置影像控制点或参考边界，无法计算 "
                    f"{positional_accuracy_pixels:g} 像元偏移；"
                    "本项明确标记为待配置，不生成虚假偏移数值"
                ),
                blocking=False,
            ),
        ]

    @staticmethod
    def _calculate_quality_score(rules: list[QualityRuleResult]) -> int:
        """按规则状态和严重度计算质量得分。

        Args:
            rules: 质量规则结果。

        Returns:
            int: 0 到 100 的质量得分。
        """
        penalties = {
            ("fail", "high"): 18,
            ("fail", "medium"): 10,
            ("fail", "low"): 5,
            ("warning", "high"): 8,
            ("warning", "medium"): 5,
            ("warning", "low"): 3,
        }
        score = 100 - sum(
            penalties.get((rule.status, rule.severity), 0) for rule in rules
        )
        return max(score, 0)

    @staticmethod
    def _to_plot_response(plot: object) -> PlotAttributesResponse:
        """将图斑 ORM 对象转换为业务属性响应。

        Args:
            plot: 解译图斑 ORM 对象。

        Returns:
            PlotAttributesResponse: 图斑业务属性响应。
        """
        return PlotAttributesResponse(
            plot_code=plot.plot_code,
            owner_village=plot.owner_village,
            area_ha=float(plot.area_ha) if plot.area_ha is not None else None,
            land_class=plot.land_class,
            crop_type=plot.crop_type,
            planting_mode=plot.planting_mode,
            irrigation_condition=plot.irrigation_condition,
            source_name=getattr(plot, "source_name", None),
            source_feature_id=getattr(plot, "source_feature_id", None),
            source_uri=getattr(plot, "source_uri", None),
            source_version=getattr(plot, "source_version", None),
            source_updated_at=getattr(plot, "source_updated_at", None),
            province_name=getattr(plot, "province_name", None),
            city_name=getattr(plot, "city_name", None),
            district_name=getattr(plot, "district_name", None),
            district_code=getattr(plot, "district_code", None),
            interpretation_status=plot.interpretation_status,
            version=plot.version,
            updated_at=plot.updated_at,
        )

    @staticmethod
    def _build_workflow(
        task: MonitoringTask,
        imagery: object | None,
        quality_gate: QualityGateSummary,
        open_issue_count: int,
        navigation_counts: WorkbenchNavigationCounts,
    ) -> WorkbenchWorkflowResponse:
        """根据数据库证据生成项目全流程状态和总体进度。

        六个业务阶段等权计算总体进度。阶段只有在对应实体数据、质量门禁、
        审核状态或成果包证据满足时才会标记完成。

        Args:
            task: 当前作业任务。
            imagery: 最新可用业务影像；不存在时为空。
            quality_gate: 当前任务图斑质量门禁汇总。
            open_issue_count: 当前未关闭质量问题数量。
            navigation_counts: 外业、灾害、影像和成果包实时数量。

        Returns:
            WorkbenchWorkflowResponse: 动态流程阶段和总体进度。
        """
        if imagery is None:
            imagery_stage = WorkflowStageResponse(
                code="imagery",
                label="影像预处理",
                status="blocked",
                progress=0,
                detail="尚未上传具备实体校验的业务影像",
            )
        else:
            imagery_completed = (
                imagery.calibration_status == "completed"
                and imagery.correction_status == "completed"
            )
            imagery_progress = (
                int(imagery.calibration_status == "completed") * 50
                + int(imagery.correction_status == "completed") * 50
            )
            imagery_stage = WorkflowStageResponse(
                code="imagery",
                label="影像预处理",
                status="completed" if imagery_completed else "active",
                progress=imagery_progress,
                detail=(
                    f"业务影像 {imagery.asset_code} 已完成定标和校正"
                    if imagery_completed
                    else f"业务影像 {imagery.asset_code} 的预处理链尚未完成"
                ),
            )

        total_plots = int(task.total_plots)
        completed_plots = int(task.completed_plots)
        interpretation_progress = (
            min(100.0, round(completed_plots / total_plots * 100, 2))
            if total_plots
            else 0.0
        )
        interpretation_completed = total_plots > 0 and completed_plots >= total_plots
        later_task_status = task.status in {
            "self_check",
            "quality_review",
            "client_review",
            "completed",
        }
        interpretation_stage = WorkflowStageResponse(
            code="interpretation",
            label="地块解译",
            status=(
                "completed"
                if interpretation_completed
                else "blocked"
                if later_task_status
                else "active"
            ),
            progress=interpretation_progress,
            detail=f"已完成 {completed_plots}/{total_plots} 个任务图斑",
        )

        quality_total = quality_gate.total_count
        quality_checked = quality_gate.checked_count
        quality_passing = quality_gate.passing_count
        quality_progress = (
            min(100.0, round(quality_passing / quality_total * 100, 2))
            if quality_total
            else 0.0
        )
        quality_completed = (
            quality_total > 0
            and quality_checked == quality_total
            and quality_passing == quality_total
            and quality_gate.average_score is not None
            and quality_gate.average_score >= 80
            and open_issue_count == 0
        )
        if quality_completed:
            quality_status = "completed"
        elif quality_checked == 0:
            quality_status = "pending"
        elif quality_checked == quality_total or later_task_status:
            quality_status = "blocked"
        else:
            quality_status = "active"
        quality_stage = WorkflowStageResponse(
            code="quality",
            label="质量检查",
            status=quality_status,
            progress=quality_progress,
            detail=(
                f"通过 {quality_passing}/{quality_total}，"
                f"未关闭问题 {open_issue_count} 条"
            ),
        )

        field_total = navigation_counts.total_field_verification_count
        field_pending = navigation_counts.pending_field_verification_count
        field_resolved = max(0, field_total - field_pending)
        field_progress = (
            min(100.0, round(field_resolved / field_total * 100, 2))
            if field_total
            else 0.0
        )
        field_stage = WorkflowStageResponse(
            code="field",
            label="外业核查",
            status=(
                "pending"
                if field_total == 0
                else "completed"
                if field_pending == 0
                else "active"
            ),
            progress=field_progress,
            detail=(
                "尚未导入外业核查记录"
                if field_total == 0
                else f"已处置 {field_resolved}/{field_total} 条外业记录"
            ),
        )

        review_progress = {
            "interpreting": 0,
            "self_check": 25,
            "quality_review": 50,
            "client_review": 75,
            "completed": 100,
            "rejected": 0,
        }.get(task.status, 0)
        review_labels = {
            "interpreting": "尚未提交内业自检",
            "self_check": "当前处于内业自检",
            "quality_review": "当前处于质检员审核",
            "client_review": "当前处于甲方复核",
            "completed": "三级审核已全部通过",
            "rejected": "审核已驳回，等待重新整改",
        }
        review_stage = WorkflowStageResponse(
            code="review",
            label="三级审核",
            status=(
                "completed"
                if task.status == "completed"
                else "blocked"
                if task.status == "rejected"
                else "active"
                if task.status in {"self_check", "quality_review", "client_review"}
                else "pending"
            ),
            progress=review_progress,
            detail=review_labels.get(task.status, f"当前任务状态：{task.status}"),
        )

        delivery_count = navigation_counts.current_delivery_package_count
        delivery_stage = WorkflowStageResponse(
            code="delivery",
            label="成果交付",
            status=(
                "completed"
                if delivery_count > 0
                else "active"
                if task.status == "completed"
                else "pending"
            ),
            progress=100 if delivery_count > 0 else 0,
            detail=(
                f"已有 {delivery_count} 个当前有效成果包"
                if delivery_count > 0
                else "三级审核完成后生成可校验成果包"
            ),
        )

        stages = [
            imagery_stage,
            interpretation_stage,
            quality_stage,
            field_stage,
            review_stage,
            delivery_stage,
        ]
        workflow_progress = round(
            sum(stage.progress for stage in stages) / len(stages),
            2,
        )
        current_stage = next(
            (stage.label for stage in stages if stage.status in {"blocked", "active"}),
            next(
                (stage.label for stage in stages if stage.status == "pending"),
                "全流程完成",
            ),
        )
        return WorkbenchWorkflowResponse(
            progress=workflow_progress,
            current_stage=current_stage,
            stages=stages,
        )

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
    ) -> WorkbenchOverviewResponse:
        """获取工作台项目、任务、影像、统计和审核聚合数据。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。

        Returns:
            WorkbenchOverviewResponse: 工作台初始化数据。
        """
        logger.info(
            "加载工作台概览: project_code=%s, task_code=%s",
            project_code,
            task_code,
        )
        project = await self.dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        task = await self.dao.get_task_by_code(db, task_code)
        if task is None or task.project_id != project.id:
            raise NotFoundException(f"未找到任务 {task_code}")
        imagery = await self.dao.get_latest_imagery(db, project.id)

        reviews = await self.dao.get_reviews(
            db,
            task.id,
            limit=20,
            current_cycle=True,
        )
        review_count = await self.dao.count_reviews(db, task.id)
        current_cycle_review_count = await self.dao.count_reviews(
            db,
            task.id,
            current_cycle=True,
        )
        issue_count = await self.dao.count_open_issues(db, task.id)
        quality_gate = await self.dao.get_quality_gate_summary(db, task.id)
        navigation_counts = await self.dao.get_navigation_counts(
            db,
            project.id,
            task.id,
        )
        workflow = self._build_workflow(
            task,
            imagery,
            quality_gate,
            issue_count,
            navigation_counts,
        )
        project_summary = ProjectSummary.model_validate(project).model_copy(
            update={"progress": workflow.progress}
        )
        return WorkbenchOverviewResponse(
            project=project_summary,
            task=TaskSummary.model_validate(task),
            imagery=(ImagerySummary.model_validate(imagery) if imagery else None),
            statistics=WorkbenchStatistics(
                plot_count=task.total_plots,
                interpreted_count=task.completed_plots,
                open_issue_count=issue_count,
                review_record_count=review_count,
                current_cycle_review_count=current_cycle_review_count,
                operational_imagery_count=(navigation_counts.operational_imagery_count),
                pending_disaster_count=(navigation_counts.pending_disaster_count),
                pending_field_verification_count=(
                    navigation_counts.pending_field_verification_count
                ),
            ),
            workflow=workflow,
            reviews=[ReviewRecordResponse.model_validate(item) for item in reviews],
        )

    async def get_plot_attributes(
        self,
        db: AsyncSession,
        task_code: str,
        plot_code: str,
    ) -> PlotAttributesResponse:
        """获取指定解译图斑业务属性。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            plot_code: 图斑编号。

        Returns:
            PlotAttributesResponse: 图斑业务属性。
        """
        task = await self.dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if not await self.dao.is_plot_assigned_to_task(db, task.id, plot_code):
            raise NotFoundException(f"当前任务未找到图斑 {plot_code}")
        plot = await self.dao.get_plot_by_code(db, plot_code)
        if plot is None or plot.interpretation_status == "deleted":
            raise NotFoundException(f"当前任务未找到图斑 {plot_code}")
        return self._to_plot_response(plot)

    async def create_plot(
        self,
        db: AsyncSession,
        task_code: str,
        request: PlotCreateRequest,
    ) -> PlotAttributesResponse:
        """创建人工解译图斑并写入初始版本和审计记录。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 新建图斑属性、几何和操作信息。

        Returns:
            PlotAttributesResponse: 新建图斑业务属性。
        """
        task = await self.dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中的任务可以新建图斑")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "edit_plots",
        )
        if request.plot_code:
            existing = await self.dao.get_plot_by_code(db, request.plot_code)
            if existing is not None:
                raise ValidationException(f"图斑编号 {request.plot_code} 已存在")
        geometry_json, area_ha = await self._validate_geometry(db, request.geometry)
        plot_code = request.plot_code or await self.dao.get_next_plot_code(db)
        try:
            plot = await self.dao.create_plot(
                db,
                plot_code=plot_code,
                owner_village=request.owner_village,
                area_ha=area_ha,
                geometry_json=geometry_json,
                land_class=request.land_class,
                crop_type=request.crop_type,
                planting_mode=request.planting_mode,
                irrigation_condition=request.irrigation_condition,
            )
            if plot is None:
                raise ValidationException("绘制范围不在已配置的黑龙江省行政区内")
            await self.dao.assign_plot_to_task(
                db,
                task.id,
                plot_code,
                operator.display_name,
                operator.user_code,
                operator.role_code,
            )
            await self.dao.add_plot_version(
                db,
                self._build_plot_version(
                    plot,
                    operator.display_name,
                    request.comment or "新建人工解译图斑",
                    operator.user_code,
                    operator.role_code,
                ),
            )
            await self.dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="interpretation",
                    action="plot_created",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"新建图斑 {plot_code}，面积 {area_ha:.4f} 公顷；"
                        f"{request.comment or '完成边界和属性录入'}"
                    ),
                ),
            )
            await self.dao.supersede_reverted_plot_operations(db, task.id)
            await self._reopen_task(db, task)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException("图斑编号或来源标识发生冲突，请重试") from exc
        await db.refresh(plot)
        return self._to_plot_response(plot)

    async def update_plot_geometry(
        self,
        db: AsyncSession,
        task_code: str,
        plot_code: str,
        request: PlotGeometryUpdateRequest,
    ) -> PlotAttributesResponse:
        """保存节点编辑后的边界并生成版本和审计记录。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            plot_code: 图斑编号。
            request: 新边界、操作人和说明。

        Returns:
            PlotAttributesResponse: 更新后的图斑属性。
        """
        task = await self.dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中的任务可以编辑图斑边界")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "edit_plots",
        )
        plot = await self.dao.get_plot_by_code_for_update(db, plot_code)
        if plot is None or plot.interpretation_status == "deleted":
            raise NotFoundException(f"未找到图斑 {plot_code}")
        if not await self.dao.is_plot_assigned_to_task(db, task.id, plot_code):
            raise ValidationException(f"图斑 {plot_code} 不属于任务 {task_code}")
        geometry_json, area_ha = await self._validate_geometry(db, request.geometry)
        updated_plot = await self.dao.update_plot_geometry(
            db,
            plot_code,
            geometry_json,
            area_ha,
        )
        if updated_plot is None:
            raise NotFoundException(f"未找到图斑 {plot_code}")
        await self.dao.add_plot_version(
            db,
            self._build_plot_version(
                updated_plot,
                operator.display_name,
                request.comment or "节点编辑调整图斑边界",
                operator.user_code,
                operator.role_code,
            ),
        )
        await self.dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="interpretation",
                action="plot_geometry_updated",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=(
                    f"更新图斑 {plot_code} 边界，面积调整为 {area_ha:.4f} 公顷，"
                    f"生成版本 v{updated_plot.version}"
                ),
            ),
        )
        await self.dao.supersede_reverted_plot_operations(db, task.id)
        await self._reopen_task(db, task)
        await db.commit()
        await db.refresh(updated_plot)
        return self._to_plot_response(updated_plot)

    async def delete_plot(
        self,
        db: AsyncSession,
        task_code: str,
        plot_code: str,
        request: PlotDeleteRequest,
    ) -> PlotAttributesResponse:
        """软删除图斑并保留版本、审计和关联处置记录。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            plot_code: 图斑编号。
            request: 操作人和删除原因。

        Returns:
            PlotAttributesResponse: 标记删除后的图斑属性。
        """
        task = await self.dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中的任务可以删除图斑")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "edit_plots",
        )
        plot = await self.dao.get_plot_by_code_for_update(db, plot_code)
        if plot is None or plot.interpretation_status == "deleted":
            raise NotFoundException(f"未找到图斑 {plot_code}")
        if not await self.dao.is_plot_assigned_to_task(db, task.id, plot_code):
            raise ValidationException(f"图斑 {plot_code} 不属于任务 {task_code}")
        deleted_plot = await self.dao.soft_delete_plot(db, plot_code)
        if deleted_plot is None:
            raise NotFoundException(f"未找到图斑 {plot_code}")
        await self.dao.add_plot_version(
            db,
            self._build_plot_version(
                deleted_plot,
                operator.display_name,
                f"软删除图斑：{request.comment}",
                operator.user_code,
                operator.role_code,
            ),
        )
        await self.dao.close_plot_issues(db, plot_code)
        await self.dao.detach_field_verifications(db, plot_code)
        await self.dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="interpretation",
                action="plot_deleted",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=f"软删除图斑 {plot_code}：{request.comment}",
            ),
        )
        await self.dao.supersede_reverted_plot_operations(db, task.id)
        await self._reopen_task(db, task)
        await db.commit()
        await db.refresh(deleted_plot)
        return self._to_plot_response(deleted_plot)

    async def split_plot(
        self,
        db: AsyncSession,
        task_code: str,
        plot_code: str,
        request: PlotSplitRequest,
    ) -> PlotSplitResponse:
        """使用 PostGIS 分割任务图斑并生成子图斑、版本和操作审计。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            plot_code: 待分割图斑编号。
            request: 分割线、稳定操作人编码和判读依据。

        Returns:
            PlotSplitResponse: 分割子图斑、面积守恒和任务进度。
        """
        task = await self.dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中的任务可以分割图斑")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "edit_plots",
        )
        source_plot = await self.dao.get_plot_by_code_for_update(db, plot_code)
        if source_plot is None or source_plot.interpretation_status == "deleted":
            raise NotFoundException(f"未找到图斑 {plot_code}")
        if not await self.dao.is_plot_assigned_to_task(db, task.id, plot_code):
            raise ValidationException(f"图斑 {plot_code} 不属于任务 {task_code}")

        cutter_json = json.dumps(
            request.cutter.model_dump(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        analysis = await self.dao.analyze_plot_split(
            db,
            plot_code,
            cutter_json,
        )
        if not analysis.cutter_simple:
            raise ValidationException("分割线存在自相交或无有效线段")
        if len(analysis.pieces) != 2:
            raise ValidationException("分割线必须完整穿过图斑并仅生成两个子图斑")
        if any(piece.area_ha < MIN_SPLIT_PIECE_AREA_HA for piece in analysis.pieces):
            raise ValidationException("分割后单个子图斑面积不得小于 0.01 公顷")
        result_area_ha = sum(piece.area_ha for piece in analysis.pieces)
        area_difference_ha = abs(analysis.source_area_ha - result_area_ha)
        # geography 面积在分割后分别计算会产生极小椭球数值差，允许万分之一误差。
        area_tolerance_ha = max(0.0001, analysis.source_area_ha * 0.0001)
        if area_difference_ha > area_tolerance_ha:
            raise ValidationException("分割结果面积不守恒，请调整分割线后重试")

        operation_code = f"PEO-{uuid4().hex.upper()}"
        child_plots: list[FarmlandPlot] = []
        child_plot_codes: list[str] = []
        try:
            for piece in analysis.pieces:
                child_plot_code = await self.dao.get_next_plot_code(
                    db,
                    prefix="SPL-HLJ",
                )
                child_plot = await self.dao.create_split_child(
                    db,
                    source_plot_code=plot_code,
                    child_plot_code=child_plot_code,
                    geometry_json=piece.geometry_json,
                    area_ha=piece.area_ha,
                )
                if child_plot is None:
                    raise ValidationException("分割子图斑写入失败，请重新绘制分割线")
                await self.dao.assign_plot_to_task(
                    db,
                    task.id,
                    child_plot_code,
                    operator.display_name,
                    operator.user_code,
                    operator.role_code,
                )
                child_plots.append(child_plot)
                child_plot_codes.append(child_plot_code)

            deleted_source = await self.dao.soft_delete_plot(db, plot_code)
            if deleted_source is None:
                raise NotFoundException(f"未找到图斑 {plot_code}")
            versions = [
                self._build_plot_version(
                    deleted_source,
                    operator.display_name,
                    (
                        f"图斑分割为 {', '.join(child_plot_codes)}；"
                        f"{request.comment}"
                    ),
                    operator.user_code,
                    operator.role_code,
                ),
                *[
                    self._build_plot_version(
                        child,
                        operator.display_name,
                        f"由图斑 {plot_code} 分割生成；{request.comment}",
                        operator.user_code,
                        operator.role_code,
                    )
                    for child in child_plots
                ],
            ]
            await self.dao.add_plot_versions(db, versions)
            await self.dao.close_plot_issues(db, plot_code)
            await self.dao.rematch_split_field_verifications(
                db,
                plot_code,
                child_plot_codes,
            )
            await self.dao.supersede_reverted_plot_operations(db, task.id)
            await self.dao.add_plot_edit_operation(
                db,
                PlotEditOperation(
                    operation_code=operation_code,
                    task_id=task.id,
                    operation_type="split",
                    source_plot_codes=[plot_code],
                    result_plot_codes=child_plot_codes,
                    applied_versions={
                        deleted_source.plot_code: deleted_source.version,
                        **{child.plot_code: child.version for child in child_plots},
                    },
                    reverted_versions={},
                    status="applied",
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                    comment=request.comment,
                ),
            )
            await self.dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="interpretation",
                    action="plot_split",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"将图斑 {plot_code} 分割为 "
                        f"{', '.join(child_plot_codes)}；"
                        f"源面积 {analysis.source_area_ha:.4f} 公顷，"
                        f"结果面积 {result_area_ha:.4f} 公顷；"
                        f"{request.comment}"
                    ),
                ),
            )
            await self._reopen_task(db, task)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException("分割子图斑编号冲突，请重试") from exc

        for child_plot in child_plots:
            await db.refresh(child_plot)
        return PlotSplitResponse(
            operation_code=operation_code,
            task_code=task_code,
            source_plot_code=plot_code,
            result_plots=[
                self._to_plot_response(child_plot) for child_plot in child_plots
            ],
            source_area_ha=analysis.source_area_ha,
            result_area_ha=result_area_ha,
            area_difference_ha=area_difference_ha,
            total_plot_count=task.total_plots,
            completed_plot_count=task.completed_plots,
            quality_recheck_required=True,
        )

    async def merge_plots(
        self,
        db: AsyncSession,
        task_code: str,
        request: PlotMergeRequest,
    ) -> PlotMergeResponse:
        """合并显式选择的相邻任务图斑并保存冲突属性结论。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 源图斑编号、确认属性、操作人和合并依据。

        Returns:
            PlotMergeResponse: 合并结果、面积守恒和任务进度。
        """
        task = await self.dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中的任务可以合并图斑")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "edit_plots",
        )
        source_plots = list(
            await self.dao.get_task_plots_by_codes_for_update(
                db,
                task.id,
                request.plot_codes,
            )
        )
        if len(source_plots) != len(request.plot_codes):
            raise ValidationException("合并选择包含非本任务、已删除或不存在的图斑")
        plots_by_code = {plot.plot_code: plot for plot in source_plots}
        ordered_plots = [plots_by_code[code] for code in request.plot_codes]
        analysis = await self.dao.analyze_plot_merge(
            db,
            task.id,
            request.plot_codes,
        )
        if analysis.source_count != len(request.plot_codes):
            raise ValidationException("合并分析未覆盖全部显式选择图斑")
        if analysis.district_count != 1:
            raise ValidationException("只能合并同一县区内的图斑")
        if analysis.overlap_area_ha > MAX_MERGE_OVERLAP_AREA_HA:
            raise ValidationException("源图斑存在超过 1 平方米的重叠，请先完成拓扑整改")
        if analysis.geometry_type != "ST_Polygon" or analysis.component_count != 1:
            raise ValidationException("所选图斑不连续，无法合并为单一面")
        if not analysis.geometry_valid or analysis.result_area_ha <= 0:
            raise ValidationException("合并结果几何无效或面积不正确")
        area_difference_ha = abs(analysis.source_area_ha - analysis.result_area_ha)
        area_tolerance_ha = max(0.0001, analysis.source_area_ha * 0.0001)
        if area_difference_ha > area_tolerance_ha:
            raise ValidationException("合并结果面积不守恒，请检查源图斑拓扑")

        conflict_fields = [
            label
            for label, values in (
                ("权属村", {plot.owner_village for plot in ordered_plots}),
                ("一级地类", {plot.land_class for plot in ordered_plots}),
                ("作物类型", {plot.crop_type for plot in ordered_plots}),
                ("种植模式", {plot.planting_mode for plot in ordered_plots}),
                (
                    "灌排条件",
                    {plot.irrigation_condition for plot in ordered_plots},
                ),
            )
            if len(values) > 1
        ]
        operation_code = f"PEO-{uuid4().hex.upper()}"
        merged_plot_code = await self.dao.get_next_plot_code(
            db,
            prefix="MRG-HLJ",
        )
        try:
            merged_plot = await self.dao.create_merged_plot(
                db,
                source_plot_code=ordered_plots[0].plot_code,
                merged_plot_code=merged_plot_code,
                geometry_json=analysis.geometry_json,
                area_ha=analysis.result_area_ha,
                owner_village=request.owner_village,
                land_class=request.land_class,
                crop_type=request.crop_type,
                planting_mode=request.planting_mode,
                irrigation_condition=request.irrigation_condition,
            )
            if merged_plot is None:
                raise ValidationException("合并结果图斑写入失败")
            await self.dao.assign_plot_to_task(
                db,
                task.id,
                merged_plot_code,
                operator.display_name,
                operator.user_code,
                operator.role_code,
            )
            deleted_sources: list[FarmlandPlot] = []
            for source_plot in ordered_plots:
                deleted = await self.dao.soft_delete_plot(
                    db,
                    source_plot.plot_code,
                )
                if deleted is None:
                    raise NotFoundException(f"未找到图斑 {source_plot.plot_code}")
                deleted_sources.append(deleted)
                await self.dao.close_plot_issues(db, source_plot.plot_code)
            await self.dao.add_plot_versions(
                db,
                [
                    *[
                        self._build_plot_version(
                            source,
                            operator.display_name,
                            (f"合并生成图斑 {merged_plot_code}；" f"{request.comment}"),
                            operator.user_code,
                            operator.role_code,
                        )
                        for source in deleted_sources
                    ],
                    self._build_plot_version(
                        merged_plot,
                        operator.display_name,
                        (
                            f"由图斑 {', '.join(request.plot_codes)} 合并生成；"
                            f"{request.comment}"
                        ),
                        operator.user_code,
                        operator.role_code,
                    ),
                ],
            )
            await self.dao.rematch_merged_field_verifications(
                db,
                request.plot_codes,
                merged_plot_code,
            )
            await self.dao.supersede_reverted_plot_operations(db, task.id)
            await self.dao.add_plot_edit_operation(
                db,
                PlotEditOperation(
                    operation_code=operation_code,
                    task_id=task.id,
                    operation_type="merge",
                    source_plot_codes=request.plot_codes,
                    result_plot_codes=[merged_plot_code],
                    applied_versions={
                        **{
                            source.plot_code: source.version
                            for source in deleted_sources
                        },
                        merged_plot.plot_code: merged_plot.version,
                    },
                    reverted_versions={},
                    status="applied",
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                    comment=request.comment,
                ),
            )
            conflict_text = (
                f"人工确认冲突字段：{', '.join(conflict_fields)}；"
                if conflict_fields
                else "源图斑属性一致；"
            )
            await self.dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="interpretation",
                    action="plot_merged",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"将图斑 {', '.join(request.plot_codes)} 合并为 "
                        f"{merged_plot_code}；{conflict_text}"
                        f"面积 {analysis.result_area_ha:.4f} 公顷；"
                        f"{request.comment}"
                    ),
                ),
            )
            await self._reopen_task(db, task)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException("合并结果图斑编号冲突，请重试") from exc

        await db.refresh(merged_plot)
        return PlotMergeResponse(
            operation_code=operation_code,
            task_code=task_code,
            source_plot_codes=request.plot_codes,
            result_plot=self._to_plot_response(merged_plot),
            source_area_ha=analysis.source_area_ha,
            result_area_ha=analysis.result_area_ha,
            area_difference_ha=area_difference_ha,
            total_plot_count=task.total_plots,
            completed_plot_count=task.completed_plots,
            quality_recheck_required=True,
        )

    async def get_plot_operation_history_state(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> PlotOperationHistoryStateResponse:
        """查询任务当前可撤销和可重做的分割/合并操作。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            PlotOperationHistoryStateResponse: 工具栏历史状态。
        """
        task = await self.dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        undo_operation = await self.dao.get_latest_undoable_plot_operation(
            db,
            task.id,
        )
        redo_operation = await self.dao.get_latest_redoable_plot_operation(
            db,
            task.id,
        )
        return PlotOperationHistoryStateResponse(
            can_undo=undo_operation is not None,
            can_redo=redo_operation is not None,
            undo_operation=(
                self._to_operation_summary(undo_operation)
                if undo_operation is not None
                else None
            ),
            redo_operation=(
                self._to_operation_summary(redo_operation)
                if redo_operation is not None
                else None
            ),
        )

    async def undo_plot_operation(
        self,
        db: AsyncSession,
        task_code: str,
        request: PlotHistoryActionRequest,
    ) -> PlotHistoryActionResponse:
        """撤销任务最近一个仍生效的分割或合并操作。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 稳定操作人编码和撤销依据。

        Returns:
            PlotHistoryActionResponse: 恢复后的活动/停用图斑和任务进度。
        """
        return await self._execute_plot_history_action(
            db,
            task_code,
            request,
            action="undo",
        )

    async def redo_plot_operation(
        self,
        db: AsyncSession,
        task_code: str,
        request: PlotHistoryActionRequest,
    ) -> PlotHistoryActionResponse:
        """重做任务最近一个已撤销且尚未失效的操作。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 稳定操作人编码和重做依据。

        Returns:
            PlotHistoryActionResponse: 重做后的活动/停用图斑和任务进度。
        """
        return await self._execute_plot_history_action(
            db,
            task_code,
            request,
            action="redo",
        )

    async def _execute_plot_history_action(
        self,
        db: AsyncSession,
        task_code: str,
        request: PlotHistoryActionRequest,
        *,
        action: str,
    ) -> PlotHistoryActionResponse:
        """执行分割/合并操作状态的双向恢复事务。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 操作人编码和证据说明。
            action: `undo` 或 `redo`。

        Returns:
            PlotHistoryActionResponse: 历史动作执行结果。
        """
        task = await self.dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中的任务可以撤销或重做编辑")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "edit_plots",
        )
        if action == "undo":
            operation = await self.dao.get_latest_undoable_plot_operation(
                db,
                task.id,
            )
            expected_versions = operation.applied_versions if operation else {}
        else:
            operation = await self.dao.get_latest_redoable_plot_operation(
                db,
                task.id,
            )
            expected_versions = operation.reverted_versions if operation else {}
        if operation is None:
            label = "撤销" if action == "undo" else "重做"
            raise ValidationException(f"当前没有可{label}的地块操作")
        if operation.operation_type not in {"split", "merge"}:
            raise ValidationException("当前操作类型不支持撤销或重做")

        all_codes = [
            *operation.source_plot_codes,
            *operation.result_plot_codes,
        ]
        plots = list(
            await self.dao.get_plots_by_codes_for_update_any_status(
                db,
                all_codes,
            )
        )
        if len(plots) != len(all_codes):
            raise ValidationException("操作关联图斑不完整，无法恢复历史状态")
        self._validate_operation_versions(operation, plots, expected_versions)
        plots_by_code = {plot.plot_code: plot for plot in plots}

        if action == "undo":
            active_codes = list(operation.source_plot_codes)
            inactive_codes = list(operation.result_plot_codes)
        else:
            active_codes = list(operation.result_plot_codes)
            inactive_codes = list(operation.source_plot_codes)
        if any(
            plots_by_code[code].interpretation_status != "deleted"
            for code in active_codes
        ) or any(
            plots_by_code[code].interpretation_status == "deleted"
            for code in inactive_codes
        ):
            raise ValidationException("操作关联图斑状态已变化，不能执行历史恢复")

        restored_plots: list[FarmlandPlot] = []
        deleted_plots: list[FarmlandPlot] = []
        for plot_code in active_codes:
            restored = await self.dao.restore_plot_from_latest_active_version(
                db,
                plot_code,
            )
            if restored is None:
                raise ValidationException(f"图斑 {plot_code} 缺少可恢复历史版本")
            restored_plots.append(restored)
        for plot_code in inactive_codes:
            deleted = await self.dao.soft_delete_plot(db, plot_code)
            if deleted is None:
                raise ValidationException(f"图斑 {plot_code} 当前状态不能停用")
            deleted_plots.append(deleted)
            await self.dao.close_plot_issues(db, plot_code)

        if operation.operation_type == "split":
            if action == "undo":
                await self.dao.rematch_merged_field_verifications(
                    db,
                    operation.result_plot_codes,
                    operation.source_plot_codes[0],
                )
            else:
                await self.dao.rematch_split_field_verifications(
                    db,
                    operation.source_plot_codes[0],
                    operation.result_plot_codes,
                )
        else:
            if action == "undo":
                await self.dao.rematch_split_field_verifications(
                    db,
                    operation.result_plot_codes[0],
                    operation.source_plot_codes,
                )
            else:
                await self.dao.rematch_merged_field_verifications(
                    db,
                    operation.source_plot_codes,
                    operation.result_plot_codes[0],
                )

        action_label = "撤销" if action == "undo" else "重做"
        await self.dao.add_plot_versions(
            db,
            [
                *[
                    self._build_plot_version(
                        plot,
                        operator.display_name,
                        (
                            f"{action_label}操作 {operation.operation_code}；"
                            f"{request.comment}"
                        ),
                        operator.user_code,
                        operator.role_code,
                    )
                    for plot in restored_plots
                ],
                *[
                    self._build_plot_version(
                        plot,
                        operator.display_name,
                        (
                            f"{action_label}操作 {operation.operation_code}；"
                            f"{request.comment}"
                        ),
                        operator.user_code,
                        operator.role_code,
                    )
                    for plot in deleted_plots
                ],
            ],
        )
        state_versions = {
            plot.plot_code: plot.version for plot in [*restored_plots, *deleted_plots]
        }
        if action == "undo":
            operation.status = "reverted"
            operation.reverted_at = datetime.now(UTC)
            operation.reverted_versions = state_versions
        else:
            operation.status = "applied"
            operation.reverted_at = None
            operation.applied_versions = state_versions
        await self.dao.add_plot_edit_operation_event(
            db,
            PlotEditOperationEvent(
                event_code=f"PEE-{uuid4().hex.upper()}",
                operation_id=operation.id,
                action=action,
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
                comment=request.comment,
            ),
        )
        await self.dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="interpretation",
                action=f"plot_operation_{action}",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=(
                    f"{action_label}{operation.operation_type}操作 "
                    f"{operation.operation_code}；活动图斑 "
                    f"{', '.join(active_codes)}；{request.comment}"
                ),
            ),
        )
        await self._reopen_task(db, task)
        await db.commit()
        return PlotHistoryActionResponse(
            action=action,
            operation=self._to_operation_summary(operation),
            active_plot_codes=active_codes,
            inactive_plot_codes=inactive_codes,
            total_plot_count=task.total_plots,
            completed_plot_count=task.completed_plots,
            quality_recheck_required=True,
        )

    async def update_plot_attributes(
        self,
        db: AsyncSession,
        task_code: str,
        plot_code: str,
        request: PlotAttributeMutationRequest,
    ) -> PlotAttributesResponse:
        """更新图斑业务属性并生成版本和操作记录。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            plot_code: 图斑编号。
            request: 已校验的属性更新请求。

        Returns:
            PlotAttributesResponse: 更新后的图斑属性。
        """
        logger.info("更新图斑属性: task=%s, plot=%s", task_code, plot_code)
        task = await self.dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中的任务可以修改图斑属性")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "edit_plots",
        )
        plot = await self.dao.get_plot_by_code_for_update(db, plot_code)
        if plot is None or plot.interpretation_status == "deleted":
            raise NotFoundException(f"未找到图斑 {plot_code}")
        if not await self.dao.is_plot_assigned_to_task(db, task.id, plot_code):
            raise ValidationException(f"图斑 {plot_code} 不属于任务 {task_code}")

        plot.land_class = request.land_class
        plot.crop_type = request.crop_type
        plot.planting_mode = request.planting_mode
        plot.irrigation_condition = request.irrigation_condition
        plot.interpretation_status = "interpreted"
        plot.version += 1
        plot.updated_at = datetime.now(UTC)
        await self.dao.add_plot_version(
            db,
            self._build_plot_version(
                plot,
                operator.display_name,
                request.comment or "更新图斑业务属性",
                operator.user_code,
                operator.role_code,
            ),
        )
        await self.dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="interpretation",
                action="plot_attribute_updated",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=f"更新图斑 {plot_code} 属性，生成版本 v{plot.version}",
            ),
        )
        await self.dao.supersede_reverted_plot_operations(db, task.id)
        await self._reopen_task(db, task)
        await db.commit()
        await db.refresh(plot)
        return self._to_plot_response(plot)

    async def batch_update_plot_attributes(
        self,
        db: AsyncSession,
        task_code: str,
        request: BatchPlotAttributeUpdateRequest,
    ) -> BatchPlotAttributeUpdateResponse:
        """对用户显式选择的任务图斑批量赋值并生成不可变版本。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 图斑编号、目标属性、操作人和说明。

        Returns:
            BatchPlotAttributeUpdateResponse: 更新数量和任务进度。
        """
        logger.info(
            "批量更新图斑属性: task=%s, count=%s, operator=%s",
            task_code,
            len(request.plot_codes),
            request.operator_code,
        )
        task = await self.dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中的任务可以批量修改图斑属性")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "edit_plots",
        )
        plots = list(
            await self.dao.get_task_plots_by_codes_for_update(
                db,
                task.id,
                request.plot_codes,
            )
        )
        found_codes = {plot.plot_code for plot in plots}
        missing_codes = [
            plot_code
            for plot_code in request.plot_codes
            if plot_code not in found_codes
        ]
        if missing_codes:
            sample = "、".join(missing_codes[:5])
            suffix = "等" if len(missing_codes) > 5 else ""
            raise ValidationException(
                f"有 {len(missing_codes)} 个图斑不属于任务或已删除：{sample}{suffix}"
            )

        updated_at = datetime.now(UTC)
        change_summary = request.comment or (
            f"批量赋值地类={request.attributes.land_class}，"
            f"作物={request.attributes.crop_type or '不适用'}"
        )
        versions: list[PlotVersion] = []
        for plot in plots:
            plot.land_class = request.attributes.land_class
            plot.crop_type = request.attributes.crop_type
            plot.planting_mode = request.attributes.planting_mode
            plot.irrigation_condition = request.attributes.irrigation_condition
            plot.interpretation_status = "interpreted"
            plot.version += 1
            plot.updated_at = updated_at
            versions.append(
                self._build_plot_version(
                    plot,
                    operator.display_name,
                    change_summary,
                    operator.user_code,
                    operator.role_code,
                )
            )

        await self.dao.add_plot_versions(db, versions)
        await self.dao.resolve_plot_quality_rules(
            db,
            task.id,
            request.plot_codes,
            ["LAND_CROP_LOGIC"],
        )
        await self.dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="interpretation",
                action="plot_attributes_batch_updated",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=(
                    f"对 {len(plots)} 个显式选择图斑批量赋值："
                    f"地类 {request.attributes.land_class}，"
                    f"作物 {request.attributes.crop_type or '不适用'}，"
                    f"种植模式 {request.attributes.planting_mode or '未填写'}，"
                    f"灌排条件 {request.attributes.irrigation_condition or '未填写'}；"
                    f"{change_summary}"
                ),
            ),
        )
        await self.dao.supersede_reverted_plot_operations(db, task.id)
        await self._reopen_task(db, task)
        await db.commit()
        return BatchPlotAttributeUpdateResponse(
            task_code=task_code,
            updated_count=len(plots),
            updated_plot_codes=request.plot_codes,
            total_plot_count=task.total_plots,
            completed_plot_count=task.completed_plots,
            quality_recheck_required=True,
        )

    async def check_plot_quality(
        self,
        db: AsyncSession,
        task_code: str,
        plot_code: str,
        request: PlotQualityCheckRequest,
    ) -> QualityCheckResponse:
        """执行图斑几何、属性、逻辑和位置精度质量检查。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            plot_code: 图斑编号。
            request: 质检操作人编码。

        Returns:
            QualityCheckResponse: 质量得分与逐项规则结果。
        """
        logger.info("执行图斑质量检查: task=%s, plot=%s", task_code, plot_code)
        task = await self.dao.get_task_by_code_for_update(db, task_code)
        plot = await self.dao.get_plot_by_code(db, plot_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中的任务可以运行图斑质量检查")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "run_plot_quality_check",
        )
        if plot is None or plot.interpretation_status == "deleted":
            raise NotFoundException(f"未找到图斑 {plot_code}")
        if not await self.dao.is_plot_assigned_to_task(db, task.id, plot_code):
            raise ValidationException(f"图斑 {plot_code} 不属于任务 {task_code}")

        metrics = await self.dao.get_plot_quality_metrics(
            db,
            plot_code,
            task.project_id,
        )
        config = await self.rule_config_service.ensure_for_project(
            db,
            task.project_id,
        )
        rules = self._build_quality_rules(
            plot,
            metrics,
            float(config.positional_accuracy_pixels),
        )
        score = self._calculate_quality_score(rules)
        can_submit = all(rule.status == "pass" for rule in rules if rule.blocking)

        await self.dao.clear_auto_issues(db, task.id, plot_code)
        issues = [
            QualityIssue(
                task_id=task.id,
                plot_code=plot_code,
                rule_code=rule.rule_code,
                issue_type="quality_rule",
                severity=rule.severity,
                description=rule.detail,
                status="open",
                source="auto",
                assignee=task.assignee,
            )
            for rule in rules
            if rule.status != "pass"
        ]
        if issues:
            await self.dao.add_quality_issues(db, issues)
        await self.dao.upsert_plot_quality_check(
            db,
            task_id=task.id,
            plot_code=plot_code,
            plot_version=plot.version,
            score=score,
            can_submit=can_submit,
            rules=[rule.model_dump() for rule in rules],
        )
        gate_summary = await self.dao.get_quality_gate_summary(db, task.id)
        task.quality_score = gate_summary.average_score
        await self.dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="quality",
                action="quality_plot_run",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=f"检查图斑 {plot_code}，质量得分 {score}",
            ),
        )
        await db.commit()
        return QualityCheckResponse(
            plot_code=plot_code,
            score=score,
            can_submit=can_submit,
            checked_plot_count=gate_summary.checked_count,
            total_plot_count=gate_summary.total_count,
            passing_plot_count=gate_summary.passing_count,
            rules=rules,
        )

    async def run_task_quality_checks(
        self,
        db: AsyncSession,
        task_code: str,
        request: TaskQualityCheckRequest,
    ) -> TaskQualityCheckResponse:
        """在单个事务内执行任务全部图斑质量检查。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 操作人和执行说明。

        Returns:
            TaskQualityCheckResponse: 覆盖率、通过率和规则汇总。
        """
        started_at = datetime.now(UTC)
        started_counter = perf_counter()
        logger.info(
            "执行任务全量质量检查: task=%s, operator=%s",
            task_code,
            request.operator_code,
        )
        task = await self.dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中的任务可以重新运行全量质量检查")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "run_quality_check",
        )

        plots = list(await self.dao.get_task_plots(db, task.id))
        if not plots:
            raise ValidationException("当前任务没有已分配的有效图斑")
        metrics_by_plot = await self.dao.get_task_quality_metrics(
            db,
            task.id,
            task.project_id,
        )
        if len(metrics_by_plot) != len(plots):
            raise ValidationException("任务图斑质量指标不完整，请检查空间数据")
        config = await self.rule_config_service.ensure_for_project(
            db,
            task.project_id,
        )

        checks: list[dict[str, object]] = []
        issues: list[QualityIssue] = []
        rule_counters: dict[str, Counter[str]] = {}
        rule_labels: dict[str, str] = {}
        for plot in plots:
            metrics = metrics_by_plot[plot.plot_code]
            rules = self._build_quality_rules(
                plot,
                metrics,
                float(config.positional_accuracy_pixels),
            )
            score = self._calculate_quality_score(rules)
            can_submit = all(rule.status == "pass" for rule in rules if rule.blocking)
            checks.append(
                {
                    "task_id": task.id,
                    "plot_code": plot.plot_code,
                    "plot_version": plot.version,
                    "score": score,
                    "can_submit": can_submit,
                    "rules": [rule.model_dump() for rule in rules],
                }
            )
            for rule in rules:
                rule_labels[rule.rule_code] = rule.label
                counter = rule_counters.setdefault(rule.rule_code, Counter())
                counter[rule.status] += 1
                if rule.blocking and rule.status != "pass":
                    counter["blocking"] += 1
                if rule.status != "pass":
                    issues.append(
                        QualityIssue(
                            task_id=task.id,
                            plot_code=plot.plot_code,
                            rule_code=rule.rule_code,
                            issue_type="quality_rule",
                            severity=rule.severity,
                            description=rule.detail,
                            status="open",
                            source="auto",
                            assignee=task.assignee,
                        )
                    )

        await self.dao.clear_task_quality_issues(db, task.id)
        if issues:
            await self.dao.add_quality_issues(db, issues)
        await self.dao.upsert_plot_quality_checks(db, checks)
        gate_summary = await self.dao.get_quality_gate_summary(db, task.id)
        task.quality_score = gate_summary.average_score
        task.updated_at = datetime.now(UTC)
        await self.dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="quality",
                action="quality_batch_run",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=(
                    request.comment
                    or (
                        f"完成 {gate_summary.checked_count} 个图斑全量质检，"
                        f"通过 {gate_summary.passing_count} 个，"
                        f"发现 {len(issues)} 条规则问题"
                    )
                ),
            ),
        )
        await db.commit()

        can_submit = (
            gate_summary.total_count > 0
            and gate_summary.checked_count == gate_summary.total_count
            and gate_summary.passing_count == gate_summary.total_count
            and gate_summary.average_score is not None
            and gate_summary.average_score >= 80
        )
        rule_summaries = [
            QualityRuleSummary(
                rule_code=rule_code,
                label=rule_labels[rule_code],
                pass_count=counter["pass"],
                warning_count=counter["warning"],
                fail_count=counter["fail"],
                blocking_issue_count=counter["blocking"],
            )
            for rule_code, counter in rule_counters.items()
        ]
        return TaskQualityCheckResponse(
            task_code=task_code,
            total_plot_count=gate_summary.total_count,
            checked_plot_count=gate_summary.checked_count,
            passing_plot_count=gate_summary.passing_count,
            failed_plot_count=(gate_summary.total_count - gate_summary.passing_count),
            average_score=gate_summary.average_score,
            issue_count=len(issues),
            can_submit=can_submit,
            duration_ms=round((perf_counter() - started_counter) * 1000),
            executed_at=started_at,
            rule_summaries=rule_summaries,
        )

    async def get_task_quality_issues(
        self,
        db: AsyncSession,
        task_code: str,
        *,
        status: str,
        rule_code: str | None,
        severity: str | None,
        issue_type: str | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> QualityIssueListResponse:
        """分页查询任务质量问题并返回规则与严重度汇总。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            status: 问题状态或 all。
            rule_code: 可选规则编码。
            severity: 可选严重度。
            issue_type: 可选问题类型。
            keyword: 可选图斑或行政区关键词。
            page: 页码。
            page_size: 每页条数。

        Returns:
            QualityIssueListResponse: 分页问题队列和汇总统计。
        """
        task = await self.dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        normalized_keyword = keyword.strip() if keyword else None
        rows, total_count = await self.dao.get_quality_issue_page(
            db,
            task.id,
            status=status,
            rule_code=rule_code,
            severity=severity,
            issue_type=issue_type,
            keyword=normalized_keyword,
            page=page,
            page_size=page_size,
        )
        summary, rule_rows = await self.dao.get_quality_issue_summary(
            db,
            task.id,
            issue_type=issue_type,
            keyword=normalized_keyword,
        )
        items = [
            QualityIssueItem(
                id=int(row["id"]),
                plot_code=row["plot_code"],
                rule_code=row["rule_code"],
                rule_label=QUALITY_RULE_LABELS.get(
                    row["rule_code"],
                    row["rule_code"],
                ),
                issue_type=row["issue_type"],
                severity=row["severity"],
                description=row["description"],
                status=row["status"],
                source=row["source"],
                assignee=row["assignee"],
                resolved_by=row["resolved_by"],
                resolved_by_code=row["resolved_by_code"],
                resolved_by_role=row["resolved_by_role"],
                resolution_comment=row["resolution_comment"],
                created_at=row["created_at"],
                resolved_at=row["resolved_at"],
                plot_version=row["plot_version"],
                city_name=row["city_name"],
                district_name=row["district_name"],
                owner_village=row["owner_village"],
                land_class=row["land_class"],
                crop_type=row["crop_type"],
                area_ha=(float(row["area_ha"]) if row["area_ha"] is not None else None),
            )
            for row in rows
        ]
        return QualityIssueListResponse(
            task_code=task_code,
            page=page,
            page_size=page_size,
            total_count=total_count,
            open_count=summary.open_count,
            resolved_count=summary.resolved_count,
            high_count=summary.high_count,
            medium_count=summary.medium_count,
            low_count=summary.low_count,
            rule_counts=[
                QualityIssueRuleCount(
                    rule_code=row["rule_code"],
                    rule_label=QUALITY_RULE_LABELS.get(
                        row["rule_code"],
                        row["rule_code"],
                    ),
                    total_count=int(row["total_count"]),
                    open_count=int(row["open_count"]),
                )
                for row in rule_rows
            ],
            items=items,
        )

    async def resolve_review_issue(
        self,
        db: AsyncSession,
        task_code: str,
        issue_id: int,
        request: QualityIssueResolveRequest,
    ) -> QualityIssueResolveResponse:
        """确认关闭审核人员提出的人工问题。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            issue_id: 问题主键。
            request: 操作人编码和关闭依据。

        Returns:
            QualityIssueResolveResponse: 关闭人和审计时间。
        """
        task = await self.dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        issue = await self.dao.get_quality_issue_for_update(
            db,
            task.id,
            issue_id,
        )
        if issue is None:
            raise NotFoundException(f"未找到问题 {issue_id}")
        if issue.status == "resolved":
            raise ValidationException("该问题已经关闭")
        if issue.source != "manual" or not issue.rule_code.startswith("REVIEW_"):
            raise ValidationException("自动质检或外业问题必须通过对应业务流程重新校验")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "resolve_review_issue",
        )
        resolved_at = datetime.now(UTC)
        issue.status = "resolved"
        issue.resolved_at = resolved_at
        issue.resolved_by = operator.display_name
        issue.resolved_by_code = operator.user_code
        issue.resolved_by_role = operator.role_code
        issue.resolution_comment = request.comment
        await self.dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="quality_issue",
                action="issue_resolved",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=f"关闭问题 {issue.id}：{request.comment}",
            ),
        )
        await db.commit()
        return QualityIssueResolveResponse(
            issue_id=issue.id,
            status=issue.status,
            resolved_by=operator.display_name,
            resolved_by_code=operator.user_code,
            resolved_by_role=operator.role_code,
            resolution_comment=request.comment,
            resolved_at=resolved_at,
        )

    async def submit_task_for_self_check(
        self,
        db: AsyncSession,
        task_code: str,
        request: TaskSubmitRequest,
    ) -> TaskSummary:
        """将解译任务提交至内业自检节点。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 提交人和备注。

        Returns:
            TaskSummary: 更新后的任务摘要。
        """
        logger.info(
            "提交任务自检: task=%s, reviewer_code=%s",
            task_code,
            request.reviewer_code,
        )
        task = await self.dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("当前任务已提交，不能重复提交自检")
        reviewer = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.reviewer_code,
            "submit_self_check",
        )
        gate_summary = await self.dao.get_quality_gate_summary(db, task.id)
        if gate_summary.total_count == 0:
            raise ValidationException("当前任务没有可提交的有效图斑")
        if gate_summary.checked_count < gate_summary.total_count:
            raise ValidationException(
                "质量检查尚未覆盖全部图斑："
                f"已检查 {gate_summary.checked_count}/"
                f"{gate_summary.total_count}"
            )
        if gate_summary.passing_count < gate_summary.total_count:
            raise ValidationException(
                "仍有图斑未通过质量门禁："
                f"通过 {gate_summary.passing_count}/"
                f"{gate_summary.total_count}"
            )
        if gate_summary.average_score is None or gate_summary.average_score < 80:
            raise ValidationException("任务平均质量得分不足 80，暂不能提交自检")

        task.status = "self_check"
        task.quality_score = gate_summary.average_score
        task.updated_at = datetime.now(UTC)
        await self.dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="self_check",
                action="submitted",
                reviewer=reviewer.display_name,
                reviewer_code=reviewer.user_code,
                reviewer_role=reviewer.role_code,
                comment=request.comment or "提交内业自检",
            ),
        )
        await db.commit()
        await db.refresh(task)
        return TaskSummary.model_validate(task)
