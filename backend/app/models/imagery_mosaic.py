"""多景影像匀色、镶嵌、覆盖率验收和实体成果模型。"""

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


class ImageryMosaicJob(Base):
    """保存多景影像镶嵌参数、覆盖验收和物理成果证据。"""

    __tablename__ = "imagery_mosaic_jobs"
    __table_args__ = (
        UniqueConstraint("project_id", "job_code", name="uq_imagery_mosaic_job"),
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
    boundary_code: Mapped[str] = mapped_column(String(50), nullable=False)
    boundary_name: Mapped[str] = mapped_column(String(100), nullable=False)
    target_crs: Mapped[str] = mapped_column(String(100), nullable=False)
    target_resolution: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False)
    color_balance_method: Mapped[str] = mapped_column(String(30), nullable=False)
    blend_method: Mapped[str] = mapped_column(String(20), nullable=False)
    resampling_method: Mapped[str] = mapped_column(String(20), nullable=False)
    coverage_threshold: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    coverage_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    boundary_pixel_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    covered_pixel_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False)
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


class ImageryMosaicInput(Base):
    """保存镶嵌任务显式输入及不可变步骤产物血缘。"""

    __tablename__ = "imagery_mosaic_inputs"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "asset_id", "step_code", name="uq_imagery_mosaic_input"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_mosaic_jobs.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="RESTRICT"), nullable=False
    )
    asset_code: Mapped[str] = mapped_column(String(80), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    step_code: Mapped[str] = mapped_column(String(50), nullable=False)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_crs: Mapped[str] = mapped_column(String(100), nullable=False)
    source_width: Mapped[int] = mapped_column(Integer, nullable=False)
    source_height: Mapped[int] = mapped_column(Integer, nullable=False)
    source_band_count: Mapped[int] = mapped_column(Integer, nullable=False)
    band_descriptions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    balance_statistics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ImageryMosaicEvent(Base):
    """保存镶嵌任务创建与下载的不可变审计事件。"""

    __tablename__ = "imagery_mosaic_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_mosaic_jobs.id", ondelete="CASCADE"), nullable=False
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
