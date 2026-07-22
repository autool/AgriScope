"""内外业联动核查业务服务。"""

import asyncio
import json
import logging
import secrets
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.field_verification_artifact_dao import (
    FieldVerificationArtifactDAO,
)
from app.dao.field_verification_dao import FieldVerificationDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.workbench import (
    FieldVerification,
    FieldVerificationArtifact,
    ImageryAsset,
    MonitoringTask,
    PlotVersion,
    ProjectRuleConfig,
    QualityIssue,
    ReviewRecord,
)
from app.schemas.field_verification import (
    FieldRematchRequest,
    FieldRematchResponse,
    FieldReopenRequest,
    FieldResolutionRequest,
    FieldVerificationBatchImportRequest,
    FieldVerificationBatchImportResponse,
    FieldVerificationCreateRequest,
    FieldVerificationFileImportMetadata,
    FieldVerificationListResponse,
    FieldVerificationResponse,
)
from app.services.field_verification_artifact_service import (
    FieldVerificationArtifactService,
)
from app.services.field_workbook_parser import FieldVerificationWorkbookParser
from app.services.project_user_service import ProjectUserService
from app.services.rule_config_service import RuleConfigService

logger = logging.getLogger(__name__)

FIELD_DECISION_LABELS = {
    "keep_internal": "保留内业成果",
    "use_field": "采用外业结论",
    "compromise": "人工折中方案",
    "reject_field": "驳回外业结论",
}


