"""成果交付包生成、清单管理与下载业务服务。"""

import asyncio
import csv
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.delivery_dao import DeliveryArchiveState, DeliveryDAO
from app.dao.workbench_dao import QualityGateSummary, WorkbenchDAO
from app.models.disaster_report import DisasterReport
from app.models.growth_monitoring import GrowthMonitoringRun
from app.models.statistics_report import StatisticsReport
from app.models.supervision import SupervisionReport
from app.models.thematic_map import ThematicMapProduct
from app.models.vector_export import VectorExportPackage
from app.models.workbench import (
    DeliveryPackage,
    ImageryProcessingStep,
    ReviewRecord,
)
from app.schemas.delivery import (
    DeliveryGenerateRequest,
    DeliveryListResponse,
    DeliveryManifestItem,
    DeliveryPackageResponse,
)
from app.services.disaster_report_service import DisasterReportService
from app.services.disaster_service import DisasterService
from app.services.field_verification_artifact_service import (
    FieldVerificationArtifactService,
)
from app.services.growth_monitoring_service import GrowthMonitoringService
from app.services.imagery_service import ImageryService
from app.services.plot_attribute_field_service import PlotAttributeFieldService
from app.services.plot_attribute_workbook_service import (
    PlotAttributeWorkbookService,
)
from app.services.project_user_service import ProjectUserService
from app.services.statistics_report_service import StatisticsReportService
from app.services.statistics_service import StatisticsService
from app.services.supervision_service import SupervisionService
from app.services.thematic_map_service import ThematicMapService
from app.services.vector_export_service import VectorExportService


@dataclass(frozen=True)
class DeliveryArchiveEntry:
    """待写入成果 ZIP 的单个实体或生成文件。"""

    path: str
    category: str
    format: str
    record_count: int | None
    description: str
    content: bytes
    source_entity_code: str | None = None
    source_uri: str | None = None
    evidence_status: str = "included"


