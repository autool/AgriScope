"""田间监测站、设备遥测、故障和病虫害预警模型。"""

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


class MonitoringStation(Base):
    """保存真实田间监测站位置、来源和实体证据。"""

    __tablename__ = "monitoring_stations"
    __table_args__ = (
        UniqueConstraint("project_id", "station_code", name="uq_station_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    station_code: Mapped[str] = mapped_column(String(80), nullable=False)
    station_name: Mapped[str] = mapped_column(String(200), nullable=False)
    province_code: Mapped[str] = mapped_column(String(50), nullable=False)
    province_name: Mapped[str] = mapped_column(String(100), nullable=False)
    city_code: Mapped[str] = mapped_column(String(50), nullable=False)
    city_name: Mapped[str] = mapped_column(String(100), nullable=False)
    district_code: Mapped[str] = mapped_column(String(50), nullable=False)
    district_name: Mapped[str] = mapped_column(String(100), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    station_type: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_department: Mapped[str] = mapped_column(String(200), nullable=False)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
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


class MonitoringDevice(Base):
    """保存站点下设备身份、归属、状态和照片证据。"""

    __tablename__ = "monitoring_devices"
    __table_args__ = (
        UniqueConstraint("project_id", "device_code", name="uq_device_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    station_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_stations.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_code: Mapped[str] = mapped_column(String(80), nullable=False)
    device_name: Mapped[str] = mapped_column(String(200), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)
    vendor: Mapped[str] = mapped_column(String(150), nullable=False)
    model_number: Mapped[str] = mapped_column(String(100), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_department: Mapped[str] = mapped_column(String(200), nullable=False)
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    photo_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    photo_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    photo_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="offline")
    last_telemetry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
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


class DeviceTelemetry(Base):
    """保存设备幂等遥测、原始载荷和可选实体证据。"""

    __tablename__ = "device_telemetry"
    __table_args__ = (
        UniqueConstraint(
            "device_id",
            "idempotency_key",
            name="uq_device_telemetry_idempotency",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    metric_code: Mapped[str] = mapped_column(String(80), nullable=False)
    metric_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
    )
    metric_unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    evidence_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    ingested_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    ingested_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class DeviceFault(Base):
    """保存设备故障、处置证据和闭环身份。"""

    __tablename__ = "device_faults"
    __table_args__ = (
        UniqueConstraint("project_id", "fault_code", name="uq_device_fault_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    fault_code: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    reported_by: Mapped[str] = mapped_column(String(100), nullable=False)
    reported_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    reported_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    resolution_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_evidence_uri: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    resolution_evidence_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    resolution_evidence_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolved_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
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


class PestModelVersion(Base):
    """保存病虫害模型版本、实体文件和评估指标。"""

    __tablename__ = "pest_model_versions"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "model_code",
            "model_version",
            name="uq_pest_model_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_code: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    deployment_target: Mapped[str] = mapped_column(String(120), nullable=False)
    training_source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    evaluation_source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    artifact_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    accuracy: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    recall: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    f1_score: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    roc_auc: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    superseded_by_version: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    registered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    registered_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    registered_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PestAssessment(Base):
    """保存模型输入、预测依据、置信度和人工复核结论。"""

    __tablename__ = "pest_assessments"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "assessment_code",
            name="uq_pest_assessment_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitoring_devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("pest_model_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assessment_code: Mapped[str] = mapped_column(String(80), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    input_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    input_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    input_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    target_name: Mapped[str] = mapped_column(String(150), nullable=False)
    prediction_label: Mapped[str] = mapped_column(String(150), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    prediction_basis: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending_review",
    )
    submitted_by: Mapped[str] = mapped_column(String(100), nullable=False)
    submitted_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    submitted_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
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


class PestAlert(Base):
    """保存经人工复核后的病虫害告警及真实送达证据。"""

    __tablename__ = "pest_alerts"
    __table_args__ = (
        UniqueConstraint("project_id", "alert_code", name="uq_pest_alert_code"),
        UniqueConstraint("assessment_id", name="uq_pest_alert_assessment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("pest_assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    alert_code: Mapped[str] = mapped_column(String(80), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    channels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    delivery_receipt_uri: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    delivery_receipt_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    delivery_receipt_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    delivered_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivered_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivered_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
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


class MonitoringEvent(Base):
    """保存监测网络所有业务动作的不可变审计事件。"""

    __tablename__ = "monitoring_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
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
