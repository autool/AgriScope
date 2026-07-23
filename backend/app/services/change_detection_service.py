"""多时相变化检测任务、候选导入与人工判读业务服务。"""

import json
import secrets
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.change_detection_dao import ChangeDetectionDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.change_detection import (
    ChangeCandidate,
    ChangeDetectionEvent,
    ChangeDetectionRun,
)
from app.models.workbench import ImageryAsset, ProjectRuleConfig
from app.schemas.change_detection import (
    ChangeCandidateGeoJsonImportRequest,
    ChangeCandidateImportResponse,
    ChangeCandidateResponse,
    ChangeCandidateReviewRequest,
    ChangeDetectionEventResponse,
    ChangeDetectionOverviewResponse,
    ChangeDetectionRunResponse,
    ChangeDiscoveryAlgorithmResponse,
    ChangeImageryResponse,
    ChangeRunCreateRequest,
)
from app.services.change_candidate_discovery_engine import (
    ChangeCandidateDiscoveryEngine,
)
from app.services.imagery_asset_service import ImageryAssetService
from app.services.imagery_registration_service import ImageryRegistrationService
from app.services.project_user_service import ProjectUserService
from app.services.rule_config_service import RuleConfigService

CONSTRUCTION_CHANGE_CLASSES = {
    "suspected_construction",
    "construction_facility_change",
}