class DeliveryService:
    """生成可下载、可校验、可审计的成果交付包。"""

    def __init__(
        self,
        dao: DeliveryDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        statistics_service: StatisticsService | None = None,
        disaster_service: DisasterService | None = None,
        project_user_service: ProjectUserService | None = None,
        imagery_service: ImageryService | None = None,
        growth_monitoring_service: GrowthMonitoringService | None = None,
        thematic_map_service: ThematicMapService | None = None,
        supervision_service: SupervisionService | None = None,
        field_artifact_service: FieldVerificationArtifactService | None = None,
        disaster_report_service: DisasterReportService | None = None,
        statistics_report_service: StatisticsReportService | None = None,
        vector_export_service: VectorExportService | None = None,
        plot_attribute_workbook_service: PlotAttributeWorkbookService | None = None,
        plot_attribute_field_service: PlotAttributeFieldService | None = None,
    ) -> None:
        """初始化成果交付服务。

        Args:
            dao: 成果交付 DAO。
            workbench_dao: 工作台公共 DAO。
            statistics_service: 面积统计服务。
            disaster_service: 灾害评估服务。
            project_user_service: 项目用户与角色校验服务。
            imagery_service: 影像实体与处理产物校验服务。
            growth_monitoring_service: 多时相 NDVI 长势成果校验服务。
            thematic_map_service: 专题图实体校验服务。
            supervision_service: 独立监理报告实体校验服务。
            field_artifact_service: 外业核查实体证据服务。
            disaster_report_service: 灾害专题报告实体校验服务。
            statistics_report_service: 面积统计正式报告实体校验服务。
            vector_export_service: 多格式矢量成果实体校验服务。
            plot_attribute_workbook_service: 地块属性导入源文件复核服务。
            plot_attribute_field_service: 项目地块自定义字段定义服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or DeliveryDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.statistics_service = statistics_service or StatisticsService()
        self.disaster_service = disaster_service or DisasterService()
        self.project_user_service = project_user_service or ProjectUserService()
        self.imagery_service = imagery_service or ImageryService()
        self.growth_monitoring_service = (
            growth_monitoring_service or GrowthMonitoringService()
        )
        self.thematic_map_service = thematic_map_service or ThematicMapService()
        self.supervision_service = supervision_service or SupervisionService()
        self.field_artifact_service = (
            field_artifact_service or FieldVerificationArtifactService()
        )
        self.disaster_report_service = (
            disaster_report_service or DisasterReportService()
        )
        self.statistics_report_service = (
            statistics_report_service or StatisticsReportService()
        )
        self.vector_export_service = vector_export_service or VectorExportService()
        self.plot_attribute_workbook_service = (
            plot_attribute_workbook_service or PlotAttributeWorkbookService()
        )
        self.plot_attribute_field_service = (
            plot_attribute_field_service or PlotAttributeFieldService()
        )
        self.storage_dir = (
            Path(__file__).resolve().parents[2] / "storage" / "deliveries"
        )

    @staticmethod
    def _get_stale_reason(
        package: DeliveryPackage,
        task: object,
        archive_state: DeliveryArchiveState,
    ) -> str | None:
        """判断成果包是否仍对应任务当前版本。

        Args:
            package: 成果交付包模型。
            task: 当前任务模型。
            archive_state: 当前专题图、监理报告和数据资产归档状态。

        Returns:
            str | None: 失效原因；仍为当前成果时返回 None。
        """
        if package.status == "superseded":
            return "成果包已被新版本替代"
        if package.status != "completed":
            return "成果包未处于已完成状态"
        if package.completed_at is None:
            return "成果包缺少完成时间"
        if package.completed_at < task.updated_at:
            return "任务在成果包生成后发生过变更"
        package_plot_count = package.quality_summary.get("plot_count")
        if package_plot_count != task.total_plots:
            return "成果包图斑数量与当前任务作用域不一致"
        snapshot_fields = {
            "thematic_map": (
                archive_state.thematic_map_count,
                archive_state.thematic_map_latest_at,
                "专题图成果",
            ),
            "supervision_report": (
                archive_state.supervision_report_count,
                archive_state.supervision_report_latest_at,
                "独立监理报告",
            ),
            "disaster_report": (
                archive_state.disaster_report_count,
                archive_state.disaster_report_latest_at,
                "灾害专题报告",
            ),
            "statistics_report": (
                archive_state.statistics_report_count,
                archive_state.statistics_report_latest_at,
                "面积统计正式报告",
            ),
            "vector_export": (
                archive_state.vector_export_count,
                archive_state.vector_export_latest_at,
                "多格式矢量成果",
            ),
            "growth_monitoring": (
                archive_state.growth_monitoring_count,
                archive_state.growth_monitoring_latest_at,
                "长势监测成果",
            ),
            "dataset_asset": (
                archive_state.dataset_asset_count,
                archive_state.dataset_asset_latest_at,
                "多源数据资产目录",
            ),
            "imagery_step": (
                archive_state.imagery_step_count,
                archive_state.imagery_step_latest_at,
                "影像处理产物",
            ),
        }
        for prefix, values in snapshot_fields.items():
            current_count, current_latest_at, label = values
            snapshot_count = package.quality_summary.get(f"{prefix}_count")
            snapshot_latest_at = package.quality_summary.get(
                f"{prefix}_latest_at"
            )
            current_latest_text = (
                current_latest_at.isoformat() if current_latest_at else None
            )
            if snapshot_count is None and current_count > 0:
                return f"成果包缺少{label}归档快照"
            if snapshot_count is not None and int(snapshot_count) != current_count:
                return f"{label}数量在成果包生成后发生变化"
            if snapshot_latest_at != current_latest_text:
                if snapshot_latest_at is not None or current_latest_text is not None:
                    return f"{label}在成果包生成后发生更新"
        return None

    @classmethod
    def _to_response(
        cls,
        package: DeliveryPackage,
        task: object,
        archive_state: DeliveryArchiveState,
    ) -> DeliveryPackageResponse:
        """将成果包模型转换为 API 响应。

        Args:
            package: 成果交付包模型。
            task: 当前任务模型。
            archive_state: 当前归档来源聚合状态。

        Returns:
            DeliveryPackageResponse: 成果交付包响应。
        """
        stale_reason = cls._get_stale_reason(package, task, archive_state)
        return DeliveryPackageResponse(
            package_code=package.package_code,
            package_name=package.package_name,
            version=package.version,
            status=package.status,
            generated_by=package.generated_by,
            generated_by_code=package.generated_by_code,
            generated_by_role=package.generated_by_role,
            file_size_bytes=package.file_size_bytes,
            checksum_sha256=package.checksum_sha256,
            manifest=[DeliveryManifestItem(**item) for item in package.manifest],
            quality_summary=package.quality_summary,
            created_at=package.created_at,
            completed_at=package.completed_at,
            download_url=(
                f"/api/v1/deliveries/{package.package_code}/download"
                if stale_reason is None
                else None
            ),
            is_current=stale_reason is None,
            stale_reason=stale_reason,
        )

    @staticmethod
    def _get_quality_gate_blocker(
        gate: QualityGateSummary,
    ) -> str | None:
        """判断当前任务质量门禁是否具备成果生成条件。

        Args:
            gate: 当前任务图斑质量门禁汇总。

        Returns:
            str | None: 阻断原因；全部图斑通过且平均分达标时为空。
        """
        if gate.total_count == 0:
            return "当前任务没有可交付的有效图斑"
        if gate.checked_count < gate.total_count:
            return (
                "质量检查尚未覆盖全部图斑：" f"{gate.checked_count}/{gate.total_count}"
            )
        if gate.passing_count < gate.total_count:
            return "仍有图斑未通过质量门禁：" f"{gate.passing_count}/{gate.total_count}"
        if gate.average_score is None or gate.average_score < 80:
            return "任务平均质量得分不足 80"
        return None

    async def list_packages(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> DeliveryListResponse:
        """查询任务交付包和当前生成条件。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            DeliveryListResponse: 交付包列表和生成条件。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        packages = await self.dao.get_packages(db, task.id)
        imagery = await self.workbench_dao.get_latest_imagery(
            db,
            task.project_id,
        )
        archive_state = await self.dao.get_archive_state(
            db,
            task.project_id,
            task.id,
            getattr(imagery, "id", None),
        )
        open_issue_count = await self.workbench_dao.count_open_issues(db, task.id)
        pending_field_count = (
            await self.workbench_dao.count_pending_field_verifications(
                db,
                task.id,
            )
        )
        missing_field_photo_count = (
            await self.field_artifact_service.count_task_records_missing_photo(
                db,
                task.id,
            )
        )
        if task.status != "completed":
            generate_blocker = "任务需完成三级审核后才能生成成果包"
        elif open_issue_count > 0:
            generate_blocker = f"仍有 {open_issue_count} 条问题未关闭"
        elif pending_field_count > 0:
            generate_blocker = f"仍有 {pending_field_count} 条外业疑点未处置"
        elif missing_field_photo_count > 0:
            generate_blocker = (
                f"仍有 {missing_field_photo_count} 条外业记录缺少已校验现场照片"
            )
        else:
            if imagery is None:
                generate_blocker = "缺少具备实体校验的业务影像"
            else:
                quality_gate = await self.workbench_dao.get_quality_gate_summary(
                    db,
                    task.id,
                )
                generate_blocker = self._get_quality_gate_blocker(quality_gate)
        can_generate = generate_blocker is None
        return DeliveryListResponse(
            task_code=task_code,
            can_generate=can_generate,
            generate_blocker=generate_blocker,
            packages=[
                self._to_response(package, task, archive_state)
                for package in packages
            ],
        )

    async def get_current_package(
        self,
        db: AsyncSession,
        task: object,
    ) -> DeliveryPackage | None:
        """查询并判定任务当前有效成果交付包。

        Args:
            db: 异步数据库会话。
            task: 当前作业任务。

        Returns:
            DeliveryPackage | None: 当前有效成果包；不存在时为空。
        """
        packages = await self.dao.get_packages(db, task.id)
        imagery = await self.workbench_dao.get_latest_imagery(
            db,
            task.project_id,
        )
        archive_state = await self.dao.get_archive_state(
            db,
            task.project_id,
            task.id,
            getattr(imagery, "id", None),
        )
        return next(
            (
                package
                for package in packages
                if self._get_stale_reason(package, task, archive_state) is None
            ),
            None,
        )

    async def generate_package(
        self,
        db: AsyncSession,
        task_code: str,
        request: DeliveryGenerateRequest,
    ) -> DeliveryPackageResponse:
        """汇集业务数据并生成实体 ZIP 成果包。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 操作人和成果包名称。

        Returns:
            DeliveryPackageResponse: 已生成成果包。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "completed":
            raise ValidationException("任务需完成三级审核后才能生成成果包")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "generate_delivery",
        )
        open_issue_count = await self.workbench_dao.count_open_issues(db, task.id)
        if open_issue_count > 0:
            raise ValidationException(
                f"仍有 {open_issue_count} 条问题未关闭，不能生成成果包"
            )
        pending_field_count = (
            await self.workbench_dao.count_pending_field_verifications(
                db,
                task.id,
            )
        )
        if pending_field_count > 0:
            raise ValidationException(
                f"仍有 {pending_field_count} 条外业疑点未处置，不能生成成果包"
            )
        missing_field_photo_count = (
            await self.field_artifact_service.count_task_records_missing_photo(
                db,
                task.id,
            )
        )
        if missing_field_photo_count > 0:
            raise ValidationException(
                f"仍有 {missing_field_photo_count} 条外业记录缺少已校验现场照片，"
                "不能生成成果包"
            )
        imagery = await self.workbench_dao.get_latest_imagery(db, task.project_id)
        if imagery is None:
            raise ValidationException("缺少具备实体校验的业务影像，不能生成成果包")
        quality_gate = await self.workbench_dao.get_quality_gate_summary(
            db,
            task.id,
        )
        quality_gate_blocker = self._get_quality_gate_blocker(quality_gate)
        if quality_gate_blocker is not None:
            raise ValidationException(f"{quality_gate_blocker}，不能生成成果包")

        version = await self.dao.get_next_version(db, task.id)
        await self.dao.supersede_completed_packages(db, task.id)
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        package_code = f"{task_code}-DELIVERY-v{version}-{timestamp}"
        package = await self.dao.add_package(
            db,
            DeliveryPackage(
                task_id=task.id,
                package_code=package_code,
                package_name=(
                    request.package_name or f"{task.task_name}遥感监测成果包 v{version}"
                ),
                version=version,
                status="generating",
                generated_by=operator.display_name,
                generated_by_code=operator.user_code,
                generated_by_role=operator.role_code,
                manifest=[],
                quality_summary={},
            ),
        )

        source_data = await self._load_source_data(db, task)
        quality_summary = self._build_quality_summary(task, source_data)
        archive_entries = self._build_archive_entries(
            task,
            source_data,
            quality_summary,
        )
        manifest = self._build_manifest(archive_entries)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        package_path = self.storage_dir / f"{package_code}.zip"
        temporary_path = package_path.with_suffix(".zip.tmp")
        try:
            self._write_zip(
                temporary_path,
                archive_entries,
                manifest,
                quality_summary,
            )
            temporary_path.replace(package_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        package.status = "completed"
        package.file_uri = str(package_path)
        package.file_size_bytes = package_path.stat().st_size
        package.checksum_sha256 = self._calculate_sha256(package_path)
        package.manifest = manifest
        package.quality_summary = quality_summary
        package.completed_at = datetime.now(UTC)
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="delivery",
                action="delivery_package_generated",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=f"生成成果交付包 {package_code}，版本 v{version}",
            ),
        )
        await db.commit()
        await db.refresh(package)
        return self._to_response(package, task, source_data["archive_state"])

    async def get_package_for_download(
        self,
        db: AsyncSession,
        package_code: str,
        user_code: str,
    ) -> DeliveryPackage:
        """校验并返回可下载成果包。

        Args:
            db: 异步数据库会话。
            package_code: 成果包编号。
            user_code: 当前项目用户稳定编码。

        Returns:
            DeliveryPackage: 可供下载的成果包模型。
        """
        package = await self.dao.get_package_by_code(db, package_code)
        if package is None:
            raise NotFoundException(f"未找到成果包 {package_code}")
        task = await self.workbench_dao.get_task_by_id(db, package.task_id)
        if task is None:
            raise NotFoundException("成果包关联任务不存在")
        await self.project_user_service.require_capability(
            db,
            task.project_id,
            user_code,
            "download_delivery",
        )
        if package.status not in {"completed", "superseded"} or not package.file_uri:
            raise ValidationException("成果包尚未生成完成")
        imagery = await self.workbench_dao.get_latest_imagery(
            db,
            task.project_id,
        )
        archive_state = await self.dao.get_archive_state(
            db,
            task.project_id,
            task.id,
            getattr(imagery, "id", None),
        )
        stale_reason = self._get_stale_reason(package, task, archive_state)
        if stale_reason is not None:
            raise ValidationException(f"成果包已失效：{stale_reason}")
        if not Path(package.file_uri).is_file():
            raise NotFoundException("成果包文件不存在，请重新生成")
        package_path = Path(package.file_uri)
        if (
            package.file_size_bytes is None
            or package_path.stat().st_size != package.file_size_bytes
        ):
            raise ValidationException("成果包文件大小校验失败，请重新生成")
        if (
            not package.checksum_sha256
            or self._calculate_sha256(package_path) != package.checksum_sha256
        ):
            raise ValidationException("成果包完整性校验失败，请重新生成")
        return package

    async def _load_source_data(
        self,
        db: AsyncSession,
        task: object,
    ) -> dict:
        """加载成果包所需的全部业务数据。

        Args:
            db: 异步数据库会话。
            task: 当前作业任务。

        Returns:
            dict: 图斑、统计、灾害、外业、质量和审核数据。
        """
        plot_rows = await self.dao.get_plot_rows(db, task.id)
        statistics = await self.statistics_service.get_area_statistics(
            db,
            task.task_code,
        )
        disasters = await self.disaster_service.get_summary(db, task.task_code)
        quality_issues = await self.dao.get_quality_issues(db, task.id)
        field_rows = await self.dao.get_field_rows(db, task.id)
        field_artifacts = (
            await self.field_artifact_service.load_verified_task_artifacts(
                db,
                task.id,
            )
        )
        field_import_workbooks = (
            await self.field_artifact_service.load_verified_import_workbooks(
                field_rows
            )
        )
        plot_attribute_import_workbooks = (
            await self.plot_attribute_workbook_service.load_verified_import_workbooks(
                db,
                task.id,
            )
        )
        plot_attribute_fields = (
            await self.plot_attribute_field_service.get_all_fields_by_project_id(
                db,
                task.project_id,
            )
        )
        field_artifact_events = await self.field_artifact_service.list_task_events(
            db,
            task.id,
        )
        field_missing_photo_count = (
            await self.field_artifact_service.count_task_records_missing_photo(
                db,
                task.id,
            )
        )
        reviews = await self.workbench_dao.get_reviews(db, task.id)
        quality_gate = await self.workbench_dao.get_quality_gate_summary(
            db,
            task.id,
        )
        imagery = await self.workbench_dao.get_latest_imagery(
            db,
            task.project_id,
        )
        thematic_products = await self.dao.get_thematic_map_products(db, task.id)
        supervision_reports = await self.dao.get_supervision_reports(db, task.id)
        disaster_reports = await self.dao.get_disaster_reports(db, task.id)
        statistics_reports = await self.dao.get_statistics_reports(db, task.id)
        vector_exports = await self.dao.get_vector_exports(db, task.id)
        growth_monitoring_runs = await self.dao.get_growth_monitoring_runs(
            db,
            task.id,
        )
        dataset_assets = await self.dao.get_dataset_assets(
            db,
            task.project_id,
            task.id,
        )
        imagery_steps = (
            await self.dao.get_imagery_steps(db, imagery.id)
            if imagery is not None
            else []
        )
        archive_state = await self.dao.get_archive_state(
            db,
            task.project_id,
            task.id,
            getattr(imagery, "id", None),
        )
        thematic_artifacts = await self._load_thematic_artifacts(
            thematic_products
        )
        supervision_artifacts = await self._load_supervision_artifacts(
            supervision_reports
        )
        disaster_report_artifacts = await self._load_disaster_report_artifacts(
            disaster_reports
        )
        statistics_report_artifacts = (
            await self._load_statistics_report_artifacts(
                db,
                statistics_reports,
                task,
                len(plot_rows),
            )
        )
        vector_export_artifacts = await self._load_vector_export_artifacts(
            db,
            vector_exports,
            task,
        )
        growth_monitoring_artifacts = await self._load_growth_monitoring_artifacts(
            db,
            growth_monitoring_runs,
            task,
        )
        imagery_lineage = await self._build_imagery_lineage(
            imagery,
            imagery_steps,
        )
        return {
            "plot_rows": plot_rows,
            "statistics": statistics,
            "disasters": disasters,
            "quality_issues": quality_issues,
            "field_rows": field_rows,
            "field_artifacts": field_artifacts,
            "field_import_workbooks": field_import_workbooks,
            "plot_attribute_import_workbooks": plot_attribute_import_workbooks,
            "plot_attribute_fields": plot_attribute_fields,
            "field_artifact_events": field_artifact_events,
            "field_missing_photo_count": field_missing_photo_count,
            "reviews": reviews,
            "quality_gate": quality_gate,
            "imagery": imagery,
            "imagery_steps": imagery_steps,
            "imagery_lineage": imagery_lineage,
            "thematic_artifacts": thematic_artifacts,
            "supervision_artifacts": supervision_artifacts,
            "disaster_report_artifacts": disaster_report_artifacts,
            "statistics_report_artifacts": statistics_report_artifacts,
            "vector_export_artifacts": vector_export_artifacts,
            "growth_monitoring_artifacts": growth_monitoring_artifacts,
            "growth_monitoring_runs": growth_monitoring_runs,
            "dataset_assets": dataset_assets,
            "archive_state": archive_state,
        }

    async def _load_thematic_artifacts(
        self,
        products: Sequence[ThematicMapProduct],
    ) -> list[dict]:
        """校验并读取待归档专题图实体。

        Args:
            products: 已完成专题图产品序列。

        Returns:
            list[dict]: 包含实体内容和来源证据的专题图归档项。
        """
        artifacts: list[dict] = []
        for product in products:
            path = await asyncio.to_thread(
                self.thematic_map_service.verify_product_file,
                product,
            )
            content = await asyncio.to_thread(path.read_bytes)
            artifacts.append(
                {
                    "path": (
                        f"thematic_maps/{product.product_code}."
                        f"{product.output_format}"
                    ),
                    "category": "专题图成果",
                    "format": product.output_format.upper(),
                    "record_count": None,
                    "description": f"{product.map_number} · {product.map_name}",
                    "content": content,
                    "source_entity_code": product.product_code,
                    "source_uri": product.file_uri,
                }
            )
        return artifacts

    async def _load_supervision_artifacts(
        self,
        reports: Sequence[SupervisionReport],
    ) -> list[dict]:
        """校验并读取待归档独立监理报告实体。

        Args:
            reports: 任务关联监理报告序列。

        Returns:
            list[dict]: 包含实体内容和来源证据的监理报告归档项。
        """
        artifacts: list[dict] = []
        for report in reports:
            path = await asyncio.to_thread(
                self.supervision_service.verify_report_file,
                report,
            )
            content = await asyncio.to_thread(path.read_bytes)
            artifacts.append(
                {
                    "path": f"supervision/{report.report_code}.json",
                    "category": "独立监理报告",
                    "format": "JSON",
                    "record_count": None,
                    "description": "独立监理抽样、检查、整改、复检和县区评价报告",
                    "content": content,
                    "source_entity_code": report.report_code,
                    "source_uri": report.file_uri,
                }
            )
        return artifacts

    async def _load_disaster_report_artifacts(
        self,
        reports: Sequence[DisasterReport],
    ) -> list[dict]:
        """校验并读取待归档灾害专题报告实体。

        Args:
            reports: 当前有效灾害专题报告序列。

        Returns:
            list[dict]: 灾害专题报告归档项。
        """
        artifacts: list[dict] = []
        for report in reports:
            path = await asyncio.to_thread(
                self.disaster_report_service.verify_report_file,
                report,
            )
            content = await asyncio.to_thread(path.read_bytes)
            artifacts.append(
                {
                    "path": f"disasters/reports/{report.report_code}.xlsx",
                    "category": "灾害监测专题报告",
                    "format": "XLSX",
                    "record_count": report.source_patch_count,
                    "description": report.report_title,
                    "content": content,
                    "source_entity_code": report.report_code,
                    "source_uri": report.file_uri,
                }
            )
        return artifacts

    async def _load_growth_monitoring_artifacts(
        self,
        db: AsyncSession,
        runs: Sequence[GrowthMonitoringRun],
        task: object,
    ) -> list[dict]:
        """校验并读取长势分级 GeoTIFF 和异常区 GeoJSON。

        Args:
            db: 异步数据库会话。
            runs: 当前任务全部长势监测任务。
            task: 当前作业任务，用于标明快照是否仍为当前版本。

        Returns:
            list[dict]: 可直接写入成果 ZIP 的长势监测实体。
        """
        artifacts: list[dict] = []
        for run in runs:
            classification_path, anomaly_path = (
                await self.growth_monitoring_service.verify_run_for_delivery(
                    db,
                    run,
                )
            )
            snapshot_label = (
                "当前任务快照"
                if run.task_updated_at == task.updated_at
                else "历史任务快照"
            )
            classification_content = await asyncio.to_thread(
                classification_path.read_bytes
            )
            anomaly_content = await asyncio.to_thread(anomaly_path.read_bytes)
            artifacts.extend(
                [
                    {
                        "path": (
                            f"growth_monitoring/{run.run_code}/"
                            f"{run.classification_filename}"
                        ),
                        "category": "作物长势分级成果",
                        "format": "GeoTIFF",
                        "record_count": run.valid_pixel_count,
                        "description": (
                            f"{run.baseline_asset_code} → "
                            f"{run.current_asset_code} · {snapshot_label}"
                        ),
                        "content": classification_content,
                        "source_entity_code": run.run_code,
                        "source_uri": run.classification_uri,
                    },
                    {
                        "path": (
                            f"growth_monitoring/{run.run_code}/"
                            f"{run.anomaly_filename}"
                        ),
                        "category": "长势异常区",
                        "format": "GeoJSON",
                        "record_count": run.anomaly_zone_count,
                        "description": (
                            f"转差异常区 {run.anomaly_zone_count} 个 · "
                            f"{float(run.anomaly_area_ha):.4f} 公顷 · "
                            f"{snapshot_label}"
                        ),
                        "content": anomaly_content,
                        "source_entity_code": run.run_code,
                        "source_uri": run.anomaly_uri,
                    },
                ]
            )
        return artifacts

    async def _load_statistics_report_artifacts(
        self,
        db: AsyncSession,
        reports: Sequence[StatisticsReport],
        task: object,
        current_plot_count: int,
    ) -> list[dict]:
        """校验并读取当前面积统计正式报告的内部实体。

        Args:
            db: 异步数据库会话。
            reports: 当前完成状态的统计报告序列。
            task: 当前作业任务。
            current_plot_count: 当前任务有效图斑数量。

        Returns:
            list[dict]: XLSX、PDF 和 manifest 归档项。
        """
        artifacts: list[dict] = []
        for report in reports:
            await self.statistics_report_service.require_current_report(
                db,
                report,
                task,
                current_plot_count,
            )
            members = await asyncio.to_thread(
                self.statistics_report_service.read_verified_members,
                report,
            )
            for filename, content in members.items():
                suffix = Path(filename).suffix.lower()
                file_format = (
                    "JSON" if filename == "manifest.json" else suffix[1:].upper()
                )
                artifacts.append(
                    {
                        "path": f"statistics/reports/{report.report_code}/{filename}",
                        "category": "面积统计正式报告",
                        "format": file_format,
                        "record_count": report.task_plot_count,
                        "description": (
                            f"{report.report_title} V{report.version} · {file_format}"
                        ),
                        "content": content,
                        "source_entity_code": report.report_code,
                        "source_uri": report.bundle_uri,
                    }
                )
        return artifacts

    async def _load_vector_export_artifacts(
        self,
        db: AsyncSession,
        packages: Sequence[VectorExportPackage],
        task: object,
    ) -> list[dict]:
        """校验并读取当前多格式矢量成果成员。

        Args:
            db: 异步数据库会话。
            packages: 当前完成状态的矢量导出包。
            task: 当前作业任务。

        Returns:
            list[dict]: GeoJSON、Shapefile、KML、FileGDB 和清单归档项。
        """
        artifacts: list[dict] = []
        for package in packages:
            await self.vector_export_service.require_current_package(
                db,
                package,
                task,
            )
            members = await asyncio.to_thread(
                self.vector_export_service.read_verified_members,
                package,
            )
            manifest_files = {
                item["path"]: item
                for item in package.export_manifest.get("files", [])
            }
            for filename, content in members.items():
                evidence = manifest_files.get(filename, {})
                artifacts.append(
                    {
                        "path": (
                            f"vector/exports/{package.export_code}/{filename}"
                        ),
                        "category": "多格式矢量成果",
                        "format": (
                            "JSON"
                            if filename == "manifest.json"
                            else evidence.get("format", "Binary")
                        ),
                        "record_count": package.feature_count,
                        "description": (
                            f"{package.export_title} V{package.version} · "
                            f"{filename}"
                        ),
                        "content": content,
                        "source_entity_code": package.export_code,
                        "source_uri": package.file_uri,
                    }
                )
        return artifacts

    async def _build_imagery_lineage(
        self,
        imagery: object | None,
        steps: Sequence[ImageryProcessingStep],
    ) -> dict:
        """重新校验业务影像及处理产物并生成归档血缘。

        Args:
            imagery: 当前可验证业务影像。
            steps: 当前影像处理步骤序列。

        Returns:
            dict: 仅引用受控实体 URI 和校验值的影像血缘清单。
        """
        if imagery is None:
            return {"status": "not_provided", "asset": None, "steps": []}
        source_path = await asyncio.to_thread(
            self.imagery_service.resolve_verified_asset_source_path,
            imagery,
        )
        step_items: list[dict] = []
        for step in steps:
            item = {
                "step_code": step.step_code,
                "step_name": step.step_name,
                "sequence": step.sequence,
                "status": step.status,
                "progress": step.progress,
                "parameters": step.parameters,
                "output_uri": step.output_uri,
                "completed_at": step.completed_at,
                "updated_at": step.updated_at,
                "physical_evidence": None,
            }
            if step.status == "completed" and step.output_uri:
                artifact_path, evidence = await asyncio.to_thread(
                    self.imagery_service.resolve_verified_step_artifact_path,
                    step,
                )
                item["physical_evidence"] = {
                    "file_size_bytes": artifact_path.stat().st_size,
                    "checksum_sha256": evidence["checksum_sha256"],
                }
            step_items.append(item)
        return {
            "status": "verified_reference",
            "asset": {
                "asset_code": imagery.asset_code,
                "asset_name": imagery.asset_name,
                "sensor_type": imagery.sensor_type,
                "acquired_at": imagery.acquired_at,
                "processing_level": imagery.processing_level,
                "data_status": imagery.data_status,
                "file_uri": imagery.file_uri,
                "file_size_bytes": source_path.stat().st_size,
                "checksum_sha256": imagery.checksum_sha256,
                "file_format": imagery.file_format,
                "crs": imagery.crs,
                "band_count": imagery.band_count,
                "raster_metadata": imagery.raster_metadata,
            },
            "steps": step_items,
        }

    @classmethod
    def _build_archive_entries(
        cls,
        task: object,
        source_data: dict,
        quality_summary: dict,
    ) -> list[DeliveryArchiveEntry]:
        """生成标准目录下全部内嵌交付实体和报告。

        Args:
            task: 当前作业任务。
            source_data: 已校验交付源数据。
            quality_summary: 质量与归档快照摘要。

        Returns:
            list[DeliveryArchiveEntry]: 待原子写入 ZIP 的文件集合。
        """
        quality_issues = [
            {
                "plot_code": item.plot_code,
                "rule_code": item.rule_code,
                "issue_type": item.issue_type,
                "severity": item.severity,
                "description": item.description,
                "status": item.status,
                "source": item.source,
                "created_at": item.created_at,
            }
            for item in source_data["quality_issues"]
        ]
        reviews = [
            {
                "review_level": item.review_level,
                "action": item.action,
                "reviewer": item.reviewer,
                "reviewer_code": item.reviewer_code,
                "reviewer_role": item.reviewer_role,
                "comment": item.comment,
                "created_at": item.created_at,
            }
            for item in source_data["reviews"]
        ]
        dataset_catalog = [
            {
                "asset_code": item.asset_code,
                "asset_name": item.asset_name,
                "asset_type": item.asset_type,
                "source_name": item.source_name,
                "source_uri": item.source_uri,
                "source_version": item.source_version,
                "checksum_sha256": item.checksum_sha256,
                "crs": item.crs,
                "time_start": item.time_start,
                "time_end": item.time_end,
                "security_classification": item.security_classification,
                "data_status": item.data_status,
                "verification_status": item.verification_status,
                "metadata": item.metadata_payload,
                "registered_by": item.registered_by,
                "registered_by_code": item.registered_by_code,
                "registered_by_role": item.registered_by_role,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in source_data["dataset_assets"]
        ]
        field_evidence_manifest = [
            {
                "verification_code": item.verification_code,
                "artifact_code": item.artifact.artifact_code,
                "artifact_type": item.artifact.artifact_type,
                "original_filename": item.artifact.original_filename,
                "media_type": item.artifact.media_type,
                "file_uri": item.artifact.file_uri,
                "file_size_bytes": item.artifact.file_size_bytes,
                "checksum_sha256": item.artifact.checksum_sha256,
                "description": item.artifact.description,
                "uploaded_by": item.artifact.uploaded_by,
                "uploaded_by_code": item.artifact.uploaded_by_code,
                "uploaded_by_role": item.artifact.uploaded_by_role,
                "created_at": item.artifact.created_at,
            }
            for item in source_data["field_artifacts"]
        ]
        plot_attribute_import_manifest = [
            {
                "batch_code": workbook.batch_code,
                "original_filename": workbook.original_filename,
                "file_uri": workbook.file_uri,
                "file_size_bytes": workbook.file_size_bytes,
                "checksum_sha256": workbook.checksum_sha256,
                "definition_snapshot": workbook.definition_snapshot,
                "definition_digest": workbook.definition_digest,
                "row_count": workbook.row_count,
                "changed_count": workbook.changed_count,
                "unchanged_count": workbook.unchanged_count,
                "imported_by": workbook.imported_by,
                "imported_by_code": workbook.imported_by_code,
                "imported_by_role": workbook.imported_by_role,
                "import_comment": workbook.import_comment,
                "imported_at": workbook.imported_at,
                "archive_path": (
                    "attributes/import_sources/"
                    f"{workbook.batch_code}/{workbook.checksum_sha256}.xlsx"
                ),
            }
            for workbook in source_data["plot_attribute_import_workbooks"]
        ]
        plot_attribute_field_manifest = [
            PlotAttributeFieldService.definition_snapshot(field)
            for field in source_data["plot_attribute_fields"]
        ]
        archive_index = {
            "schema_version": "delivery-archive-v5",
            "task_code": task.task_code,
            "task_name": task.task_name,
            "categories": {
                "source_imagery": {
                    "status": source_data["imagery_lineage"]["status"],
                    "count": 1 if source_data["imagery"] is not None else 0,
                },
                "imagery_processing_artifacts": {
                    "status": "referenced",
                    "count": quality_summary["imagery_step_count"],
                },
                "dataset_catalog": {
                    "status": "included",
                    "count": quality_summary["dataset_asset_count"],
                },
                "thematic_maps": {
                    "status": (
                        "included"
                        if quality_summary["thematic_map_count"] > 0
                        else "not_provided"
                    ),
                    "count": quality_summary["thematic_map_count"],
                },
                "supervision_reports": {
                    "status": (
                        "included"
                        if quality_summary["supervision_report_count"] > 0
                        else "not_provided"
                    ),
                    "count": quality_summary["supervision_report_count"],
                },
                "disaster_reports": {
                    "status": (
                        "included"
                        if quality_summary["disaster_report_count"] > 0
                        else "not_provided"
                    ),
                    "count": quality_summary["disaster_report_count"],
                },
                "statistics_reports": {
                    "status": (
                        "included"
                        if quality_summary["statistics_report_count"] > 0
                        else "not_provided"
                    ),
                    "count": quality_summary["statistics_report_count"],
                },
                "vector_exports": {
                    "status": (
                        "included"
                        if quality_summary["vector_export_count"] > 0
                        else "not_provided"
                    ),
                    "count": quality_summary["vector_export_count"],
                },
                "growth_monitoring": {
                    "status": (
                        "included"
                        if quality_summary["growth_monitoring_count"] > 0
                        else "not_provided"
                    ),
                    "count": quality_summary["growth_monitoring_count"],
                    "artifact_count": len(
                        source_data["growth_monitoring_artifacts"]
                    ),
                },
                "field_evidence": {
                    "status": quality_summary["field_evidence_status"],
                    "count": (
                        quality_summary["field_verified_artifact_count"]
                        + quality_summary["field_import_workbook_count"]
                    ),
                    "record_count": quality_summary["field_verification_count"],
                    "artifact_count": quality_summary[
                        "field_verified_artifact_count"
                    ],
                    "import_workbook_count": quality_summary[
                        "field_import_workbook_count"
                    ],
                    "missing_photo_count": quality_summary[
                        "field_missing_photo_count"
                    ],
                },
                "plot_attribute_imports": {
                    "status": (
                        "included"
                        if quality_summary[
                            "plot_attribute_import_workbook_count"
                        ]
                        > 0
                        else "not_provided"
                    ),
                    "count": quality_summary[
                        "plot_attribute_import_workbook_count"
                    ],
                    "row_count": quality_summary[
                        "plot_attribute_import_row_count"
                    ],
                    "changed_count": quality_summary[
                        "plot_attribute_import_changed_count"
                    ],
                },
                "plot_attribute_field_schema": {
                    "status": "included",
                    "count": len(plot_attribute_field_manifest),
                    "active_count": sum(
                        item["status"] == "active"
                        for item in plot_attribute_field_manifest
                    ),
                },
                "disaster_evidence": {
                    "status": quality_summary["disaster_evidence_status"],
                    "count": quality_summary["disaster_patch_count"],
                },
            },
        }
        entries = [
            cls._text_entry(
                "vector/farmland_plots.geojson",
                "矢量成果",
                "GeoJSON",
                len(source_data["plot_rows"]),
                "最终地块边界及种植属性",
                cls._build_plot_geojson(source_data["plot_rows"]),
            ),
            cls._text_entry(
                "statistics/area_statistics.csv",
                "统计成果",
                "CSV",
                len(source_data["statistics"].by_village),
                "村级、地类和作物面积汇总",
                cls._build_statistics_csv(source_data["statistics"]),
            ),
            cls._text_entry(
                "disasters/disaster_patches.geojson",
                "灾害成果",
                "GeoJSON",
                source_data["disasters"].total_patches,
                "灾害等级和受灾范围图斑",
                cls._json_text(source_data["disasters"].feature_collection),
            ),
            cls._text_entry(
                "field/field_verifications.geojson",
                "外业核查",
                "GeoJSON",
                len(source_data["field_rows"]),
                "外业核查点及空间匹配结论",
                cls._build_field_geojson(source_data["field_rows"]),
            ),
            cls._text_entry(
                "field/evidence_manifest.json",
                "外业实体证据",
                "JSON",
                len(field_evidence_manifest),
                "现场照片、语音和调查表实体的来源、大小及 SHA-256 清单",
                cls._json_text(field_evidence_manifest),
            ),
            cls._text_entry(
                "field/evidence_events.json",
                "外业证据审计",
                "JSON",
                len(source_data["field_artifact_events"]),
                "外业实体证据上传和下载的稳定用户角色事件",
                cls._json_text(source_data["field_artifact_events"]),
            ),
            cls._text_entry(
                "attributes/field_definitions.json",
                "地块属性定义",
                "JSON",
                len(plot_attribute_field_manifest),
                "项目自定义字段编码、类型、必填、选项、状态和版本快照",
                cls._json_text(plot_attribute_field_manifest),
            ),
            cls._text_entry(
                "attributes/import_manifest.json",
                "地块属性导入审计",
                "JSON",
                len(plot_attribute_import_manifest),
                "逐行属性工作簿批次、实体大小、SHA-256 和稳定用户角色清单",
                cls._json_text(plot_attribute_import_manifest),
            ),
            cls._text_entry(
                "quality/quality_issues.json",
                "质量检查",
                "JSON",
                len(quality_issues),
                "质量问题和整改状态清单",
                cls._json_text(quality_issues),
            ),
            cls._text_entry(
                "review/review_records.json",
                "审核记录",
                "JSON",
                len(reviews),
                "三级审核、版本和操作审计记录",
                cls._json_text(reviews),
            ),
            cls._text_entry(
                "reports/quality_report.md",
                "质量报告",
                "Markdown",
                None,
                "成果质量检查报告",
                cls._build_quality_report(task, quality_summary),
            ),
            cls._text_entry(
                "reports/acceptance_report.md",
                "验收报告",
                "Markdown",
                None,
                "项目成果验收报告",
                cls._build_acceptance_report(task, source_data, quality_summary),
            ),
            cls._text_entry(
                "archive/imagery_lineage.json",
                "影像血缘",
                "JSON",
                quality_summary["imagery_step_count"],
                "业务影像源实体及全部处理产物校验引用",
                cls._json_text(source_data["imagery_lineage"]),
                source_entity_code=quality_summary["imagery_asset_code"],
                source_uri=getattr(source_data["imagery"], "file_uri", None),
                evidence_status="referenced",
            ),
            cls._text_entry(
                "archive/dataset_catalog.json",
                "多源数据目录",
                "JSON",
                len(dataset_catalog),
                "项目级及任务级数据资产来源、版本、密级和校验目录",
                cls._json_text(dataset_catalog),
            ),
            cls._text_entry(
                "archive/archive_index.json",
                "归档索引",
                "JSON",
                len(archive_index["categories"]),
                "各类成果的已纳入、仅引用或未提供状态",
                cls._json_text(archive_index),
            ),
        ]
        for artifact in (
            source_data["thematic_artifacts"]
            + source_data["supervision_artifacts"]
            + source_data["disaster_report_artifacts"]
            + source_data["statistics_report_artifacts"]
            + source_data["vector_export_artifacts"]
            + source_data["growth_monitoring_artifacts"]
        ):
            entries.append(DeliveryArchiveEntry(**artifact))
        for item in source_data["field_artifacts"]:
            suffix = Path(item.artifact.original_filename).suffix.lower()
            content = item.path.read_bytes()
            if (
                len(content) != item.artifact.file_size_bytes
                or hashlib.sha256(content).hexdigest()
                != item.artifact.checksum_sha256
            ):
                raise ValidationException("外业实体证据在归档写入前发生变化")
            entries.append(
                DeliveryArchiveEntry(
                    path=(
                        f"field/evidence/{item.verification_code}/"
                        f"{item.artifact.artifact_code}{suffix}"
                    ),
                    category="外业实体证据",
                    format=suffix.removeprefix(".").upper(),
                    record_count=None,
                    description=(
                        f"{item.verification_code} · "
                        f"{item.artifact.artifact_type} · "
                        f"{item.artifact.original_filename}"
                    ),
                    content=content,
                    source_entity_code=item.artifact.artifact_code,
                    source_uri=item.artifact.file_uri,
                )
            )
        for workbook in source_data["field_import_workbooks"]:
            content = workbook.path.read_bytes()
            if (
                len(content) != workbook.file_size_bytes
                or hashlib.sha256(content).hexdigest() != workbook.checksum_sha256
            ):
                raise ValidationException("外业导入工作簿在归档写入前发生变化")
            entries.append(
                DeliveryArchiveEntry(
                    path=(
                        "field/import_sources/"
                        f"{workbook.checksum_sha256}.xlsx"
                    ),
                    category="外业导入源文件",
                    format="XLSX",
                    record_count=None,
                    description=(
                        f"{workbook.source_name or '外业导入源'} · "
                        f"{workbook.source_version or '未标版本'}"
                    ),
                    content=content,
                    source_entity_code=workbook.import_batch_code,
                    source_uri=workbook.file_uri,
                )
            )
        for workbook in source_data["plot_attribute_import_workbooks"]:
            content = workbook.path.read_bytes()
            if (
                len(content) != workbook.file_size_bytes
                or hashlib.sha256(content).hexdigest()
                != workbook.checksum_sha256
            ):
                raise ValidationException(
                    "地块属性导入工作簿在归档写入前发生变化"
                )
            entries.append(
                DeliveryArchiveEntry(
                    path=(
                        "attributes/import_sources/"
                        f"{workbook.batch_code}/"
                        f"{workbook.checksum_sha256}.xlsx"
                    ),
                    category="地块属性导入源文件",
                    format="XLSX",
                    record_count=workbook.row_count,
                    description=(
                        f"{workbook.original_filename} · 更新 "
                        f"{workbook.changed_count} 个 · 未变化 "
                        f"{workbook.unchanged_count} 个"
                    ),
                    content=content,
                    source_entity_code=workbook.batch_code,
                    source_uri=workbook.file_uri,
                )
            )
        return entries

    @staticmethod
    def _text_entry(
        path: str,
        category: str,
        file_format: str,
        record_count: int | None,
        description: str,
        content: str,
        *,
        source_entity_code: str | None = None,
        source_uri: str | None = None,
        evidence_status: str = "included",
    ) -> DeliveryArchiveEntry:
        """将 UTF-8 文本转换为归档实体。

        Args:
            path: ZIP 内相对路径。
            category: 成果分类。
            file_format: 文件格式。
            record_count: 业务记录数量。
            description: 文件说明。
            content: UTF-8 文本内容。
            source_entity_code: 可选来源实体编号。
            source_uri: 可选来源实体地址。
            evidence_status: 内嵌、引用或未提供状态。

        Returns:
            DeliveryArchiveEntry: 可写入 ZIP 的字节实体。
        """
        return DeliveryArchiveEntry(
            path=path,
            category=category,
            format=file_format,
            record_count=record_count,
            description=description,
            content=content.encode("utf-8"),
            source_entity_code=source_entity_code,
            source_uri=source_uri,
            evidence_status=evidence_status,
        )

    @staticmethod
    def _build_manifest(entries: list[DeliveryArchiveEntry]) -> list[dict]:
        """构建带逐文件大小和 SHA-256 的成果清单。

        Args:
            entries: 已生成或已校验的 ZIP 文件实体。

        Returns:
            list[dict]: 成果文件清单，末项为清单自身。
        """
        manifest = [
            {
                "path": entry.path,
                "category": entry.category,
                "format": entry.format,
                "record_count": entry.record_count,
                "description": entry.description,
                "file_size_bytes": len(entry.content),
                "checksum_sha256": hashlib.sha256(entry.content).hexdigest(),
                "source_entity_code": entry.source_entity_code,
                "source_uri": entry.source_uri,
                "evidence_status": entry.evidence_status,
            }
            for entry in entries
        ]
        manifest.append(
            {
                "path": "manifest.json",
                "category": "成果清单",
                "format": "JSON",
                "record_count": len(entries),
                "description": "交付包逐文件校验值、来源和验收摘要",
                "file_size_bytes": None,
                "checksum_sha256": None,
                "source_entity_code": None,
                "source_uri": None,
                "evidence_status": "included",
            }
        )
        return manifest

    @staticmethod
    def _build_quality_summary(task: object, source_data: dict) -> dict:
        """构建交付包质量与验收摘要。

        Args:
            task: 当前作业任务。
            source_data: 成果包源数据。

        Returns:
            dict: 可持久化质量摘要。
        """
        issues = source_data["quality_issues"]
        field_rows = source_data["field_rows"]
        field_artifacts = source_data.get("field_artifacts", [])
        field_import_workbooks = source_data.get("field_import_workbooks", [])
        plot_attribute_import_workbooks = source_data.get(
            "plot_attribute_import_workbooks",
            [],
        )
        quality_gate = source_data["quality_gate"]
        imagery = source_data["imagery"]
        field_count = len(field_rows)
        disaster_count = source_data["disasters"].total_patches
        archive_state = source_data["archive_state"]
        return {
            "quality_score": float(quality_gate.average_score or 0),
            "plot_count": len(source_data["plot_rows"]),
            "quality_total_count": quality_gate.total_count,
            "quality_checked_count": quality_gate.checked_count,
            "quality_passing_count": quality_gate.passing_count,
            "quality_gate_complete": (
                DeliveryService._get_quality_gate_blocker(quality_gate) is None
            ),
            "open_issue_count": sum(issue.status == "open" for issue in issues),
            "resolved_issue_count": sum(issue.status != "open" for issue in issues),
            "field_verification_count": field_count,
            "field_verified_artifact_count": len(field_artifacts),
            "field_import_workbook_count": len(field_import_workbooks),
            "plot_attribute_import_workbook_count": len(
                plot_attribute_import_workbooks
            ),
            "plot_attribute_import_row_count": sum(
                workbook.row_count
                for workbook in plot_attribute_import_workbooks
            ),
            "plot_attribute_import_changed_count": sum(
                workbook.changed_count
                for workbook in plot_attribute_import_workbooks
            ),
            "field_missing_photo_count": source_data.get(
                "field_missing_photo_count",
                field_count if field_count > 0 else 0,
            ),
            "pending_field_count": sum(
                item.resolution_status == "pending" for item, _ in field_rows
            ),
            "field_evidence_status": (
                "not_provided"
                if field_count == 0
                else "included"
                if field_artifacts
                and source_data.get("field_missing_photo_count", 0) == 0
                else "missing_physical_evidence"
            ),
            "disaster_patch_count": disaster_count,
            "affected_area_ha": source_data["disasters"].affected_area_ha,
            "disaster_evidence_status": (
                "provided" if disaster_count > 0 else "not_provided"
            ),
            "imagery_asset_code": getattr(imagery, "asset_code", None),
            "imagery_acquired_at": getattr(imagery, "acquired_at", None),
            "imagery_processing_complete": bool(
                imagery
                and imagery.calibration_status == "completed"
                and imagery.correction_status == "completed"
            ),
            "review_record_count": len(source_data["reviews"]),
            "thematic_map_count": archive_state.thematic_map_count,
            "thematic_map_latest_at": (
                archive_state.thematic_map_latest_at.isoformat()
                if archive_state.thematic_map_latest_at
                else None
            ),
            "supervision_report_count": archive_state.supervision_report_count,
            "supervision_report_latest_at": (
                archive_state.supervision_report_latest_at.isoformat()
                if archive_state.supervision_report_latest_at
                else None
            ),
            "disaster_report_count": archive_state.disaster_report_count,
            "disaster_report_latest_at": (
                archive_state.disaster_report_latest_at.isoformat()
                if archive_state.disaster_report_latest_at
                else None
            ),
            "statistics_report_count": archive_state.statistics_report_count,
            "statistics_report_latest_at": (
                archive_state.statistics_report_latest_at.isoformat()
                if archive_state.statistics_report_latest_at
                else None
            ),
            "vector_export_count": archive_state.vector_export_count,
            "vector_export_latest_at": (
                archive_state.vector_export_latest_at.isoformat()
                if archive_state.vector_export_latest_at
                else None
            ),
            "growth_monitoring_count": archive_state.growth_monitoring_count,
            "growth_monitoring_latest_at": (
                archive_state.growth_monitoring_latest_at.isoformat()
                if archive_state.growth_monitoring_latest_at
                else None
            ),
            "dataset_asset_count": archive_state.dataset_asset_count,
            "dataset_asset_latest_at": (
                archive_state.dataset_asset_latest_at.isoformat()
                if archive_state.dataset_asset_latest_at
                else None
            ),
            "imagery_step_count": archive_state.imagery_step_count,
            "imagery_step_latest_at": (
                archive_state.imagery_step_latest_at.isoformat()
                if archive_state.imagery_step_latest_at
                else None
            ),
            "task_status": task.status,
        }

    def _write_zip(
        self,
        package_path: Path,
        entries: list[DeliveryArchiveEntry],
        manifest: list[dict],
        quality_summary: dict,
    ) -> None:
        """将业务数据和报告写入 ZIP 文件。

        Args:
            package_path: ZIP 输出路径。
            entries: 已生成或已校验的归档实体。
            manifest: 成果文件清单。
            quality_summary: 质量与验收摘要。

        Returns:
            None: 无返回值。
        """
        with ZipFile(package_path, "w", ZIP_DEFLATED) as archive:
            for entry in entries:
                archive.writestr(entry.path, entry.content)
            archive.writestr(
                "manifest.json",
                self._json_text(
                    {"manifest": manifest, "quality_summary": quality_summary}
                ),
            )

    @staticmethod
    def _build_plot_geojson(rows: list[object]) -> str:
        """生成最终图斑 GeoJSON。

        Args:
            rows: 图斑数据库行。

        Returns:
            str: GeoJSON 文本。
        """
        features = []
        for row in rows:
            features.append(
                {
                    "type": "Feature",
                    "geometry": json.loads(row.geometry),
                    "properties": {
                        "plot_code": row.plot_code,
                        "owner_village": row.owner_village,
                        "area_ha": float(row.area_ha)
                        if row.area_ha is not None
                        else None,
                        "land_class": row.land_class,
                        "crop_type": row.crop_type,
                        "planting_mode": row.planting_mode,
                        "irrigation_condition": row.irrigation_condition,
                        "custom_attributes": dict(row.custom_attributes or {}),
                        "interpretation_status": row.interpretation_status,
                        "version": row.version,
                    },
                }
            )
        return DeliveryService._json_text(
            {"type": "FeatureCollection", "features": features}
        )

    @staticmethod
    def _build_field_geojson(rows: list[tuple[object, str]]) -> str:
        """生成外业核查点 GeoJSON。

        Args:
            rows: 外业记录和点位几何。

        Returns:
            str: GeoJSON 文本。
        """
        features = [
            {
                "type": "Feature",
                "geometry": json.loads(geometry),
                "properties": {
                    "verification_code": item.verification_code,
                    "investigator": item.investigator,
                    "observed_land_class": item.observed_land_class,
                    "observed_crop_type": item.observed_crop_type,
                    "location_accuracy_m": (
                        float(item.location_accuracy_m)
                        if getattr(item, "location_accuracy_m", None) is not None
                        else None
                    ),
                    "matched_plot_code": item.matched_plot_code,
                    "offset_distance_m": float(item.offset_distance_m)
                    if item.offset_distance_m is not None
                    else None,
                    "match_status": item.match_status,
                    "resolution_status": item.resolution_status,
                    "resolution_decision": item.resolution_decision,
                    "captured_at": item.captured_at,
                    "source_name": getattr(item, "source_name", None),
                    "source_uri": getattr(item, "source_uri", None),
                    "source_version": getattr(item, "source_version", None),
                    "source_checksum_sha256": getattr(
                        item,
                        "source_checksum_sha256",
                        None,
                    ),
                    "source_file_uri": getattr(item, "source_file_uri", None),
                    "source_file_size_bytes": getattr(
                        item,
                        "source_file_size_bytes",
                        None,
                    ),
                    "legacy_photo_urls": getattr(item, "photo_urls", []),
                    "legacy_voice_url": getattr(item, "voice_url", None),
                },
            }
            for item, geometry in rows
        ]
        return DeliveryService._json_text(
            {"type": "FeatureCollection", "features": features}
        )

    @staticmethod
    def _build_statistics_csv(statistics: object) -> str:
        """生成多维面积统计 CSV。

        Args:
            statistics: 面积统计响应。

        Returns:
            str: UTF-8 CSV 文本。
        """
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["统计维度", "分类", "图斑数", "面积(公顷)", "面积(亩)", "占比(%)"]
        )
        for dimension, items in (
            ("地类", statistics.by_land_class),
            ("作物", statistics.by_crop_type),
            ("权属村", statistics.by_village),
        ):
            for item in items:
                writer.writerow(
                    [
                        dimension,
                        item.label,
                        item.plot_count,
                        item.area_ha,
                        item.area_mu,
                        item.percentage,
                    ]
                )
        return "\ufeff" + output.getvalue()

    @staticmethod
    def _build_quality_report(task: object, summary: dict) -> str:
        """生成质量检查报告。

        Args:
            task: 当前作业任务。
            summary: 质量与验收摘要。

        Returns:
            str: Markdown 质量报告。
        """
        imagery_text = (
            f"{summary['imagery_asset_code']} / {summary['imagery_acquired_at']}"
            if summary["imagery_asset_code"]
            else "未关联可验证业务影像"
        )
        field_text = (
            f"已纳入 {summary['field_verification_count']} 条外业核查记录，"
            f"嵌入 {summary['field_verified_artifact_count']} 份通过大小、格式和 "
            "SHA-256 复核的现场实体证据，待处置记录和缺失照片记录均为 0。"
            if summary["field_verification_count"] > 0
            else "本成果包未包含外业核查记录，不作外业一致性结论。"
        )
        return f"""# 遥感监测成果质量检查报告

