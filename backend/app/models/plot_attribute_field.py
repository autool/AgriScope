"""项目级地块自定义属性字段及审计模型。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.plot import Base


class ProjectPlotAttributeField(Base):
    """项目级地块自定义属性字段定义。"""

    __tablename__ = "project_plot_attribute_fields"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "field_code",
            name="uq_project_plot_attribute_field_code",
        ),
        CheckConstraint(
            "field_type IN ('text', 'number', 'date', 'boolean', 'single_select')",
            name="ck_project_plot_attribute_field_type",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_project_plot_attribute_field_status",
        ),
        CheckConstraint(
            "display_order BETWEEN 0 AND 9999",
            name="ck_project_plot_attribute_field_order",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_project_plot_attribute_field_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_code: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    updated_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
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


class ProjectPlotAttributeFieldAudit(Base):
    """项目级地块自定义属性字段变更审计。"""

    __tablename__ = "project_plot_attribute_field_audits"
    __table_args__ = (
        CheckConstraint(
            "action IN ('created', 'updated')",
            name="ck_project_plot_attribute_field_audit_action",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_id: Mapped[int] = mapped_column(
        ForeignKey("project_plot_attribute_fields.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    new_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    operator_code: Mapped[str] = mapped_column(String(50), nullable=False)
    operator_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
