"""外业核查照片、语音和调查表实体证据服务。"""

import asyncio
import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.field_verification_artifact_dao import (
    FieldVerificationArtifactDAO,
)
from app.dao.field_verification_dao import FieldVerificationDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.workbench import (
    FieldVerificationArtifact,
    FieldVerificationArtifactEvent,
    ReviewRecord,
)
from app.schemas.field_verification import FieldVerificationArtifactResponse
from app.services.project_user_service import ProjectUserService

ARTIFACT_SUFFIXES: dict[str, set[str]] = {
    "photo": {".jpg", ".jpeg", ".png", ".webp"},
    "voice": {".wav", ".mp3", ".m4a", ".ogg"},
    "form": {".pdf", ".xlsx"},
}


@dataclass(frozen=True)
class PreparedFieldArtifact:
    """已写入临时文件并通过格式、大小与校验值检查的证据。"""

    temporary_path: Path
    original_filename: str
    suffix: str
    media_type: str
    file_size_bytes: int
    checksum_sha256: str


@dataclass(frozen=True)
class FieldArtifactDownload:
    """通过下载前复核的外业证据文件。"""

    path: Path
    filename: str
    media_type: str
    checksum_sha256: str


@dataclass(frozen=True)
class VerifiedTaskFieldArtifact:
    """成果归档使用的已复核任务外业证据。"""

    artifact: FieldVerificationArtifact
    verification_code: str
    path: Path


@dataclass(frozen=True)
class StoredFieldImportWorkbook:
    """已在受控目录原子发布的外业批量导入工作簿。"""

    path: Path
    file_uri: str
    file_size_bytes: int
    checksum_sha256: str
    created_new: bool


@dataclass(frozen=True)
class VerifiedFieldImportWorkbook:
    """成果归档使用的已复核外业导入源工作簿。"""

    path: Path
    file_uri: str
    file_size_bytes: int
    checksum_sha256: str
    source_name: str | None
    source_version: str | None
    import_batch_code: str | None


