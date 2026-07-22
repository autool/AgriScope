"""多景影像匀色、镶嵌和覆盖验收请求响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImageryMosaicSourceRequest(BaseModel):
    """显式选择一个已校验影像步骤产物。"""

    asset_code: str = Field(min_length=1, max_length=80)
    step_code: Literal["geometric", "clip", "enhancement", "band_products"]

    model_config = ConfigDict(extra="forbid")

    @field_validator("asset_code")
    @classmethod
    def normalize_asset_code(cls, value: str) -> str:
        """清理影像资产编号。

        Args:
            value: 原始资产编号。

        Returns:
            str: 去除空白后的编号。
        """
        return value.strip()


class ImageryMosaicCreateRequest(BaseModel):
    """创建并执行多景影像镶嵌任务。"""

    job_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    job_name: str = Field(min_length=1, max_length=200)
    boundary_code: str = Field(min_length=1, max_length=50)
    target_crs: str = Field(min_length=1, max_length=100)
    target_resolution: float = Field(gt=0, le=1_000_000)
    color_balance_method: Literal["none", "mean_std"] = "mean_std"
    blend_method: Literal["first", "mean"] = "mean"
    resampling_method: Literal["nearest", "bilinear", "cubic"] = "bilinear"
    coverage_threshold: float = Field(default=98, gt=0, le=100)
    sources: list[ImageryMosaicSourceRequest] = Field(min_length=2, max_length=20)
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=10, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "job_code",
        "job_name",
        "boundary_code",
        "target_crs",
        "operator_code",
        "comment",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """清理镶嵌任务必填文本。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空白后的文本。
        """
        return value.strip()

    @field_validator("sources")
    @classmethod
    def reject_duplicate_sources(
        cls,
        value: list[ImageryMosaicSourceRequest],
    ) -> list[ImageryMosaicSourceRequest]:
        """拒绝重复选择同一资产步骤。

        Args:
            value: 输入来源列表。

        Returns:
            list[ImageryMosaicSourceRequest]: 唯一来源列表。
        """
        keys = {(item.asset_code, item.step_code) for item in value}
        if len(keys) != len(value):
            raise ValueError("镶嵌输入不能重复")
        asset_codes = {item.asset_code for item in value}
        if len(asset_codes) != len(value):
            raise ValueError("同一影像资产只能选择一个步骤产物")
        return value


class ImageryMosaicSourceResponse(BaseModel):
    """可用于镶嵌或已固化的输入来源。"""

    asset_code: str
    asset_name: str
    step_code: str
    step_name: str
    source_uri: str
    source_size_bytes: int
    source_sha256: str
    source_crs: str
    source_width: int
    source_height: int
    source_band_count: int
    band_descriptions: list[str | None]
    bounds_wgs84: list[float] | None = None
    balance_statistics: dict


class ImageryMosaicJobResponse(BaseModel):
    """已完成镶嵌任务和验收结果。"""

    job_code: str
    job_name: str
    boundary_code: str
    boundary_name: str
    target_crs: str
    target_resolution: float
    color_balance_method: str
    blend_method: str
    resampling_method: str
    coverage_threshold: float
    coverage_ratio: float
    meets_coverage: bool
    boundary_pixel_count: int
    covered_pixel_count: int
    source_count: int
    raster_width: int
    raster_height: int
    band_count: int
    dtype: str
    original_filename: str
    file_size_bytes: int
    checksum_sha256: str
    bounds_wgs84: list[float]
    manifest: dict
    created_by: str
    created_by_code: str
    created_by_role: str
    created_at: datetime
    inputs: list[ImageryMosaicSourceResponse]
    artifact_verified: bool
    artifact_error: str | None
    download_url: str | None


class ImageryMosaicOverviewResponse(BaseModel):
    """镶嵌生产可用输入和历史成果总览。"""

    max_output_pixels: int
    available_sources: list[ImageryMosaicSourceResponse]
    jobs: list[ImageryMosaicJobResponse]
