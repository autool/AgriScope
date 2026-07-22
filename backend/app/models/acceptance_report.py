"""成果验收正式报告持久化模型。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.plot import Base


class AcceptanceReport(Base):
    """绑定当前成果交付包的版本化 DOCX/PDF 验收报告。"""

    __tablename__ = "acceptance_reports"
    __table_args__ = (
        UniqueConstraint("report_code", name="uq_acceptance_report_code"),
        UniqueConstraint(
            "task_id",
            "version",
            name="uq_acceptance_report_task_version",
        ),
        CheckConstraint(
            "status IN ('completed', 'superseded', 'invalid')",
            name="ck_acceptance_report_status",
        ),
        CheckConstraint(
            "bundle_size_bytes > 0 AND docx_size_bytes > 0 " "AND pdf_size_bytes > 0",
            name="ck_acceptance_report_file_sizes",
        ),
        CheckConstraint(
            "char_length(bundle_checksum_sha256) = 64 "
            "AND char_length(docx_checksum_sha256) = 64 "
            "AND char_length(pdf_checksum_sha256) = 64 "
            "AND char_length(delivery_package_checksum_sha256) = 64 "
            "AND char_length(quality_summary_checksum_sha256) = 64",
            name="ck_acceptance_report_checksums",
        ),
        CheckConstraint(
            "task_plot_count >= 0 AND delivery_manifest_count >= 0",
            name="ck_acceptance_report_source_counts",
        ),
        Index(
            "ix_acceptance_reports_task_status_generated",
            "task_id",
            "status",
            "generated_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    delivery_package_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_packages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    report_code: Mapped[str] = mapped_column(String(110), nullable=False)
    report_title: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    bundle_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    bundle_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bundle_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    docx_filename: Mapped[str] = mapped_column(String(160), nullable=False)
    docx_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    docx_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pdf_filename: Mapped[str] = mapped_column(String(160), nullable=False)
    pdf_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pdf_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    task_plot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    task_updated_at_snapshot: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    delivery_package_code: Mapped[str] = mapped_column(String(80), nullable=False)
    delivery_package_completed_at_snapshot: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    delivery_package_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    delivery_package_checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    delivery_manifest_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_summary_checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    report_manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    generation_comment: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
