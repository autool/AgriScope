"""专题制图模板、实体成果和不可变事件模型。"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
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


class ThematicMapTemplate(Base):
    """项目级专题图版式模板。"""

    __tablename__ = "thematic_map_templates"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "template_code",
            name="uq_thematic_map_template_project_code",
        ),
        CheckConstraint(
            "page_width_px BETWEEN 800 AND 8000 "
            "AND page_height_px BETWEEN 600 AND 8000",
            name="ck_thematic_map_template_dimensions",
        ),
        CheckConstraint(
            "dpi BETWEEN 72 AND 600 AND margin_px BETWEEN 20 AND 800",
            name="ck_thematic_map_template_print",
        ),
        CheckConstraint(
            "legend_position IN ('bottom_right', 'bottom_left')",
            name="ck_thematic_map_template_legend_position",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_code: Mapped[str] = mapped_column(String(80), nullable=False)
    template_name: Mapped[str] = mapped_column(String(150), nullable=False)
    title_pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    producer: Mapped[str] = mapped_column(String(150), nullable=False)
    page_width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    page_height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    dpi: Mapped[int] = mapped_column(Integer, nullable=False)
    margin_px: Mapped[int] = mapped_column(Integer, nullable=False)
    legend_position: Mapped[str] = mapped_column(String(30), nullable=False)
    include_neatline: Mapped[bool] = mapped_column(Boolean, nullable=False)
    include_north_arrow: Mapped[bool] = mapped_column(Boolean, nullable=False)
    include_scale_bar: Mapped[bool] = mapped_column(Boolean, nullable=False)
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
        nullable=False,
    )


class ThematicMapProduct(Base):
    """由已校验影像产品生成的实体专题图成果。"""

    __tablename__ = "thematic_map_products"
    __table_args__ = (
        UniqueConstraint("product_code", name="uq_thematic_map_product_code"),
        UniqueConstraint(
            "task_id",
            "map_number",
            "source_product_code",
            "output_format",
            name="uq_thematic_map_product_business_key",
        ),
        CheckConstraint(
            "source_product_code IN ('true_color', 'false_color', 'ndvi')",
            name="ck_thematic_map_product_source_code",
        ),
        CheckConstraint(
            "output_format IN ('png', 'pdf')",
            name="ck_thematic_map_product_format",
        ),
        CheckConstraint(
            "status IN ('completed', 'invalid')",
            name="ck_thematic_map_product_status",
        ),
        CheckConstraint(
            "file_size_bytes > 0 AND char_length(checksum_sha256) = 64",
            name="ck_thematic_map_product_file_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("thematic_map_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("imagery_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_code: Mapped[str] = mapped_column(String(100), nullable=False)
    map_name: Mapped[str] = mapped_column(String(200), nullable=False)
    map_number: Mapped[str] = mapped_column(String(100), nullable=False)
    map_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_product_code: Mapped[str] = mapped_column(String(30), nullable=False)
    output_format: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    file_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    page_height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    dpi: Mapped[int] = mapped_column(Integer, nullable=False)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    source_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_bounds_wgs84: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    render_manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ThematicMapAtlas(Base):
    """由任务全部有效 PNG 专题图编排形成的实体图集。"""

    __tablename__ = "thematic_map_atlases"
    __table_args__ = (
        UniqueConstraint("atlas_code", name="uq_thematic_map_atlas_code"),
        UniqueConstraint(
            "task_id",
            "version",
            name="uq_thematic_map_atlas_task_version",
        ),
        CheckConstraint(
            "status IN ('completed', 'superseded', 'invalid')",
            name="ck_thematic_map_atlas_status",
        ),
        CheckConstraint(
            "member_count BETWEEN 2 AND 50 "
            "AND pdf_page_count >= member_count + 2",
            name="ck_thematic_map_atlas_counts",
        ),
        CheckConstraint(
            "package_size_bytes > 0 AND pdf_size_bytes > 0 "
            "AND char_length(package_checksum_sha256) = 64 "
            "AND char_length(pdf_checksum_sha256) = 64 "
            "AND char_length(source_snapshot_sha256) = 64",
            name="ck_thematic_map_atlas_file_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    atlas_code: Mapped[str] = mapped_column(String(100), nullable=False)
    atlas_name: Mapped[str] = mapped_column(String(200), nullable=False)
    atlas_number: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    package_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    package_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    package_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pdf_filename: Mapped[str] = mapped_column(String(200), nullable=False)
    pdf_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    pdf_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pdf_page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    product_count_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    product_latest_at_snapshot: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    atlas_manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    generated_by_code: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_by_role: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ThematicMapAtlasItem(Base):
    """图集内专题图顺序和不可变来源快照。"""

    __tablename__ = "thematic_map_atlas_items"
    __table_args__ = (
        UniqueConstraint(
            "atlas_id",
            "sequence",
            name="uq_thematic_map_atlas_item_sequence",
        ),
        UniqueConstraint(
            "atlas_id",
            "product_id",
            name="uq_thematic_map_atlas_item_product",
        ),
        CheckConstraint(
            "sequence BETWEEN 1 AND 50 "
            "AND product_size_bytes > 0 "
            "AND char_length(product_checksum_sha256) = 64",
            name="ck_thematic_map_atlas_item_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    atlas_id: Mapped[int] = mapped_column(
        ForeignKey("thematic_map_atlases.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("thematic_map_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    product_code: Mapped[str] = mapped_column(String(100), nullable=False)
    map_name: Mapped[str] = mapped_column(String(200), nullable=False)
    map_number: Mapped[str] = mapped_column(String(100), nullable=False)
    map_date: Mapped[date] = mapped_column(Date, nullable=False)
    product_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    product_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    member_path: Mapped[str] = mapped_column(String(300), nullable=False)


class ThematicMapEvent(Base):
    """专题图模板、生成和下载的不可变审计事件。"""

    __tablename__ = "thematic_map_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("monitoring_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_code: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    event_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    operator_code: Mapped[str] = mapped_column(String(50), nullable=False)
    operator_role: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