- 作业任务：{task.task_code} / {task.task_name}
- 行政区域：{task.administrative_region}
- 业务影像：{imagery_text}
- 质量得分：{summary['quality_score']}
- 最终图斑数：{summary['plot_count']}
- 质量检查覆盖：{summary['quality_checked_count']} / {summary['quality_total_count']}
- 质量门禁通过：{summary['quality_passing_count']} / {summary['quality_total_count']}
- 未关闭问题：{summary['open_issue_count']}
- 已整改问题：{summary['resolved_issue_count']}
- 外业核查记录：{summary['field_verification_count']}
- 外业实体证据：{summary['field_verified_artifact_count']}
- 外业导入源工作簿：{summary['field_import_workbook_count']}
- 地块属性导入工作簿：{summary['plot_attribute_import_workbook_count']}
- 地块属性导入行数：{summary['plot_attribute_import_row_count']}
- 地块属性实际更新：{summary['plot_attribute_import_changed_count']}
- 缺少实体照片：{summary['field_missing_photo_count']}
- 待处置外业记录：{summary['pending_field_count']}
- 实体专题图：{summary['thematic_map_count']} 张
- 独立监理报告：{summary['supervision_report_count']} 份
- 灾害专题报告：{summary['disaster_report_count']} 份
- 作物长势监测：{summary['growth_monitoring_count']} 期
- 多源数据资产目录：{summary['dataset_asset_count']} 项
- 已校验影像处理产物：{summary['imagery_step_count']} 项

