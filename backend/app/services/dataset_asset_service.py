"""多源数据资产实体上传、核验、下载和交付复核服务。"""

import asyncio
import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dataset_files import DatasetFileInspection, inspect_dataset_file
from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.production_dao import ProductionDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.dataset_asset_verification import DatasetAssetVerification
from app.models.workbench import (
    DatasetAsset,
    DatasetLineage,
    ProductionAuditEvent,
)
from app.schemas.production import (
    DatasetAssetResponse,
    DatasetAssetUploadRequest,
    DatasetAssetVerificationResponse,
    DatasetAssetVerifyRequest,
)
from app.services.project_user_service import ProjectUserService


@dataclass(frozen=True)
class PreparedDatasetUpload:
    """已临时落盘并完成服务端格式检查的数据资产。"""

    temporary_path: Path
    original_filename: str
    file_size_bytes: int
    checksum_sha256: str
    inspection: DatasetFileInspection


@dataclass(frozen=True)
class DatasetAssetDownload:
    """供路由构造 FileResponse 的已复核下载信息。"""

    path: Path
    filename: str
    media_type: str
    checksum_sha256: str


@dataclass(frozen=True)
class VerifiedDatasetAssetFile:
    """交付归档可引用的已复核数据资产实体。"""

    asset_code: str
    path: Path
    file_uri: str
    original_filename: str
    file_size_bytes: int
    checksum_sha256: str
    media_type: str
    verified_at: datetime
    verified_by: str
    verified_by_code: str
    verified_by_role: str
    verification_comment: str


