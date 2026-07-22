"""双景影像自动配准、残差验收和实体成果模型。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.plot import Base


class ImageryRegistrationJob(Base):
    """保存参考景、待配准景、自动位移、残差和物理成果证据。"""

    __tablename__ = "imagery_registration_jobs"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "job_code",
            name="uq_imagery_registration_job",
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
    job_code: Mapped[str] = mapped_column(String(80), nullable=False)
    job_name: Mapped[str] = mapped_column(String(200), nullable=False)
    reference_asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    moving_asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reference_asset_code: Mapped[str] = mapped_column(String(80), nullable=False)
    moving_asset_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_step_code: Mapped[str] = mapped_column(String(50), nullable=False)
    moving_step_code: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    reference_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    moving_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    moving_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    moving_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_band_index: Mapped[int] = mapped_column(Integer, nullable=False)
    moving_band_index: Mapped[int] = mapped_column(Integer, nullable=False)
    resampling_method: Mapped[str] = mapped_column(String(20), nullable=False)
    initial_shift_x_pixels: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False
    )
    initial_shift_y_pixels: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False
    )
    initial_offset_pixels: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False
    )
    residual_shift_x_pixels: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False
    )
    residual_shift_y_pixels: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False
    )
    residual_offset_pixels: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False
    )
    overlap_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 5), nullable=False)
    peak_to_sidelobe_ratio: Mapped[Decimal] = mapped_column(
        Numeric(12, 5), nullable=False
    )
    residual_threshold_pixels: Mapped[Decimal] = mapped_column(
        Numeric(8, 3), nullable=False
    )
    output_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_crs: Mapped[str] = mapped_column(String(100), nullable=False)
    output_resolution_x: Mapped[Decimal] = mapped_column(
        Numeric(16, 8), nullable=False
    )
    output_resolution_y: Mapped[Decimal] = mapped_column(
        Numeric(16, 8), nullable=False
    )
    raster_width: Mapped[int] = mapped_column(Integer, nullable=False)
    raster_height: Mapped[int] = mapped_column(Integer, nullable=False)
    band_count: Mapped[int] = mapped_column(Integer, nullable=False)
    dtype: Mapped[str] = mapped_column(String(30), nullable=False)
    bounds_wgs84: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ImageryRegistrationEvent(Base):
    """保存配准创建和成果下载的不可变审计事件。"""

    __tablename__ = "imagery_registration_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_registration_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_code: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
