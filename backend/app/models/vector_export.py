"""任务作用域多格式矢量成果导出包模型。"""

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


class VectorExportPackage(Base):
    """GeoJSON、Shapefile、KML 和 FileGDB 原子成果包。"""

    __tablename__ = "vector_export_packages"
    __table_args__ = (
        UniqueConstraint("export_code", name="uq_vector_export_code"),
        UniqueConstraint(
            "task_id",
            "version",
            name="uq_vector_export_task_version",
        ),
        CheckConstraint(
            "status IN ('completed', 'superseded', 'invalid')",
            name="ck_vector_export_status",
        ),
        CheckConstraint(
            "file_size_bytes > 0 AND char_length(checksum_sha256) = 64",
            name="ck_vector_export_file_evidence",
        ),
        CheckConstraint(
            "feature_count >= 0 AND task_plot_count >= 0",
            name="ck_vector_export_counts",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    export_code: Mapped[str] = mapped_column(String(100), nullable=False)
    export_title: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    formats: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    district_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    land_classes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False)
    task_plot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    task_updated_at_snapshot: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    file_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    export_manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    generation_comment: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
