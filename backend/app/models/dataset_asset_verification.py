"""多源数据资产实体核验尝试模型。"""

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.plot import Base


class DatasetAssetVerification(Base):
    """保存多源数据资产每次实体核验的不可变证据。"""

    __tablename__ = "dataset_asset_verifications"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('verified', 'rejected')",
            name="ck_dataset_asset_verification_status",
        ),
        CheckConstraint(
            "file_size_bytes > 0 "
            "AND char_length(expected_checksum_sha256) = 64 "
            "AND char_length(computed_checksum_sha256) = 64",
            name="ck_dataset_asset_verification_file",
        ),
        CheckConstraint(
            "(verification_status = 'verified' AND file_uri IS NOT NULL) "
            "OR (verification_status = 'rejected' AND file_uri IS NULL)",
            name="ck_dataset_asset_verification_publication",
        ),
        Index(
            "idx_dataset_asset_verifications_asset_created",
            "asset_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    verification_code: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False,
    )
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    computed_checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    inspection_metadata: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    verification_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    operator_code: Mapped[str] = mapped_column(String(50), nullable=False)
    operator_role: Mapped[str] = mapped_column(String(40), nullable=False)
    verification_comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
