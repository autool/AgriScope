"""多光谱与全色影像融合任务、质量验收和审计模型。"""

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


class ImageryFusionJob(Base):
    """保存全色融合输入、算法参数、质量指标和物理成果。"""

    __tablename__ = "imagery_fusion_jobs"
    __table_args__ = (
        UniqueConstraint("project_id", "job_code", name="uq_imagery_fusion_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"), nullable=False
    )
    job_code: Mapped[str] = mapped_column(String(80), nullable=False)
    job_name: Mapped[str] = mapped_column(String(200), nullable=False)
    multispectral_asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="RESTRICT"), nullable=False
    )
    multispectral_asset_code: Mapped[str] = mapped_column(String(80), nullable=False)
    multispectral_asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    panchromatic_asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="RESTRICT"), nullable=False
    )
    panchromatic_asset_code: Mapped[str] = mapped_column(String(80), nullable=False)
    panchromatic_asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    multispectral_band_indexes: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    panchromatic_band_index: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm_code: Mapped[str] = mapped_column(String(50), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    resampling_method: Mapped[str] = mapped_column(String(20), nullable=False)
    overlap_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    spectral_correlations: Mapped[list] = mapped_column(JSON, nullable=False)
    minimum_spectral_correlation: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False
    )
    mean_spectral_correlation: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False
    )
    spatial_detail_gain: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False
    )
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
    output_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bounds_wgs84: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ImageryFusionEvent(Base):
    """保存融合任务创建与下载的不可变审计事件。"""

    __tablename__ = "imagery_fusion_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_fusion_jobs.id", ondelete="CASCADE"), nullable=False
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