class FieldVerificationService:
    """处理外业点导入、空间匹配、疑点生成和人工处置。"""

    def __init__(
        self,
        dao: FieldVerificationDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        rule_config_service: RuleConfigService | None = None,
        project_user_service: ProjectUserService | None = None,
        workbook_parser: FieldVerificationWorkbookParser | None = None,
        artifact_dao: FieldVerificationArtifactDAO | None = None,
        artifact_service: FieldVerificationArtifactService | None = None,
    ) -> None:
        """初始化内外业核查服务。

        Args:
            dao: 外业核查 DAO。
            workbench_dao: 工作台公共 DAO。
            rule_config_service: 项目规则配置服务。
            project_user_service: 项目用户与角色校验服务。
            workbook_parser: Excel 工作簿解析服务。
            artifact_dao: 外业实体证据 DAO。
            artifact_service: 外业受控文件存储与复核服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or FieldVerificationDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.rule_config_service = rule_config_service or RuleConfigService()
        self.project_user_service = project_user_service or ProjectUserService()
        self.workbook_parser = workbook_parser or FieldVerificationWorkbookParser()
        self.artifact_dao = artifact_dao or FieldVerificationArtifactDAO()
        self.artifact_service = (
            artifact_service or FieldVerificationArtifactService()
        )

    @staticmethod
    def _to_response(
        record: FieldVerification,
        lon: float,
        lat: float,
        artifacts: list[FieldVerificationArtifact] | None = None,
    ) -> FieldVerificationResponse:
        """组装外业核查响应。

        Args:
            record: 外业核查 ORM 对象。
            lon: WGS84 经度。
            lat: WGS84 纬度。
            artifacts: 已通过数据库登记的实体证据列表。

        Returns:
            FieldVerificationResponse: 外业核查响应。
        """
        artifact_items = artifacts or []
        return FieldVerificationResponse(
            verification_code=record.verification_code,
            investigator=record.investigator,
            investigator_code=record.investigator_code,
            lon=lon,
            lat=lat,
            observed_land_class=record.observed_land_class,
            observed_crop_type=record.observed_crop_type,
            photo_urls=record.photo_urls or [],
            voice_url=record.voice_url,
            remark=record.remark,
            captured_at=record.captured_at,
            source_name=getattr(record, "source_name", None),
            source_uri=getattr(record, "source_uri", None),
            source_version=getattr(record, "source_version", None),
            source_record_id=getattr(record, "source_record_id", None),
            source_checksum_sha256=getattr(
                record,
                "source_checksum_sha256",
                None,
            ),
            source_file_uri=getattr(record, "source_file_uri", None),
            source_file_size_bytes=getattr(
                record,
                "source_file_size_bytes",
                None,
            ),
            import_batch_code=getattr(record, "import_batch_code", None),
            imported_by=getattr(record, "imported_by", None),
            imported_by_code=getattr(record, "imported_by_code", None),
            imported_by_role=getattr(record, "imported_by_role", None),
            matched_plot_code=record.matched_plot_code,
            offset_distance_m=(
                float(record.offset_distance_m)
                if record.offset_distance_m is not None
                else None
            ),
            match_status=record.match_status,
            resolution_status=record.resolution_status,
            resolution_decision=record.resolution_decision,
            resolution_comment=record.resolution_comment,
            resolved_by=record.resolved_by,
            resolved_by_code=record.resolved_by_code,
            resolved_by_role=record.resolved_by_role,
            verified_artifact_count=len(artifact_items),
            artifacts=[
                FieldVerificationArtifactService.to_response(
                    artifact,
                    record.verification_code,
                )
                for artifact in artifact_items
            ],
        )

    async def list_records(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> FieldVerificationListResponse:
        """查询任务外业记录及匹配状态统计。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            FieldVerificationListResponse: 外业记录列表和统计。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        rows = await self.dao.get_task_records(db, task.id)
        artifacts = await self.artifact_dao.list_by_verification_ids(
            db,
            [row[0].id for row in rows],
        )
        artifacts_by_record: dict[int, list[FieldVerificationArtifact]] = {}
        for artifact in artifacts:
            artifacts_by_record.setdefault(
                artifact.field_verification_id,
                [],
            ).append(artifact)
        items = [
            self._to_response(
                row[0],
                float(row.lon),
                float(row.lat),
                artifacts_by_record.get(row[0].id, []),
            )
            for row in rows
        ]
        return FieldVerificationListResponse(
            total=len(items),
            consistent=sum(item.match_status == "consistent" for item in items),
            offset=sum(item.match_status == "offset" for item in items),
            unmatched=sum(item.match_status == "unmatched" for item in items),
            time_mismatch=sum(
                item.match_status == "time_mismatch" for item in items
            ),
            pending_resolution=sum(
                item.resolution_status == "pending"
                and item.match_status in {"offset", "unmatched", "time_mismatch"}
                for item in items
            ),
            items=items,
        )

    async def _match_record(
        self,
        db: AsyncSession,
        task: MonitoringTask,
        record: FieldVerification,
        config: ProjectRuleConfig,
        imagery: ImageryAsset | None,
    ) -> bool:
        """对单条外业记录执行最近邻匹配并生成疑点。

        Args:
            db: 异步数据库会话。
            task: 当前作业任务。
            record: 外业核查记录。
            config: 当前项目生效规则。
            imagery: 项目最新影像资产。

        Returns:
            bool: 是否生成异常疑点。
        """
        await self.dao.clear_field_issue(db, task.id, record.verification_code)
        offset_threshold_m = float(config.field_offset_threshold_m)
        search_radius_m = float(config.field_search_radius_m)
        nearest = await self.dao.find_nearest_plot(
            db,
            task.id,
            record,
            search_radius_m,
        )
        if nearest is None:
            record.matched_plot_code = None
            record.offset_distance_m = None
            record.match_status = "unmatched"
        else:
            plot_code, distance_m, contains = nearest
            record.matched_plot_code = plot_code
            record.offset_distance_m = round(distance_m, 2)
            if contains or distance_m <= offset_threshold_m:
                record.match_status = "consistent"
            else:
                record.match_status = "offset"

        time_gap_days: float | None = None
        if imagery is not None:
            time_gap_days = abs(
                (record.captured_at - imagery.acquired_at).total_seconds()
            ) / 86400
            if (
                record.match_status == "consistent"
                and time_gap_days > config.max_capture_image_days
            ):
                record.match_status = "time_mismatch"

        if record.match_status == "consistent":
            record.resolution_status = "not_required"
            return False
        record.resolution_status = "pending"

        severity = "high" if record.match_status == "unmatched" else "medium"
        descriptions = []
        if record.match_status == "offset":
            descriptions.append(
                f"外业点偏离图斑 {record.offset_distance_m} 米，"
                f"超过 {offset_threshold_m:g} 米阈值"
            )
        elif record.match_status == "unmatched":
            descriptions.append(
                f"外业点 {search_radius_m:g} 米范围内未匹配到内业图斑"
            )
        if (
            time_gap_days is not None
            and time_gap_days > config.max_capture_image_days
        ):
            descriptions.append(
                f"外业采集时间与最新影像相差 {time_gap_days:.1f} 天，"
                f"超过 {config.max_capture_image_days} 天阈值"
            )
        await self.workbench_dao.add_quality_issues(
            db,
            [
                QualityIssue(
                    task_id=task.id,
                    plot_code=record.matched_plot_code,
                    rule_code=f"FIELD_{record.verification_code}",
                    issue_type="field_verification",
                    severity=severity,
                    description="；".join(descriptions),
                    status="open",
                    source="auto",
                    assignee=task.assignee,
                )
            ],
        )
        return True

    async def create_record(
        self,
        db: AsyncSession,
        task_code: str,
        request: FieldVerificationCreateRequest,
    ) -> FieldVerificationResponse:
        """创建外业记录并立即执行空间匹配。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 外业核查采集数据。

        Returns:
            FieldVerificationResponse: 已匹配的外业记录。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status == "completed":
            raise ValidationException("已完成任务不得新增外业核查记录")
        if await self.dao.get_by_code(db, request.verification_code):
            raise ValidationException(f"外业记录 {request.verification_code} 已存在")
        investigator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.investigator_code,
            "upload_field_data",
        )
        if not await self.dao.is_point_within_project(
            db,
            task.project_id,
            request.lon,
            request.lat,
        ):
            raise ValidationException("外业核查点超出项目行政区范围")
        source_payload = request.model_dump(mode="json")
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
            f"FIELD-{imported_at:%Y%m%dT%H%M%S}-"
            f"{source_checksum[:8]}-{secrets.token_hex(4)}"
        )
        record = FieldVerification(
            task_id=task.id,
            verification_code=request.verification_code,
            investigator=investigator.display_name,
            investigator_code=investigator.user_code,
            observed_land_class=request.observed_land_class,
            observed_crop_type=request.observed_crop_type,
            photo_urls=request.photo_urls,
            voice_url=request.voice_url,
            remark=request.remark,
            captured_at=request.captured_at,
            source_name=request.source_name,
            source_uri=request.source_uri,
            source_version=request.source_version,
            source_record_id=request.source_record_id,
            source_checksum_sha256=source_checksum,
            import_batch_code=batch_code,
            imported_by=investigator.display_name,
            imported_by_code=investigator.user_code,
            imported_by_role=investigator.role_code,
            match_status="pending",
            resolution_status="pending",
        )
        await self.dao.create(db, record, request.lon, request.lat)
        config = await self.rule_config_service.ensure_for_project(
            db,
            task.project_id,
        )
        imagery = await self.workbench_dao.get_latest_imagery(db, task.project_id)
        await self._match_record(db, task, record, config, imagery)
        task.updated_at = imported_at
        await db.commit()
        lon, lat = await self.dao.get_coordinates(db, record.id)
        return self._to_response(record, lon, lat)

    async def import_batch(
        self,
        db: AsyncSession,
        task_code: str,
        request: FieldVerificationBatchImportRequest,
        *,
        source_checksum_sha256: str | None = None,
        source_file_name: str | None = None,
        source_file_uri: str | None = None,
        source_file_size_bytes: int | None = None,
    ) -> FieldVerificationBatchImportResponse:
        """批量导入外业记录并在一个事务中完成空间匹配。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 来源元数据、上传人和外业记录。
            source_checksum_sha256: 可选原始实体文件 SHA256。
            source_file_name: 可选原始实体文件名。
            source_file_uri: 可选受控原始文件 URI。
            source_file_size_bytes: 可选原始文件大小。

        Returns:
            FieldVerificationBatchImportResponse: 批次和匹配状态统计。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status in {"client_review", "completed"}:
            raise ValidationException("甲方复核或已完成任务不得导入外业记录")
        uploader = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.uploader_code,
            "upload_field_data",
        )
        verification_codes = [
            item.verification_code for item in request.records
        ]
        source_record_ids = [item.source_record_id for item in request.records]
        conflicts = await self.dao.get_import_conflicts_for_update(
            db,
            task.id,
            verification_codes,
            request.source_name,
            source_record_ids,
        )
        if conflicts:
            conflict_codes = "、".join(
                sorted(record.verification_code for record in conflicts)[:5]
            )
            suffix = "等" if len(conflicts) > 5 else ""
            raise ValidationException(
                f"外业记录编号或来源记录已存在：{conflict_codes}{suffix}"
            )

        source_payload = {
            "source_name": request.source_name,
            "source_uri": request.source_uri,
            "source_version": request.source_version,
            "records": [item.model_dump(mode="json") for item in request.records],
        }
        source_checksum = source_checksum_sha256 or sha256(
            json.dumps(
                source_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        imported_at = datetime.now(UTC)
        batch_code = (
            f"FIELD-{imported_at:%Y%m%dT%H%M%S}-"
            f"{source_checksum[:8]}-{secrets.token_hex(4)}"
        )
        config = await self.rule_config_service.ensure_for_project(
            db,
            task.project_id,
        )
        imagery = await self.workbench_dao.get_latest_imagery(db, task.project_id)
        records: list[FieldVerification] = []
        try:
            for item in request.records:
                if not await self.dao.is_point_within_project(
                    db,
                    task.project_id,
                    item.lon,
                    item.lat,
                ):
                    raise ValidationException(
                        f"外业记录 {item.verification_code} 超出项目行政区范围"
                    )
                record = FieldVerification(
                    task_id=task.id,
                    verification_code=item.verification_code,
                    investigator=uploader.display_name,
                    investigator_code=uploader.user_code,
                    observed_land_class=item.observed_land_class,
                    observed_crop_type=item.observed_crop_type,
                    photo_urls=item.photo_urls,
                    voice_url=item.voice_url,
                    remark=item.remark,
                    captured_at=item.captured_at,
                    source_name=request.source_name,
                    source_uri=request.source_uri,
                    source_version=request.source_version,
                    source_record_id=item.source_record_id,
                    source_checksum_sha256=source_checksum,
                    source_file_uri=source_file_uri,
                    source_file_size_bytes=source_file_size_bytes,
                    import_batch_code=batch_code,
                    imported_by=uploader.display_name,
                    imported_by_code=uploader.user_code,
                    imported_by_role=uploader.role_code,
                    match_status="pending",
                    resolution_status="pending",
                )
                await self.dao.create(db, record, item.lon, item.lat)
                await self._match_record(db, task, record, config, imagery)
                records.append(record)
            issue_count = sum(
                record.match_status != "consistent" for record in records
            )
            if issue_count and task.status != "interpreting":
                task.status = "interpreting"
                task.quality_score = None
            task.updated_at = imported_at
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="field_verification",
                    action="field_records_imported",
                    reviewer=uploader.display_name,
                    reviewer_code=uploader.user_code,
                    reviewer_role=uploader.role_code,
                    comment=(
                        f"批次 {batch_code} 导入 {len(records)} 条外业记录，"
                        f"生成 {issue_count} 条疑点；来源 {request.source_name} "
                        f"{request.source_version}；SHA256 {source_checksum}；"
                        f"文件 {source_file_name or '结构化请求'}；"
                        f"受控实体 {source_file_uri or '未提供'}；"
                        f"{request.comment}"
                    ),
                ),
            )
            await db.commit()
        except ValidationException:
            await db.rollback()
            raise
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException(
                "外业记录编号或来源记录与现有数据冲突"
            ) from exc
        return FieldVerificationBatchImportResponse(
            task_code=task_code,
            batch_code=batch_code,
            imported_count=len(records),
            consistent_count=sum(
                record.match_status == "consistent" for record in records
            ),
            offset_count=sum(record.match_status == "offset" for record in records),
            unmatched_count=sum(
                record.match_status == "unmatched" for record in records
            ),
            time_mismatch_count=sum(
                record.match_status == "time_mismatch" for record in records
            ),
            issue_count=issue_count,
            source_checksum_sha256=source_checksum,
            imported_by=uploader.display_name,
            imported_by_code=uploader.user_code,
            imported_by_role=uploader.role_code,
            imported_at=imported_at,
        )

    async def import_xlsx(
        self,
        db: AsyncSession,
        task_code: str,
        metadata: FieldVerificationFileImportMetadata,
        filename: str,
        content: bytes,
    ) -> FieldVerificationBatchImportResponse:
        """解析并原子导入外业核查 XLSX 实体文件。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            metadata: 来源、版本、上传人和审计说明。
            filename: 原始文件名。
            content: 原始 XLSX 字节。

        Returns:
            FieldVerificationBatchImportResponse: 导入批次和匹配统计。
        """
        records = self.workbook_parser.parse(filename, content)
        stored_workbook = await asyncio.to_thread(
            self.artifact_service.store_import_workbook,
            filename,
            content,
        )
        request = FieldVerificationBatchImportRequest(
            source_name=metadata.source_name,
            source_uri=metadata.source_uri,
            source_version=metadata.source_version,
            uploader_code=metadata.uploader_code,
            comment=metadata.comment,
            records=records,
        )
        completed = False
        try:
            result = await self.import_batch(
                db,
                task_code,
                request,
                source_checksum_sha256=stored_workbook.checksum_sha256,
                source_file_name=filename,
                source_file_uri=stored_workbook.file_uri,
                source_file_size_bytes=stored_workbook.file_size_bytes,
            )
            completed = True
            return result
        finally:
            if not completed and stored_workbook.created_new:
                stored_workbook.path.unlink(missing_ok=True)

    def build_xlsx_template(self) -> bytes:
        """生成外业核查 XLSX 导入模板。

        Returns:
            bytes: 标准 Excel 工作簿。
        """
        return self.workbook_parser.build_template()

    async def rematch_task(
        self,
        db: AsyncSession,
        task_code: str,
        request: FieldRematchRequest,
    ) -> FieldRematchResponse:
        """按当前项目规则重新匹配任务全部外业记录。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 重新匹配操作人编码。

        Returns:
            FieldRematchResponse: 匹配结果和疑点数量。
        """
        logger.info("重新匹配外业记录: task=%s", task_code)
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "rematch_field_data",
        )
        config = await self.rule_config_service.ensure_for_project(
            db,
            task.project_id,
        )
        imagery = await self.workbench_dao.get_latest_imagery(db, task.project_id)
        rows = await self.dao.get_task_records(db, task.id)
        issue_count = 0
        for row in rows:
            issue_count += await self._match_record(
                db,
                task,
                row[0],
                config,
                imagery,
            )
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="field_verification",
                action="field_records_rematched",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=f"重新匹配 {len(rows)} 条外业记录，生成 {issue_count} 条疑点",
            ),
        )
        await db.commit()
        result = await self.list_records(db, task_code)
        return FieldRematchResponse(
            matched_count=result.total,
            issue_count=issue_count,
            items=result.items,
        )

    async def resolve_record(
        self,
        db: AsyncSession,
        verification_code: str,
        request: FieldResolutionRequest,
    ) -> FieldVerificationResponse:
        """人工处置外业疑点并记录审核日志。

        Args:
            db: 异步数据库会话。
            verification_code: 外业记录编号。
            request: 处置决策、人员和说明。

        Returns:
            FieldVerificationResponse: 处置后的外业记录。
        """
        record = await self.dao.get_by_code_for_update(db, verification_code)
        if record is None:
            raise NotFoundException(f"未找到外业记录 {verification_code}")
        if record.match_status == "consistent":
            raise ValidationException("一致记录无需人工处置")
        if record.resolution_status == "resolved":
            raise ValidationException("该外业疑点已经处置")
        task = await self.workbench_dao.get_task_by_id_for_update(
            db,
            record.task_id,
        )
        if task is None:
            raise NotFoundException("外业记录关联任务不存在")
        reviewer = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.reviewer_code,
            "resolve_field_issue",
        )
        if (
            await self.artifact_dao.count_by_record_type(
                db,
                record.id,
                "photo",
            )
            == 0
        ):
            raise ValidationException(
                "外业疑点闭环前必须上传至少一张通过校验的现场照片"
            )

        plot_changed = False
        final_land_class: str | None = None
        final_crop_type: str | None = None
        if request.decision in {"use_field", "compromise"}:
            if not record.matched_plot_code:
                raise ValidationException(
                    "未匹配记录不能采用外业或折中修改，请先重新匹配或驳回"
                )
            if not await self.workbench_dao.is_plot_assigned_to_task(
                db,
                task.id,
                record.matched_plot_code,
            ):
                raise ValidationException("匹配图斑不属于当前任务")
            plot = await self.workbench_dao.get_plot_by_code(
                db,
                record.matched_plot_code,
            )
            if plot is None:
                raise NotFoundException("外业记录匹配图斑不存在")
            if request.decision == "use_field":
                if not record.observed_land_class:
                    raise ValidationException("采用外业结论前必须填写现场地类")
                final_land_class = record.observed_land_class
                final_crop_type = record.observed_crop_type
            else:
                final_land_class = request.target_land_class
                final_crop_type = request.target_crop_type
            if final_land_class == "耕地" and not final_crop_type:
                raise ValidationException("最终地类为耕地时必须填写作物类型")
            if final_land_class != "耕地" and final_crop_type:
                raise ValidationException("最终地类非耕地时不得填写作物类型")
            plot_changed = (
                plot.land_class != final_land_class
                or plot.crop_type != final_crop_type
            )
            if plot_changed:
                plot.land_class = final_land_class
                plot.crop_type = final_crop_type
                plot.version += 1
                plot.updated_at = datetime.now(UTC)
                await self.workbench_dao.add_plot_version(
                    db,
                    PlotVersion(
                        plot_code=plot.plot_code,
                        version=plot.version,
                        owner_village=getattr(plot, "owner_village", None),
                        land_class=plot.land_class,
                        crop_type=plot.crop_type,
                        planting_mode=plot.planting_mode,
                        irrigation_condition=plot.irrigation_condition,
                        interpretation_status=plot.interpretation_status,
                        geom=plot.geom,
                        change_summary=(
                            f"{FIELD_DECISION_LABELS[request.decision]}："
                            f"外业记录 {verification_code}，最终地类 "
                            f"{final_land_class}，作物 {final_crop_type or '无'}"
                        ),
                        created_by=reviewer.display_name,
                        created_by_code=reviewer.user_code,
                        created_by_role=reviewer.role_code,
                    ),
                )

        if plot_changed:
            task.status = "interpreting"
            task.quality_score = None
            task.updated_at = datetime.now(UTC)

        record.resolution_status = "resolved"
        record.resolution_decision = request.decision
        record.resolution_comment = request.comment
        record.resolved_by = reviewer.display_name
        record.resolved_by_code = reviewer.user_code
        record.resolved_by_role = reviewer.role_code
        record.updated_at = datetime.now(UTC)
        await self.dao.resolve_quality_issue(
            db,
            record.task_id,
            verification_code,
            reviewer.display_name,
            reviewer.user_code,
            reviewer.role_code,
            request.comment,
        )
        applied_attribute_summary = (
            f"最终地类 {final_land_class}；"
            f"最终作物 {final_crop_type or '无'}；"
            if final_land_class is not None
            else "图斑属性 未改写；"
        )
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=record.task_id,
                review_level="field_verification",
                action="field_issue_resolved",
                reviewer=reviewer.display_name,
                reviewer_code=reviewer.user_code,
                reviewer_role=reviewer.role_code,
                comment=(
                    f"{verification_code}："
                    f"{FIELD_DECISION_LABELS[request.decision]}；"
                    f"{applied_attribute_summary}"
                    f"依据 {request.comment}"
                ),
            ),
        )
        await db.commit()
        lon, lat = await self.dao.get_coordinates(db, record.id)
        artifacts = await self.artifact_dao.list_by_verification_ids(
            db,
            [record.id],
        )
        return self._to_response(record, lon, lat, list(artifacts))

    async def reopen_record(
        self,
        db: AsyncSession,
        verification_code: str,
        request: FieldReopenRequest,
    ) -> FieldVerificationResponse:
        """重新打开已处置外业疑点并回退任务质量门禁。

        Args:
            db: 异步数据库会话。
            verification_code: 外业记录编号。
            request: 操作人稳定编码和重新打开依据。

        Returns:
            FieldVerificationResponse: 已恢复待处置状态的外业记录。
        """
        record = await self.dao.get_by_code_for_update(db, verification_code)
        if record is None:
            raise NotFoundException(f"未找到外业记录 {verification_code}")
        if record.match_status == "consistent":
            raise ValidationException("一致记录不存在可重新打开的疑点")
        if record.resolution_status != "resolved":
            raise ValidationException("仅已完成处置的外业疑点可以重新打开")
        task = await self.workbench_dao.get_task_by_id_for_update(
            db,
            record.task_id,
        )
        if task is None:
            raise NotFoundException("外业记录关联任务不存在")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "resolve_field_issue",
        )
        previous_decision = record.resolution_decision
        previous_comment = record.resolution_comment
        issue_reopened = await self.dao.reopen_quality_issue(
            db,
            record.task_id,
            verification_code,
        )
        if not issue_reopened:
            await self.workbench_dao.add_quality_issues(
                db,
                [
                    QualityIssue(
                        task_id=record.task_id,
                        plot_code=record.matched_plot_code,
                        rule_code=f"FIELD_{verification_code}",
                        issue_type="field_verification",
                        severity="high",
                        description=(
                            f"外业记录 {verification_code} 已重新打开，"
                            "需重新核对现场证据和处置结论"
                        ),
                        status="open",
                        source="auto",
                        assignee=getattr(task, "assignee", None),
                    )
                ],
            )
        now = datetime.now(UTC)
        record.resolution_status = "pending"
        record.resolution_decision = None
        record.resolution_comment = None
        record.resolved_by = None
        record.resolved_by_code = None
        record.resolved_by_role = None
        record.updated_at = now
        task.status = "interpreting"
        task.quality_score = None
        task.updated_at = now
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=record.task_id,
                review_level="field_verification",
                action="field_issue_reopened",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=(
                    f"{verification_code}：重新打开；上次决策 "
                    f"{FIELD_DECISION_LABELS.get(previous_decision or '', '-')}；"
                    f"上次依据 {previous_comment or '-'}；"
                    f"重开依据 {request.comment}"
                ),
            ),
        )
        await db.commit()
        lon, lat = await self.dao.get_coordinates(db, record.id)
        artifacts = await self.artifact_dao.list_by_verification_ids(
            db,
            [record.id],
        )
        return self._to_response(record, lon, lat, list(artifacts))
