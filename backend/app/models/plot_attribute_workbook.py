"""地块属性 Excel 导入批次模型。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.plot import Base


class PlotAttributeImportBatch(Base):
    """任务地块属性工作簿原子导入批次及实体证据。"""

    __tablename__ = "plot_attribute_import_batches"
    __table_args__ = (
        CheckConstraint(
            "row_count BETWEEN 1 AND 500",
            name="ck_plot_attribute_import_row_count",
        ),
        CheckConstraint(
            "changed_count >= 0 AND unchanged_count >= 0 "
            "AND changed_count + unchanged_count = row_count",
            name="ck_plot_attribute_import_result_counts",
        ),
        CheckConstraint(
            "file_size_bytes > 0",
            name="ck_plot_attribute_import_file_size",
        ),
        CheckConstraint(
            "length(checksum_sha256) = 64",
            name="ck_plot_attribute_import_checksum",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    batch_code: Mapped[str] = mapped_column(
        String(90),
        unique=True,
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_by: Mapped[str] = mapped_column(String(100), nullable=False)
    imported_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    imported_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    import_comment: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
