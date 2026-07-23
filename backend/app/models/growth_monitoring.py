"""多时相 NDVI 长势监测任务、异常区和审计模型。"""

from datetime import datetime
from decimal import Decimal

from geoalchemy2 import Geometry
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


class GrowthMonitoringRun(Base):
    """保存两期 NDVI 来源、分级参数、质量门禁和物理成果。"""

    __tablename__ = "growth_monitoring_runs"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "run_code",
            name="uq_growth_monitoring_run",
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
    run_code: Mapped[str] = mapped_column(String(80), nullable=False)
    run_name: Mapped[str] = mapped_column(String(200), nullable=False)
    baseline_asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    baseline_asset_code: Mapped[str] = mapped_column(String(80), nullable=False)
    baseline_asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    baseline_acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    baseline_step_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_processing_steps.id", ondelete="RESTRICT"),
        nullable=False,
    )
    baseline_source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    baseline_source_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    baseline_source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    current_asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    current_asset_code: Mapped[str] = mapped_column(String(80), nullable=False)
    current_asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    current_acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    current_step_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_processing_steps.id", ondelete="RESTRICT"),
        nullable=False,
    )
    current_source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    current_source_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    current_source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    poor_delta_threshold: Mapped[Decimal] = mapped_column(
        Numeric(7, 4),
        nullable=False,
    )
    good_delta_threshold: Mapped[Decimal] = mapped_column(
        Numeric(7, 4),
        nullable=False,
    )
    minimum_zone_area_ha: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        nullable=False,
    )
    minimum_spatial_coverage_ratio: Mapped[Decimal] = mapped_column(
        Numeric(8, 6),
        nullable=False,
    )
    minimum_valid_pixel_ratio: Mapped[Decimal] = mapped_column(
        Numeric(8, 6),
        nullable=False,
    )
    algorithm_code: Mapped[str] = mapped_column(String(80), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    task_plot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    task_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    output_crs: Mapped[str] = mapped_column(String(100), nullable=False)
    output_resolution_x: Mapped[Decimal] = mapped_column(
        Numeric(16, 8),
        nullable=False,
    )
    output_resolution_y: Mapped[Decimal] = mapped_column(
        Numeric(16, 8),
        nullable=False,
    )
    raster_width: Mapped[int] = mapped_column(Integer, nullable=False)
    raster_height: Mapped[int] = mapped_column(Integer, nullable=False)
    bounds_wgs84: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    task_farmland_area_ha: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
    )
    common_footprint_farmland_area_ha: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
    )
    spatial_coverage_ratio: Mapped[Decimal] = mapped_column(
        Numeric(8, 6),
        nullable=False,
    )
    common_footprint_mask_pixel_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    valid_pixel_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    valid_pixel_ratio: Mapped[Decimal] = mapped_column(
        Numeric(8, 6),
        nullable=False,
    )
    poor_pixel_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    normal_pixel_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    good_pixel_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    anomaly_zone_count: Mapped[int] = mapped_column(Integer, nullable=False)
    anomaly_area_ha: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    classification_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    classification_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    classification_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    classification_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    anomaly_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    anomaly_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    anomaly_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    anomaly_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class GrowthMonitoringZone(Base):
    """保存长势转差连通区及服务端重算面积和 NDVI 统计。"""

    __tablename__ = "growth_monitoring_zones"
    __table_args__ = (
        UniqueConstraint("run_id", "zone_code", name="uq_growth_monitoring_zone"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("growth_monitoring_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    zone_code: Mapped[str] = mapped_column(String(100), nullable=False)
    area_ha: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    baseline_ndvi_mean: Mapped[Decimal] = mapped_column(
        Numeric(8, 5),
        nullable=False,
    )
    current_ndvi_mean: Mapped[Decimal] = mapped_column(
        Numeric(8, 5),
        nullable=False,
    )
    ndvi_delta_mean: Mapped[Decimal] = mapped_column(
        Numeric(8, 5),
        nullable=False,
    )
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class GrowthMonitoringEvent(Base):
    """保存长势监测生成和下载的不可变用户审计。"""

    __tablename__ = "growth_monitoring_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("growth_monitoring_runs.id", ondelete="CASCADE"),
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
