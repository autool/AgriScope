"""API 响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlotInfoResponse(BaseModel):
    """图斑属性响应。"""

    plot_code: str
    owner_village: str | None
    area_ha: float | None
    land_class: str | None = None
    source_name: str | None = None
    source_feature_id: str | None = None
    source_uri: str | None = None
    source_version: str | None = None
    source_updated_at: datetime | None = None
    province_name: str | None = None
    city_name: str | None = None
    district_name: str | None = None
    district_code: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PlotCatalogItem(BaseModel):
    """轻量地块目录中的单个真实地块。"""

    plot_code: str
    source_feature_id: str | None
    land_class: str | None
    extent: tuple[float, float, float, float]


class PlotCatalogDistrict(BaseModel):
    """按县区组织的任务地块目录。"""

    district_code: str
    plot_count: int
    plots: list[PlotCatalogItem]


class PlotCatalogResponse(BaseModel):
    """不携带完整几何的任务地块分级目录。"""

    task_code: str
    total_count: int
    land_class_counts: dict[str, int]
    districts: list[PlotCatalogDistrict]


class PlotViewportResponse(BaseModel):
    """当前地图视野内的完整地块 GeoJSON。"""

    type: str = "FeatureCollection"
    features: list[dict]
    matched_count: int
    max_features: int
    requires_zoom: bool


class ErrorResponse(BaseModel):
    """统一错误响应，不包含数据库堆栈或内部实现信息。"""

    code: int
    msg: str
