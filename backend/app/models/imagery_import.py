"""影像原子批量入库批次与成员模型。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.plot import Base


class ImageryImportBatch(Base):
    """保存一次原子影像批量入库的清单摘要与稳定用户审计。"""

    __tablename__ = "imagery_import_batches"
    __table_args__ = (
        CheckConstraint(
            "item_count BETWEEN 1 AND 20 "
            "AND total_size_bytes > 0 "
            "AND char_length(manifest_sha256) = 64 "
            "AND char_length(trim(import_comment)) >= 10",
            name="ck_imagery_import_batch_values",
        ),
        Index(
            "idx_imagery_import_batches_project_created",
            "project_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    batch_code: Mapped[str] = mapped_column(String(90), unique=True, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_by: Mapped[str] = mapped_column(String(100), nullable=False)
    imported_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    imported_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    import_comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ImageryImportBatchItem(Base):
    """保存批次中每个影像实体、顺序、大小和 SHA-256。"""

    __tablename__ = "imagery_import_batch_items"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "sequence",
            name="uq_imagery_import_batch_item_sequence",
        ),
        UniqueConstraint(
            "batch_id",
            "asset_id",
            name="uq_imagery_import_batch_item_asset",
        ),
        CheckConstraint(
            "sequence BETWEEN 1 AND 20 "
            "AND file_size_bytes > 0 "
            "AND char_length(checksum_sha256) = 64",
            name="ck_imagery_import_batch_item_values",
        ),
        Index(
            "idx_imagery_import_batch_items_batch",
            "batch_id",
            "sequence",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_import_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