## 质量结论

当前任务质量门禁已覆盖全部交付图斑，所有阻断规则均已通过，
且任务已完成三级成果审核。具体逐图规则、问题整改和版本证据
以交付包内 JSON 数据为准。

{field_text}
"""

    @staticmethod
    def _build_acceptance_report(
        task: object,
        source_data: dict,
        summary: dict,
    ) -> str:
        """生成项目验收报告。

        Args:
            task: 当前作业任务。
            source_data: 成果包源数据。
            summary: 质量与验收摘要。

        Returns:
            str: Markdown 验收报告。
        """
        statistics = source_data["statistics"]
        field_text = (
            f"已提供 {summary['field_verification_count']} 条外业核查记录及 "
            f"{summary['field_verified_artifact_count']} 份校验通过的现场实体证据"
            if summary["field_verification_count"] > 0
            else "未提供外业核查记录，外业文件为空集合"
        )
        disaster_text = (
            f"已提供 {summary['disaster_patch_count']} 个灾害斑块"
            if summary["disaster_patch_count"] > 0
            else "未导入灾害模型成果，灾害文件为空集合"
        )
        disaster_report_text = (
            "已纳入 XLSX 实体报告"
            if summary["disaster_report_count"] > 0
            else "未提供"
        )
        attribute_import_text = (
            "已纳入原始 XLSX 与批次审计"
            if summary["plot_attribute_import_workbook_count"] > 0
            else "未提供属性工作簿导入记录"
        )
        growth_monitoring_text = (
            "已纳入分级 GeoTIFF 与异常区 GeoJSON"
            if summary["growth_monitoring_count"] > 0
            else "未提供"
        )
        return f"""# 遥感监测项目验收报告

