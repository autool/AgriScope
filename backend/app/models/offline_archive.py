"""源栅格离线介质封存、分卷与不可变审计模型。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.plot import Base


class OfflineArchive(Base):
    """任务级源栅格离线封存版本。"""

    __tablename__ = "offline_archives"
    __table_args__ = (
        UniqueConstraint("archive_code", name="uq_offline_archive_code"),
        UniqueConstraint(
            "task_id",
            "version",
            name="uq_offline_archive_task_version",
        ),
        CheckConstraint(
            "status IN ('completed', 'superseded', 'invalid')",
            name="ck_offline_archive_status",
        ),
        CheckConstraint(
            "volume_capacity_bytes >= 67108864 "
            "AND volume_count > 0 AND source_count > 0 "
            "AND total_source_bytes > 0 AND total_archive_bytes > 0",
            name="ck_offline_archive_counts",
        ),
        CheckConstraint(
            "manifest_size_bytes > 0 "
            "AND char_length(source_snapshot_sha256) = 64 "
            "AND char_length(manifest_checksum_sha256) = 64 "
            "AND char_length(delivery_package_checksum_sha256) = 64",
            name="ck_offline_archive_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    delivery_package_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_packages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    archive_code: Mapped[str] = mapped_column(String(100), nullable=False)
    archive_name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    volume_capacity_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    volume_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_source_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_archive_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    manifest_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    manifest_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    manifest_checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    delivery_package_code: Mapped[str] = mapped_column(String(80), nullable=False)
    delivery_package_completed_at_snapshot: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    delivery_package_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    delivery_package_checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    generation_comment: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class OfflineArchiveVolume(Base):
    """离线封存中的单个独立 ZIP64 卷。"""

    __tablename__ = "offline_archive_volumes"
    __table_args__ = (
        UniqueConstraint(
            "archive_id",
            "sequence",
            name="uq_offline_archive_volume_sequence",
        ),
        UniqueConstraint(
            "archive_id",
            "filename",
            name="uq_offline_archive_volume_filename",
        ),
        CheckConstraint(
            "sequence > 0 AND member_count > 0 "
            "AND source_size_bytes > 0 AND file_size_bytes > 0 "
            "AND char_length(checksum_sha256) = 64",
            name="ck_offline_archive_volume_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archive_id: Mapped[int] = mapped_column(
        ForeignKey("offline_archives.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    file_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    volume_manifest: Mapped[dict] = mapped_column(JSON, nullable=False)


class OfflineArchiveSource(Base):
    """离线封存成员的受控实体和来源快照。"""

    __tablename__ = "offline_archive_sources"
    __table_args__ = (
        UniqueConstraint(
            "archive_id",
            "sequence",
            name="uq_offline_archive_source_sequence",
        ),
        UniqueConstraint(
            "archive_id",
            "archive_path",
            name="uq_offline_archive_source_path",
        ),
        CheckConstraint(
            "sequence > 0 AND volume_sequence > 0 AND file_size_bytes > 0 "
            "AND char_length(checksum_sha256) = 64",
            name="ck_offline_archive_source_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archive_id: Mapped[int] = mapped_column(
        ForeignKey("offline_archives.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    volume_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_entity_code: Mapped[str] = mapped_column(String(100), nullable=False)
    archive_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    security_classification: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class OfflineArchiveEvent(Base):
    """离线封存生成、替代和下载的不可变事件。"""

    __tablename__ = "offline_archive_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    archive_id: Mapped[int] = mapped_column(
        ForeignKey("offline_archives.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_code: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