class DatasetAssetService:
    """管理多源数据目录中可重复验证的物理实体。"""

    STORAGE_PREFIX = "storage://datasets/"

    def __init__(
        self,
        dao: ProductionDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        user_service: ProjectUserService | None = None,
        storage_root: Path | None = None,
    ) -> None:
        """初始化数据资产实体服务。

        Args:
            dao: 生产模块数据访问对象。
            workbench_dao: 项目和任务查询对象。
            user_service: 稳定项目用户能力服务。
            storage_root: 测试或部署注入的受控目录。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ProductionDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.user_service = user_service or ProjectUserService()
        self.storage_root = storage_root or (
            Path(__file__).resolve().parents[2] / "storage" / "datasets"
        )

    async def _resolve_context(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
    ) -> tuple[object, object]:
        """解析当前项目和任务并验证归属关系。

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
    def to_response(row: object, parent_codes: list[str]) -> DatasetAssetResponse:
        """把资产和空间范围查询行转换为 API 响应。

        Args:
            row: 包含 DatasetAsset 与四个包围盒坐标的映射行。
            parent_codes: 父资产编号列表。

        Returns:
            DatasetAssetResponse: 多源数据目录项。
        """
        asset = row[DatasetAsset]
        bbox_values = (
            row["min_lon"],
            row["min_lat"],
            row["max_lon"],
            row["max_lat"],
        )
        bbox = (
            tuple(float(value) for value in bbox_values)
            if all(value is not None for value in bbox_values)
            else None
        )
        return DatasetAssetResponse(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset_type=asset.asset_type,
            source_name=asset.source_name,
            source_uri=asset.source_uri,
            source_version=asset.source_version,
            checksum_sha256=asset.checksum_sha256,
            crs=asset.crs,
            extent_bbox=bbox,
            time_start=asset.time_start,
            time_end=asset.time_end,
            security_classification=asset.security_classification,
            data_status=asset.data_status,
            verification_status=asset.verification_status,
            physical_file_uri=asset.physical_file_uri,
            physical_original_filename=asset.physical_original_filename,
            physical_file_size_bytes=asset.physical_file_size_bytes,
            physical_checksum_sha256=asset.physical_checksum_sha256,
            physical_media_type=asset.physical_media_type,
            verified_at=asset.verified_at,
            verified_by=asset.verified_by,
            verified_by_code=asset.verified_by_code,
            verified_by_role=asset.verified_by_role,
            verification_comment=asset.verification_comment,
            parent_asset_codes=parent_codes,
            metadata=asset.metadata_payload or {},
            registered_by=asset.registered_by,
            registered_by_code=asset.registered_by_code,
            registered_by_role=asset.registered_by_role,
            created_at=asset.created_at,
        )

    async def get_asset_response(
        self,
        db: AsyncSession,
        project_id: int,
        asset_code: str,
    ) -> DatasetAssetResponse:
        """重新读取一个资产的空间范围和父级血缘。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            asset_code: 资产编号。

        Returns:
            DatasetAssetResponse: 数据资产目录响应。
        """
        row = await self.dao.get_asset_row_by_code(db, project_id, asset_code)
        if row is None:
            raise NotFoundException(f"未找到数据资产 {asset_code}")
        asset = row[DatasetAsset]
        parent_codes = await self.dao.list_parent_asset_codes(db, asset.id)
        return self.to_response(row, parent_codes)

    def prepare_upload(
        self,
        file_handle: BinaryIO,
        original_filename: str,
        asset_type: str,
        reported_media_type: str | None,
    ) -> PreparedDatasetUpload:
        """流式临时落盘、计算 SHA-256 并检查文件结构。

        Args:
            file_handle: FastAPI 上传文件二进制流。
            original_filename: 浏览器提交的原始文件名。
            asset_type: 数据目录资产类型。
            reported_media_type: 浏览器报告 MIME。

        Returns:
            PreparedDatasetUpload: 已完成服务端检查的临时实体。
        """
        safe_name = Path(original_filename).name.strip()
        if not safe_name or safe_name in {".", ".."}:
            raise ValidationException("数据资产原始文件名不合法")
        upload_dir = (self.storage_root.resolve() / ".uploads").resolve()
        upload_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = upload_dir / f"{uuid4().hex}.part"
        digest = hashlib.sha256()
        file_size = 0
        try:
            file_handle.seek(0)
            with temporary_path.open("xb") as output:
                while chunk := file_handle.read(1024 * 1024):
                    file_size += len(chunk)
                    if file_size > settings.max_dataset_asset_upload_bytes:
                        raise ValidationException(
                            "数据资产实体超过平台允许的最大上传大小"
                        )
                    digest.update(chunk)
                    output.write(chunk)
            if file_size <= 0:
                raise ValidationException("数据资产实体不能为空文件")
            inspection = inspect_dataset_file(
                temporary_path,
                asset_type,
                safe_name,
                reported_media_type,
                settings.max_dataset_archive_expanded_bytes,
            )
            return PreparedDatasetUpload(
                temporary_path=temporary_path,
                original_filename=safe_name,
                file_size_bytes=file_size,
                checksum_sha256=digest.hexdigest(),
                inspection=inspection,
            )
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    def publish_upload(
        self,
        prepared: PreparedDatasetUpload,
        asset_code: str,
        verification_code: str,
    ) -> tuple[Path, str]:
        """通过排他硬链接原子发布实体，禁止覆盖并发目标。

        Args:
            prepared: 已检查临时文件。
            asset_code: 数据资产编号。
            verification_code: 本次核验编号。

        Returns:
            tuple[Path, str]: 绝对路径和受控 URI。
        """
        relative_path = (
            Path(asset_code)
            / f"{verification_code}{prepared.inspection.suffix}"
        )
        storage_root = self.storage_root.resolve()
        final_path = (storage_root / relative_path).resolve()
        if not final_path.is_relative_to(storage_root):
            raise ValidationException("数据资产实体存储路径不合法")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(prepared.temporary_path, final_path)
        except FileExistsError as exc:
            raise ValidationException("数据资产实体目标文件已存在，请重试") from exc
        except OSError as exc:
            raise ValidationException("数据资产实体原子发布失败") from exc
        try:
            prepared.temporary_path.unlink(missing_ok=True)
        except OSError as exc:
            try:
                final_path.unlink(missing_ok=True)
            except OSError as cleanup_exc:
                raise ValidationException(
                    "数据资产实体发布后临时文件与目标文件清理失败"
                ) from cleanup_exc
            raise ValidationException(
                "数据资产实体发布后临时文件清理失败，目标文件已撤销"
            ) from exc
        return final_path, self.STORAGE_PREFIX + relative_path.as_posix()

    def resolve_verified_file(self, asset: DatasetAsset) -> Path:
        """重新检查已核验资产的路径、格式、大小和 SHA-256。

        Args:
            asset: 标记为已核验的数据资产。

        Returns:
            Path: 通过全部复核的受控实体路径。
        """
        required_values = (
            asset.physical_file_uri,
            asset.physical_original_filename,
            asset.physical_file_size_bytes,
            asset.physical_checksum_sha256,
            asset.physical_media_type,
            asset.verified_at,
            asset.verified_by,
            asset.verified_by_code,
            asset.verified_by_role,
            asset.verification_comment,
        )
        if asset.verification_status != "verified" or any(
            value is None for value in required_values
        ):
            raise ValidationException(
                f"数据资产 {asset.asset_code} 缺少完整实体核验证据"
            )
        if asset.physical_checksum_sha256 != asset.checksum_sha256:
            raise ValidationException(
                f"数据资产 {asset.asset_code} 目录校验值与实体校验值不一致"
            )
        file_uri = str(asset.physical_file_uri)
        if not file_uri.startswith(self.STORAGE_PREFIX):
            raise ValidationException(
                f"数据资产 {asset.asset_code} 不在受控存储中"
            )
        storage_root = self.storage_root.resolve()
        path = (storage_root / file_uri.removeprefix(self.STORAGE_PREFIX)).resolve()
        if not path.is_relative_to(storage_root) or not path.is_file():
            raise NotFoundException(f"数据资产 {asset.asset_code} 实体不存在")
        if path.stat().st_size != int(asset.physical_file_size_bytes):
            raise ValidationException(
                f"数据资产 {asset.asset_code} 实体大小校验失败"
            )
        inspection = inspect_dataset_file(
            path,
            asset.asset_type,
            str(asset.physical_original_filename),
            str(asset.physical_media_type),
            settings.max_dataset_archive_expanded_bytes,
        )
        if inspection.media_type != asset.physical_media_type:
            raise ValidationException(
                f"数据资产 {asset.asset_code} 媒体类型校验失败"
            )
        if calculate_sha256(path) != asset.physical_checksum_sha256:
            raise ValidationException(
                f"数据资产 {asset.asset_code} SHA-256 校验失败"
            )
        return path

    async def register_uploaded_asset(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: DatasetAssetUploadRequest,
        original_filename: str,
        reported_media_type: str | None,
        file_handle: BinaryIO,
    ) -> DatasetAssetResponse:
        """上传实体、登记资产、血缘、核验和生产审计。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            request: 来源、范围、密级和核验依据。
            original_filename: 原始文件名。
            reported_media_type: 浏览器报告 MIME。
            file_handle: 上传二进制流。

        Returns:
            DatasetAssetResponse: 已通过实体核验的数据资产。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_datasets",
        )
        if await self.dao.get_asset_by_code(db, project.id, request.asset_code):
            raise ValidationException(f"资产编号 {request.asset_code} 已存在")
        parent_assets = await self.dao.get_assets_by_codes(
            db,
            project.id,
            request.parent_asset_codes,
        )
        if len(parent_assets) != len(request.parent_asset_codes):
            found = {asset.asset_code for asset in parent_assets}
            missing = [code for code in request.parent_asset_codes if code not in found]
            raise ValidationException(f"父资产不存在：{', '.join(missing)}")
        prepared = await asyncio.to_thread(
            self.prepare_upload,
            file_handle,
            original_filename,
            request.asset_type,
            reported_media_type,
        )
        final_path: Path | None = None
        published = False
        try:
            duplicate = await self.dao.get_asset_by_checksum(
                db,
                project.id,
                prepared.checksum_sha256,
            )
            if duplicate is not None:
                raise ValidationException(
                    f"相同内容已登记为资产 {duplicate.asset_code}，"
                    "请建立血缘而非重复入库"
                )
            now = datetime.now(UTC)
            verification_code = (
                f"DSVERIFY-{now:%Y%m%dT%H%M%S}-{uuid4().hex[:10]}"
            )
            final_path, file_uri = await asyncio.to_thread(
                self.publish_upload,
                prepared,
                request.asset_code,
                verification_code,
            )
            published = True
            extent = (
                func.ST_MakeEnvelope(*request.extent_bbox, 4326)
                if request.extent_bbox
                else None
            )
            metadata = dict(request.metadata)
            metadata["entity_inspection"] = prepared.inspection.metadata
            asset = await self.dao.add_asset(
                db,
                DatasetAsset(
                    project_id=project.id,
                    task_id=task.id,
                    asset_code=request.asset_code,
                    asset_name=request.asset_name,
                    asset_type=request.asset_type,
                    source_name=request.source_name,
                    source_uri=request.source_uri,
                    source_version=request.source_version,
                    checksum_sha256=prepared.checksum_sha256,
                    crs=request.crs,
                    extent=extent,
                    time_start=request.time_start,
                    time_end=request.time_end,
                    security_classification=request.security_classification,
                    data_status=request.data_status,
                    verification_status="verified",
                    physical_file_uri=file_uri,
                    physical_original_filename=prepared.original_filename,
                    physical_file_size_bytes=prepared.file_size_bytes,
                    physical_checksum_sha256=prepared.checksum_sha256,
                    physical_media_type=prepared.inspection.media_type,
                    verified_at=now,
                    verified_by=operator.display_name,
                    verified_by_code=operator.user_code,
                    verified_by_role=operator.role_code,
                    verification_comment=request.verification_comment,
                    metadata_payload=metadata,
                    registered_by=operator.display_name,
                    registered_by_code=operator.user_code,
                    registered_by_role=operator.role_code,
                    created_at=now,
                    updated_at=now,
                ),
            )
            await self.dao.add_lineages(
                db,
                [
                    DatasetLineage(
                        parent_asset_id=parent.id,
                        derived_asset_id=asset.id,
                        relation_type=request.lineage_relation_type,
                        process_code=request.process_code,
                    )
                    for parent in parent_assets
                ],
            )
            await self.dao.add_dataset_asset_verification(
                db,
                DatasetAssetVerification(
                    asset_id=asset.id,
                    verification_code=verification_code,
                    verification_status="verified",
                    original_filename=prepared.original_filename,
                    file_uri=file_uri,
                    file_size_bytes=prepared.file_size_bytes,
                    expected_checksum_sha256=prepared.checksum_sha256,
                    computed_checksum_sha256=prepared.checksum_sha256,
                    media_type=prepared.inspection.media_type,
                    inspection_metadata=prepared.inspection.metadata,
                    verification_error=None,
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                    verification_comment=request.verification_comment,
                    created_at=now,
                ),
            )
            await self.dao.add_audit_event(
                db,
                ProductionAuditEvent(
                    project_id=project.id,
                    task_id=task.id,
                    entity_type="dataset_asset",
                    entity_code=asset.asset_code,
                    action="uploaded_and_verified",
                    previous_values={},
                    new_values={
                        "asset_type": asset.asset_type,
                        "source_name": asset.source_name,
                        "source_version": asset.source_version,
                        "checksum_sha256": asset.checksum_sha256,
                        "verification_status": "verified",
                        "physical_file_uri": file_uri,
                        "physical_file_size_bytes": prepared.file_size_bytes,
                        "physical_media_type": prepared.inspection.media_type,
                        "verification_code": verification_code,
                        "parent_asset_codes": request.parent_asset_codes,
                        "verification_comment": request.verification_comment,
                    },
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                    created_at=now,
                ),
            )
            await db.commit()
        except SQLAlchemyError as exc:
            try:
                await db.rollback()
            finally:
                if published and final_path is not None:
                    final_path.unlink(missing_ok=True)
            raise ValidationException("数据资产实体登记失败，请重试") from exc
        except BaseException:
            try:
                await db.rollback()
            finally:
                if published and final_path is not None:
                    final_path.unlink(missing_ok=True)
            raise
        finally:
            prepared.temporary_path.unlink(missing_ok=True)
        return await self.get_asset_response(db, project.id, request.asset_code)

    async def verify_existing_asset(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        asset_code: str,
        request: DatasetAssetVerifyRequest,
        original_filename: str,
        reported_media_type: str | None,
        file_handle: BinaryIO,
    ) -> DatasetAssetVerificationResponse:
        """为既有待核验资产补传实体并保存通过或拒绝证据。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            asset_code: 待核验资产编号。
            request: 操作人和人工核验依据。
            original_filename: 原始文件名。
            reported_media_type: 浏览器报告 MIME。
            file_handle: 上传二进制流。

        Returns:
            DatasetAssetVerificationResponse: 本次核验结果和资产当前态。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_datasets",
        )
        existing = await self.dao.get_asset_by_code(db, project.id, asset_code)
        if existing is None:
            raise NotFoundException(f"未找到数据资产 {asset_code}")
        if existing.task_id is not None and existing.task_id != task.id:
            raise NotFoundException(f"当前任务内未找到数据资产 {asset_code}")
        if existing.verification_status == "verified":
            raise ValidationException("数据资产实体已经核验，无需重复补传")
        prepared = await asyncio.to_thread(
            self.prepare_upload,
            file_handle,
            original_filename,
            existing.asset_type,
            reported_media_type,
        )
        final_path: Path | None = None
        published = False
        verification: DatasetAssetVerification | None = None
        try:
            asset = await self.dao.get_asset_by_code_for_update(
                db,
                project.id,
                asset_code,
            )
            if asset is None or (
                asset.task_id is not None and asset.task_id != task.id
            ):
                raise NotFoundException(f"当前任务内未找到数据资产 {asset_code}")
            if asset.verification_status == "verified":
                raise ValidationException("数据资产实体已经核验，无需重复补传")
            now = datetime.now(UTC)
            verification_code = (
                f"DSVERIFY-{now:%Y%m%dT%H%M%S}-{uuid4().hex[:10]}"
            )
            previous_verification_status = asset.verification_status
            checksum_match = prepared.checksum_sha256 == asset.checksum_sha256
            verification_status = "verified" if checksum_match else "rejected"
            verification_error = (
                None
                if checksum_match
                else "服务端计算 SHA-256 与资产登记校验值不一致"
            )
            file_uri = None
            if checksum_match:
                final_path, file_uri = await asyncio.to_thread(
                    self.publish_upload,
                    prepared,
                    asset.asset_code,
                    verification_code,
                )
                published = True
                asset.verification_status = "verified"
                asset.physical_file_uri = file_uri
                asset.physical_original_filename = prepared.original_filename
                asset.physical_file_size_bytes = prepared.file_size_bytes
                asset.physical_checksum_sha256 = prepared.checksum_sha256
                asset.physical_media_type = prepared.inspection.media_type
                asset.verified_at = now
                asset.verified_by = operator.display_name
                asset.verified_by_code = operator.user_code
                asset.verified_by_role = operator.role_code
                asset.verification_comment = request.verification_comment
                metadata = dict(asset.metadata_payload or {})
                metadata["entity_inspection"] = prepared.inspection.metadata
                asset.metadata_payload = metadata
            else:
                asset.verification_status = "rejected"
            asset.updated_at = now
            verification = await self.dao.add_dataset_asset_verification(
                db,
                DatasetAssetVerification(
                    asset_id=asset.id,
                    verification_code=verification_code,
                    verification_status=verification_status,
                    original_filename=prepared.original_filename,
                    file_uri=file_uri,
                    file_size_bytes=prepared.file_size_bytes,
                    expected_checksum_sha256=asset.checksum_sha256,
                    computed_checksum_sha256=prepared.checksum_sha256,
                    media_type=prepared.inspection.media_type,
                    inspection_metadata=prepared.inspection.metadata,
                    verification_error=verification_error,
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                    verification_comment=request.verification_comment,
                    created_at=now,
                ),
            )
            await self.dao.add_audit_event(
                db,
                ProductionAuditEvent(
                    project_id=project.id,
                    task_id=task.id,
                    entity_type="dataset_asset",
                    entity_code=asset.asset_code,
                    action=(
                        "physical_verification_passed"
                        if checksum_match
                        else "physical_verification_rejected"
                    ),
                    previous_values={
                        "verification_status": previous_verification_status,
                    },
                    new_values={
                        "verification_status": verification_status,
                        "verification_code": verification_code,
                        "expected_checksum_sha256": asset.checksum_sha256,
                        "computed_checksum_sha256": prepared.checksum_sha256,
                        "physical_file_uri": file_uri,
                        "physical_file_size_bytes": prepared.file_size_bytes,
                        "verification_comment": request.verification_comment,
                        "verification_error": verification_error,
                    },
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                    created_at=now,
                ),
            )
            await db.commit()
        except SQLAlchemyError as exc:
            try:
                await db.rollback()
            finally:
                if published and final_path is not None:
                    final_path.unlink(missing_ok=True)
            raise ValidationException("数据资产实体核验登记失败，请重试") from exc
        except BaseException:
            try:
                await db.rollback()
            finally:
                if published and final_path is not None:
                    final_path.unlink(missing_ok=True)
            raise
        finally:
            prepared.temporary_path.unlink(missing_ok=True)
        if verification is None:
            raise ValidationException("数据资产实体核验未生成结果")
        asset_response = await self.get_asset_response(db, project.id, asset_code)
        return DatasetAssetVerificationResponse(
            verification_code=verification.verification_code,
            verification_status=verification.verification_status,
            checksum_match=(verification.verification_status == "verified"),
            expected_checksum_sha256=verification.expected_checksum_sha256,
            computed_checksum_sha256=verification.computed_checksum_sha256,
            file_size_bytes=verification.file_size_bytes,
            media_type=verification.media_type,
            verification_error=verification.verification_error,
            created_at=verification.created_at,
            asset=asset_response,
        )

    async def get_download(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        asset_code: str,
        operator_code: str,
    ) -> DatasetAssetDownload:
        """授权并在重新复核实体后返回下载信息。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            asset_code: 数据资产编号。
            operator_code: 当前项目用户稳定编码。

        Returns:
            DatasetAssetDownload: 已复核下载文件信息。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            operator_code,
            "manage_datasets",
        )
        asset = await self.dao.get_asset_by_code(db, project.id, asset_code)
        if asset is None or (
            asset.task_id is not None and asset.task_id != task.id
        ):
            raise NotFoundException(f"当前任务内未找到数据资产 {asset_code}")
        path = await asyncio.to_thread(self.resolve_verified_file, asset)
        try:
            await self.dao.add_audit_event(
                db,
                ProductionAuditEvent(
                    project_id=project.id,
                    task_id=task.id,
                    entity_type="dataset_asset",
                    entity_code=asset.asset_code,
                    action="physical_file_downloaded",
                    previous_values={},
                    new_values={
                        "physical_file_uri": asset.physical_file_uri,
                        "physical_file_size_bytes": asset.physical_file_size_bytes,
                        "physical_checksum_sha256": asset.physical_checksum_sha256,
                    },
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                ),
            )
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            raise ValidationException("数据资产下载审计写入失败") from exc
        return DatasetAssetDownload(
            path=path,
            filename=str(asset.physical_original_filename),
            media_type=str(asset.physical_media_type),
            checksum_sha256=str(asset.physical_checksum_sha256),
        )

    async def load_verified_files(
        self,
        assets: Sequence[DatasetAsset],
    ) -> list[VerifiedDatasetAssetFile]:
        """为交付包重新复核目录内全部已验证实体。

        Args:
            assets: 当前项目和任务的数据资产序列。

        Returns:
            list[VerifiedDatasetAssetFile]: 可被交付目录引用的实体证据。
        """
        verified: list[VerifiedDatasetAssetFile] = []
        for asset in assets:
            if asset.verification_status != "verified":
                continue
            path = await asyncio.to_thread(self.resolve_verified_file, asset)
            verified.append(
                VerifiedDatasetAssetFile(
                    asset_code=asset.asset_code,
                    path=path,
                    file_uri=str(asset.physical_file_uri),
                    original_filename=str(asset.physical_original_filename),
                    file_size_bytes=int(asset.physical_file_size_bytes),
                    checksum_sha256=str(asset.physical_checksum_sha256),
                    media_type=str(asset.physical_media_type),
                    verified_at=asset.verified_at,
                    verified_by=str(asset.verified_by),
                    verified_by_code=str(asset.verified_by_code),
                    verified_by_role=str(asset.verified_by_role),
                    verification_comment=str(asset.verification_comment),
                )
            )
        return verified
