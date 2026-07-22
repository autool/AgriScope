"""多时相变化检测任务、候选图斑与不可变复核事件模型。"""

from datetime import datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
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


class ChangeDetectionRun(Base):
    """绑定两期真实影像、规则版本与任务数据快照的变化检测任务。"""

    __tablename__ = "change_detection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    run_name: Mapped[str] = mapped_column(String(200), nullable=False)
    baseline_asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_profile_snapshot: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    source_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    task_plot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    task_updated_at_snapshot: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    alignment_method: Mapped[str] = mapped_column(String(120), nullable=False)
    alignment_offset_pixels: Mapped[Decimal] = mapped_column(
        Numeric(8, 3),
        nullable=False,
    )
    alignment_overlap_ratio: Mapped[Decimal] = mapped_column(
        Numeric(7, 4),
        nullable=False,
    )
    alignment_evidence_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="active",
    )
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


class ChangeCandidate(Base):
    """外部模型或生产工具生成并等待人工判读的变化候选图斑。"""

    __tablename__ = "change_candidates"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "candidate_code",
            name="uq_change_candidate_code",
        ),
        UniqueConstraint(
            "run_id",
            "source_name",
            "source_feature_id",
            name="uq_change_candidate_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("change_detection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_code: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_feature_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    import_batch_code: Mapped[str] = mapped_column(String(100), nullable=False)
    change_class: Mapped[str] = mapped_column(String(60), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    area_ha: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    evidence_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    imported_by: Mapped[str] = mapped_column(String(100), nullable=False)
    imported_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    imported_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
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


class ChangeDetectionEvent(Base):
    """变化检测任务、导入批次与人工判读的不可变审计事件。"""

    __tablename__ = "change_detection_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("change_detection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("change_candidates.id", ondelete="CASCADE"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    previous_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    new_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    operator_code: Mapped[str] = mapped_column(String(50), nullable=False)
    operator_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
