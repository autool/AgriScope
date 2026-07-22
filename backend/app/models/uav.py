"""无人机航空器、飞行任务、实体成果、疑点和审计模型。"""

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


class UavAircraft(Base):
    """保存航空器、挂载传感器和注册证书实体证据。"""

    __tablename__ = "uav_aircraft"
    __table_args__ = (
        UniqueConstraint("project_id", "aircraft_code", name="uq_uav_aircraft_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    aircraft_code: Mapped[str] = mapped_column(String(80), nullable=False)
    aircraft_name: Mapped[str] = mapped_column(String(200), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(150), nullable=False)
    model_number: Mapped[str] = mapped_column(String(100), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(120), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(120), nullable=False)
    sensor_name: Mapped[str] = mapped_column(String(150), nullable=False)
    sensor_model: Mapped[str] = mapped_column(String(120), nullable=False)
    sensor_serial_number: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_department: Mapped[str] = mapped_column(String(200), nullable=False)
    certificate_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    certificate_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    certificate_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    certificate_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    registered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    registered_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    registered_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UavMission(Base):
    """保存任务范围、飞手资质、飞行参数和受控状态。"""

    __tablename__ = "uav_missions"
    __table_args__ = (
        UniqueConstraint("project_id", "mission_code", name="uq_uav_mission_code"),
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
    aircraft_id: Mapped[int] = mapped_column(
        ForeignKey("uav_aircraft.id", ondelete="RESTRICT"),
        nullable=False,
    )
    mission_code: Mapped[str] = mapped_column(String(80), nullable=False)
    mission_name: Mapped[str] = mapped_column(String(200), nullable=False)
    district_code: Mapped[str] = mapped_column(String(50), nullable=False)
    district_name: Mapped[str] = mapped_column(String(100), nullable=False)
    flight_boundary: Mapped[object] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )
    planned_area_ha: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    pilot_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pilot_license_number: Mapped[str] = mapped_column(String(120), nullable=False)
    pilot_license_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    pilot_license_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    pilot_license_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pilot_license_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    planned_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    planned_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    actual_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    actual_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    altitude_m: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    expected_resolution_cm: Mapped[Decimal] = mapped_column(
        Numeric(8, 3),
        nullable=False,
    )
    forward_overlap_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )
    side_overlap_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )
    weather_note: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="planned")
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UavArtifact(Base):
    """保存无人机原始数据、航迹、影像、视频和正射实体成果。"""

    __tablename__ = "uav_artifacts"
    __table_args__ = (
        UniqueConstraint("mission_id", "artifact_code", name="uq_uav_artifact_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mission_id: Mapped[int] = mapped_column(
        ForeignKey("uav_missions.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_code: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    file_format: Mapped[str] = mapped_column(String(40), nullable=False)
    crs: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolution_cm: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
    )
    raster_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raster_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    footprint: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    verification_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="verified",
    )
    uploaded_by: Mapped[str] = mapped_column(String(100), nullable=False)
    uploaded_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    uploaded_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class UavFinding(Base):
    """保存无人机任务空间疑点、证据成果和人工复核结论。"""

    __tablename__ = "uav_findings"
    __table_args__ = (
        UniqueConstraint("mission_id", "finding_code", name="uq_uav_finding_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mission_id: Mapped[int] = mapped_column(
        ForeignKey("uav_missions.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_id: Mapped[int] = mapped_column(
        ForeignKey("uav_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    finding_code: Mapped[str] = mapped_column(String(80), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    plot_code: Mapped[str | None] = mapped_column(
        ForeignKey("farmland_plots.plot_code", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending_review",
    )
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UavEvent(Base):
    """保存无人机任务全部动作的不可变审计事件。"""

    __tablename__ = "uav_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    mission_id: Mapped[int | None] = mapped_column(
        ForeignKey("uav_missions.id", ondelete="CASCADE"),
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_code: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_code: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
