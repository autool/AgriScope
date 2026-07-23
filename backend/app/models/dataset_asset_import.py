"""多源数据资产原子批量入库批次与成员模型。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
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


class DatasetAssetImportBatch(Base):
    """保存一次多源实体原子批量入库的规范化清单摘要。"""

    __tablename__ = "dataset_asset_import_batches"
    __table_args__ = (
        CheckConstraint(
            "item_count BETWEEN 1 AND 20 "
            "AND total_size_bytes > 0 "
            "AND char_length(manifest_sha256) = 64 "
            "AND char_length(trim(import_comment)) >= 10",
            name="ck_dataset_asset_import_batch_values",
        ),
        Index(
            "idx_dataset_asset_import_batches_project_created",
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
    manifest_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    imported_by: Mapped[str] = mapped_column(String(100), nullable=False)
    imported_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    imported_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    import_comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class DatasetAssetImportBatchItem(Base):
    """保存批次成员顺序、实体证据和对应核验记录。"""

    __tablename__ = "dataset_asset_import_batch_items"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "sequence",
            name="uq_dataset_asset_import_batch_item_sequence",
        ),
        UniqueConstraint(
            "batch_id",
            "asset_id",
            name="uq_dataset_asset_import_batch_item_asset",
        ),
        UniqueConstraint(
            "batch_id",
            "verification_id",
            name="uq_dataset_asset_import_batch_item_verification",
        ),
        CheckConstraint(
            "sequence BETWEEN 1 AND 20 "
            "AND file_size_bytes > 0 "
            "AND char_length(checksum_sha256) = 64",
            name="ck_dataset_asset_import_batch_item_values",
        ),
        Index(
            "idx_dataset_asset_import_batch_items_batch",
            "batch_id",
            "sequence",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_asset_import_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    verification_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_asset_verifications.id", ondelete="RESTRICT"),
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