class FieldVerificationArtifactService:
    """负责受控保存、权限审计、下载复核和交付读取。"""

    def __init__(
        self,
        dao: FieldVerificationArtifactDAO | None = None,
        field_dao: FieldVerificationDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        user_service: ProjectUserService | None = None,
        storage_root: Path | None = None,
    ) -> None:
        """初始化外业实体证据服务。

        Args:
            dao: 外业证据 DAO。
            field_dao: 外业核查记录 DAO。
            workbench_dao: 任务和审核记录 DAO。
            user_service: 项目用户权限服务。
            storage_root: 可注入受控存储根目录。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or FieldVerificationArtifactDAO()
        self.field_dao = field_dao or FieldVerificationDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.user_service = user_service or ProjectUserService()
        self.storage_root = storage_root or (
            Path(__file__).resolve().parents[2] / "storage" / "field-evidence"
        )

    @staticmethod
    def to_response(
        artifact: FieldVerificationArtifact,
        verification_code: str,
    ) -> FieldVerificationArtifactResponse:
        """把实体证据模型转换为 API 摘要。

        Args:
            artifact: 外业实体证据模型。
            verification_code: 所属外业记录编号。

        Returns:
            FieldVerificationArtifactResponse: 带受控下载地址的摘要。
        """
        return FieldVerificationArtifactResponse(
            artifact_code=artifact.artifact_code,
            artifact_type=artifact.artifact_type,
            original_filename=artifact.original_filename,
            media_type=artifact.media_type,
            file_size_bytes=artifact.file_size_bytes,
            checksum_sha256=artifact.checksum_sha256,
            description=artifact.description,
            uploaded_by=artifact.uploaded_by,
            uploaded_by_code=artifact.uploaded_by_code,
            uploaded_by_role=artifact.uploaded_by_role,
            created_at=artifact.created_at,
            download_url=(
                f"/api/v1/field-verifications/{verification_code}/artifacts/"
                f"{artifact.artifact_code}/download"
            ),
        )

    @staticmethod
    def _max_bytes(artifact_type: str) -> int:
        """读取服务端配置的证据类型大小上限。

        Args:
            artifact_type: photo、voice 或 form。

        Returns:
            int: 最大允许字节数。
        """
        return {
            "photo": settings.max_field_photo_bytes,
            "voice": settings.max_field_voice_bytes,
            "form": settings.max_field_form_bytes,
        }[artifact_type]

    @staticmethod
    def _inspect_xlsx(path: Path, max_bytes: int) -> None:
        """校验 XLSX ZIP 结构、内部路径、加密标记和解压规模。

        Args:
            path: 待检查 XLSX 临时文件。
            max_bytes: 该类证据上传字节上限。

        Returns:
            None: 校验通过无返回值。
        """
        try:
            with ZipFile(path) as archive:
                names: set[str] = set()
                expanded_size = 0
                for item in archive.infolist():
                    normalized = item.filename.replace("\\", "/")
                    pure_path = PurePosixPath(normalized)
                    if (
                        normalized.startswith("/")
                        or ".." in pure_path.parts
                        or not normalized
                    ):
                        raise ValidationException("调查表 XLSX 包含不安全内部路径")
                    if item.flag_bits & 0x1:
                        raise ValidationException("调查表 XLSX 不得加密")
                    expanded_size += item.file_size
                    if expanded_size > max_bytes * 5:
                        raise ValidationException("调查表 XLSX 解压后体积超过限制")
                    names.add(normalized)
                required = {"[Content_Types].xml", "xl/workbook.xml"}
                if not required.issubset(names):
                    raise ValidationException("调查表不是有效的 XLSX 工作簿")
                if archive.testzip() is not None:
                    raise ValidationException("调查表 XLSX 压缩内容已损坏")
        except BadZipFile as exc:
            raise ValidationException("调查表不是有效的 XLSX 文件") from exc

    @classmethod
    def _inspect_signature(
        cls,
        path: Path,
        artifact_type: str,
        suffix: str,
        reported_media_type: str | None,
        max_bytes: int,
    ) -> str:
        """按扩展名、文件签名和 MIME 声明复核实体类型。

        Args:
            path: 临时实体文件。
            artifact_type: 业务证据类型。
            suffix: 规范化扩展名。
            reported_media_type: 浏览器报告的 MIME。
            max_bytes: 该类型服务端大小上限。

        Returns:
            str: 服务端确认的规范 MIME。
        """
        with path.open("rb") as file_handle:
            prefix = file_handle.read(32)
        checks: dict[str, tuple[str, bool, set[str]]] = {
            ".jpg": (
                "image/jpeg",
                prefix.startswith(b"\xff\xd8\xff"),
                {"image/jpeg", "image/pjpeg"},
            ),
            ".jpeg": (
                "image/jpeg",
                prefix.startswith(b"\xff\xd8\xff"),
                {"image/jpeg", "image/pjpeg"},
            ),
            ".png": (
                "image/png",
                prefix.startswith(b"\x89PNG\r\n\x1a\n"),
                {"image/png"},
            ),
            ".webp": (
                "image/webp",
                prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP",
                {"image/webp"},
            ),
            ".wav": (
                "audio/wav",
                prefix.startswith(b"RIFF") and prefix[8:12] == b"WAVE",
                {"audio/wav", "audio/x-wav", "audio/wave"},
            ),
            ".mp3": (
                "audio/mpeg",
                prefix.startswith(b"ID3")
                or (
                    len(prefix) >= 2
                    and prefix[0] == 0xFF
                    and prefix[1] & 0xE0 == 0xE0
                ),
                {"audio/mpeg", "audio/mp3"},
            ),
            ".m4a": (
                "audio/mp4",
                len(prefix) >= 12 and prefix[4:8] == b"ftyp",
                {"audio/mp4", "audio/x-m4a", "video/mp4"},
            ),
            ".ogg": (
                "audio/ogg",
                prefix.startswith(b"OggS"),
                {"audio/ogg", "application/ogg"},
            ),
            ".pdf": (
                "application/pdf",
                prefix.startswith(b"%PDF-"),
                {"application/pdf"},
            ),
            ".xlsx": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                prefix.startswith(b"PK\x03\x04"),
                {
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "application/zip",
                },
            ),
        }
        media_type, signature_valid, allowed_reported = checks[suffix]
        if not signature_valid:
            raise ValidationException("上传文件扩展名与实体签名不一致")
        normalized_reported = (reported_media_type or "").split(";", 1)[0].strip()
        if normalized_reported and normalized_reported not in {
            "application/octet-stream",
            *allowed_reported,
        }:
            raise ValidationException("浏览器报告的 MIME 与实体格式不一致")
        if artifact_type == "form" and suffix == ".xlsx":
            cls._inspect_xlsx(path, max_bytes)
        return media_type

    def _prepare_upload(
        self,
        file_handle: BinaryIO,
        original_filename: str,
        artifact_type: str,
        reported_media_type: str | None,
    ) -> PreparedFieldArtifact:
        """流式保存临时文件并计算服务端大小和 SHA-256。

        Args:
            file_handle: 上传二进制流。
            original_filename: 原始文件名。
            artifact_type: photo、voice 或 form。
            reported_media_type: 浏览器报告 MIME。

        Returns:
            PreparedFieldArtifact: 已通过实体检查的临时文件。
        """
        safe_name = Path(original_filename).name.strip()
        if not safe_name or safe_name in {".", ".."}:
            raise ValidationException("上传文件名不合法")
        suffix = Path(safe_name).suffix.lower()
        allowed_suffixes = ARTIFACT_SUFFIXES.get(artifact_type)
        if allowed_suffixes is None or suffix not in allowed_suffixes:
            allowed = "、".join(sorted(allowed_suffixes or set()))
            raise ValidationException(f"{artifact_type} 证据仅允许 {allowed}")
        max_bytes = self._max_bytes(artifact_type)
        storage_root = self.storage_root.resolve()
        upload_dir = (storage_root / ".uploads").resolve()
        upload_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = upload_dir / f"{uuid4().hex}{suffix}.part"
        digest = hashlib.sha256()
        file_size = 0
        file_handle.seek(0)
        try:
            with temporary_path.open("wb") as output:
                while chunk := file_handle.read(1024 * 1024):
                    file_size += len(chunk)
                    if file_size > max_bytes:
                        raise ValidationException("外业证据文件超过服务端大小限制")
                    digest.update(chunk)
                    output.write(chunk)
            if file_size == 0:
                raise ValidationException("外业证据文件为空")
            media_type = self._inspect_signature(
                temporary_path,
                artifact_type,
                suffix,
                reported_media_type,
                max_bytes,
            )
            return PreparedFieldArtifact(
                temporary_path=temporary_path,
                original_filename=safe_name,
                suffix=suffix,
                media_type=media_type,
                file_size_bytes=file_size,
                checksum_sha256=digest.hexdigest(),
            )
        except (OSError, ValidationException):
            temporary_path.unlink(missing_ok=True)
            raise

    def verify_artifact_file(self, artifact: FieldVerificationArtifact) -> Path:
        """下载或归档前重新校验受控路径、签名、大小和 SHA-256。

        Args:
            artifact: 外业实体证据模型。

        Returns:
            Path: 已通过复核的实体路径。
        """
        prefix = "storage://field-evidence/"
        if not artifact.file_uri.startswith(prefix):
            raise ValidationException("外业证据不在受控存储中")
        storage_root = self.storage_root.resolve()
        path = (storage_root / artifact.file_uri.removeprefix(prefix)).resolve()
        if not path.is_relative_to(storage_root) or not path.is_file():
            raise NotFoundException("外业证据实体文件不存在")
        if path.stat().st_size != artifact.file_size_bytes:
            raise ValidationException("外业证据实体大小校验失败")
        suffix = Path(artifact.original_filename).suffix.lower()
        media_type = self._inspect_signature(
            path,
            artifact.artifact_type,
            suffix,
            artifact.media_type,
            self._max_bytes(artifact.artifact_type),
        )
        if media_type != artifact.media_type:
            raise ValidationException("外业证据媒体类型校验失败")
        if calculate_sha256(path) != artifact.checksum_sha256:
            raise ValidationException("外业证据 SHA-256 校验失败")
        return path

    def store_import_workbook(
        self,
        original_filename: str,
        content: bytes,
    ) -> StoredFieldImportWorkbook:
        """校验并原子保存批量导入原始 XLSX 工作簿。

        Args:
            original_filename: 原始工作簿文件名。
            content: 原始 XLSX 字节。

        Returns:
            StoredFieldImportWorkbook: 受控路径、大小和 SHA-256。
        """
        prepared = self._prepare_upload(
            BytesIO(content),
            original_filename,
            "form",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if prepared.suffix != ".xlsx":
            prepared.temporary_path.unlink(missing_ok=True)
            raise ValidationException("外业批量导入源文件必须为 XLSX")
        relative_path = Path("imports") / f"{prepared.checksum_sha256}.xlsx"
        storage_root = self.storage_root.resolve()
        final_path = (storage_root / relative_path).resolve()
        if not final_path.is_relative_to(storage_root):
            prepared.temporary_path.unlink(missing_ok=True)
            raise ValidationException("外业导入工作簿存储路径不合法")
        created_new = not final_path.exists()
        try:
            if created_new:
                final_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(prepared.temporary_path, final_path)
            elif (
                final_path.stat().st_size != prepared.file_size_bytes
                or calculate_sha256(final_path) != prepared.checksum_sha256
            ):
                raise ValidationException("同校验值外业工作簿实体不一致")
            return StoredFieldImportWorkbook(
                path=final_path,
                file_uri=(
                    "storage://field-evidence/" + relative_path.as_posix()
                ),
                file_size_bytes=prepared.file_size_bytes,
                checksum_sha256=prepared.checksum_sha256,
                created_new=created_new,
            )
        finally:
            prepared.temporary_path.unlink(missing_ok=True)

    def verify_import_workbook(
        self,
        file_uri: str,
        file_size_bytes: int,
        checksum_sha256: str,
    ) -> Path:
        """复核受控外业批量导入 XLSX 源文件。

        Args:
            file_uri: 受控存储 URI。
            file_size_bytes: 入库时服务端文件大小。
            checksum_sha256: 入库时服务端校验值。

        Returns:
            Path: 已通过路径、结构、大小和 SHA-256 复核的工作簿。
        """
        prefix = "storage://field-evidence/"
        if not file_uri.startswith(prefix):
            raise ValidationException("外业导入工作簿不在受控存储中")
        storage_root = self.storage_root.resolve()
        path = (storage_root / file_uri.removeprefix(prefix)).resolve()
        if not path.is_relative_to(storage_root) or not path.is_file():
            raise NotFoundException("外业导入工作簿实体不存在")
        if path.suffix.lower() != ".xlsx":
            raise ValidationException("外业导入工作簿扩展名不合法")
        if path.stat().st_size != file_size_bytes:
            raise ValidationException("外业导入工作簿大小校验失败")
        self._inspect_signature(
            path,
            "form",
            ".xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            settings.max_field_form_bytes,
        )
        if calculate_sha256(path) != checksum_sha256:
            raise ValidationException("外业导入工作簿 SHA-256 校验失败")
        return path

    async def load_verified_import_workbooks(
        self,
        field_rows: Sequence[tuple[object, str]],
    ) -> list[VerifiedFieldImportWorkbook]:
        """去重并复核任务外业记录关联的原始 XLSX 工作簿。

        Args:
            field_rows: 外业记录及其点位 GeoJSON。

        Returns:
            list[VerifiedFieldImportWorkbook]: 可嵌入成果包的源工作簿。
        """
        verified: list[VerifiedFieldImportWorkbook] = []
        seen_uris: set[str] = set()
        for record, _geometry in field_rows:
            file_uri = getattr(record, "source_file_uri", None)
            file_size = getattr(record, "source_file_size_bytes", None)
            checksum = getattr(record, "source_checksum_sha256", None)
            if not file_uri and file_size is None:
                continue
            if not file_uri or file_size is None or not checksum:
                raise ValidationException("外业导入工作簿证据字段不完整")
            if file_uri in seen_uris:
                continue
            path = await asyncio.to_thread(
                self.verify_import_workbook,
                file_uri,
                int(file_size),
                checksum,
            )
            seen_uris.add(file_uri)
            verified.append(
                VerifiedFieldImportWorkbook(
                    path=path,
                    file_uri=file_uri,
                    file_size_bytes=int(file_size),
                    checksum_sha256=checksum,
                    source_name=getattr(record, "source_name", None),
                    source_version=getattr(record, "source_version", None),
                    import_batch_code=getattr(record, "import_batch_code", None),
                )
            )
        return verified

    async def upload_artifact(
        self,
        db: AsyncSession,
        verification_code: str,
        artifact_type: str,
        uploader_code: str,
        comment: str,
        original_filename: str,
        reported_media_type: str | None,
        file_handle: BinaryIO,
    ) -> FieldVerificationArtifactResponse:
        """上传并原子登记一份外业实体证据。

        Args:
            db: 异步数据库会话。
            verification_code: 外业记录业务编号。
            artifact_type: 证据类型。
            uploader_code: 上传人稳定项目用户编码。
            comment: 证据来源与用途说明。
            original_filename: 原始文件名。
            reported_media_type: 浏览器报告 MIME。
            file_handle: 上传二进制流。

        Returns:
            FieldVerificationArtifactResponse: 已登记实体证据摘要。
        """
        record = await self.field_dao.get_by_code_for_update(db, verification_code)
        if record is None:
            raise NotFoundException(f"未找到外业记录 {verification_code}")
        task = await self.workbench_dao.get_task_by_id(db, record.task_id)
        if task is None:
            raise NotFoundException("外业记录关联任务不存在")
        if task.status in {"client_review", "completed"}:
            raise ValidationException("甲方复核或已完成任务不得补传外业证据")
        uploader = await self.user_service.require_capability(
            db,
            task.project_id,
            uploader_code,
            "upload_field_data",
        )
        prepared = await asyncio.to_thread(
            self._prepare_upload,
            file_handle,
            original_filename,
            artifact_type,
            reported_media_type,
        )
        final_path: Path | None = None
        published_new = False
        try:
            duplicate = await self.dao.find_duplicate_for_update(
                db,
                record.id,
                prepared.checksum_sha256,
            )
            if duplicate is not None:
                return self.to_response(duplicate, verification_code)
            now = datetime.now(UTC)
            artifact_code = (
                f"FIELD-EV-{now:%Y%m%dT%H%M%S}-{uuid4().hex[:10]}"
            )
            relative_path = Path(verification_code) / (
                f"{artifact_code}{prepared.suffix}"
            )
            storage_root = self.storage_root.resolve()
            final_path = (storage_root / relative_path).resolve()
            if not final_path.is_relative_to(storage_root):
                raise ValidationException("外业证据存储路径不合法")
            final_path.parent.mkdir(parents=True, exist_ok=True)
            if final_path.exists():
                raise ValidationException("外业证据目标文件已存在")
            os.replace(prepared.temporary_path, final_path)
            published_new = True
            artifact = await self.dao.add_artifact(
                db,
                FieldVerificationArtifact(
                    field_verification_id=record.id,
                    artifact_code=artifact_code,
                    artifact_type=artifact_type,
                    original_filename=prepared.original_filename,
                    media_type=prepared.media_type,
                    file_uri=(
                        "storage://field-evidence/" + relative_path.as_posix()
                    ),
                    file_size_bytes=prepared.file_size_bytes,
                    checksum_sha256=prepared.checksum_sha256,
                    description=comment,
                    uploaded_by=uploader.display_name,
                    uploaded_by_code=uploader.user_code,
                    uploaded_by_role=uploader.role_code,
                    created_at=now,
                ),
            )
            await self.dao.add_event(
                db,
                FieldVerificationArtifactEvent(
                    field_verification_id=record.id,
                    artifact_id=artifact.id,
                    event_type="uploaded",
                    detail={
                        "artifact_code": artifact_code,
                        "artifact_type": artifact_type,
                        "original_filename": prepared.original_filename,
                        "file_size_bytes": prepared.file_size_bytes,
                        "checksum_sha256": prepared.checksum_sha256,
                        "comment": comment,
                    },
                    actor=uploader.display_name,
                    actor_code=uploader.user_code,
                    actor_role=uploader.role_code,
                ),
            )
            task.updated_at = now
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="field_verification",
                    action="field_evidence_uploaded",
                    reviewer=uploader.display_name,
                    reviewer_code=uploader.user_code,
                    reviewer_role=uploader.role_code,
                    comment=(
                        f"{verification_code} 上传 {artifact_type} 实体证据 "
                        f"{artifact_code}，SHA256 {prepared.checksum_sha256}；"
                        f"{comment}"
                    ),
                ),
            )
            await db.commit()
            return self.to_response(artifact, verification_code)
        except ValidationException:
            await db.rollback()
            if published_new and final_path is not None:
                final_path.unlink(missing_ok=True)
            raise
        except SQLAlchemyError as exc:
            await db.rollback()
            if published_new and final_path is not None:
                final_path.unlink(missing_ok=True)
            raise ValidationException("外业证据登记失败，请重试") from exc
        finally:
            prepared.temporary_path.unlink(missing_ok=True)

    async def get_artifact_for_download(
        self,
        db: AsyncSession,
        verification_code: str,
        artifact_code: str,
        operator_code: str,
    ) -> FieldArtifactDownload:
        """授权、复核并记录外业实体证据下载事件。

        Args:
            db: 异步数据库会话。
            verification_code: 外业记录业务编号。
            artifact_code: 实体证据业务编号。
            operator_code: 当前项目用户稳定编码。

        Returns:
            FieldArtifactDownload: 可供 FileResponse 使用的下载信息。
        """
        row = await self.dao.get_artifact_record(
            db,
            verification_code,
            artifact_code,
        )
        if row is None:
            raise NotFoundException("未找到外业实体证据")
        artifact, record = row
        task = await self.workbench_dao.get_task_by_id(db, record.task_id)
        if task is None:
            raise NotFoundException("外业记录关联任务不存在")
        user = await self.user_service.require_capability(
            db,
            task.project_id,
            operator_code,
            "view_field_evidence",
        )
        path = await asyncio.to_thread(self.verify_artifact_file, artifact)
        try:
            await self.dao.add_event(
                db,
                FieldVerificationArtifactEvent(
                    field_verification_id=record.id,
                    artifact_id=artifact.id,
                    event_type="downloaded",
                    detail={
                        "artifact_code": artifact.artifact_code,
                        "checksum_sha256": artifact.checksum_sha256,
                    },
                    actor=user.display_name,
                    actor_code=user.user_code,
                    actor_role=user.role_code,
                ),
            )
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            raise ValidationException("外业证据下载审计写入失败") from exc
        return FieldArtifactDownload(
            path=path,
            filename=artifact.original_filename,
            media_type=artifact.media_type,
            checksum_sha256=artifact.checksum_sha256,
        )

    async def count_task_records_missing_photo(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> int:
        """统计任务中缺少现场照片实体的外业记录。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            int: 缺少实体照片的外业记录数。
        """
        return await self.dao.count_task_records_missing_photo(db, task_id)

    async def load_verified_task_artifacts(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> list[VerifiedTaskFieldArtifact]:
        """为成果归档加载并逐一复核任务外业证据。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            list[VerifiedTaskFieldArtifact]: 已通过复核的证据列表。
        """
        rows = await self.dao.list_task_artifacts(db, task_id)
        verified: list[VerifiedTaskFieldArtifact] = []
        for row in rows:
            artifact = row[0]
            path = await asyncio.to_thread(self.verify_artifact_file, artifact)
            verified.append(
                VerifiedTaskFieldArtifact(
                    artifact=artifact,
                    verification_code=str(row.verification_code),
                    path=path,
                )
            )
        return verified

    async def list_task_events(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> list[dict]:
        """生成可归档的外业证据事件清单。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            list[dict]: 上传和下载事件审计数据。
        """
        rows = await self.dao.list_task_events(db, task_id)
        return [
            {
                "verification_code": row.verification_code,
                "artifact_code": row.artifact_code,
                "event_type": row[0].event_type,
                "detail": row[0].detail,
                "actor": row[0].actor,
                "actor_code": row[0].actor_code,
                "actor_role": row[0].actor_role,
                "created_at": row[0].created_at,
            }
            for row in rows
        ]