## 基本信息

- 任务编号：{task.task_code}
- 作业单元：{task.task_name}
- 监测区域：{task.administrative_region}
- 审核状态：三级审核完成

## 工作量与成果

- 图斑数量：{summary['plot_count']} 个
- 监测面积：{statistics.total_area_ha} 公顷 / {statistics.total_area_mu} 亩
- 灾害斑块：{summary['disaster_patch_count']} 个
- 受灾面积：{summary['affected_area_ha']} 公顷
- 外业核查：{summary['field_verification_count']} 条
- 外业实体证据：{summary['field_verified_artifact_count']} 份
- 外业导入源工作簿：{summary['field_import_workbook_count']} 份
- 地块属性导入工作簿：{summary['plot_attribute_import_workbook_count']} 份
- 地块属性导入行数：{summary['plot_attribute_import_row_count']} 行
- 地块属性实际更新：{summary['plot_attribute_import_changed_count']} 个图斑
- 审核及操作记录：{summary['review_record_count']} 条
- 专题图成果：{summary['thematic_map_count']} 张
- 独立监理报告：{summary['supervision_report_count']} 份
- 灾害专题报告：{summary['disaster_report_count']} 份
- 作物长势监测：{summary['growth_monitoring_count']} 期
- 多源数据资产：{summary['dataset_asset_count']} 项
- 影像处理产物：{summary['imagery_step_count']} 项