class ChangeDetectionService:
    """编排真实影像资格、变化候选空间校验和人工判读审计。"""

    def __init__(
        self,
        dao: ChangeDetectionDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        user_service: ProjectUserService | None = None,
        rule_service: RuleConfigService | None = None,
        imagery_service: ImageryAssetService | None = None,
        registration_service: ImageryRegistrationService | None = None,
        discovery_engine: ChangeCandidateDiscoveryEngine | None = None,
    ) -> None:
        """初始化变化检测服务。

        Args:
            dao: 变化检测 DAO。
            workbench_dao: 项目任务公共 DAO。
            user_service: 项目成员能力服务。
            rule_service: 项目规则服务。
            imagery_service: 真实影像文件校验服务。
            registration_service: 物理配准成果校验服务。
            discovery_engine: 自动候选算法注册表。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ChangeDetectionDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.user_service = user_service or ProjectUserService()
        self.rule_service = rule_service or RuleConfigService()
        self.imagery_service = imagery_service or ImageryAssetService()
        self.registration_service = (
            registration_service or ImageryRegistrationService()
        )
        self.discovery_engine = discovery_engine or ChangeCandidateDiscoveryEngine()

    async def _resolve_context(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
    ) -> tuple[object, object]:
        """解析并校验项目、任务归属关系。

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
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.project_id != project.id:
            raise ValidationException("作业任务不属于当前项目")
        return project, task

    @staticmethod
    def _rule_snapshot(config: ProjectRuleConfig) -> dict[str, object]:
        """固化变化候选生产所需项目规则。

        Args:
            config: 当前项目规则 ORM 对象。

        Returns:
            dict[str, object]: 不可变规则快照。
        """
        return {
            "construction_min_area_sqm": float(
                config.construction_min_area_sqm
            ),
            "other_agricultural_min_area_sqm": float(
                config.other_agricultural_min_area_sqm
            ),
            "positional_accuracy_pixels": float(
                config.positional_accuracy_pixels
            ),
            "completeness_rate_min": float(config.completeness_rate_min),
            "boundary_agreement_rate_min": float(
                config.boundary_agreement_rate_min
            ),
            "land_class_accuracy_min": float(config.land_class_accuracy_min),
            "key_field_accuracy_min": float(config.key_field_accuracy_min),
            "max_cloud_cover_percent": (
                float(config.max_cloud_cover_percent)
                if config.max_cloud_cover_percent is not None
                else None
            ),
            "output_crs": config.output_crs,
            "output_projection": config.output_projection,
        }

    def _imagery_eligibility(
        self,
        asset: ImageryAsset,
        max_cloud_cover_percent: float | None = None,
    ) -> tuple[bool, bool, str | None]:
        """判断影像是否具备变化检测实体与预处理资格。

        Args:
            asset: 影像资产 ORM 对象。
            max_cloud_cover_percent: 项目允许的最大云量百分比。

        Returns:
            tuple[bool, bool, str | None]: 文件有效、可用和阻断原因。
        """
        file_verified, file_error = self.imagery_service.verify_asset_file(asset)
        if not file_verified:
            return False, False, file_error
        if asset.data_status != "operational":
            return True, False, "演示影像不能作为正式变化检测证据"
        if not asset.checksum_sha256:
            return True, False, "影像缺少 SHA-256 校验值"
        if asset.calibration_status != "completed":
            return True, False, "影像尚未完成辐射定标"
        if asset.correction_status != "completed":
            return True, False, "影像尚未完成几何/大气校正流程"
        if (
            max_cloud_cover_percent is not None
            and asset.cloud_cover is not None
            and float(asset.cloud_cover) > max_cloud_cover_percent
        ):
            return (
                True,
                False,
                f"影像云量超过项目规则上限 {max_cloud_cover_percent:g}%",
            )
        return True, True, None

    def _imagery_response(
        self,
        asset: ImageryAsset,
        footprint_text: str | None,
        max_cloud_cover_percent: float | None,
    ) -> ChangeImageryResponse:
        """组装变化检测影像资格响应。

        Args:
            asset: 影像资产 ORM 对象。
            footprint_text: WGS84 GeoJSON 范围文本。
            max_cloud_cover_percent: 项目允许的最大云量百分比。

        Returns:
            ChangeImageryResponse: 影像资格和阻断原因。
        """
        file_verified, eligible, reason = self._imagery_eligibility(
            asset,
            max_cloud_cover_percent,
        )
        return ChangeImageryResponse(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            sensor_type=asset.sensor_type,
            acquired_at=asset.acquired_at,
            resolution_m=(
                float(asset.resolution_m) if asset.resolution_m is not None else None
            ),
            cloud_cover=(
                float(asset.cloud_cover) if asset.cloud_cover is not None else None
            ),
            checksum_sha256=asset.checksum_sha256,
            crs=asset.crs,
            footprint=json.loads(footprint_text) if footprint_text else None,
            file_verified=file_verified,
            eligible=eligible,
            eligibility_reason=reason,
        )

    @staticmethod
    def _event_response(
        event: ChangeDetectionEvent,
    ) -> ChangeDetectionEventResponse:
        """转换不可变变化检测事件。

        Args:
            event: 事件 ORM 对象。

        Returns:
            ChangeDetectionEventResponse: 事件响应。
        """
        return ChangeDetectionEventResponse(
            event_type=event.event_type,
            previous_values=event.previous_values or {},
            new_values=event.new_values or {},
            comment=event.comment,
            operator=event.operator,
            operator_code=event.operator_code,
            operator_role=event.operator_role,
            created_at=event.created_at,
        )

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
    ) -> ChangeDetectionOverviewResponse:
        """查询影像资格、检测任务、候选队列和判读历史。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。

        Returns:
            ChangeDetectionOverviewResponse: 变化检测完整工作台状态。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        config = await self.rule_service.ensure_for_project(db, project.id)
        max_cloud_cover_percent = (
            float(config.max_cloud_cover_percent)
            if config.max_cloud_cover_percent is not None
            else None
        )
        imagery_rows = await self.dao.list_imagery_assets(db, project.id)
        imagery = [
            self._imagery_response(
                row[ImageryAsset],
                row["footprint"],
                max_cloud_cover_percent,
            )
            for row in imagery_rows
        ]
        imagery_codes_by_id = {
            row[ImageryAsset].id: row[ImageryAsset].asset_code
            for row in imagery_rows
        }
        runs = list(await self.dao.list_runs(db, task.id))
        registrations = await self.registration_service.list_project_job_responses(
            db,
            project.id,
        )
        run_ids = [run.id for run in runs]
        candidate_rows = await self.dao.list_candidate_rows(db, run_ids)
        events = await self.dao.list_events(db, run_ids)

        events_by_candidate: dict[int, list[ChangeDetectionEventResponse]] = (
            defaultdict(list)
        )
        for event in events:
            if event.candidate_id is not None:
                events_by_candidate[event.candidate_id].append(
                    self._event_response(event)
                )

        candidates_by_run: dict[int, list[ChangeCandidateResponse]] = defaultdict(list)
        for row in candidate_rows:
            candidate = row[ChangeCandidate]
            geometry = json.loads(row["geometry"])
            candidates_by_run[candidate.run_id].append(
                ChangeCandidateResponse(
                    candidate_code=candidate.candidate_code,
                    source_name=candidate.source_name,
                    source_uri=candidate.source_uri,
                    source_version=candidate.source_version,
                    source_feature_id=candidate.source_feature_id,
                    source_checksum_sha256=candidate.source_checksum_sha256,
                    import_batch_code=candidate.import_batch_code,
                    change_class=candidate.change_class,
                    confidence=float(candidate.confidence),
                    area_ha=float(candidate.area_ha),
                    evidence_uri=candidate.evidence_uri,
                    status=candidate.status,
                    exclusion_reason=candidate.exclusion_reason,
                    review_comment=candidate.review_comment,
                    reviewed_by=candidate.reviewed_by,
                    reviewed_by_code=candidate.reviewed_by_code,
                    reviewed_by_role=candidate.reviewed_by_role,
                    reviewed_at=candidate.reviewed_at,
                    imported_by=candidate.imported_by,
                    imported_by_code=candidate.imported_by_code,
                    imported_by_role=candidate.imported_by_role,
                    created_at=candidate.created_at,
                    geometry=geometry,
                    history=events_by_candidate.get(candidate.id, []),
                )
            )

        run_responses: list[ChangeDetectionRunResponse] = []
        for run in runs:
            candidates = candidates_by_run.get(run.id, [])
            class_counts: dict[str, int] = defaultdict(int)
            for candidate in candidates:
                class_counts[candidate.change_class] += 1
            run_responses.append(
                ChangeDetectionRunResponse(
                    run_code=run.run_code,
                    run_name=run.run_name,
                    baseline_asset_code=imagery_codes_by_id.get(
                        run.baseline_asset_id,
                        "已删除影像",
                    ),
                    target_asset_code=imagery_codes_by_id.get(
                        run.target_asset_id,
                        "已删除影像",
                    ),
                    registration_job_code=str(
                        (run.source_snapshot or {})
                        .get("registration", {})
                        .get("job_code", "legacy-unverified")
                    ),
                    rule_config_version=run.rule_config_version,
                    rule_profile_snapshot=run.rule_profile_snapshot or {},
                    source_snapshot=run.source_snapshot or {},
                    task_plot_count=run.task_plot_count,
                    task_updated_at_snapshot=run.task_updated_at_snapshot,
                    alignment_method=run.alignment_method,
                    alignment_offset_pixels=float(run.alignment_offset_pixels),
                    alignment_overlap_ratio=float(run.alignment_overlap_ratio),
                    alignment_evidence_uri=run.alignment_evidence_uri,
                    status=run.status,
                    candidate_count=len(candidates),
                    pending_count=sum(
                        candidate.status == "pending" for candidate in candidates
                    ),
                    confirmed_count=sum(
                        candidate.status == "confirmed" for candidate in candidates
                    ),
                    excluded_count=sum(
                        candidate.status == "excluded" for candidate in candidates
                    ),
                    class_counts=dict(class_counts),
                    created_by=run.created_by,
                    created_by_code=run.created_by_code,
                    created_by_role=run.created_by_role,
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                    candidates=candidates,
                    feature_collection={
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "geometry": candidate.geometry,
                                "properties": {
                                    "candidate_code": candidate.candidate_code,
                                    "change_class": candidate.change_class,
                                    "confidence": candidate.confidence,
                                    "area_ha": candidate.area_ha,
                                    "status": candidate.status,
                                },
                            }
                            for candidate in candidates
                        ],
                    },
                )
            )

        eligible_count = sum(item.eligible for item in imagery)
        blockers: list[str] = []
        if eligible_count < 2:
            blockers.append(
                "至少需要两期具备实体文件、SHA-256 且完成定标和校正的业务影像"
            )
        if not any(item.artifact_verified for item in registrations):
            blockers.append("至少需要一个通过实体残差门禁的双景配准成果")
        if task.status != "interpreting":
            blockers.append("当前任务不处于解译阶段，不能新建变化检测任务")
        return ChangeDetectionOverviewResponse(
            project_code=project_code,
            task_code=task_code,
            blockers=blockers,
            discovery_algorithms=[
                ChangeDiscoveryAlgorithmResponse(
                    code=algorithm.code,
                    name=algorithm.name,
                    version=algorithm.version,
                    description=algorithm.description,
                    score_formula=algorithm.score_formula,
                    default_threshold=algorithm.default_threshold,
                    threshold_min=algorithm.threshold_min,
                    threshold_max=algorithm.threshold_max,
                )
                for algorithm in self.discovery_engine.algorithm_descriptors()
            ],
            imagery=imagery,
            registrations=registrations,
            runs=run_responses,
        )

    async def create_run(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: ChangeRunCreateRequest,
    ) -> ChangeDetectionRunResponse:
        """绑定两期可验证影像、规则和配准证据创建检测任务。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            request: 时相影像、配准证据和操作人。

        Returns:
            ChangeDetectionRunResponse: 新建检测任务。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        if task.status != "interpreting":
            raise ValidationException("仅解译中任务允许创建变化检测任务")
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "run_change_detection",
        )
        if await self.dao.get_run_by_code(db, task.id, request.run_code):
            raise ValidationException(f"变化检测任务 {request.run_code} 已存在")
        baseline = await self.dao.get_imagery_asset(
            db,
            project.id,
            request.baseline_asset_code,
        )
        target = await self.dao.get_imagery_asset(
            db,
            project.id,
            request.target_asset_code,
        )
        if baseline is None or target is None:
            raise ValidationException("前后时相影像不存在或不属于当前项目")
        if baseline.id == target.id:
            raise ValidationException("前后时相影像不能相同")
        if target.acquired_at <= baseline.acquired_at:
            raise ValidationException("后时相影像采集时间必须晚于前时相影像")
        if (
            baseline.processing_level
            and target.processing_level
            and baseline.processing_level != target.processing_level
        ):
            raise ValidationException("前后时相影像处理级别不一致")
        config = await self.rule_service.ensure_for_project(db, project.id)
        max_cloud_cover_percent = (
            float(config.max_cloud_cover_percent)
            if config.max_cloud_cover_percent is not None
            else None
        )
        for label, asset in (("前时相", baseline), ("后时相", target)):
            _, eligible, reason = self._imagery_eligibility(
                asset,
                max_cloud_cover_percent,
            )
            if not eligible:
                raise ValidationException(f"{label}影像不可用于检测：{reason}")

        registration, _ = await self.registration_service.resolve_verified_job(
            db,
            project.id,
            request.registration_job_code,
        )
        if registration.task_id != task.id:
            raise ValidationException("配准成果不属于当前变化检测任务")
        if (
            registration.reference_asset_id != baseline.id
            or registration.moving_asset_id != target.id
        ):
            raise ValidationException("配准成果绑定的参考景和待配准景与两期影像不一致")
        max_offset = float(config.positional_accuracy_pixels)
        registration_residual = float(registration.residual_offset_pixels)
        if registration_residual > max_offset:
            raise ValidationException(
                f"影像配准残差 {registration_residual} 像素超过规则上限 "
                f"{max_offset} 像素"
            )
        pair_metrics = await self.dao.analyze_asset_pair(db, baseline.id, target.id)
        if pair_metrics is None or not bool(pair_metrics["has_extents"]):
            raise ValidationException("前后时相影像缺少可核验 WGS84 覆盖范围")
        if not bool(pair_metrics["intersects"]):
            raise ValidationException("前后时相影像覆盖范围不相交")
        overlap_ratio = Decimal(
            str(min(
                max(float(registration.overlap_ratio), 0),
                float(pair_metrics["overlap_ratio"] or 0),
                1,
            ))
        )
        if overlap_ratio <= 0:
            raise ValidationException("前后时相影像没有有效重叠面积")
        task_plot_count = await self.dao.count_task_plots(db, task.id)
        if task_plot_count <= 0:
            raise ValidationException("当前任务没有显式图斑范围，不能开展变化检测")
        now = datetime.now(UTC)
        run = ChangeDetectionRun(
            project_id=project.id,
            task_id=task.id,
            run_code=request.run_code,
            run_name=request.run_name,
            baseline_asset_id=baseline.id,
            target_asset_id=target.id,
            registration_job_id=registration.id,
            rule_config_version=config.version,
            rule_profile_snapshot=self._rule_snapshot(config),
            source_snapshot={
                "baseline": {
                    "asset_code": baseline.asset_code,
                    "checksum_sha256": baseline.checksum_sha256,
                    "acquired_at": baseline.acquired_at.isoformat(),
                    "crs": baseline.crs,
                    "processing_level": baseline.processing_level,
                    "resolution_m": (
                        float(baseline.resolution_m)
                        if baseline.resolution_m is not None
                        else None
                    ),
                },
                "target": {
                    "asset_code": target.asset_code,
                    "checksum_sha256": target.checksum_sha256,
                    "acquired_at": target.acquired_at.isoformat(),
                    "crs": target.crs,
                    "processing_level": target.processing_level,
                    "resolution_m": (
                        float(target.resolution_m)
                        if target.resolution_m is not None
                        else None
                    ),
                },
                "registration": {
                    "job_code": registration.job_code,
                    "output_uri": registration.output_uri,
                    "output_size_bytes": registration.file_size_bytes,
                    "output_sha256": registration.checksum_sha256,
                    "initial_offset_pixels": float(
                        registration.initial_offset_pixels
                    ),
                    "residual_offset_pixels": registration_residual,
                    "residual_threshold_pixels": float(
                        registration.residual_threshold_pixels
                    ),
                    "peak_to_sidelobe_ratio": float(
                        registration.peak_to_sidelobe_ratio
                    ),
                },
            },
            task_plot_count=task_plot_count,
            task_updated_at_snapshot=task.updated_at,
            alignment_method="phase_correlation_translation",
            alignment_offset_pixels=Decimal(str(registration_residual)),
            alignment_overlap_ratio=overlap_ratio,
            alignment_evidence_uri=registration.output_uri,
            status="active",
            created_by=operator.display_name,
            created_by_code=operator.user_code,
            created_by_role=operator.role_code,
            updated_at=now,
        )
        try:
            await self.dao.add_run(db, run)
            await self.dao.add_event(
                db,
                ChangeDetectionEvent(
                    run_id=run.id,
                    candidate_id=None,
                    event_type="run_created",
                    previous_values={},
                    new_values={
                        "baseline_asset_code": baseline.asset_code,
                        "target_asset_code": target.asset_code,
                        "rule_config_version": config.version,
                        "task_plot_count": task_plot_count,
                        "registration_job_code": registration.job_code,
                        "alignment_offset_pixels": registration_residual,
                        "alignment_overlap_ratio": float(overlap_ratio),
                    },
                    comment="创建变化检测任务并固化影像、规则与任务范围快照",
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                ),
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException("变化检测任务编号已存在") from exc
        overview = await self.get_overview(db, project_code, task_code)
        return next(item for item in overview.runs if item.run_code == run.run_code)

    @staticmethod
    def _candidate_min_area_sqm(
        change_class: str,
        rule_snapshot: dict[str, object],
    ) -> float:
        """按采购规则返回变化类别最小面积。

        Args:
            change_class: 六类变化编码。
            rule_snapshot: 检测任务创建时固化的规则快照。

        Returns:
            float: 最小面积平方米。
        """
        if change_class in CONSTRUCTION_CHANGE_CLASSES:
            return float(rule_snapshot["construction_min_area_sqm"])
        return float(rule_snapshot["other_agricultural_min_area_sqm"])

    async def import_candidates(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        run_code: str,
        request: ChangeCandidateGeoJsonImportRequest,
    ) -> ChangeCandidateImportResponse:
        """原子导入真实 GeoJSON 候选并保存来源、面积和用户审计。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            run_code: 检测任务编号。
            request: 候选 FeatureCollection 和来源证据。

        Returns:
            ChangeCandidateImportResponse: 导入批次与候选统计。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        if task.status != "interpreting":
            raise ValidationException("仅解译中任务允许导入变化候选")
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "run_change_detection",
        )
        run = await self.dao.get_run_by_code_for_update(db, task.id, run_code)
        if run is None:
            raise NotFoundException(f"未找到变化检测任务 {run_code}")
        if run.status != "active":
            raise ValidationException("每个检测任务只能导入一个冻结候选批次")
        current_plot_count = await self.dao.count_task_plots(db, task.id)
        if (
            current_plot_count != run.task_plot_count
            or task.updated_at != run.task_updated_at_snapshot
        ):
            raise ValidationException(
                "任务图斑范围或数据版本已变化，请重新创建变化检测任务"
            )
        source_payload = {
            "type": request.type,
            "features": [
                feature.model_dump(mode="json") for feature in request.features
            ],
        }
        source_checksum = sha256(
            json.dumps(
                source_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        imported_at = datetime.now(UTC)
        batch_code = (
            f"CDIMP-{imported_at:%Y%m%dT%H%M%S}-"
            f"{source_checksum[:8]}-{secrets.token_hex(4)}"
        )
        candidate_codes = [
            feature.properties.candidate_code for feature in request.features
        ]
        source_feature_ids = [
            feature.properties.source_feature_id for feature in request.features
        ]
        conflicts = await self.dao.get_conflicting_candidates_for_update(
            db,
            run.id,
            candidate_codes,
            request.source_name,
            source_feature_ids,
        )
        if conflicts:
            preview = "、".join(
                candidate.candidate_code for candidate in list(conflicts)[:5]
            )
            raise ValidationException(f"变化候选编号或来源要素已存在：{preview}")
        prepared_values: list[dict[str, object]] = []
        for feature in request.features:
            geometry_json = json.dumps(
                feature.geometry.model_dump(),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            metrics = await self.dao.analyze_import_geometry(
                db,
                project.id,
                geometry_json,
            )
            candidate_code = feature.properties.candidate_code
            if metrics is None:
                raise ValidationException("项目未配置省级行政区边界")
            if not bool(metrics["geometry_valid"]):
                raise ValidationException(f"变化候选 {candidate_code} 几何无效")
            if not bool(metrics["within_project"]):
                raise ValidationException(
                    f"变化候选 {candidate_code} 超出项目行政区范围"
                )
            area_ha = float(metrics["area_ha"] or 0)
            if area_ha <= 0:
                raise ValidationException(f"变化候选 {candidate_code} 面积必须大于 0")
            properties = feature.properties
            min_area_sqm = self._candidate_min_area_sqm(
                properties.change_class,
                run.rule_profile_snapshot,
            )
            if area_ha * 10000 < min_area_sqm:
                raise ValidationException(
                    f"变化候选 {candidate_code} 面积低于当前类别最小阈值 "
                    f"{min_area_sqm:g} 平方米"
                )
            prepared_values.append(
                {
                    "run_id": run.id,
                    "candidate_code": candidate_code,
                    "source_name": request.source_name,
                    "source_uri": request.source_uri,
                    "source_version": request.source_version,
                    "source_feature_id": properties.source_feature_id,
                    "source_checksum_sha256": source_checksum,
                    "import_batch_code": batch_code,
                    "change_class": properties.change_class,
                    "confidence": properties.confidence,
                    "area_ha": round(area_ha, 4),
                    "evidence_uri": properties.evidence_uri,
                    "imported_by": operator.display_name,
                    "imported_by_code": operator.user_code,
                    "imported_by_role": operator.role_code,
                    "geometry": geometry_json,
                }
            )
        try:
            for values in prepared_values:
                candidate = await self.dao.insert_candidate(db, values)
                await self.dao.add_event(
                    db,
                    ChangeDetectionEvent(
                        run_id=run.id,
                        candidate_id=candidate.id,
                        event_type="candidate_imported",
                        previous_values={},
                        new_values={
                            "status": "pending",
                            "change_class": candidate.change_class,
                            "confidence": float(candidate.confidence),
                            "area_ha": float(candidate.area_ha),
                            "source_checksum_sha256": source_checksum,
                            "import_batch_code": batch_code,
                        },
                        comment=request.comment,
                        operator=operator.display_name,
                        operator_code=operator.user_code,
                        operator_role=operator.role_code,
                    ),
                )
            run.status = "reviewing"
            run.updated_at = imported_at
            task.updated_at = imported_at
            await self.dao.add_event(
                db,
                ChangeDetectionEvent(
                    run_id=run.id,
                    candidate_id=None,
                    event_type="candidate_batch_imported",
                    previous_values={"status": "active"},
                    new_values={
                        "status": "reviewing",
                        "batch_code": batch_code,
                        "imported_count": len(prepared_values),
                        "source_checksum_sha256": source_checksum,
                    },
                    comment=request.comment,
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                ),
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException("变化候选编号或来源要素与现有数据冲突") from exc
        return ChangeCandidateImportResponse(
            run_code=run_code,
            batch_code=batch_code,
            imported_count=len(prepared_values),
            candidate_codes=candidate_codes,
            source_checksum_sha256=source_checksum,
            imported_by=operator.display_name,
            imported_by_code=operator.user_code,
            imported_by_role=operator.role_code,
            imported_at=imported_at,
        )

    async def review_candidate(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        run_code: str,
        candidate_code: str,
        request: ChangeCandidateReviewRequest,
    ) -> ChangeCandidateResponse:
        """人工确认、重分类或排除候选并追加不可变历史。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            run_code: 检测任务编号。
            candidate_code: 候选编号。
            request: 判读结论、证据和稳定用户编码。

        Returns:
            ChangeCandidateResponse: 更新后的候选及完整历史。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        if task.status != "interpreting":
            raise ValidationException("仅解译中任务允许判读变化候选")
        reviewer = await self.user_service.require_capability(
            db,
            project.id,
            request.reviewer_code,
            "review_change_candidate",
        )
        run = await self.dao.get_run_by_code_for_update(db, task.id, run_code)
        if run is None:
            raise NotFoundException(f"未找到变化检测任务 {run_code}")
        if run.status == "cancelled":
            raise ValidationException("已取消检测任务不能继续判读")
        candidate = await self.dao.get_candidate_for_update(
            db,
            run.id,
            candidate_code,
        )
        if candidate is None:
            raise NotFoundException(f"未找到变化候选 {candidate_code}")
        new_class = request.change_class or candidate.change_class
        if request.decision == "confirmed":
            if new_class == "unclassified":
                raise ValidationException("确认变化候选前必须归入六类变化之一")
            min_area_sqm = self._candidate_min_area_sqm(
                new_class,
                run.rule_profile_snapshot,
            )
            if float(candidate.area_ha) * 10000 < min_area_sqm:
                raise ValidationException(
                    f"候选面积低于重分类后的最小阈值 {min_area_sqm:g} 平方米"
                )
        previous_values = {
            "status": candidate.status,
            "change_class": candidate.change_class,
            "exclusion_reason": candidate.exclusion_reason,
            "review_comment": candidate.review_comment,
            "reviewed_by_code": candidate.reviewed_by_code,
        }
        new_values = {
            "status": request.decision,
            "change_class": new_class,
            "exclusion_reason": request.exclusion_reason,
            "review_comment": request.evidence_comment,
            "reviewed_by_code": reviewer.user_code,
        }
        if previous_values == new_values:
            raise ValidationException("变化候选已经是相同判读结论")
        reviewed_at = datetime.now(UTC)
        candidate.status = request.decision
        candidate.change_class = new_class
        candidate.exclusion_reason = request.exclusion_reason
        candidate.review_comment = request.evidence_comment
        candidate.reviewed_by = reviewer.display_name
        candidate.reviewed_by_code = reviewer.user_code
        candidate.reviewed_by_role = reviewer.role_code
        candidate.reviewed_at = reviewed_at
        candidate.updated_at = reviewed_at
        await self.dao.add_event(
            db,
            ChangeDetectionEvent(
                run_id=run.id,
                candidate_id=candidate.id,
                event_type="candidate_reviewed",
                previous_values=previous_values,
                new_values=new_values,
                comment=request.evidence_comment,
                operator=reviewer.display_name,
                operator_code=reviewer.user_code,
                operator_role=reviewer.role_code,
            ),
        )
        await db.flush()
        status_counts = await self.dao.count_candidate_statuses(db, run.id)
        run.status = (
            "completed"
            if status_counts.get("pending", 0) == 0
            and sum(status_counts.values()) > 0
            else "reviewing"
        )
        run.updated_at = reviewed_at
        task.updated_at = reviewed_at
        await db.commit()
        overview = await self.get_overview(db, project_code, task_code)
        response_run = next(item for item in overview.runs if item.run_code == run_code)
        return next(
            item
            for item in response_run.candidates
            if item.candidate_code == candidate_code
        )
