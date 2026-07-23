"""源栅格离线介质容量预估、版本封存和逐卷下载服务。"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.dao.offline_archive_dao import OfflineArchiveDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.offline_archive import OfflineArchive, OfflineArchiveEvent
from app.models.workbench import ReviewRecord
from app.schemas.offline_archive import (
    OfflineArchiveGenerateRequest,
    OfflineArchiveOverviewResponse,
    OfflineArchiveResponse,
)
from app.services.dataset_asset_service import DatasetAssetService
from app.services.delivery_service import DeliveryService
from app.services.imagery_service import ImageryService
from app.services.offline_archive_inventory_service import (
    OfflineArchiveInventoryService,
)
from app.services.offline_archive_model_factory import OfflineArchiveModelFactory
from app.services.offline_archive_response_builder import (
    OfflineArchiveResponseBuilder,
)
from app.services.offline_archive_writer import OfflineArchiveWriter
from app.services.project_user_service import ProjectUserService


@dataclass(frozen=True)
class OfflineArchiveDownload:
    """路由层构造 FileResponse 所需的已验证实体。"""

    path: Path
    filename: str
    media_type: str


class OfflineArchiveService:
    """管理任务级真实源栅格 ZIP64 离线封存闭环。"""

    def __init__(
        self,
        dao: OfflineArchiveDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        delivery_service: DeliveryService | None = None,
        imagery_service: ImageryService | None = None,
        dataset_asset_service: DatasetAssetService | None = None,
        user_service: ProjectUserService | None = None,
        writer: OfflineArchiveWriter | None = None,
    ) -> None:
        """初始化离线封存服务依赖。

        Args:
            dao: 离线封存 DAO。
            workbench_dao: 项目、任务和审计 DAO。
            delivery_service: 当前成果包与实体复核服务。
            imagery_service: 源影像和处理产物实体复核服务。
            dataset_asset_service: 多源数据实体复核服务。
            user_service: 稳定项目用户能力服务。
            writer: ZIP64 分卷写入与复核器。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or OfflineArchiveDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        resolved_delivery_service = delivery_service or DeliveryService()
        resolved_imagery_service = imagery_service or ImageryService()
        resolved_dataset_service = dataset_asset_service or DatasetAssetService()
        self.user_service = user_service or ProjectUserService()
        self.writer = writer or OfflineArchiveWriter()
        self.inventory_service = OfflineArchiveInventoryService(
            self.dao,
            resolved_delivery_service,
            resolved_imagery_service,
            resolved_dataset_service,
        )
        self.response_builder = OfflineArchiveResponseBuilder(self.dao)
        self.model_factory = OfflineArchiveModelFactory()

    async def get_overview(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> OfflineArchiveOverviewResponse:
        """查询真实容量预估、生成门禁和封存历史。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            OfflineArchiveOverviewResponse: 离线介质工作台数据。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        package = None
        current_sources = []
        generate_blocker: str | None = None
        try:
            package, current_sources = (
                await self.inventory_service.load_current_sources(db, task)
            )
        except (NotFoundException, ValidationException) as exc:
            generate_blocker = exc.message
            try:
                current_sources = (
                    await self.inventory_service.load_non_delivery_sources(db, task)
                )
                current_sources = self.inventory_service.assign_sequences(
                    current_sources
                )
            except (NotFoundException, ValidationException) as source_exc:
                if generate_blocker is None:
                    generate_blocker = source_exc.message
                current_sources = []
        snapshot = (
            self.writer.snapshot_sha256(current_sources)
            if package is not None and current_sources
            else None
        )
        archives = await self.dao.list_archives(db, task.id)
        responses = [
            await self.response_builder.to_response(
                db,
                archive,
                package,
                snapshot,
            )
            for archive in archives
        ]
        return OfflineArchiveOverviewResponse(
            task_code=task_code,
            can_generate=generate_blocker is None,
            generate_blocker=generate_blocker,
            recommended_volume_capacity_bytes=(
                settings.offline_archive_default_volume_bytes
            ),
            max_volume_capacity_bytes=settings.offline_archive_max_volume_bytes,
            source_count=len(current_sources),
            total_source_bytes=sum(
                source.file_size_bytes for source in current_sources
            ),
            largest_source_bytes=max(
                (source.file_size_bytes for source in current_sources),
                default=0,
            ),
            source_summaries=self.inventory_service.source_summaries(
                current_sources
            ),
            archives=responses,
        )

    async def generate_archive(
        self,
        db: AsyncSession,
        task_code: str,
        request: OfflineArchiveGenerateRequest,
    ) -> OfflineArchiveResponse:
        """生成、原子发布并持久化新的离线介质封存版本。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 容量、名称、操作人和生成依据。

        Returns:
            OfflineArchiveResponse: 新生成封存版本及分卷清单。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        operator = await self.user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "generate_delivery",
        )
        package, sources = await self.inventory_service.load_current_sources(
            db,
            task,
        )
        volume_capacity_bytes = (
            request.volume_capacity_bytes
            or settings.offline_archive_default_volume_bytes
        )
        version = await self.dao.get_next_version(db, task.id)
        generated_at = datetime.now(UTC)
        timestamp = generated_at.strftime("%Y%m%d%H%M%S")
        archive_code = f"{task_code}-OFFLINE-v{version}-{timestamp}"
        archive_name = (
            request.archive_name
            or f"{task.task_name}源栅格离线介质封存 V{version}"
        )
        source_snapshot_sha256 = self.writer.snapshot_sha256(sources)
        delivery_snapshot = self.inventory_service.delivery_snapshot(package)
        write_result = await asyncio.to_thread(
            self.writer.write_archive,
            archive_code,
            archive_name,
            generated_at,
            volume_capacity_bytes,
            source_snapshot_sha256,
            delivery_snapshot,
            sources,
        )
        try:
            await self._supersede_previous_archives(
                db,
                task.id,
                archive_code,
                operator,
            )
            archive = await self.dao.add_archive(
                db,
                self.model_factory.build_archive(
                    task.id,
                    package,
                    archive_code,
                    archive_name,
                    version,
                    volume_capacity_bytes,
                    source_snapshot_sha256,
                    operator,
                    request.comment,
                    generated_at,
                    write_result,
                ),
            )
            volume_models, source_models = self.model_factory.build_children(
                archive.id,
                write_result,
            )
            await self.dao.add_volumes(db, volume_models)
            await self.dao.add_sources(db, source_models)
            await self._record_generation_event(
                db,
                archive,
                operator,
                request.comment,
            )
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="delivery",
                    action="offline_archive_generated",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"生成离线封存 {archive_code}，共 "
                        f"{archive.volume_count} 卷、{archive.source_count} 个实体；"
                        f"{request.comment}"
                    ),
                ),
            )
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            await asyncio.to_thread(self.writer.remove_archive, archive_code)
            raise ValidationException(
                "离线封存数据库写入失败，已清理全部新分卷"
            ) from exc
        return await self.response_builder.to_response(
            db,
            archive,
            package,
            source_snapshot_sha256,
        )

    async def _supersede_previous_archives(
        self,
        db: AsyncSession,
        task_id: int,
        archive_code: str,
        operator: object,
    ) -> None:
        """将已有当前封存转为历史并记录稳定角色事件。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            archive_code: 新离线封存编号。
            operator: 已授权项目负责人。

        Returns:
            None: 旧版本和事件写入会话后结束。
        """
        superseded_at = datetime.now(UTC)
        previous_archives = await self.dao.list_current_archives_for_update(
            db,
            task_id,
        )
        for previous in previous_archives:
            previous.status = "superseded"
            previous.superseded_at = superseded_at
            await self.dao.add_event(
                db,
                OfflineArchiveEvent(
                    archive_id=previous.id,
                    event_type="superseded",
                    actor=operator.display_name,
                    actor_code=operator.user_code,
                    actor_role=operator.role_code,
                    detail={"superseded_by": archive_code},
                    comment="生成新的源栅格离线封存版本",
                ),
            )

    async def _record_generation_event(
        self,
        db: AsyncSession,
        archive: OfflineArchive,
        operator: object,
        comment: str,
    ) -> None:
        """记录新封存版本的实体摘要和稳定角色快照。

        Args:
            db: 异步数据库会话。
            archive: 新生成离线封存。
            operator: 已授权项目负责人。
            comment: 生成依据。

        Returns:
            None: 事件写入会话后结束。
        """
        await self.dao.add_event(
            db,
            OfflineArchiveEvent(
                archive_id=archive.id,
                event_type="generated",
                actor=operator.display_name,
                actor_code=operator.user_code,
                actor_role=operator.role_code,
                detail={
                    "version": archive.version,
                    "volume_count": archive.volume_count,
                    "source_count": archive.source_count,
                    "total_source_bytes": archive.total_source_bytes,
                    "source_snapshot_sha256": archive.source_snapshot_sha256,
                },
                comment=comment,
            ),
        )

    async def _require_current_archive(
        self,
        db: AsyncSession,
        archive_code: str,
        requester_code: str,
    ) -> tuple[OfflineArchive, object]:
        """校验下载权限、当前来源快照和顶层清单实体。

        Args:
            db: 异步数据库会话。
            archive_code: 离线封存编号。
            requester_code: 下载人稳定编码。

        Returns:
            tuple[OfflineArchive, object]: 当前有效封存及下载用户。
        """
        archive = await self.dao.get_archive_by_code(db, archive_code)
        if archive is None:
            raise NotFoundException(f"未找到离线封存 {archive_code}")
        task = await self.workbench_dao.get_task_by_id(db, archive.task_id)
        if task is None:
            raise NotFoundException("离线封存关联任务不存在")
        requester = await self.user_service.require_capability(
            db,
            task.project_id,
            requester_code,
            "download_delivery",
        )
        package, sources = await self.inventory_service.load_current_sources(
            db,
            task,
        )
        snapshot = self.writer.snapshot_sha256(sources)
        volumes = list(await self.dao.list_volumes(db, archive.id))
        stale_reason = self.response_builder.stale_reason(
            archive,
            package,
            snapshot,
            volumes,
        )
        if stale_reason is not None:
            raise ValidationException(f"离线封存已失效：{stale_reason}")
        await asyncio.to_thread(
            self.writer.verify_manifest,
            archive.manifest_uri,
            archive.manifest_size_bytes,
            archive.manifest_checksum_sha256,
            archive.canonical_manifest,
        )
        return archive, requester

    async def get_manifest_for_download(
        self,
        db: AsyncSession,
        archive_code: str,
        requester_code: str,
    ) -> OfflineArchiveDownload:
        """复核并返回顶层规范清单下载实体。

        Args:
            db: 异步数据库会话。
            archive_code: 离线封存编号。
            requester_code: 下载人稳定编码。

        Returns:
            OfflineArchiveDownload: JSON 清单路径和文件名。
        """
        archive, requester = await self._require_current_archive(
            db,
            archive_code,
            requester_code,
        )
        path = await asyncio.to_thread(
            self.writer.verify_manifest,
            archive.manifest_uri,
            archive.manifest_size_bytes,
            archive.manifest_checksum_sha256,
            archive.canonical_manifest,
        )
        await self._record_download_event(
            db,
            archive,
            requester,
            "manifest_downloaded",
            {"manifest_checksum_sha256": archive.manifest_checksum_sha256},
        )
        return OfflineArchiveDownload(
            path=path,
            filename=path.name,
            media_type="application/json",
        )

    async def get_volume_for_download(
        self,
        db: AsyncSession,
        archive_code: str,
        sequence: int,
        requester_code: str,
    ) -> OfflineArchiveDownload:
        """复核当前性、顶层清单、卷和全部卷内成员后返回下载实体。

        Args:
            db: 异步数据库会话。
            archive_code: 离线封存编号。
            sequence: 待下载分卷序号。
            requester_code: 下载人稳定编码。

        Returns:
            OfflineArchiveDownload: ZIP64 分卷路径和文件名。
        """
        archive, requester = await self._require_current_archive(
            db,
            archive_code,
            requester_code,
        )
        volume = await self.dao.get_volume(db, archive.id, sequence)
        if volume is None:
            raise NotFoundException(
                f"离线封存 {archive_code} 不存在第 {sequence} 卷"
            )
        path = await asyncio.to_thread(
            self.writer.verify_volume,
            volume.file_uri,
            volume.file_size_bytes,
            volume.checksum_sha256,
            volume.volume_manifest,
        )
        await self._record_download_event(
            db,
            archive,
            requester,
            "volume_downloaded",
            {
                "volume_sequence": volume.sequence,
                "filename": volume.filename,
                "file_size_bytes": volume.file_size_bytes,
                "checksum_sha256": volume.checksum_sha256,
            },
        )
        return OfflineArchiveDownload(
            path=path,
            filename=volume.filename,
            media_type="application/zip",
        )

    async def _record_download_event(
        self,
        db: AsyncSession,
        archive: OfflineArchive,
        requester: object,
        event_type: str,
        detail: dict,
    ) -> None:
        """持久化稳定下载人角色快照，失败时拒绝下载。

        Args:
            db: 异步数据库会话。
            archive: 被下载的离线封存。
            requester: 已授权稳定项目用户。
            event_type: 清单或分卷下载事件编码。
            detail: 被下载实体证据。

        Returns:
            None: 事件提交后无返回值。
        """
        try:
            await self.dao.add_event(
                db,
                OfflineArchiveEvent(
                    archive_id=archive.id,
                    event_type=event_type,
                    actor=requester.display_name,
                    actor_code=requester.user_code,
                    actor_role=requester.role_code,
                    detail=detail,
                    comment="实体完整性复核通过后下载",
                ),
            )
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            raise ValidationException("离线封存下载审计写入失败") from exc
