"""行政区划边界 GeoJSON 响应模型。"""

from pydantic import BaseModel


class BoundaryFeatureCollectionResponse(BaseModel):
    """项目行政区划边界 GeoJSON 集合。"""

    type: str = "FeatureCollection"
    features: list[dict]
