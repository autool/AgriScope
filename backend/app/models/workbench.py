"""遥感监测项目、任务、影像、质量问题和审核记录模型。"""

from datetime import date, datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
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


class MonitoringProject(Base):
    """遥感监测项目。"""

    __tablename__ = "monitoring_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    province: Mapped[str] = mapped_column(String(100), nullable=False)
    monitor_year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    progress: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ProjectUser(Base):
    """项目成员及其业务角色。"""

    __tablename__ = "project_users"
    __table_args__ = (
        UniqueConstraint("project_id", "user_code", name="uq_project_user_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_code: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_code: Mapped[str] = mapped_column(String(40), nullable=False)
    role_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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


class ProjectRuleConfig(Base):
    """项目级质量与内外业校核规则配置。"""

    __tablename__ = "project_rule_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    field_offset_threshold_m: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
        default=5,
    )
    field_search_radius_m: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=1000,
    )
    positional_accuracy_pixels: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
        default=2,
    )
    max_capture_image_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=15,
    )
    construction_min_area_sqm: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=200,
    )
    other_agricultural_min_area_sqm: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=400,
    )
    completeness_rate_min: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=98,
    )
    boundary_agreement_rate_min: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=90,
    )
    land_class_accuracy_min: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=90,
    )
    key_field_accuracy_min: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=95,
    )
    max_cloud_cover_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )
    output_crs: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="EPSG:4490",
    )
    output_projection: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="CGCS2000 高斯-克吕格（按成果分幅配置中央经线）",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ProjectRuleConfigAudit(Base):
    """项目规则配置修改审计。"""

    __tablename__ = "project_rule_config_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    operator_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    operator_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    previous_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    new_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

