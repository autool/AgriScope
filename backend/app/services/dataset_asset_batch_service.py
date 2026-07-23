"""多源数据资产 1–20 文件原子批量入库服务。"""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.dao.production_dao import ProductionDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.dataset_asset_import import (
    DatasetAssetImportBatch,
    DatasetAssetImportBatchItem,
)
from app.models.dataset_asset_verification import DatasetAssetVerification
from app.models.workbench import (
    DatasetAsset,
    DatasetLineage,
    ProductionAuditEvent,
)
from app.schemas.production import (
    DatasetAssetBatchCreateRequest,
    DatasetAssetBatchItemRequest,
    DatasetAssetBatchResponse,
)
from app.services.dataset_asset_service import (
    DatasetAssetService,
    PreparedDatasetUpload,
)
from app.services.project_user_service import ProjectUserService


@dataclass(frozen=True)
class DatasetAssetBatchUploadFile:
    """multipart 中一个数据资产文件名和二进制流。"""

    filename: str
    file_handle: BinaryIO
    reported_media_type: str | None


@dataclass(frozen=True)
class PreparedDatasetBatchItem:
    """已完成全部前置校验但尚未发布的批次成员。"""

    request: DatasetAssetBatchItemRequest
    prepared: PreparedDatasetUpload


@dataclass(frozen=True)
class PublishedDatasetBatchItem:
    """已发布受控文件和本次核验编号。"""

    prepared_item: PreparedDatasetBatchItem
    verification_code: str
    final_path: Path
    file_uri: str


