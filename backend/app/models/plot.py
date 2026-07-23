"""永久基本农田图斑 ORM 模型。"""

from datetime import datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import JSON, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 声明式模型基类。"""


class FarmlandPlot(Base):
    """永久基本农田图斑。"""

    __tablename__ = "farmland_plots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plot_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    owner_village: Mapped[str | None] = mapped_column(String(100), nullable=True)
    area_ha: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=False,
    )
    land_class: Mapped[str | None] = mapped_column(String(50), nullable=True)
    crop_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    planting_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    irrigation_condition: Mapped[str | None] = mapped_column(String(20), nullable=True)
    custom_attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_feature_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    province_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    interpretation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="interpreting",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
