"""任务地块属性 Excel 导入导出业务服务。"""

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.plot_attribute_workbook_dao import PlotAttributeWorkbookDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.plot import FarmlandPlot
from app.models.plot_attribute_workbook import PlotAttributeImportBatch
from app.models.workbench import PlotVersion, ReviewRecord
from app.schemas.plot_attribute_workbook import (
    PlotAttributeImportBatchListResponse,
    PlotAttributeImportBatchResponse,
    PlotAttributeWorkbookExportRequest,
    PlotAttributeWorkbookImportMetadata,
    PlotAttributeWorkbookRow,
)
from app.services.plot_attribute_field_service import PlotAttributeFieldService
from app.services.plot_attribute_workbook_parser import (
    MAX_WORKBOOK_ROWS,
    PlotAttributeWorkbookParser,
)
from app.services.plot_attribute_workbook_storage import (
    PlotAttributeWorkbookStorage,
    VerifiedPlotAttributeImportWorkbook,
)
from app.services.project_user_service import ProjectUserService


@dataclass(frozen=True)
class PlotAttributeWorkbookExport:
    """可直接作为 HTTP 附件返回的地块属性工作簿。"""

    filename: str
    content: bytes
    row_count: int


class PlotAttributeWorkbookService:
    """编排任务范围校验、并发检查、版本生成和实体审计。"""

    def __init__(
        self,
        dao: PlotAttributeWorkbookDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        parser: PlotAttributeWorkbookParser | None = None,
        storage: PlotAttributeWorkbookStorage | None = None,
        user_service: ProjectUserService | None = None,
        field_service: PlotAttributeFieldService | None = None,
    ) -> None:
        """初始化地块属性工作簿服务。

        Args:
            dao: 导入批次 DAO。
            workbench_dao: 任务、图斑、版本和审核 DAO。
            parser: XLSX 安全解析与生成器。
            storage: 原始工作簿受控存储。
            user_service: 稳定项目用户权限服务。
            field_service: 项目自定义字段定义与值校验服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or PlotAttributeWorkbookDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.parser = parser or PlotAttributeWorkbookParser()
        self.storage = storage or PlotAttributeWorkbookStorage()
        self.user_service = user_service or ProjectUserService()
        self.field_service = field_service or PlotAttributeFieldService()

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """提取受控长度的原始文件名。

        Args:
            filename: 上传端提供的文件名。

        Returns:
            str: 不包含目录的安全展示文件名。
        """
        normalized = Path(filename.strip()).name
        if not normalized:
            return "plot_attributes.xlsx"
        return normalized[:255]

    @staticmethod
    def _build_version(
        plot: FarmlandPlot,
        operator_name: str,
        operator_code: str,
        operator_role: str,
        change_summary: str,
    ) -> PlotVersion:
        """根据已更新图斑生成完整不可变版本。

        Args:
            plot: 已应用新属性和版本号的图斑。
            operator_name: 操作人显示名称。
            operator_code: 操作人稳定编码。
            operator_role: 操作时角色快照。
            change_summary: Excel 导入证据说明。

        Returns:
            PlotVersion: 待持久化完整版本。
        """
        return PlotVersion(
            plot_code=plot.plot_code,
            version=plot.version,
            owner_village=plot.owner_village,
            land_class=plot.land_class,
            crop_type=plot.crop_type,
            planting_mode=plot.planting_mode,
            irrigation_condition=plot.irrigation_condition,
            custom_attributes=dict(getattr(plot, "custom_attributes", {}) or {}),
            interpretation_status=plot.interpretation_status,
            geom=plot.geom,
            change_summary=change_summary,
            created_by=operator_name,
            created_by_code=operator_code,
            created_by_role=operator_role,
        )

    @staticmethod
    def _row_changes_plot(
        row: PlotAttributeWorkbookRow,
        plot: FarmlandPlot,
    ) -> bool:
        """判断工作簿行是否改变任一受控业务属性。

        Args:
            row: 已校验工作簿行。
            plot: 数据库当前图斑。

        Returns:
            bool: 至少一项属性不同时返回 True。
        """
        return any(
            (
                plot.owner_village != row.owner_village,
                plot.land_class != row.land_class,
                plot.crop_type != row.crop_type,
                plot.planting_mode != row.planting_mode,
                plot.irrigation_condition != row.irrigation_condition,
                dict(getattr(plot, "custom_attributes", {}) or {})
                != row.custom_attributes,
            )
        )

    @staticmethod
    def _to_batch_response(
        batch: PlotAttributeImportBatch,
        task_code: str,
        updated_plot_codes: list[str] | None = None,
    ) -> PlotAttributeImportBatchResponse:
        """将导入批次转换为前端证据响应。

        Args:
            batch: 数据库导入批次。
            task_code: 作业任务编号。
            updated_plot_codes: 当前请求实际产生新版本的编号。

        Returns:
            PlotAttributeImportBatchResponse: 导入证据摘要。
        """
        return PlotAttributeImportBatchResponse(
            batch_code=batch.batch_code,
            task_code=task_code,
            original_filename=batch.original_filename,
            file_size_bytes=batch.file_size_bytes,
            checksum_sha256=batch.checksum_sha256,
            definition_snapshot=list(batch.definition_snapshot or []),
            definition_digest=batch.definition_digest,
            row_count=batch.row_count,
            changed_count=batch.changed_count,
            unchanged_count=batch.unchanged_count,
            updated_plot_codes=updated_plot_codes or [],
            imported_by=batch.imported_by,
            imported_by_code=batch.imported_by_code,
            imported_by_role=batch.imported_by_role,
            import_comment=batch.import_comment,
            imported_at=batch.imported_at,
            quality_recheck_required=batch.changed_count > 0,
        )

    async def export_workbook(
        self,
        db: AsyncSession,
        task_code: str,
        request: PlotAttributeWorkbookExportRequest,
    ) -> PlotAttributeWorkbookExport:
        """导出任务全部或显式选择的当前地块属性。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 操作人和可选显式图斑范围。

        Returns:
            PlotAttributeWorkbookExport: 标准 XLSX 内容和文件名。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中的任务可以导出属性回写工作簿")
        await self.user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "export_plot_attributes",
        )
        if request.plot_codes is None:
            task_plot_count, _ = await self.workbench_dao.count_plot_progress(
                db,
                task.id,
            )
            if task_plot_count > MAX_WORKBOOK_ROWS:
                raise ValidationException(
                    f"当前任务有 {task_plot_count} 个有效图斑，"
                    "单次最多导出 500 个；"
                    "请显式填写图斑编号范围"
                )
            plots = list(await self.workbench_dao.get_task_plots(db, task.id))
        else:
            plots = list(
                await self.workbench_dao.get_task_plots_by_codes(
                    db,
                    task.id,
                    request.plot_codes,
                )
            )
            found_codes = {plot.plot_code for plot in plots}
            missing_codes = [
                code for code in request.plot_codes if code not in found_codes
            ]
            if missing_codes:
                sample = "、".join(missing_codes[:5])
                suffix = "等" if len(missing_codes) > 5 else ""
                raise ValidationException(
                    f"有 {len(missing_codes)} 个图斑不属于任务或已删除："
                    f"{sample}{suffix}"
                )
        if not plots:
            raise ValidationException("当前导出范围没有有效图斑")
        active_fields = await self.field_service.get_active_fields_by_project_id(
            db,
            task.project_id,
        )
        definition_snapshot = self.field_service.build_schema_snapshot(active_fields)
        safe_task_code = re.sub(r"[^\w-]+", "_", task_code)
        return PlotAttributeWorkbookExport(
            filename=f"{safe_task_code}_plot_attributes.xlsx",
            content=self.parser.build_export(plots, definition_snapshot),
            row_count=len(plots),
        )

    async def import_workbook(
        self,
        db: AsyncSession,
        task_code: str,
        metadata: PlotAttributeWorkbookImportMetadata,
        filename: str,
        content: bytes,
    ) -> PlotAttributeImportBatchResponse:
        """校验并原子导入逐行不同的任务地块属性。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            metadata: 稳定操作人编码和人工证据说明。
            filename: 原始工作簿文件名。
            content: 原始 XLSX 字节。

        Returns:
            PlotAttributeImportBatchResponse: 批次、实体证据和变更数量。
        """
        task_snapshot = await self.workbench_dao.get_task_by_code(db, task_code)
        if task_snapshot is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task_snapshot.status != "interpreting":
            raise ValidationException("仅解译中的任务可以导入地块属性")
        await self.user_service.require_capability(
            db,
            task_snapshot.project_id,
            metadata.operator_code,
            "import_plot_attributes",
        )
        active_fields = await self.field_service.get_active_fields_by_project_id(
            db,
            task_snapshot.project_id,
        )
        definition_snapshot = self.field_service.build_schema_snapshot(active_fields)
        definition_digest = self.field_service.schema_digest(definition_snapshot)
        parsed = self.parser.parse(
            filename,
            content,
            expected_snapshot=definition_snapshot,
            expected_digest=definition_digest,
        )
        rows = parsed.rows
        stored = await asyncio.to_thread(self.storage.store, filename, content)
        completed = False
        try:
            task = await self.workbench_dao.get_task_by_code_for_update(
                db,
                task_code,
            )
            if task is None:
                raise NotFoundException(f"未找到任务 {task_code}")
            if task.status != "interpreting":
                raise ValidationException("仅解译中的任务可以导入地块属性")
            operator = await self.user_service.require_capability(
                db,
                task.project_id,
                metadata.operator_code,
                "import_plot_attributes",
            )
            all_field_definitions = (
                await self.field_service.get_all_fields_by_project_id(
                    db,
                    task.project_id,
                )
            )
            plot_codes = [row.plot_code for row in rows]
            plots = list(
                await self.workbench_dao.get_task_plots_by_codes_for_update(
                    db,
                    task.id,
                    plot_codes,
                )
            )
            plots_by_code = {plot.plot_code: plot for plot in plots}
            missing_codes = [code for code in plot_codes if code not in plots_by_code]
            if missing_codes:
                sample = "、".join(missing_codes[:5])
                suffix = "等" if len(missing_codes) > 5 else ""
                raise ValidationException(
                    f"有 {len(missing_codes)} 个图斑不属于任务或已删除："
                    f"{sample}{suffix}"
                )

            stale_rows = [
                row
                for row in rows
                if plots_by_code[row.plot_code].version != row.expected_version
            ]
            if stale_rows:
                sample = "、".join(
                    f"{row.plot_code}(期望 v{row.expected_version}，当前 "
                    f"v{plots_by_code[row.plot_code].version})"
                    for row in stale_rows[:5]
                )
                suffix = "等" if len(stale_rows) > 5 else ""
                raise ValidationException(
                    f"有 {len(stale_rows)} 个图斑版本已变化：{sample}{suffix}；"
                    "请重新导出工作簿后再导入"
                )

            updated_at = datetime.now(UTC)
            change_summary = (
                f"属性 Excel 原子导入 {Path(filename).name}；{metadata.comment}"
            )[:500]
            versions: list[PlotVersion] = []
            updated_plot_codes: list[str] = []
            for row in rows:
                plot = plots_by_code[row.plot_code]
                normalized_custom_attributes = (
                    self.field_service.validate_custom_attributes(
                        all_field_definitions,
                        row.custom_attributes,
                        existing=dict(getattr(plot, "custom_attributes", {}) or {}),
                    )
                )
                row = row.model_copy(
                    update={"custom_attributes": normalized_custom_attributes}
                )
                if not self._row_changes_plot(row, plot):
                    continue
                plot.owner_village = row.owner_village
                plot.land_class = row.land_class
                plot.crop_type = row.crop_type
                plot.planting_mode = row.planting_mode
                plot.irrigation_condition = row.irrigation_condition
                plot.custom_attributes = row.custom_attributes
                plot.interpretation_status = "interpreted"
                plot.version += 1
                plot.updated_at = updated_at
                updated_plot_codes.append(plot.plot_code)
                versions.append(
                    self._build_version(
                        plot,
                        operator.display_name,
                        operator.user_code,
                        operator.role_code,
                        change_summary,
                    )
                )

            changed_count = len(updated_plot_codes)
            unchanged_count = len(rows) - changed_count
            if versions:
                await self.workbench_dao.add_plot_versions(db, versions)
                await self.dao.reset_quality_evidence(
                    db,
                    task.id,
                    updated_plot_codes,
                )
                await self.workbench_dao.supersede_reverted_plot_operations(
                    db,
                    task.id,
                )
                (
                    total_plots,
                    completed_plots,
                ) = await self.workbench_dao.count_plot_progress(db, task.id)
                task.status = "interpreting"
                task.total_plots = total_plots
                task.completed_plots = completed_plots
                task.quality_score = None
                task.updated_at = updated_at

            batch = await self.dao.add_batch(
                db,
                PlotAttributeImportBatch(
                    task_id=task.id,
                    batch_code=(
                        f"PATTR-{updated_at.strftime('%Y%m%d%H%M%S')}-"
                        f"{uuid4().hex[:10].upper()}"
                    ),
                    original_filename=self._safe_filename(filename),
                    file_uri=stored.file_uri,
                    file_size_bytes=stored.file_size_bytes,
                    checksum_sha256=stored.checksum_sha256,
                    definition_snapshot=parsed.definition_snapshot,
                    definition_digest=parsed.definition_digest,
                    row_count=len(rows),
                    changed_count=changed_count,
                    unchanged_count=unchanged_count,
                    imported_by=operator.display_name,
                    imported_by_code=operator.user_code,
                    imported_by_role=operator.role_code,
                    import_comment=metadata.comment,
                    imported_at=updated_at,
                ),
            )
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="interpretation",
                    action=(
                        "plot_attributes_xlsx_imported"
                        if changed_count
                        else "plot_attributes_xlsx_validated"
                    ),
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"地块属性工作簿 {batch.original_filename} 原子校验 "
                        f"{batch.row_count} 行，更新 {changed_count} 个、"
                        f"未变化 {unchanged_count} 个；文件 {batch.file_size_bytes} "
                        f"字节，SHA256={batch.checksum_sha256}；"
                        f"{metadata.comment}"
                    ),
                ),
            )
            await db.commit()
            completed = True
            return self._to_batch_response(batch, task_code, updated_plot_codes)
        finally:
            if not completed and stored.created_new:
                stored.path.unlink(missing_ok=True)

    async def list_import_batches(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> PlotAttributeImportBatchListResponse:
        """查询任务最近的属性工作簿导入证据。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            PlotAttributeImportBatchListResponse: 最近 20 个导入批次。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        batches = await self.dao.list_batches(db, task.id)
        return PlotAttributeImportBatchListResponse(
            task_code=task_code,
            items=[self._to_batch_response(batch, task_code) for batch in batches],
        )

    async def load_verified_import_workbooks(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> list[VerifiedPlotAttributeImportWorkbook]:
        """加载任务全部属性导入源文件并执行成果归档前复核。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            list[VerifiedPlotAttributeImportWorkbook]: 通过实体复核的工作簿。
        """
        batches = await self.dao.list_all_batches(db, task_id)
        verified: list[VerifiedPlotAttributeImportWorkbook] = []
        for batch in batches:
            verified.append(
                await asyncio.to_thread(
                    self.storage.verify_import_workbook,
                    batch,
                    self.parser,
                )
            )
        return verified
