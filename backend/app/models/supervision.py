"""独立项目监理计划、检查、整改复检、县区评价与报告模型。"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
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


class SupervisionPlan(Base):
    """独立监理抽样计划及任务数据快照。"""

    __tablename__ = "supervision_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    plan_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sampling_method: Mapped[str] = mapped_column(String(30), nullable=False)
    sample_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    minimum_per_region: Mapped[int] = mapped_column(Integer, nullable=False)
    region_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    task_plot_count_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    task_updated_at_snapshot: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    planned_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
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


class SupervisionSample(Base):
    """从任务真实图斑中确定性抽取的监理样本。"""

    __tablename__ = "supervision_samples"
    __table_args__ = (
        UniqueConstraint("plan_id", "plot_code", name="uq_supervision_sample_plot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("supervision_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    plot_code: Mapped[str] = mapped_column(
        ForeignKey("farmland_plots.plot_code", ondelete="RESTRICT"),
        nullable=False,
    )
    region_code: Mapped[str] = mapped_column(String(50), nullable=False)
    region_name: Mapped[str] = mapped_column(String(100), nullable=False)
    plot_version_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    selection_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SupervisionInspection(Base):
    """独立监理对生产环节执行的过程检查。"""

    __tablename__ = "supervision_inspections"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "inspection_code",
            name="uq_supervision_inspection_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("supervision_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    inspection_code: Mapped[str] = mapped_column(String(80), nullable=False)
    inspection_stage: Mapped[str] = mapped_column(String(40), nullable=False)
    inspected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    conclusion: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    inspector: Mapped[str] = mapped_column(String(100), nullable=False)
    inspector_code: Mapped[str] = mapped_column(String(50), nullable=False)
    inspector_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SupervisionFinding(Base):
    """监理检查发现的问题、整改证据和当前闭环状态。"""

    __tablename__ = "supervision_findings"
    __table_args__ = (
        UniqueConstraint(
            "inspection_id",
            "finding_code",
            name="uq_supervision_finding_code",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_id: Mapped[int] = mapped_column(
        ForeignKey("supervision_inspections.id", ondelete="CASCADE"),
        nullable=False,
    )
    sample_id: Mapped[int | None] = mapped_column(
        ForeignKey("supervision_samples.id", ondelete="SET NULL"),
        nullable=True,
    )
    finding_code: Mapped[str] = mapped_column(String(80), nullable=False)
    region_code: Mapped[str] = mapped_column(String(50), nullable=False)
    region_name: Mapped[str] = mapped_column(String(100), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    rework_deadline: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="open")
    rectification_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    rectification_evidence_uri: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    rectified_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rectified_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rectified_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rectified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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


class SupervisionReinspection(Base):
    """监理问题逐轮复检的不可覆盖记录。"""

    __tablename__ = "supervision_reinspections"
    __table_args__ = (
        UniqueConstraint(
            "finding_id",
            "round_no",
            name="uq_supervision_reinspection_round",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(
        ForeignKey("supervision_findings.id", ondelete="CASCADE"),
        nullable=False,
    )
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    inspector: Mapped[str] = mapped_column(String(100), nullable=False)
    inspector_code: Mapped[str] = mapped_column(String(50), nullable=False)
    inspector_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SupervisionCountyEvaluation(Base):
    """按县区保存独立监理量化评价。"""

    __tablename__ = "supervision_county_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "region_code",
            name="uq_supervision_county_evaluation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("supervision_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    region_code: Mapped[str] = mapped_column(String(50), nullable=False)
    region_name: Mapped[str] = mapped_column(String(100), nullable=False)
    quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    timeliness_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    compliance_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    grade: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    evaluated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    evaluated_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    evaluated_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class SupervisionReport(Base):
    """从完整监理证据生成的不可变实体 JSON 报告。"""

    __tablename__ = "supervision_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("supervision_plans.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    report_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    file_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class SupervisionEvent(Base):
    """独立监理全流程不可变操作事件。"""

    __tablename__ = "supervision_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("supervision_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_code: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
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
