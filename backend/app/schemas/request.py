"""API 请求模型，所有经纬度均使用 WGS84（EPSG:4326）。"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PointQueryRequest(BaseModel):
    """WGS84 点查询请求。"""

    lon: float
    lat: float

    model_config = ConfigDict(extra="forbid")

    @field_validator("lon")
    @classmethod
    def validate_lon(cls, value: float) -> float:
        """校验 WGS84 经度。

        Args:
            value: 待校验经度。

        Returns:
            float: 合法经度。
        """
        if not -180 <= value <= 180:
            raise ValueError("经度必须位于 -180 到 180 之间")
        return value

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, value: float) -> float:
        """校验 WGS84 纬度。

        Args:
            value: 待校验纬度。

        Returns:
            float: 合法纬度。
        """
        if not -90 <= value <= 90:
            raise ValueError("纬度必须位于 -90 到 90 之间")
        return value


class BBoxRequest(BaseModel):
    """WGS84 视野包围盒请求。"""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    model_config = ConfigDict(extra="forbid")

    @field_validator("min_lon", "max_lon")
    @classmethod
    def validate_lon(cls, value: float) -> float:
        """校验包围盒经度。

        Args:
            value: 待校验经度。

        Returns:
            float: 合法经度。
        """
        if not -180 <= value <= 180:
            raise ValueError("经度必须位于 -180 到 180 之间")
        return value

    @field_validator("min_lat", "max_lat")
    @classmethod
    def validate_lat(cls, value: float) -> float:
        """校验包围盒纬度。

        Args:
            value: 待校验纬度。

        Returns:
            float: 合法纬度。
        """
        if not -90 <= value <= 90:
            raise ValueError("纬度必须位于 -90 到 90 之间")
        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """校验包围盒最小值必须小于最大值。

        Returns:
            Self: 通过校验的请求对象。
        """
        if self.min_lon >= self.max_lon or self.min_lat >= self.max_lat:
            raise ValueError("包围盒最小坐标必须小于最大坐标")
        return self


class PlotViewportRequest(BBoxRequest):
    """任务作用域内按当前视野加载图斑请求。"""

    task_code: str = Field(default="RS-2026-045", min_length=1, max_length=50)
    max_features: int = Field(default=5000, ge=100, le=5000)
