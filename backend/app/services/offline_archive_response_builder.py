"""离线介质封存当前性判断与 API 响应组装。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.offline_archive_dao import OfflineArchiveDAO
from app.models.offline_archive import OfflineArchive, OfflineArchiveVolume
from app.schemas.offline_archive import (
    OfflineArchiveResponse,
    OfflineArchiveVolumeResponse,
)


class OfflineArchiveResponseBuilder:
    """按当前成果和来源快照组装离线封存响应。"""

    def __init__(self, dao: OfflineArchiveDAO) -> None:
        """初始化响应组装器。

        Args:
            dao: 离线封存 DAO。

        Returns:
            None: 无返回值。
        """
        self.dao = dao

    @staticmethod
    def stale_reason(
        archive: OfflineArchive,
        package: object | None,
        source_snapshot_sha256: str | None,
        volumes: list[OfflineArchiveVolume],
    ) -> str | None:
        """判断历史离线封存是否仍对应当前受控来源。

        Args:
            archive: 离线封存版本。
            package: 当前有效成果包；不存在时为空。
            source_snapshot_sha256: 当前来源快照；无法加载时为空。
            volumes: 该封存版本的全部分卷记录。

        Returns:
            str | None: 失效原因；仍有效时为空。
        """
        if archive.status == "superseded":
            return "离线封存已被新版本替代"
        if archive.status == "invalid":
            return "离线封存已标记为无效"
        if package is None:
            return "当前成果包不存在或已经失效"
        if (
            archive.delivery_package_id != package.id
            or archive.delivery_package_code != package.package_code
            or archive.delivery_package_size_bytes != package.file_size_bytes
            or archive.delivery_package_checksum_sha256 != package.checksum_sha256
            or archive.delivery_package_completed_at_snapshot != package.completed_at
        ):
            return "当前成果包版本或实体证据已变化"
        if source_snapshot_sha256 != archive.source_snapshot_sha256:
            return "源栅格、处理产物或多源数据实体快照已变化"
        if len(volumes) != archive.volume_count:
            return "离线封存分卷记录数量不一致"
        return None

    async def to_response(
        self,
        db: AsyncSession,
        archive: OfflineArchive,
        package: object | None,
        source_snapshot_sha256: str | None,
    ) -> OfflineArchiveResponse:
        """组装带当前性判断和逐卷下载地址的响应。

        Args:
            db: 异步数据库会话。
            archive: 离线封存版本。
            package: 当前成果包。
            source_snapshot_sha256: 当前来源快照 SHA-256。

        Returns:
            OfflineArchiveResponse: 前端版本和分卷响应。
        """
        volumes = list(await self.dao.list_volumes(db, archive.id))
        stale_reason = self.stale_reason(
            archive,
            package,
            source_snapshot_sha256,
            volumes,
        )
        is_current = stale_reason is None
        return OfflineArchiveResponse(
            archive_code=archive.archive_code,
            archive_name=archive.archive_name,
            version=archive.version,
            status=archive.status,
            volume_capacity_bytes=archive.volume_capacity_bytes,
            volume_count=archive.volume_count,
            source_count=archive.source_count,
            total_source_bytes=archive.total_source_bytes,
            total_archive_bytes=archive.total_archive_bytes,
            source_snapshot_sha256=archive.source_snapshot_sha256,
            manifest_size_bytes=archive.manifest_size_bytes,
            manifest_checksum_sha256=archive.manifest_checksum_sha256,
            delivery_package_code=archive.delivery_package_code,
            delivery_package_checksum_sha256=(
                archive.delivery_package_checksum_sha256
            ),
            generated_by=archive.generated_by,
            generated_by_code=archive.generated_by_code,
            generated_by_role=archive.generated_by_role,
            generation_comment=archive.generation_comment,
            generated_at=archive.generated_at,
            superseded_at=archive.superseded_at,
            is_current=is_current,
            stale_reason=stale_reason,
            manifest_download_url=(
                f"/api/v1/offline-archives/{archive.archive_code}/manifest"
                if is_current
                else None
            ),
            volumes=[
                OfflineArchiveVolumeResponse(
                    sequence=volume.sequence,
                    filename=volume.filename,
                    file_size_bytes=volume.file_size_bytes,
                    checksum_sha256=volume.checksum_sha256,
                    member_count=volume.member_count,
                    source_size_bytes=volume.source_size_bytes,
                    download_url=(
                        f"/api/v1/offline-archives/{archive.archive_code}/"
                        f"volumes/{volume.sequence}/download"
                        if is_current
                        else None
                    ),
                )
                for volume in volumes
            ],
        )