class MonitoringTask(Base):
    """遥感监测作业任务。"""

    __tablename__ = "monitoring_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    administrative_region: Mapped[str] = mapped_column(String(150), nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    total_plots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_plots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class TaskPlot(Base):
    """作业任务与纳入质检范围图斑的关联。"""

    __tablename__ = "task_plots"
    __table_args__ = (
        UniqueConstraint("task_id", "plot_code", name="uq_task_plot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    plot_code: Mapped[str] = mapped_column(
        ForeignKey("farmland_plots.plot_code", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_by: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ImageryAsset(Base):
    """遥感影像资产元数据。"""

    __tablename__ = "imagery_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(80), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    cloud_cover: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    resolution_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    processing_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    data_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="operational",
    )
    calibration_status: Mapped[str] = mapped_column(String(30), nullable=False)
    correction_status: Mapped[str] = mapped_column(String(30), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_format: Mapped[str | None] = mapped_column(String(30), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    band_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raster_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raster_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crs: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raster_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    imported_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    spatial_extent: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class QualityIssue(Base):
    """自动或人工发现的数据质量问题。"""

    __tablename__ = "quality_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    plot_code: Mapped[str | None] = mapped_column(
        ForeignKey("farmland_plots.plot_code", ondelete="CASCADE"),
        nullable=True,
    )
    rule_code: Mapped[str] = mapped_column(String(60), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolved_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolution_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class PlotQualityCheck(Base):
    """图斑指定版本的最近一次自动质量检查结果。"""

    __tablename__ = "plot_quality_checks"
    __table_args__ = (
        UniqueConstraint("task_id", "plot_code", name="uq_plot_quality_check"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    plot_code: Mapped[str] = mapped_column(
        ForeignKey("farmland_plots.plot_code", ondelete="CASCADE"),
        nullable=False,
    )
    plot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    can_submit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rules: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ReviewRecord(Base):
    """任务审核与整改操作记录。"""

    __tablename__ = "review_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_level: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(100), nullable=False)
    reviewer_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewer_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class FieldVerification(Base):
    """外业人员采集的现场核查记录。"""

    __tablename__ = "field_verifications"
    __table_args__ = (
        CheckConstraint(
            "source_file_size_bytes IS NULL OR source_file_size_bytes > 0",
            name="ck_field_verification_source_file_size",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    verification_code: Mapped[str] = mapped_column(
        String(60),
        unique=True,
        nullable=False,
    )
    investigator: Mapped[str] = mapped_column(String(100), nullable=False)
    investigator_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=False,
    )
    observed_land_class: Mapped[str | None] = mapped_column(String(50), nullable=True)
    observed_crop_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    photo_urls: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    voice_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    source_file_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    import_batch_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    imported_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    imported_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    imported_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    matched_plot_code: Mapped[str | None] = mapped_column(
        ForeignKey("farmland_plots.plot_code"),
        nullable=True,
    )
    offset_distance_m: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    match_status: Mapped[str] = mapped_column(String(30), nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(30), nullable=False)
    resolution_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    resolution_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolved_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class FieldVerificationArtifact(Base):
    """外业核查照片、语音和调查表受控实体。"""

    __tablename__ = "field_verification_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "field_verification_id",
            "checksum_sha256",
            name="uq_field_verification_artifact_checksum",
        ),
        CheckConstraint(
            "artifact_type IN ('photo', 'voice', 'form')",
            name="ck_field_verification_artifact_type",
        ),
        CheckConstraint(
            "file_size_bytes > 0",
            name="ck_field_verification_artifact_size",
        ),
        CheckConstraint(
            "length(checksum_sha256) = 64",
            name="ck_field_verification_artifact_checksum_length",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_verification_id: Mapped[int] = mapped_column(
        ForeignKey("field_verifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_code: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(String(20), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(100), nullable=False)
    uploaded_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    uploaded_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class FieldVerificationArtifactEvent(Base):
    """外业实体证据上传与下载的不可变审计事件。"""

    __tablename__ = "field_verification_artifact_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('uploaded', 'downloaded')",
            name="ck_field_verification_artifact_event_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_verification_id: Mapped[int] = mapped_column(
        ForeignKey("field_verifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("field_verification_artifacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_code: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PlotVersion(Base):
    """解译图斑属性和几何历史版本。"""

    __tablename__ = "plot_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plot_code: Mapped[str] = mapped_column(
        ForeignKey("farmland_plots.plot_code", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    land_class: Mapped[str | None] = mapped_column(String(50), nullable=True)
    crop_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    planting_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    irrigation_condition: Mapped[str | None] = mapped_column(String(20), nullable=True)
    interpretation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )
    change_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PlotEditOperation(Base):
    """地块分割、合并和恢复操作的不可变业务审计。"""

    __tablename__ = "plot_edit_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_code: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False,
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_plot_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    result_plot_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    applied_versions: Mapped[dict[str, int]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    reverted_versions: Mapped[dict[str, int]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="applied",
    )
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    operator_code: Mapped[str] = mapped_column(String(50), nullable=False)
    operator_role: Mapped[str] = mapped_column(String(40), nullable=False)
    comment: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    reverted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class PlotEditOperationEvent(Base):
    """地块编辑操作每次撤销、重做或失效的不可变事件。"""

    __tablename__ = "plot_edit_operation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    operation_id: Mapped[int] = mapped_column(
        ForeignKey("plot_edit_operations.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    operator_code: Mapped[str] = mapped_column(String(50), nullable=False)
    operator_role: Mapped[str] = mapped_column(String(40), nullable=False)
    comment: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AreaStatisticsImportBatch(Base):
    """历史年度面积统计导入批次及不可变来源证据。"""

    __tablename__ = "area_statistics_import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    batch_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    conflict_strategy: Mapped[str] = mapped_column(String(20), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_payload: Mapped[list[dict]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    imported_by: Mapped[str] = mapped_column(String(100), nullable=False)
    imported_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    imported_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    import_comment: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AreaStatisticsSnapshot(Base):
    """项目年度种植面积统计快照。"""

    __tablename__ = "area_statistics_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    monitor_year: Mapped[int] = mapped_column(Integer, nullable=False)
    total_area_ha: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    farmland_area_ha: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    crop_area_ha: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("area_statistics_import_batches.id", ondelete="SET NULL"),
        nullable=True,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class DisasterPatch(Base):
    """遥感识别的农业灾害斑块。"""

    __tablename__ = "disaster_patches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    patch_code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    disaster_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    affected_area_ha: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    crop_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detected_at: Mapped[date] = mapped_column(Date, nullable=False)
    ndvi_change: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_feature_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    source_checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    import_batch_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    imported_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    imported_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    imported_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reviewed_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ImageryProcessingStep(Base):
    """遥感影像预处理流水线步骤。"""

    __tablename__ = "imagery_processing_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_code: Mapped[str] = mapped_column(String(50), nullable=False)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class DeliveryPackage(Base):
    """审核通过后生成的成果交付包。"""

    __tablename__ = "delivery_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    package_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    package_name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_by_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    generated_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    file_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manifest: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    quality_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class AdministrativeBoundary(Base):
    """项目监测范围内的行政区划边界。"""

    __tablename__ = "administrative_boundaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    boundary_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    boundary_name: Mapped[str] = mapped_column(String(100), nullable=False)
    boundary_level: Mapped[str] = mapped_column(String(20), nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_updated_at: Mapped[date | None] = mapped_column(Date, nullable=True)
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


class DatasetAsset(Base):
    """多源生产数据资产及其可追溯元数据。"""

    __tablename__ = "dataset_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    asset_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    source_version: Mapped[str] = mapped_column(String(80), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    crs: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extent: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    time_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    time_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    security_classification: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    data_status: Mapped[str] = mapped_column(String(20), nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )
    metadata_payload: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
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


class DatasetLineage(Base):
    """多源数据资产之间的显式派生血缘。"""

    __tablename__ = "dataset_lineages"
    __table_args__ = (
        UniqueConstraint(
            "parent_asset_id",
            "derived_asset_id",
            "relation_type",
            name="uq_dataset_lineage_relation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_asset_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    derived_asset_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    process_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ProductionBatch(Base):
    """影像到达或生产计划触发的遥感生产批次。"""

    __tablename__ = "production_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    batch_code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    batch_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_assets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    target_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_assets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    rule_config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_profile_snapshot: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    planned_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
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


class WorkPackage(Base):
    """生产批次按行政区拆分的可审计作业包。"""

    __tablename__ = "work_packages"
    __table_args__ = (
        UniqueConstraint("batch_id", "region_code", name="uq_work_package_region"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("production_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    package_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    package_name: Mapped[str] = mapped_column(String(200), nullable=False)
    region_code: Mapped[str] = mapped_column(String(50), nullable=False)
    region_name: Mapped[str] = mapped_column(String(100), nullable=False)
    region_level: Mapped[str] = mapped_column(String(20), nullable=False)
    planned_area_ha: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    planned_plot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    assignee_code: Mapped[str] = mapped_column(String(50), nullable=False)
    assignee_name: Mapped[str] = mapped_column(String(100), nullable=False)
    deadline: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
    )
    reconciliation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
    )
    delivery_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
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


class WorkPackagePlot(Base):
    """作业包与任务图斑的显式生产范围关联。"""

    __tablename__ = "work_package_plots"
    __table_args__ = (
        UniqueConstraint("work_package_id", "plot_code", name="uq_work_package_plot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_package_id: Mapped[int] = mapped_column(
        ForeignKey("work_packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    plot_code: Mapped[str] = mapped_column(
        ForeignKey("farmland_plots.plot_code", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ProductionAuditEvent(Base):
    """生产调度与数据目录的不可变业务操作审计。"""

    __tablename__ = "production_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_code: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
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
