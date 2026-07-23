"""离线介质封存 ORM 主记录、分卷和来源快照工厂。"""

from datetime import datetime

from app.models.offline_archive import (
    OfflineArchive,
    OfflineArchiveSource,
    OfflineArchiveVolume,
)
from app.services.offline_archive_writer import OfflineArchiveWriteResult


class OfflineArchiveModelFactory:
    """把实体分卷结果转换为分层持久化模型。"""

    @staticmethod
    def build_archive(
        task_id: int,
        package: object,
        archive_code: str,
        archive_name: str,
        version: int,
        volume_capacity_bytes: int,
        source_snapshot_sha256: str,
        operator: object,
        generation_comment: str,
        generated_at: datetime,
        result: OfflineArchiveWriteResult,
    ) -> OfflineArchive:
        """从实体写入结果构造离线封存主记录。

        Args:
            task_id: 作业任务主键。
            package: 当前成果交付包。
            archive_code: 离线封存编号。
            archive_name: 离线封存名称。
            version: 任务内版本号。
            volume_capacity_bytes: 单卷配置容量。
            source_snapshot_sha256: 来源快照 SHA-256。
            operator: 已授权稳定项目用户。
            generation_comment: 生成依据。
            generated_at: 统一生成时间。
            result: ZIP64 分卷实体写入结果。

        Returns:
            OfflineArchive: 待持久化主记录。
        """
        return OfflineArchive(
            task_id=task_id,
            delivery_package_id=package.id,
            archive_code=archive_code,
            archive_name=archive_name,
            version=version,
            status="completed",
            volume_capacity_bytes=volume_capacity_bytes,
            volume_count=len(result.volumes),
            source_count=result.canonical_manifest["source_count"],
            total_source_bytes=result.canonical_manifest["total_source_bytes"],
            total_archive_bytes=result.canonical_manifest["total_archive_bytes"],
            source_snapshot_sha256=source_snapshot_sha256,
            canonical_manifest=result.canonical_manifest,
            manifest_uri=result.manifest_uri,
            manifest_size_bytes=result.manifest_size_bytes,
            manifest_checksum_sha256=result.manifest_checksum_sha256,
            delivery_package_code=package.package_code,
            delivery_package_completed_at_snapshot=package.completed_at,
            delivery_package_size_bytes=package.file_size_bytes,
            delivery_package_checksum_sha256=package.checksum_sha256,
            generated_by=operator.display_name,
            generated_by_code=operator.user_code,
            generated_by_role=operator.role_code,
            generation_comment=generation_comment,
            generated_at=generated_at,
        )

    @staticmethod
    def build_children(
        archive_id: int,
        result: OfflineArchiveWriteResult,
    ) -> tuple[list[OfflineArchiveVolume], list[OfflineArchiveSource]]:
        """构造分卷记录和每个成员的不可变来源快照。

        Args:
            archive_id: 离线封存主键。
            result: ZIP64 分卷实体写入结果。

        Returns:
            tuple[list[OfflineArchiveVolume], list[OfflineArchiveSource]]:
                分卷和来源记录。
        """
        volumes: list[OfflineArchiveVolume] = []
        sources: list[OfflineArchiveSource] = []
        for volume in result.volumes:
            volumes.append(
                OfflineArchiveVolume(
                    archive_id=archive_id,
                    sequence=volume.sequence,
                    filename=volume.filename,
                    file_uri=volume.file_uri,
                    file_size_bytes=volume.file_size_bytes,
                    checksum_sha256=volume.checksum_sha256,
                    member_count=len(volume.sources),
                    source_size_bytes=volume.source_size_bytes,
                    volume_manifest=volume.volume_manifest,
                )
            )
            for source in volume.sources:
                sources.append(
                    OfflineArchiveSource(
                        archive_id=archive_id,
                        sequence=source.sequence,
                        volume_sequence=volume.sequence,
                        source_kind=source.source_kind,
                        source_entity_id=source.source_entity_id,
                        source_entity_code=source.source_entity_code,
                        archive_path=source.archive_path,
                        original_filename=source.original_filename,
                        file_uri=source.file_uri,
                        file_size_bytes=source.file_size_bytes,
                        checksum_sha256=source.checksum_sha256,
                        media_type=source.media_type,
                        source_version=source.source_version,
                        security_classification=source.security_classification,
                        source_updated_at=source.source_updated_at,
                    )
                )
        return volumes, sources
