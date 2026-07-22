"""成果验收正式报告生成、校验、版本和下载服务。"""

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
from app.dao.acceptance_report_dao import AcceptanceReportDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.acceptance_report import AcceptanceReport
from app.models.workbench import DeliveryPackage, ReviewRecord
from app.schemas.acceptance_report import (
    AcceptanceReportFileEvidence,
    AcceptanceReportGenerateRequest,
    AcceptanceReportListResponse,
    AcceptanceReportResponse,
)
from app.services.acceptance_report_renderer import AcceptanceReportRenderer
from app.services.delivery_service import DeliveryService
from app.services.project_user_service import ProjectUserService


@dataclass(frozen=True)
class AcceptanceReportDownload:
    """通过权限与实体复核的验收报告下载信息。"""

    path: Path
    filename: str
    checksum_sha256: str


class AcceptanceReportService:
    """管理绑定当前成果包的 DOCX/PDF 验收报告。"""

    def __init__(
        self,
        dao: AcceptanceReportDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        delivery_service: DeliveryService | None = None,
        project_user_service: ProjectUserService | None = None,
        renderer: AcceptanceReportRenderer | None = None,
        storage_root: Path | None = None,
    ) -> None:
        """初始化成果验收报告服务。

        Args:
            dao: 验收报告 DAO。
            workbench_dao: 工作台公共 DAO。
            delivery_service: 当前成果包判定与实体校验服务。
            project_user_service: 项目用户能力服务。
            renderer: DOCX/PDF 渲染器。
            storage_root: 可注入受控存储根目录。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or AcceptanceReportDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.delivery_service = delivery_service or DeliveryService()
        self.project_user_service = project_user_service or ProjectUserService()
        self.renderer = renderer or AcceptanceReportRenderer()
        self.storage_root = storage_root or (
            Path(__file__).resolve().parents[2] / "storage" / "acceptance-reports"
        )

    def _resolve_path(self, relative_path: str) -> Path:
        """解析并约束验收报告受控路径。

        Args:
            relative_path: 相对受控根目录的路径。

        Returns:
            Path: 未越界绝对路径。
        """
        root = self.storage_root.resolve()
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root):
            raise ValidationException("成果验收报告存储路径越界")
        return path

    @staticmethod
    def _same_datetime(left: datetime, right: datetime) -> bool:
        """比较数据库驱动可能返回的不同时区时间。

        Args:
            left: 左侧时间。
            right: 右侧时间。

        Returns:
            bool: 两者表示同一时刻时为真。
        """
        left_value = left if left.tzinfo else left.replace(tzinfo=UTC)
        right_value = right if right.tzinfo else right.replace(tzinfo=UTC)
        return left_value.astimezone(UTC) == right_value.astimezone(UTC)

    @staticmethod
    def quality_summary_checksum(summary: dict) -> str:
        """计算成果包质量摘要规范化校验值。

        Args:
            summary: 成果包质量摘要。

        Returns:
            str: 64 位 SHA-256。
        """
        canonical = json.dumps(
            summary,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return sha256(canonical).hexdigest()

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        """解析 manifest 中的 ISO 时间。

        Args:
            value: JSON 时间值。

        Returns:
            datetime: 可比较的时间对象。
        """
        if not isinstance(value, str):
            raise ValidationException("成果验收 manifest 时间字段类型不合法")
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationException("成果验收 manifest 时间格式不合法") from exc

    @classmethod
    def get_stale_reason(
        cls,
        report: AcceptanceReport,
        task: object,
        current_package: DeliveryPackage | None,
    ) -> str | None:
        """判断验收报告是否仍绑定当前任务与成果包。

        Args:
            report: 验收报告模型。
            task: 当前作业任务。
            current_package: 当前有效成果交付包。

        Returns:
            str | None: 失效原因；当前有效时为空。
        """
        if report.status == "invalid":
            return "报告实体已损坏或缺失"
        if report.status == "superseded":
            return "报告已被新版本替代"
        if report.status != "completed":
            return "报告未处于已完成状态"
        if int(report.task_plot_count) != int(task.total_plots):
            return "任务图斑数量在报告生成后发生变化"
        if not cls._same_datetime(report.task_updated_at_snapshot, task.updated_at):
            return "任务数据在报告生成后发生更新"
        if current_package is None:
            return "当前任务没有有效成果交付包"
        if report.delivery_package_id != current_package.id:
            return "当前成果交付包已更换"
        if report.delivery_package_code != current_package.package_code:
            return "成果包编号快照不一致"
        if (
            not current_package.checksum_sha256
            or report.delivery_package_checksum_sha256
            != current_package.checksum_sha256
        ):
            return "成果包 SHA-256 在报告生成后发生变化"
        if (
            current_package.file_size_bytes is None
            or report.delivery_package_size_bytes != current_package.file_size_bytes
        ):
            return "成果包文件大小在报告生成后发生变化"
        if current_package.completed_at is None or not cls._same_datetime(
            report.delivery_package_completed_at_snapshot,
            current_package.completed_at,
        ):
            return "成果包完成时间快照不一致"
        if report.delivery_manifest_count != len(current_package.manifest):
            return "成果包文件清单数量在报告生成后发生变化"
        if report.quality_summary_checksum_sha256 != cls.quality_summary_checksum(
            current_package.quality_summary
        ):
            return "成果包质量摘要在报告生成后发生变化"
        return None

    def _package_path(self, report: AcceptanceReport) -> Path:
        """从受控 URI 解析报告 ZIP 路径。

        Args:
            report: 验收报告模型。

        Returns:
            Path: 受控 ZIP 路径。
        """
        prefix = "storage://acceptance-reports/"
        if not report.bundle_uri.startswith(prefix):
            raise ValidationException("成果验收报告未登记受控文件地址")
        return self._resolve_path(report.bundle_uri.removeprefix(prefix))

    def verify_report_bundle(self, report: AcceptanceReport) -> Path:
        """复核 ZIP、DOCX、PDF、manifest 和数据库快照。

        Args:
            report: 待复核验收报告。

        Returns:
            Path: 已通过复核的 ZIP 路径。
        """
        path = self._package_path(report)
        if not path.is_file():
            raise NotFoundException("成果验收报告实体不存在")
        if path.stat().st_size != report.bundle_size_bytes:
            raise ValidationException("成果验收报告 ZIP 大小校验失败")
        if path.read_bytes()[:4] != b"PK\x03\x04":
            raise ValidationException("成果验收报告不是有效 ZIP")
        if calculate_sha256(path) != report.bundle_checksum_sha256:
            raise ValidationException("成果验收报告 ZIP SHA-256 校验失败")
        try:
            with ZipFile(path) as archive:
                names = archive.namelist()
                expected_names = {
                    report.docx_filename,
                    report.pdf_filename,
                    "manifest.json",
                }
                if (
                    set(names) != expected_names
                    or len(names) != len(set(names))
                    or any(
                        name.startswith("/") or ".." in Path(name).parts
                        for name in names
                    )
                ):
                    raise ValidationException("成果验收报告 ZIP 成员不完整或不安全")
                docx_content = archive.read(report.docx_filename)
                pdf_content = archive.read(report.pdf_filename)
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except (BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationException("成果验收报告 ZIP 或 manifest 损坏") from exc
        if manifest != report.report_manifest:
            raise ValidationException("成果验收 manifest 与数据库快照不一致")
        if (
            manifest.get("schema_version") != "acceptance-report-v1"
            or manifest.get("report_code") != report.report_code
            or manifest.get("report_title") != report.report_title
            or manifest.get("version") != report.version
        ):
            raise ValidationException("成果验收 manifest 报告身份不一致")
        task_snapshot = manifest.get("task")
        package_snapshot = manifest.get("delivery_package")
        generator_snapshot = manifest.get("generator")
        if (
            not isinstance(task_snapshot, dict)
            or task_snapshot.get("task_plot_count") != report.task_plot_count
            or not self._same_datetime(
                self._parse_datetime(
                    task_snapshot.get("task_updated_at_snapshot")
                ),
                report.task_updated_at_snapshot,
            )
            or not isinstance(package_snapshot, dict)
            or package_snapshot.get("package_code") != report.delivery_package_code
            or package_snapshot.get("file_size_bytes")
            != report.delivery_package_size_bytes
            or package_snapshot.get("checksum_sha256")
            != report.delivery_package_checksum_sha256
            or package_snapshot.get("manifest_count") != report.delivery_manifest_count
            or package_snapshot.get("quality_summary_checksum_sha256")
            != report.quality_summary_checksum_sha256
            or not self._same_datetime(
                self._parse_datetime(
                    package_snapshot.get("completed_at_snapshot")
                ),
                report.delivery_package_completed_at_snapshot,
            )
        ):
            raise ValidationException("成果验收 manifest 来源快照不一致")
        if (
            not isinstance(generator_snapshot, dict)
            or generator_snapshot.get("display_name") != report.generated_by
            or generator_snapshot.get("user_code") != report.generated_by_code
            or generator_snapshot.get("role_code") != report.generated_by_role
            or generator_snapshot.get("generation_comment")
            != report.generation_comment
            or not self._same_datetime(
                self._parse_datetime(generator_snapshot.get("generated_at")),
                report.generated_at,
            )
        ):
            raise ValidationException("成果验收 manifest 生成人审计不一致")
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) != 2:
            raise ValidationException("成果验收 manifest 文件清单不完整")
        file_map = {
            item.get("path"): item
            for item in files
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        if set(file_map) != {report.docx_filename, report.pdf_filename}:
            raise ValidationException("成果验收 manifest 文件名不一致")
        evidence = (
            (
                report.docx_filename,
                docx_content,
                report.docx_size_bytes,
                report.docx_checksum_sha256,
            ),
            (
                report.pdf_filename,
                pdf_content,
                report.pdf_size_bytes,
                report.pdf_checksum_sha256,
            ),
        )
        for filename, content, size, checksum in evidence:
            item = file_map[filename]
            if (
                len(content) != size
                or sha256(content).hexdigest() != checksum
                or item.get("file_size_bytes") != size
                or item.get("checksum_sha256") != checksum
            ):
                raise ValidationException(f"成果验收报告文件证据不一致：{filename}")
        self.renderer.validate_docx(docx_content, report.report_code)
        pdf_page_count = self.renderer.validate_pdf(
            pdf_content,
            report.report_code,
        )
        if file_map[report.pdf_filename].get("page_count") != pdf_page_count:
            raise ValidationException("成果验收 PDF 页数与 manifest 不一致")
        return path

    def _quick_entity_valid(self, report: AcceptanceReport) -> bool:
        """对列表执行不解压历史 ZIP 的轻量实体检查。

        Args:
            report: 验收报告模型。

        Returns:
            bool: 路径存在且大小匹配时为真。
        """
        try:
            path = self._package_path(report)
        except ValidationException:
            return False
        return path.is_file() and path.stat().st_size == report.bundle_size_bytes

    def _to_response(
        self,
        report: AcceptanceReport,
        task: object,
        current_package: DeliveryPackage | None,
        *,
        entity_valid: bool,
    ) -> AcceptanceReportResponse:
        """将报告模型转换为前端摘要。

        Args:
            report: 验收报告模型。
            task: 当前作业任务。
            current_package: 当前有效成果包。
            entity_valid: 轻量实体检查结果。

        Returns:
            AcceptanceReportResponse: 报告版本摘要。
        """
        stale_reason = self.get_stale_reason(report, task, current_package)
        effective_status = report.status if entity_valid else "invalid"
        if effective_status == "completed" and stale_reason is not None:
            effective_status = "superseded"
        is_current = effective_status == "completed" and stale_reason is None
        files = report.report_manifest.get("files", [])
        return AcceptanceReportResponse(
            report_code=report.report_code,
            report_title=report.report_title,
            version=report.version,
            status=effective_status,
            delivery_package_code=report.delivery_package_code,
            delivery_package_checksum_sha256=(report.delivery_package_checksum_sha256),
            task_plot_count=report.task_plot_count,
            task_updated_at_snapshot=report.task_updated_at_snapshot,
            delivery_manifest_count=report.delivery_manifest_count,
            bundle_size_bytes=report.bundle_size_bytes,
            bundle_checksum_sha256=report.bundle_checksum_sha256,
            files=[AcceptanceReportFileEvidence(**item) for item in files],
            generation_comment=report.generation_comment,
            generated_by=report.generated_by,
            generated_by_code=report.generated_by_code,
            generated_by_role=report.generated_by_role,
            generated_at=report.generated_at,
            download_url=(
                f"/api/v1/acceptance-reports/{report.report_code}/download"
                if entity_valid
                else None
            ),
            is_current=is_current,
            stale_reason=(
                stale_reason if entity_valid else "报告实体文件缺失或大小校验失败"
            ),
        )

    async def list_reports(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> AcceptanceReportListResponse:
        """查询验收报告版本和当前生成条件。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            AcceptanceReportListResponse: 门禁与报告列表。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        current_package = await self.delivery_service.get_current_package(db, task)
        reports = await self.dao.get_reports(db, task.id)
        if task.status != "completed":
            blocker = "任务需完成三级审核后才能生成验收报告"
        elif current_package is None:
            blocker = "请先生成与当前任务一致的成果交付包"
        else:
            blocker = None
        return AcceptanceReportListResponse(
            task_code=task_code,
            can_generate=blocker is None,
            generate_blocker=blocker,
            current_delivery_package_code=(
                current_package.package_code if current_package else None
            ),
            items=[
                self._to_response(
                    report,
                    task,
                    current_package,
                    entity_valid=self._quick_entity_valid(report),
                )
                for report in reports
            ],
        )

    @staticmethod
    def _serialize_reviews(reviews: list[object]) -> list[dict]:
        """将审核记录转换为可渲染冻结快照。

        Args:
            reviews: ORM 审核记录。

        Returns:
            list[dict]: 报告使用的审核摘要。
        """
        return [
            {
                "review_level": item.review_level,
                "action": item.action,
                "reviewer": item.reviewer,
                "reviewer_code": item.reviewer_code,
                "reviewer_role": item.reviewer_role,
                "comment": item.comment,
                "created_at": item.created_at.isoformat(),
            }
            for item in reviews
        ]

    async def generate_report(
        self,
        db: AsyncSession,
        task_code: str,
        request: AcceptanceReportGenerateRequest,
    ) -> AcceptanceReportResponse:
        """从当前有效成果包生成 DOCX/PDF 验收报告包。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 报告标题、操作人和生成依据。

        Returns:
            AcceptanceReportResponse: 新报告摘要。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "completed":
            raise ValidationException("任务需完成三级审核后才能生成验收报告")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "generate_acceptance_report",
        )
        current_package = await self.delivery_service.get_current_package(db, task)
        if current_package is None:
            raise ValidationException("请先生成与当前任务一致的成果交付包")
        verified_package = await self.delivery_service.get_package_for_download(
            db,
            current_package.package_code,
            operator.user_code,
        )
        if verified_package.id != current_package.id:
            raise ValidationException("成果交付包在验收报告生成前发生变化")
        if (
            verified_package.completed_at is None
            or verified_package.file_size_bytes is None
            or not verified_package.checksum_sha256
        ):
            raise ValidationException("成果交付包缺少完整实体证据")
        reviews = list(await self.workbench_dao.get_reviews(db, task.id))
        version = await self.dao.get_next_version(db, task.id)
        generated_at = datetime.now(UTC)
        report_code = (
            f"ACCRPT-{task_code}-V{version:03d}-"
            f"{generated_at:%Y%m%dT%H%M%S}-{secrets.token_hex(4)}"
        )
        docx_filename = f"{report_code}.docx"
        pdf_filename = f"{report_code}.pdf"
        quality_checksum = self.quality_summary_checksum(
            verified_package.quality_summary
        )
        data = {
            "report_code": report_code,
            "report_title": request.report_title,
            "version": version,
            "task_code": task.task_code,
            "task_name": task.task_name,
            "task_plot_count": int(task.total_plots),
            "task_updated_at_snapshot": task.updated_at.isoformat(),
            "delivery_package_code": verified_package.package_code,
            "delivery_package_completed_at_snapshot": (
                verified_package.completed_at.isoformat()
            ),
            "delivery_package_size_bytes": verified_package.file_size_bytes,
            "delivery_package_checksum_sha256": (verified_package.checksum_sha256),
            "delivery_manifest": verified_package.manifest,
            "quality_summary": verified_package.quality_summary,
            "quality_summary_checksum_sha256": quality_checksum,
            "reviews": self._serialize_reviews(reviews),
            "generated_by": operator.display_name,
            "generated_by_code": operator.user_code,
            "generated_by_role": operator.role_code,
            "generated_at": generated_at.isoformat(),
            "generation_comment": request.comment,
            "docx_filename": docx_filename,
            "pdf_filename": pdf_filename,
        }
        docx_content, pdf_result = await asyncio.gather(
            asyncio.to_thread(self.renderer.build_docx, data),
            asyncio.to_thread(self.renderer.build_pdf, data),
        )
        pdf_content, pdf_page_count = pdf_result
        self.renderer.validate_docx(docx_content, report_code)
        validated_page_count = self.renderer.validate_pdf(
            pdf_content,
            report_code,
        )
        if validated_page_count != pdf_page_count:
            raise ValidationException("成果验收 PDF 生成页数复核失败")
        manifest = self.renderer.build_manifest(
            data,
            docx_content,
            pdf_content,
            pdf_page_count,
        )
        bundle_content = self.renderer.build_bundle(
            docx_filename,
            docx_content,
            pdf_filename,
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
            raise ValidationException("成果验收报告包原子发布失败") from exc
        report = AcceptanceReport(
            task_id=task.id,
            delivery_package_id=verified_package.id,
            report_code=report_code,
            report_title=request.report_title,
            version=version,
            status="completed",
            bundle_uri=f"storage://acceptance-reports/{relative_path}",
            bundle_size_bytes=final_path.stat().st_size,
            bundle_checksum_sha256=calculate_sha256(final_path),
            docx_filename=docx_filename,
            docx_size_bytes=len(docx_content),
            docx_checksum_sha256=sha256(docx_content).hexdigest(),
            pdf_filename=pdf_filename,
            pdf_size_bytes=len(pdf_content),
            pdf_checksum_sha256=sha256(pdf_content).hexdigest(),
            task_plot_count=int(task.total_plots),
            task_updated_at_snapshot=task.updated_at,
            delivery_package_code=verified_package.package_code,
            delivery_package_completed_at_snapshot=verified_package.completed_at,
            delivery_package_size_bytes=verified_package.file_size_bytes,
            delivery_package_checksum_sha256=verified_package.checksum_sha256,
            delivery_manifest_count=len(verified_package.manifest),
            quality_summary_checksum_sha256=quality_checksum,
            report_manifest=manifest,
            generation_comment=request.comment,
            generated_by=operator.display_name,
            generated_by_code=operator.user_code,
            generated_by_role=operator.role_code,
            generated_at=generated_at,
        )
        try:
            await asyncio.to_thread(self.verify_report_bundle, report)
            superseded_count = await self.dao.supersede_completed_reports(
                db,
                task.id,
            )
            report = await self.dao.add_report(db, report)
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="delivery",
                    action="acceptance_report_generated",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"生成成果验收报告 {report_code} V{version}；"
                        f"绑定成果包 {verified_package.package_code}；"
                        f"图斑 {task.total_plots} 块；"
                        f"PDF {pdf_page_count} 页；"
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
            verified_package,
            entity_valid=True,
        )

    async def authorize_download(
        self,
        db: AsyncSession,
        report_code: str,
        requester_code: str,
    ) -> AcceptanceReportDownload:
        """鉴权、复核并审计验收报告包下载。

        Args:
            db: 异步数据库会话。
            report_code: 验收报告编号。
            requester_code: 下载人稳定用户编码。

        Returns:
            AcceptanceReportDownload: 已验证下载信息。
        """
        report = await self.dao.get_report_by_code(db, report_code)
        if report is None:
            raise NotFoundException(f"未找到成果验收报告 {report_code}")
        task = await self.workbench_dao.get_task_by_id(db, report.task_id)
        if task is None:
            raise NotFoundException("成果验收报告关联任务不存在")
        requester = await self.project_user_service.require_capability(
            db,
            task.project_id,
            requester_code,
            "download_acceptance_report",
        )
        try:
            path = await asyncio.to_thread(self.verify_report_bundle, report)
        except (NotFoundException, ValidationException):
            report.status = "invalid"
            await db.commit()
            raise
        current_package = await self.delivery_service.get_current_package(db, task)
        stale_reason = self.get_stale_reason(report, task, current_package)
        if report.status == "completed" and stale_reason is not None:
            report.status = "superseded"
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="delivery",
                action="acceptance_report_downloaded",
                reviewer=requester.display_name,
                reviewer_code=requester.user_code,
                reviewer_role=requester.role_code,
                comment=(
                    f"下载成果验收报告 {report.report_code} V{report.version}；"
                    f"状态 {report.status}；"
                    f"ZIP SHA256 {report.bundle_checksum_sha256}"
                ),
            ),
        )
        await db.commit()
        return AcceptanceReportDownload(
            path=path,
            filename=f"{report.report_code}.zip",
            checksum_sha256=report.bundle_checksum_sha256,
        )
