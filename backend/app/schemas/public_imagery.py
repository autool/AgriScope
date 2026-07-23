"""公开历史遥感影像检索与实体导入请求响应模型。"""

from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.imagery import ImageryAssetResponse


class PublicImagerySearchRequest(BaseModel):
    """固定公开 STAC 来源的 Landsat 历史影像检索条件。"""

    bbox: tuple[float, float, float, float]
    start_date: date
    end_date: date
    max_cloud_cover: float = Field(default=20, ge=0, le=100)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_search_scope(self) -> Self:
        """校验日期跨度和 WGS84 裁取窗口。

        Returns:
            Self: 已通过范围校验的检索请求。
        """
        _validate_bbox(self.bbox)
        if self.start_date > self.end_date:
            raise ValueError("开始日期不得晚于结束日期")
        if (self.end_date - self.start_date).days > 3660:
            raise ValueError("单次公开影像检索时间跨度不得超过 10 年")
        return self


class PublicImageryCandidateResponse(BaseModel):
    """一个由服务端固定 STAC 源返回的真实 Landsat 候选。"""

    item_id: str
    acquired_at: datetime
    cloud_cover: float | None
    platform: str
    instrument: str
    processing_level: str
    collection_category: str | None
    wrs_path: int | None
    wrs_row: int | None
    resolution_m: float
    bbox: tuple[float, float, float, float]
    fully_covers_query: bool
    stac_item_url: str


class PublicImagerySearchResponse(BaseModel):
    """公开历史影像候选和固定来源说明。"""

    provider: str
    collection: str
    license_name: str
    license_url: str
    non_statutory_notice: str
    query_bbox: tuple[float, float, float, float]
    total: int
    items: list[PublicImageryCandidateResponse]


class PublicImageryImportRequest(BaseModel):
    """从固定公开 STAC 条目裁取并入库的业务请求。"""

    project_code: str = Field(min_length=1, max_length=50)
    task_code: str = Field(min_length=1, max_length=50)
    item_id: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    bbox: tuple[float, float, float, float]
    asset_code: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    asset_name: str = Field(min_length=1, max_length=200)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "project_code",
        "task_code",
        "item_id",
        "asset_code",
        "asset_name",
        "operator_code",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理公开影像导入文本。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空白的文本。
        """
        return value.strip()

    @model_validator(mode="after")
    def validate_import_scope(self) -> Self:
        """校验导入裁取窗口。

        Returns:
            Self: 已通过 WGS84 范围校验的导入请求。
        """
        _validate_bbox(self.bbox)
        return self


class PublicImageryImportResponse(BaseModel):
    """公开 Landsat 实体裁取和影像资产入库结果。"""

    provider: str
    collection: str
    item_id: str
    source_product_id: str
    source_acquired_at: datetime
    source_cloud_cover: float | None
    source_wrs_path: int | None
    source_wrs_row: int | None
    license_name: str
    non_statutory_notice: str
    asset: ImageryAssetResponse


def _validate_bbox(bbox: tuple[float, float, float, float]) -> None:
    """校验公开影像检索和裁取使用的 WGS84 窗口。

    Args:
        bbox: 左、下、右、上四个坐标。

    Returns:
        None: 校验通过后无返回值。
    """
    left, bottom, right, top = bbox
    if not (-180 <= left < right <= 180 and -90 <= bottom < top <= 90):
        raise ValueError("bbox 超出 WGS84 合法范围或顺序错误")
    if right - left > 3 or top - bottom > 3:
        raise ValueError("单次公开影像检索范围不得超过经纬方向各 3 度")