class DatasetAssetBatchService:
    """编排数据资产批量检查、发布、持久化和回滚清理。"""

    def __init__(
        self,
        dao: ProductionDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        user_service: ProjectUserService | None = None,
        asset_service: DatasetAssetService | None = None,
    ) -> None:
        """初始化数据资产批量入库服务。

        Args:
            dao: 生产模块数据访问对象。
            workbench_dao: 项目和任务公共查询对象。
            user_service: 稳定项目用户能力服务。
            asset_service: 单文件实体检查、发布和响应服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ProductionDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.user_service = user_service or ProjectUserService()
        self.asset_service = asset_service or DatasetAssetService(
            dao=self.dao,
            workbench_dao=self.workbench_dao,
            user_service=self.user_service,
        )

    @staticmethod
    def _validate_internal_lineage(
        items: list[DatasetAssetBatchItemRequest],
    ) -> None:
        """拒绝同批资产血缘循环。

        Args:
            items: 已通过字段校验的批次成员。

        Returns:
            None: 血缘为有向无环图时无返回值。
        """
        batch_codes = {item.asset_code for item in items}
        graph = {
            item.asset_code: [
                code for code in item.parent_asset_codes if code in batch_codes
            ]
            for item in items
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(asset_code: str) -> None:
            if asset_code in visiting:
                raise ValidationException("批次内父资产血缘不得形成循环")
            if asset_code in visited:
                return
            visiting.add(asset_code)
            for parent_code in graph[asset_code]:
                visit(parent_code)
            visiting.remove(asset_code)
            visited.add(asset_code)

        for code in graph:
            visit(code)

    @staticmethod
    def _manifest_payload(
        request: DatasetAssetBatchCreateRequest,
        prepared: list[PreparedDatasetBatchItem],
    ) -> dict[str, object]:
        """构造包含规范化业务元数据和服务端实体证据的清单。

        Args:
            request: 原子批量入库请求。
            prepared: 已完成服务端检查的成员。

        Returns:
            dict[str, object]: 可持久化并重新计算摘要的规范化清单。
        """
        return {
            "schema_version": "dataset-asset-batch-v1",
            "batch_code": request.batch_code,
            "operator_code": request.operator_code,
            "comment": request.comment,
            "items": [
                {
                    "sequence": sequence,
                    "metadata": item.request.model_dump(mode="json"),
                    "file_size_bytes": item.prepared.file_size_bytes,
                    "checksum_sha256": item.prepared.checksum_sha256,
                    "media_type": item.prepared.inspection.media_type,
                    "inspection": item.prepared.inspection.metadata,
                }
                for sequence, item in enumerate(prepared, start=1)
            ],
        }
    @staticmethod
    def _manifest_sha256(payload: dict[str, object]) -> str:
        """计算规范化批次清单 SHA-256。

        Args:
            payload: 已包含最终实体证据的规范化清单。

        Returns:
            str: 规范化 JSON 的小写 SHA-256。
        """
        content = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(content).hexdigest()

    @staticmethod
    def _remove_published_files(paths: list[Path]) -> None:
        """删除当前失败批次已经发布的全部目标文件。

        Args:
            paths: 已发布目标路径。

        Returns:
            None: 文件清理完成后无返回值。
        """
        cleanup_errors: list[OSError] = []
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            raise ValidationException("数据资产批次回滚时实体清理失败") from (
                cleanup_errors[0]
            )

    async def _rollback_and_remove_published_files(
        self,
        db: AsyncSession,
        paths: list[Path],
    ) -> None:
        """回滚数据库并独立执行全部已发布实体清理。

        Args:
            db: 当前异步数据库会话。
            paths: 当前失败批次已经发布的目标路径。

        Returns:
            None: 数据库与实体恢复完成后无返回值。
        """
        rollback_error: BaseException | None = None
        cleanup_error: BaseException | None = None
        try:
            await db.rollback()
        except BaseException as exc:
            rollback_error = exc
        try:
            await asyncio.to_thread(self._remove_published_files, paths)
        except BaseException as exc:
            cleanup_error = exc
        if cleanup_error is not None:
            raise ValidationException(
                "数据资产批次失败后受控实体清理失败"
            ) from cleanup_error
        if rollback_error is not None:
            raise ValidationException(
                "数据资产批次数据库回滚失败，已发布实体已清理"
            ) from rollback_error

    async def _prepare_items(
        self,
        db: AsyncSession,
        project_id: int,
        request: DatasetAssetBatchCreateRequest,
        files: list[DatasetAssetBatchUploadFile],
    ) -> list[PreparedDatasetBatchItem]:
        """校验文件映射、重复内容、存量资产和批次总大小。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            request: 批量清单。
            files: multipart 文件列表。

        Returns:
            list[PreparedDatasetBatchItem]: 全部通过检查的临时成员。
        """
        if len(files) != len(request.items):
            raise ValidationException("上传文件数量与数据资产批次清单不一致")
        file_by_name = {item.filename.casefold(): item for item in files}
        if len(file_by_name) != len(files):
            raise ValidationException("上传文件名不得重复")
        manifest_names = {item.filename.casefold() for item in request.items}
        if set(file_by_name) != manifest_names:
            raise ValidationException("上传文件名与数据资产批次清单不完全一致")

        prepared: list[PreparedDatasetBatchItem] = []
        batch_checksums: set[str] = set()
        total_size = 0
        try:
            for item in request.items:
                if await self.dao.get_asset_by_code(
                    db,
                    project_id,
                    item.asset_code,
                ):
                    raise ValidationException(f"资产编号 {item.asset_code} 已存在")
                upload = file_by_name[item.filename.casefold()]
                entity = await asyncio.to_thread(
                    self.asset_service.prepare_upload,
                    upload.file_handle,
                    upload.filename,
                    item.asset_type,
                    upload.reported_media_type,
                )
                try:
                    if entity.checksum_sha256 in batch_checksums:
                        raise ValidationException(
                            f"文件 {entity.original_filename} "
                            "与同批其他文件内容重复"
                        )
                    next_total_size = total_size + entity.file_size_bytes
                    if (
                        next_total_size
                        > settings.max_dataset_asset_batch_upload_bytes
                    ):
                        raise ValidationException(
                            "数据资产批次总大小超过平台允许上限"
                        )
                    batch_checksums.add(entity.checksum_sha256)
                    total_size = next_total_size
                    prepared.append(
                        PreparedDatasetBatchItem(request=item, prepared=entity)
                    )
                except BaseException:
                    entity.temporary_path.unlink(missing_ok=True)
                    raise
        except BaseException:
            for item in prepared:
                item.prepared.temporary_path.unlink(missing_ok=True)
            raise
        return prepared

    async def upload_assets_batch(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: DatasetAssetBatchCreateRequest,
        files: list[DatasetAssetBatchUploadFile],
    ) -> DatasetAssetBatchResponse:
        """在一次请求和一次业务事务内导入 1–20 个数据资产实体。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            request: 批次编号、逐文件元数据、操作人和依据。
            files: multipart 中全部文件。

        Returns:
            DatasetAssetBatchResponse: 批次摘要和全部已核验资产。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None or task.project_id != project.id:
            raise NotFoundException(f"项目内未找到任务 {task_code}")
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_datasets",
        )
        if await self.dao.get_dataset_import_batch_by_code(db, request.batch_code):
            raise ValidationException(f"数据资产入库批次 {request.batch_code} 已存在")
        self._validate_internal_lineage(request.items)

        batch_codes = {item.asset_code for item in request.items}
        external_parent_codes = sorted({
            parent_code
            for item in request.items
            for parent_code in item.parent_asset_codes
            if parent_code not in batch_codes
        })
        external_parents = await self.dao.get_assets_by_codes(
            db,
            project.id,
            external_parent_codes,
        )
        if len(external_parents) != len(external_parent_codes):
            found = {asset.asset_code for asset in external_parents}
            missing = [code for code in external_parent_codes if code not in found]
            raise ValidationException(f"父资产不存在：{', '.join(missing)}")

        prepared: list[PreparedDatasetBatchItem] = []
        published: list[PublishedDatasetBatchItem] = []
        assets: list[DatasetAsset] = []
        verifications: list[DatasetAssetVerification] = []
        try:
            prepared = await self._prepare_items(
                db,
                project.id,
                request,
                files,
            )
            for item in prepared:
                duplicate = await self.dao.get_asset_by_checksum(
                    db,
                    project.id,
                    item.prepared.checksum_sha256,
                )
                if duplicate is not None:
                    raise ValidationException(
                        f"文件 {item.prepared.original_filename} 已登记为资产 "
                        f"{duplicate.asset_code}"
                    )

            manifest_payload = self._manifest_payload(request, prepared)
            manifest_checksum = self._manifest_sha256(manifest_payload)
            now = datetime.now(UTC)
            for item in prepared:
                verification_code = (
                    f"DSVERIFY-{now:%Y%m%dT%H%M%S}-{uuid4().hex[:10]}"
                )
                final_path, file_uri = await asyncio.to_thread(
                    self.asset_service.publish_upload,
                    item.prepared,
                    item.request.asset_code,
                    verification_code,
                )
                published.append(
                    PublishedDatasetBatchItem(
                        prepared_item=item,
                        verification_code=verification_code,
                        final_path=final_path,
                        file_uri=file_uri,
                    )
                )

            for sequence, item in enumerate(published, start=1):
                request_item = item.prepared_item.request
                entity = item.prepared_item.prepared
                metadata = dict(request_item.metadata)
                metadata.update({
                    "entity_inspection": entity.inspection.metadata,
                    "import_batch_code": request.batch_code,
                    "import_batch_sequence": sequence,
                    "import_manifest_sha256": manifest_checksum,
                })
                extent = (
                    func.ST_MakeEnvelope(*request_item.extent_bbox, 4326)
                    if request_item.extent_bbox
                    else None
                )
                asset = await self.dao.add_asset(
                    db,
                    DatasetAsset(
                        project_id=project.id,
                        task_id=task.id,
                        asset_code=request_item.asset_code,
                        asset_name=request_item.asset_name,
                        asset_type=request_item.asset_type,
                        source_name=request_item.source_name,
                        source_uri=request_item.source_uri,
                        source_version=request_item.source_version,
                        checksum_sha256=entity.checksum_sha256,
                        crs=request_item.crs,
                        extent=extent,
                        time_start=request_item.time_start,
                        time_end=request_item.time_end,
                        security_classification=(
                            request_item.security_classification
                        ),
                        data_status=request_item.data_status,
                        verification_status="verified",
                        physical_file_uri=item.file_uri,
                        physical_original_filename=entity.original_filename,
                        physical_file_size_bytes=entity.file_size_bytes,
                        physical_checksum_sha256=entity.checksum_sha256,
                        physical_media_type=entity.inspection.media_type,
                        verified_at=now,
                        verified_by=operator.display_name,
                        verified_by_code=operator.user_code,
                        verified_by_role=operator.role_code,
                        verification_comment=request.comment,
                        metadata_payload=metadata,
                        registered_by=operator.display_name,
                        registered_by_code=operator.user_code,
                        registered_by_role=operator.role_code,
                        created_at=now,
                        updated_at=now,
                    ),
                )
                assets.append(asset)
                verification = await self.dao.add_dataset_asset_verification(
                    db,
                    DatasetAssetVerification(
                        asset_id=asset.id,
                        verification_code=item.verification_code,
                        verification_status="verified",
                        original_filename=entity.original_filename,
                        file_uri=item.file_uri,
                        file_size_bytes=entity.file_size_bytes,
                        expected_checksum_sha256=entity.checksum_sha256,
                        computed_checksum_sha256=entity.checksum_sha256,
                        media_type=entity.inspection.media_type,
                        inspection_metadata=entity.inspection.metadata,
                        verification_error=None,
                        operator=operator.display_name,
                        operator_code=operator.user_code,
                        operator_role=operator.role_code,
                        verification_comment=request.comment,
                        created_at=now,
                    ),
                )
                verifications.append(verification)

            asset_by_code = {asset.asset_code: asset for asset in assets}
            parent_by_code = {
                asset.asset_code: asset for asset in external_parents
            } | asset_by_code
            lineages = [
                DatasetLineage(
                    parent_asset_id=parent_by_code[parent_code].id,
                    derived_asset_id=asset_by_code[item.asset_code].id,
                    relation_type=item.lineage_relation_type,
                    process_code=item.process_code,
                )
                for item in request.items
                for parent_code in item.parent_asset_codes
            ]
            await self.dao.add_lineages(db, lineages)

            batch = await self.dao.add_dataset_import_batch(
                db,
                DatasetAssetImportBatch(
                    project_id=project.id,
                    task_id=task.id,
                    batch_code=request.batch_code,
                    item_count=len(assets),
                    total_size_bytes=sum(
                        item.prepared_item.prepared.file_size_bytes
                        for item in published
                    ),
                    manifest_sha256=manifest_checksum,
                    manifest_payload=manifest_payload,
                    imported_by=operator.display_name,
                    imported_by_code=operator.user_code,
                    imported_by_role=operator.role_code,
                    import_comment=request.comment,
                    created_at=now,
                ),
            )
            await self.dao.add_dataset_import_batch_items(
                db,
                [
                    DatasetAssetImportBatchItem(
                        batch_id=batch.id,
                        asset_id=asset.id,
                        verification_id=verification.id,
                        sequence=sequence,
                        original_filename=item.prepared_item.prepared.original_filename,
                        file_size_bytes=(
                            item.prepared_item.prepared.file_size_bytes
                        ),
                        checksum_sha256=(
                            item.prepared_item.prepared.checksum_sha256
                        ),
                        created_at=now,
                    )
                    for sequence, (item, asset, verification) in enumerate(
                        zip(published, assets, verifications, strict=True),
                        start=1,
                    )
                ],
            )
            for sequence, (item, asset) in enumerate(
                zip(published, assets, strict=True),
                start=1,
            ):
                entity = item.prepared_item.prepared
                await self.dao.add_audit_event(
                    db,
                    ProductionAuditEvent(
                        project_id=project.id,
                        task_id=task.id,
                        entity_type="dataset_asset",
                        entity_code=asset.asset_code,
                        action="batch_uploaded_and_verified",
                        previous_values={},
                        new_values={
                            "batch_code": request.batch_code,
                            "sequence": sequence,
                            "asset_type": asset.asset_type,
                            "checksum_sha256": asset.checksum_sha256,
                            "physical_file_uri": item.file_uri,
                            "physical_file_size_bytes": entity.file_size_bytes,
                            "verification_code": item.verification_code,
                            "manifest_sha256": manifest_checksum,
                            "parent_asset_codes": (
                                item.prepared_item.request.parent_asset_codes
                            ),
                            "verification_comment": request.comment,
                        },
                        operator=operator.display_name,
                        operator_code=operator.user_code,
                        operator_role=operator.role_code,
                        created_at=now,
                    ),
                )
            await self.dao.add_audit_event(
                db,
                ProductionAuditEvent(
                    project_id=project.id,
                    task_id=task.id,
                    entity_type="dataset_asset_batch",
                    entity_code=batch.batch_code,
                    action="atomic_batch_imported",
                    previous_values={},
                    new_values={
                        "item_count": batch.item_count,
                        "total_size_bytes": batch.total_size_bytes,
                        "manifest_sha256": batch.manifest_sha256,
                        "asset_codes": [asset.asset_code for asset in assets],
                        "comment": request.comment,
                    },
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                    created_at=now,
                ),
            )
            responses = [
                await self.asset_service.get_asset_response(
                    db,
                    project.id,
                    asset.asset_code,
                )
                for asset in assets
            ]
            await db.commit()
            return DatasetAssetBatchResponse(
                batch_code=batch.batch_code,
                item_count=batch.item_count,
                total_size_bytes=batch.total_size_bytes,
                manifest_sha256=batch.manifest_sha256,
                imported_by=batch.imported_by,
                imported_by_code=batch.imported_by_code,
                imported_by_role=batch.imported_by_role,
                comment=batch.import_comment,
                created_at=batch.created_at,
                items=responses,
            )
        except IntegrityError as exc:
            await self._rollback_and_remove_published_files(
                db,
                [item.final_path for item in published],
            )
            raise ValidationException(
                "数据资产批次、资产编号或实体校验值已存在"
            ) from exc
        except SQLAlchemyError as exc:
            await self._rollback_and_remove_published_files(
                db,
                [item.final_path for item in published],
            )
            raise ValidationException("数据资产批次事务提交失败") from exc
        except BaseException:
            await self._rollback_and_remove_published_files(
                db,
                [item.final_path for item in published],
            )
            raise
        finally:
            for item in prepared:
                item.prepared.temporary_path.unlink(missing_ok=True)
