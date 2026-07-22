"""受控地图与数据共享服务、申请、凭证、健康和审计模型。"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
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


class SharedService(Base):
    """项目登记并经过审批的地图或数据服务。"""

    __tablename__ = "shared_services"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "service_code",
            name="uq_shared_service_project_code",
        ),
        CheckConstraint(
            "service_type IN ('stac', 'wms', 'wmts', 'wfs', 'rest', 'download')",
            name="ck_shared_service_type",
        ),
        CheckConstraint(
            "resource_type IN ('external_api', 'imagery', 'vector', "
            "'thematic_map', 'delivery', 'statistics', 'other')",
            name="ck_shared_service_resource_type",
        ),
        CheckConstraint(
            "data_classification IN ('public', 'internal', 'confidential')",
            name="ck_shared_service_classification",
        ),
        CheckConstraint(
            "exposure_scope IN ('public', 'project', 'restricted')",
            name="ck_shared_service_scope",
        ),
        CheckConstraint(
            "auth_mode IN ('none', 'api_key', 'oauth2', 'network_whitelist')",
            name="ck_shared_service_auth_mode",
        ),
        CheckConstraint(
            "status IN ('pending_approval', 'active', 'rejected', "
            "'suspended', 'revoked')",
            name="ck_shared_service_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    service_code: Mapped[str] = mapped_column(String(80), nullable=False)
    service_name: Mapped[str] = mapped_column(String(200), nullable=False)
    service_type: Mapped[str] = mapped_column(String(30), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    health_check_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    documentation_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_code: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    data_classification: Mapped[str] = mapped_column(String(30), nullable=False)
    exposure_scope: Mapped[str] = mapped_column(String(30), nullable=False)
    auth_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    owner_department: Mapped[str] = mapped_column(String(150), nullable=False)
    registered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    registered_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    registered_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revoked_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    revoked_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
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


class ServiceAccessRequest(Base):
    """项目成员对已激活共享服务提出的访问申请。"""

    __tablename__ = "service_access_requests"
    __table_args__ = (
        UniqueConstraint("request_code", name="uq_service_access_request_code"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'revoked', 'expired')",
            name="ck_service_access_request_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("shared_services.id", ondelete="CASCADE"),
        nullable=False,
    )
    request_code: Mapped[str] = mapped_column(String(100), nullable=False)
    applicant_organization: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    requested_until: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    applicant: Mapped[str] = mapped_column(String(100), nullable=False)
    applicant_code: Mapped[str] = mapped_column(String(50), nullable=False)
    applicant_role: Mapped[str] = mapped_column(String(40), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decided_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    decided_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ServiceCredential(Base):
    """仅保存哈希和末四位的服务访问凭证。"""

    __tablename__ = "service_credentials"
    __table_args__ = (
        UniqueConstraint("credential_code", name="uq_service_credential_code"),
        UniqueConstraint(
            "access_request_id",
            name="uq_service_credential_access_request",
        ),
        CheckConstraint(
            "status IN ('active', 'revoked', 'expired')",
            name="ck_service_credential_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("shared_services.id", ondelete="CASCADE"),
        nullable=False,
    )
    access_request_id: Mapped[int] = mapped_column(
        ForeignKey("service_access_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    credential_code: Mapped[str] = mapped_column(String(100), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    secret_last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    issued_by: Mapped[str] = mapped_column(String(100), nullable=False)
    issued_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    issued_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revoked_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    revoked_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ServiceHealthCheck(Base):
    """共享服务每次真实探测的不可覆盖健康证据。"""

    __tablename__ = "service_health_checks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('healthy', 'degraded', 'unavailable')",
            name="ck_service_health_check_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("shared_services.id", ondelete="CASCADE"),
        nullable=False,
    )
    checked_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    checked_by: Mapped[str] = mapped_column(String(100), nullable=False)
    checked_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    checked_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class ServiceUsageEvent(Base):
    """服务注册、审批、凭证、调用和撤销的不可变审计事件。"""

    __tablename__ = "service_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("shared_services.id", ondelete="CASCADE"),
        nullable=False,
    )
    access_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_access_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    credential_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_credentials.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    request_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    request_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_code: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
