"""灾害监测专题报告实体和审计快照模型。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
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


class DisasterReport(Base):
    """由已复核灾害斑块生成的不可变 XLSX 专题报告。"""

    __tablename__ = "disaster_reports"
    __table_args__ = (
        UniqueConstraint("report_code", name="uq_disaster_report_code"),
        CheckConstraint(
            "status IN ('completed', 'superseded', 'invalid')",
            name="ck_disaster_report_status",
        ),
        CheckConstraint(
            "file_size_bytes > 0 AND char_length(checksum_sha256) = 64",
            name="ck_disaster_report_file_evidence",
        ),
        CheckConstraint(
            "source_patch_count >= 0 AND source_confirmed_count >= 0 "
            "AND source_excluded_count >= 0",
            name="ck_disaster_report_source_counts",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_code: Mapped[str] = mapped_column(String(100), nullable=False)
    report_title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    file_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_patch_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_confirmed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_excluded_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_latest_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    affected_area_ha: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
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
