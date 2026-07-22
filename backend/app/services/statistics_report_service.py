"""面积统计正式报告包生成、失效、下载与归档服务。"""

import asyncio
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.statistics_dao import StatisticsDAO
from app.dao.statistics_report_dao import StatisticsReportDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.statistics_report import StatisticsReport
from app.models.workbench import ReviewRecord
from app.schemas.statistics import (
    StatisticsReportGenerateRequest,
    StatisticsReportListResponse,
    StatisticsReportResponse,
)
from app.services.project_user_service import ProjectUserService
from app.services.statistics_report_renderer import StatisticsReportRenderer
from app.services.statistics_service import StatisticsService


@dataclass(frozen=True)
class StatisticsReportDownload:
    """通过权限和实体复核的统计报告下载信息。"""

    path: Path
    filename: str
    checksum_sha256: str


class StatisticsReportService:
    """生成并管理包含 XLSX、PDF 和清单的统计报告包。"""

    def __init__(
        self,
        dao: StatisticsReportDAO | None = None,
        statistics_dao: StatisticsDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        statistics_service: StatisticsService | None = None,
        project_user_service: ProjectUserService | None = None,
        renderer: StatisticsReportRenderer | None = None,
        storage_root: Path | None = None,
    ) -> None:
        """初始化统计报告服务。

        Args:
            dao: 统计报告 DAO。
            statistics_dao: 面积聚合 DAO。
            workbench_dao: 工作台公共 DAO。
            statistics_service: 面积统计业务服务。
            project_user_service: 项目用户能力服务。
            renderer: XLSX/PDF 渲染器。
            storage_root: 可注入受控存储根目录。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or StatisticsReportDAO()
        self.statistics_dao = statistics_dao or StatisticsDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.statistics_service = statistics_service or StatisticsService()
        self.project_user_service = project_user_service or ProjectUserService()
        self.renderer = renderer or StatisticsReportRenderer()
        self.storage_root = storage_root or (
            Path(__file__).resolve().parents[2] / "storage" / "statistics-reports"
        )

    def _resolve_path(self, relative_path: str) -> Path:
        """解析并约束统计报告受控路径。

        Args:
            relative_path: 相对于报告存储根目录的路径。

        Returns:
            Path: 未越界的绝对路径。
        """
        root = self.storage_root.resolve()
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root):
            raise ValidationException("面积统计报告存储路径越界")
        return path

    @staticmethod
    def _same_datetime(left: datetime | None, right: datetime | None) -> bool:
        """比较可能来自数据库驱动的时区时间值。

        Args:
            left: 左侧时间。
            right: 右侧时间。

        Returns:
            bool: 两者均为空或代表同一时刻时为真。
        """
        if left is None or right is None:
            return left is right
        left_value = left if left.tzinfo else left.replace(tzinfo=UTC)
        right_value = right if right.tzinfo else right.replace(tzinfo=UTC)
        return left_value.astimezone(UTC) == right_value.astimezone(UTC)

    @classmethod
    def get_stale_reason(
        cls,
        report: StatisticsReport,
        task: object,
        current_plot_count: int,
        history_state: tuple[int, datetime | None],
    ) -> str | None:
        """判断报告是否仍对应当前任务与历史快照。

        Args:
            report: 报告模型。
            task: 当前作业任务。
            current_plot_count: 当前任务有效图斑数量。
            history_state: 当前历史快照数量与最近更新时间。

        Returns:
            str | None: 失效原因；当前有效时为空。
        """
        if report.status == "invalid":
            return "报告实体已损坏或缺失"
        if report.status == "superseded":
            return "报告已被新版本替代或来源数据发生变化"
        if report.status != "completed":
            return "报告未处于已完成状态"
        if report.task_plot_count != current_plot_count:
            return "任务有效图斑数量在报告生成后发生变化"
        if not cls._same_datetime(
            report.task_updated_at_snapshot,
            task.updated_at,
        ):
            return "任务数据在报告生成后发生更新"
        history_count, history_latest_at = history_state
        if report.history_snapshot_count != history_count:
            return "历史年度统计快照数量发生变化"
        if not cls._same_datetime(
            report.history_latest_updated_at,
            history_latest_at,
        ):
            return "历史年度统计快照发生更新"
        return None

    def verify_report_bundle(self, report: StatisticsReport) -> Path:
        """复核 ZIP、内嵌 XLSX/PDF 和 manifest 的大小与 SHA-256。

        Args:
            report: 统计报告模型。

        Returns:
            Path: 已验证 ZIP 报告包路径。
        """
        prefix = "storage://statistics-reports/"
        if not report.bundle_uri.startswith(prefix):
            raise ValidationException("面积统计报告未登记受控文件地址")
        path = self._resolve_path(report.bundle_uri.removeprefix(prefix))
        if not path.is_file():
            raise NotFoundException("面积统计报告实体文件不存在")
        if path.stat().st_size != report.bundle_size_bytes:
            raise ValidationException("面积统计报告包大小校验失败")
        if path.read_bytes()[:4] != b"PK\x03\x04":
            raise ValidationException("面积统计报告包不是有效 ZIP 文件")
        if calculate_sha256(path) != report.bundle_checksum_sha256:
            raise ValidationException("面积统计报告包 SHA-256 校验失败")
        xlsx_name = f"{report.report_code}.xlsx"
        pdf_name = f"{report.report_code}.pdf"
        try:
            with ZipFile(path) as archive:
                names = set(archive.namelist())
                expected = {xlsx_name, pdf_name, "manifest.json"}
                if names != expected:
                    raise ValidationException("面积统计报告包文件清单不完整")
                xlsx_content = archive.read(xlsx_name)
                pdf_content = archive.read(pdf_name)
                manifest_content = archive.read("manifest.json")
        except BadZipFile as exc:
            raise ValidationException("面积统计报告包 ZIP 结构损坏") from exc
        if (
            len(xlsx_content) != report.xlsx_size_bytes
            or calculate_sha256_bytes(xlsx_content) != report.xlsx_checksum_sha256
            or not xlsx_content.startswith(b"PK\x03\x04")
        ):
            raise ValidationException("面积统计 XLSX 实体校验失败")
        if (
            len(pdf_content) != report.pdf_size_bytes
            or calculate_sha256_bytes(pdf_content) != report.pdf_checksum_sha256
            or not pdf_content.startswith(b"%PDF")
        ):
            raise ValidationException("面积统计 PDF 实体校验失败")
        try:
            manifest = json.loads(manifest_content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationException("面积统计报告清单结构损坏") from exc
        if manifest != report.report_manifest:
            raise ValidationException("面积统计报告清单与数据库快照不一致")
        self._validate_manifest_evidence(
            report,
            manifest,
            xlsx_name,
            xlsx_content,
            pdf_name,
            pdf_content,
        )
        return path

    @classmethod
    def _validate_manifest_evidence(
        cls,
        report: StatisticsReport,
        manifest: dict,
        xlsx_name: str,
        xlsx_content: bytes,
        pdf_name: str,
        pdf_content: bytes,
    ) -> None:
        """交叉校验 manifest、报告表快照与内部文件实体。

        Args:
            report: 报告数据库实体。
            manifest: ZIP 内清单。
            xlsx_name: XLSX 文件名。
            xlsx_content: XLSX 实体字节。
            pdf_name: PDF 文件名。
            pdf_content: PDF 实体字节。

        Returns:
            None: 全部证据一致时无返回值。
        """
        if (
            manifest.get("report_code") != report.report_code
            or manifest.get("version") != report.version
        ):
            raise ValidationException("面积统计报告清单版本身份不一致")
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) != 2:
            raise ValidationException("面积统计报告清单文件证据不完整")
        file_map = {
            item.get("path"): item
            for item in files
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        expected_files = {
            xlsx_name: (
                "XLSX",
                len(xlsx_content),
                calculate_sha256_bytes(xlsx_content),
            ),
            pdf_name: (
                "PDF",
                len(pdf_content),
                calculate_sha256_bytes(pdf_content),
            ),
        }
        if set(file_map) != set(expected_files):
            raise ValidationException("面积统计报告清单文件名不一致")
        for filename, (file_format, size_bytes, checksum) in expected_files.items():
            item = file_map[filename]
            if (
                item.get("format") != file_format
                or item.get("file_size_bytes") != size_bytes
                or item.get("checksum_sha256") != checksum
            ):
                raise ValidationException(
                    f"面积统计报告清单中的 {file_format} 证据不一致"
                )
        task_snapshot = manifest.get("task")
        if not isinstance(task_snapshot, dict):
            raise ValidationException("面积统计报告清单缺少任务快照")
        if task_snapshot.get("task_plot_count") != report.task_plot_count:
            raise ValidationException("面积统计报告清单图斑数量不一致")
        task_updated_at = cls._parse_manifest_datetime(
            task_snapshot.get("task_updated_at_snapshot")
        )
        if not cls._same_datetime(
            task_updated_at,
            report.task_updated_at_snapshot,
        ):
            raise ValidationException("面积统计报告清单任务时间快照不一致")
        history_snapshot = manifest.get("history_snapshot")
        if not isinstance(history_snapshot, dict):
            raise ValidationException("面积统计报告清单缺少历史快照")
        if history_snapshot.get("count") != report.history_snapshot_count:
            raise ValidationException("面积统计报告清单历史快照数量不一致")
        history_latest_at = cls._parse_manifest_datetime(
            history_snapshot.get("latest_updated_at")
        )
        if not cls._same_datetime(
            history_latest_at,
            report.history_latest_updated_at,
        ):
            raise ValidationException("面积统计报告清单历史快照时间不一致")
        statistics_snapshot = manifest.get("statistics_snapshot")
        if (
            not isinstance(statistics_snapshot, dict)
            or statistics_snapshot.get("total_plot_count")
            != report.task_plot_count
        ):
            raise ValidationException("面积统计报告清单统计快照不一致")

    @staticmethod
    def _parse_manifest_datetime(value: object) -> datetime | None:
        """解析 manifest ISO 时间并拒绝非法类型。

        Args:
            value: JSON 时间值。

        Returns:
            datetime | None: 解析后的时间或空值。
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValidationException("面积统计报告清单时间字段类型不合法")
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationException("面积统计报告清单时间字段格式不合法") from exc

    def read_verified_members(self, report: StatisticsReport) -> dict[str, bytes]:
        """读取通过完整性复核的 XLSX、PDF 和清单实体。

        Args:
            report: 统计报告模型。

        Returns:
            dict[str, bytes]: 以 ZIP 内文件名索引的实体内容。
        """
        path = self.verify_report_bundle(report)
        with ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}

    async def require_current_report(
        self,
        db: AsyncSession,
        report: StatisticsReport,
        task: object,
        current_plot_count: int,
    ) -> None:
        """校验报告仍对应当前任务和历史快照。

        Args:
            db: 异步数据库会话。
            report: 待归档统计报告。
            task: 当前作业任务。
            current_plot_count: 当前任务有效图斑数量。

        Returns:
            None: 报告当前有效时无返回值。
        """
        history_state = await self.dao.get_history_state(db, task.project_id)
        stale_reason = self.get_stale_reason(
            report,
            task,
            current_plot_count,
            history_state,
        )
        if stale_reason is not None:
            raise ValidationException(f"面积统计正式报告已失效：{stale_reason}")

    def _to_response(
        self,
        report: StatisticsReport,
        task: object,
        current_plot_count: int,
        history_state: tuple[int, datetime | None],
        *,
        entity_valid: bool,
    ) -> StatisticsReportResponse:
        """转换报告响应并计算当前状态。

        Args:
            report: 报告模型。
            task: 当前作业任务。
            current_plot_count: 当前有效图斑数量。
            history_state: 历史快照状态。
            entity_valid: 实体校验是否通过。

        Returns:
            StatisticsReportResponse: 前端报告摘要。
        """
        stale_reason = self.get_stale_reason(
            report,
            task,
            current_plot_count,
            history_state,
        )
        effective_status = report.status if entity_valid else "invalid"
        if effective_status == "completed" and stale_reason is not None:
            effective_status = "superseded"
        is_current = effective_status == "completed" and stale_reason is None
        return StatisticsReportResponse(
            report_code=report.report_code,
            report_title=report.report_title,
            version=report.version,
            status=effective_status,
            bundle_size_bytes=report.bundle_size_bytes,
            bundle_checksum_sha256=report.bundle_checksum_sha256,
            xlsx_size_bytes=report.xlsx_size_bytes,
            xlsx_checksum_sha256=report.xlsx_checksum_sha256,
            pdf_size_bytes=report.pdf_size_bytes,
            pdf_checksum_sha256=report.pdf_checksum_sha256,
            task_plot_count=report.task_plot_count,
            task_updated_at_snapshot=report.task_updated_at_snapshot,
            history_snapshot_count=report.history_snapshot_count,
            history_latest_updated_at=report.history_latest_updated_at,
            report_manifest=self._build_public_manifest(report.report_manifest),
            generation_comment=report.generation_comment,
            generated_by=report.generated_by,
            generated_by_code=report.generated_by_code,
            generated_by_role=report.generated_by_role,
            generated_at=report.generated_at,
            download_url=(
                f"/api/v1/statistics/reports/{report.report_code}/download"
                if entity_valid
                else None
            ),
            is_current=is_current,
            stale_reason=(
                stale_reason
                if entity_valid
                else "报告实体文件缺失或完整性校验失败"
            ),
        )

    @staticmethod
    def _build_public_manifest(manifest: dict) -> dict:
        """压缩旧版本超大统计快照，保留前端需要的校验证据。

        Args:
            manifest: 数据库保存的完整报告清单。

        Returns:
            dict: 不携带逐村明细的报告摘要清单。
        """
        public_manifest = dict(manifest)
        statistics_snapshot = public_manifest.get("statistics_snapshot")
        if not isinstance(statistics_snapshot, dict):
            return public_manifest
        if "canonical_payload_sha256" in statistics_snapshot:
            return public_manifest
        public_manifest["statistics_snapshot"] = {
            "generated_at": statistics_snapshot.get("generated_at"),
            "total_plot_count": statistics_snapshot.get("total_plot_count"),
            "total_area_ha": statistics_snapshot.get("total_area_ha"),
            "total_area_mu": statistics_snapshot.get("total_area_mu"),
            "farmland_area_ha": statistics_snapshot.get("farmland_area_ha"),
            "crop_assignment_rate": statistics_snapshot.get(
                "crop_assignment_rate"
            ),
            "legacy_full_snapshot_stored": True,
        }
        return public_manifest

    async def list_reports(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> StatisticsReportListResponse:
        """查询任务统计报告历史并计算当前来源状态。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            StatisticsReportListResponse: 报告历史列表。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        totals = await self.statistics_dao.get_totals(db, task.id)
        current_plot_count = int(totals[0])
        history_state = await self.dao.get_history_state(db, task.project_id)
        reports = await self.dao.list_reports(db, task.id)
        return StatisticsReportListResponse(
            task_code=task_code,
            items=[
                self._to_response(
                    report,
                    task,
                    current_plot_count,
                    history_state,
                    entity_valid=report.status != "invalid",
                )
                for report in reports
            ],
        )

    async def generate_report(
        self,
        db: AsyncSession,
        task_code: str,
        request: StatisticsReportGenerateRequest,
    ) -> StatisticsReportResponse:
        """生成包含 XLSX、PDF 和 manifest 的正式报告 ZIP。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 操作人、报告标题和生成依据。

        Returns:
            StatisticsReportResponse: 新生成报告摘要。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "generate_statistics_report",
        )
        summary = await self.statistics_service.get_area_statistics(db, task_code)
        if summary.total_plot_count <= 0:
            raise ValidationException("当前任务没有有效图斑，不能生成统计报告")
        history_state = await self.dao.get_history_state(db, task.project_id)
        version = await self.dao.get_next_version(db, task.id)
        generated_at = datetime.now(UTC)
        report_code = (
            f"STRPT-{task_code}-V{version:03d}-"
            f"{generated_at:%Y%m%dT%H%M%S}-{secrets.token_hex(4)}"
        )
        xlsx_content, pdf_content = await asyncio.gather(
            asyncio.to_thread(
                self.renderer.build_xlsx,
                task,
                summary,
                request.report_title,
                generated_at,
                operator,
                request.comment,
            ),
            asyncio.to_thread(
                self.renderer.build_pdf,
                task,
                summary,
                request.report_title,
                generated_at,
                operator,
                request.comment,
            ),
        )
        manifest = self.renderer.build_manifest(
            task,
            summary,
            report_code,
            request.report_title,
            version,
            generated_at,
            operator,
            request.comment,
            xlsx_content,
            pdf_content,
            history_state[0],
            history_state[1],
        )
        bundle_content = self.renderer.build_bundle(
            report_code,
            xlsx_content,
            pdf_content,
            manifest,
        )
        relative_path = f"{task_code}/{report_code}.zip"
        final_path = self._resolve_path(relative_path)
        temporary_path = self._resolve_path(
            f"{task_code}/.{report_code}.{secrets.token_hex(6)}.tmp"
        )
        final_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(temporary_path.write_bytes, bundle_content)
            await asyncio.to_thread(os.replace, temporary_path, final_path)
        except OSError as exc:
            await asyncio.to_thread(temporary_path.unlink, missing_ok=True)
            raise ValidationException("面积统计报告包原子发布失败") from exc
        report = StatisticsReport(
            task_id=task.id,
            report_code=report_code,
            report_title=request.report_title,
            version=version,
            status="completed",
            bundle_uri=f"storage://statistics-reports/{relative_path}",
            bundle_size_bytes=final_path.stat().st_size,
            bundle_checksum_sha256=calculate_sha256(final_path),
            xlsx_size_bytes=len(xlsx_content),
            xlsx_checksum_sha256=calculate_sha256_bytes(xlsx_content),
            pdf_size_bytes=len(pdf_content),
            pdf_checksum_sha256=calculate_sha256_bytes(pdf_content),
            task_plot_count=summary.total_plot_count,
            task_updated_at_snapshot=task.updated_at,
            history_snapshot_count=history_state[0],
            history_latest_updated_at=history_state[1],
            report_manifest=manifest,
            generation_comment=request.comment,
            generated_by=operator.display_name,
            generated_by_code=operator.user_code,
            generated_by_role=operator.role_code,
            generated_at=generated_at,
        )
        try:
            superseded_count = await self.dao.supersede_completed_reports(
                db,
                task.id,
            )
            report = await self.dao.add_report(db, report)
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="statistics",
                    action="statistics_report_generated",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"生成面积统计报告 {report_code} V{version}；"
                        f"图斑 {summary.total_plot_count} 块，"
                        f"历史快照 {history_state[0]} 个；"
                        f"替代历史报告 {superseded_count} 份；"
                        f"ZIP SHA256 {report.bundle_checksum_sha256}；"
                        f"{request.comment}"
                    ),
                ),
            )
            await db.commit()
        except SQLAlchemyError:
            await db.rollback()
            await asyncio.to_thread(final_path.unlink, missing_ok=True)
            raise
        return self._to_response(
            report,
            task,
            summary.total_plot_count,
            history_state,
            entity_valid=True,
        )

    async def authorize_download(
        self,
        db: AsyncSession,
        report_code: str,
        requester_code: str,
    ) -> StatisticsReportDownload:
        """鉴权、复核并审计统计报告包下载。

        Args:
            db: 异步数据库会话。
            report_code: 报告业务编号。
            requester_code: 下载人稳定用户编码。

        Returns:
            StatisticsReportDownload: 已验证下载信息。
        """
        report = await self.dao.get_report_by_code(db, report_code)
        if report is None:
            raise NotFoundException(f"未找到面积统计报告 {report_code}")
        task = await self.workbench_dao.get_task_by_id(db, report.task_id)
        if task is None:
            raise NotFoundException("面积统计报告关联任务不存在")
        requester = await self.project_user_service.require_capability(
            db,
            task.project_id,
            requester_code,
            "download_statistics_report",
        )
        try:
            path = await asyncio.to_thread(self.verify_report_bundle, report)
        except (NotFoundException, ValidationException):
            report.status = "invalid"
            await db.commit()
            raise
        totals = await self.statistics_dao.get_totals(db, task.id)
        history_state = await self.dao.get_history_state(db, task.project_id)
        stale_reason = self.get_stale_reason(
            report,
            task,
            int(totals[0]),
            history_state,
        )
        if report.status == "completed" and stale_reason is not None:
            report.status = "superseded"
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="statistics",
                action="statistics_report_downloaded",
                reviewer=requester.display_name,
                reviewer_code=requester.user_code,
                reviewer_role=requester.role_code,
                comment=(
                    f"下载面积统计报告 {report.report_code} V{report.version}；"
                    f"状态 {report.status}；"
                    f"ZIP SHA256 {report.bundle_checksum_sha256}"
                ),
            ),
        )
        await db.commit()
        return StatisticsReportDownload(
            path=path,
            filename=f"{report.report_code}.zip",
            checksum_sha256=report.bundle_checksum_sha256,
        )


def calculate_sha256_bytes(content: bytes) -> str:
    """计算内存实体 SHA-256。

    Args:
        content: 文件字节。

    Returns:
        str: 64 位十六进制校验值。
    """
    return sha256(content).hexdigest()
