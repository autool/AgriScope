"""面积统计正式报告包实体与生成快照模型。"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
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


class StatisticsReport(Base):
    """由任务实时统计和真实历史快照生成的不可变报告包。"""

    __tablename__ = "statistics_reports"
    __table_args__ = (
        UniqueConstraint("report_code", name="uq_statistics_report_code"),
        UniqueConstraint(
            "task_id",
            "version",
            name="uq_statistics_report_task_version",
        ),
        CheckConstraint(
            "status IN ('completed', 'superseded', 'invalid')",
            name="ck_statistics_report_status",
        ),
        CheckConstraint(
            "bundle_size_bytes > 0 "
            "AND xlsx_size_bytes > 0 "
            "AND pdf_size_bytes > 0",
            name="ck_statistics_report_file_sizes",
        ),
        CheckConstraint(
            "char_length(bundle_checksum_sha256) = 64 "
            "AND char_length(xlsx_checksum_sha256) = 64 "
            "AND char_length(pdf_checksum_sha256) = 64",
            name="ck_statistics_report_checksums",
        ),
        CheckConstraint(
            "task_plot_count >= 0 AND history_snapshot_count >= 0",
            name="ck_statistics_report_source_counts",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_code: Mapped[str] = mapped_column(String(100), nullable=False)
    report_title: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    bundle_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    bundle_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bundle_checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    xlsx_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    xlsx_checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    pdf_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pdf_checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    task_plot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    task_updated_at_snapshot: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    history_snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    history_latest_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