## 专项证据状态

- 外业核查：{field_text}
- 地块属性导入：{attribute_import_text}
- 灾害监测：{disaster_text}
- 灾害专题报告：{disaster_report_text}
- 作物长势监测：{growth_monitoring_text}
- 业务影像：{summary['imagery_asset_code'] or '未关联'}
- 专题图：{'已纳入实体成果' if summary['thematic_map_count'] > 0 else '未提供'}
- 独立监理：{'已纳入实体报告' if summary['supervision_report_count'] > 0 else '未提供'}

## 验收结论

本成果包包含最终地块数据、属性、属性工作簿导入证据、面积统计、
完整质量问题清单、审核记录、
质量报告、影像血缘和数据资产目录。外业照片、语音、调查表、专题图、灾害专题
报告与独立监理报告均以通过受控路径、格式、大小和 SHA-256 复核的原始实体写入；
外业、灾害、
专题图和监理证据是否存在以上述
专项证据状态为准，不以空集合冒充已完成成果。

文件清单与校验摘要已写入 manifest.json，可进入甲方成果交付和归档环节。
"""

    @staticmethod
    def _json_text(value: object) -> str:
        """序列化为格式化中文 JSON。

        Args:
            value: 待序列化对象。

        Returns:
            str: JSON 文本。
        """
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def _calculate_sha256(path: Path) -> str:
        """计算文件 SHA-256 校验值。

        Args:
            path: 待校验文件路径。

        Returns:
            str: 十六进制 SHA-256。
        """
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
