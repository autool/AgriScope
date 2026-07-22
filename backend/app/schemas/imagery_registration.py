"""双景影像自动配准请求与响应模型。"""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ImageryRegistrationSourceRequest(BaseModel):
    """一个已校验影像步骤实体选择。"""

    asset_code: str = Field(min_length=1, max_length=80)
    step_code: Literal["geometric", "clip", "enhancement", "band_products"]
    band_index: int = Field(ge=1, le=256)

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


class ImageryRegistrationCreateRequest(BaseModel):
    """创建并执行一次双景自动配准。"""

    job_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    job_name: str = Field(min_length=1, max_length=200)
    reference: ImageryRegistrationSourceRequest
    moving: ImageryRegistrationSourceRequest
    resampling_method: Literal["nearest", "bilinear", "cubic"] = "bilinear"
    max_initial_offset_pixels: float = Field(default=100, gt=0, le=1000)
    max_residual_pixels: float = Field(default=1, gt=0, le=10)
    minimum_overlap_ratio: float = Field(default=0.2, gt=0, le=1)
    minimum_peak_to_sidelobe_ratio: float = Field(default=5, gt=0, le=1000)
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=10, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("job_code", "job_name", "operator_code", "comment")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """清理配准任务必填文本。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空白后的文本。
        """
        return value.strip()

    @model_validator(mode="after")
    def validate_distinct_assets(self) -> Self:
        """确保参考景与待配准景是不同影像资产。

        Returns:
            Self: 校验通过的请求。
        """
        if self.reference.asset_code == self.moving.asset_code:
            raise ValueError("参考影像与待配准影像不能相同")
        return self


class ImageryRegistrationSourceResponse(BaseModel):
    """可用于配准的已校验步骤实体。"""

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
    bounds_wgs84: list[float]
    data_status: str
    eligible: bool
    eligibility_reason: str | None


class ImageryRegistrationJobResponse(BaseModel):
    """已完成配准任务、残差与实体证据。"""

    job_code: str
    job_name: str
    reference_asset_code: str
    moving_asset_code: str
    reference_step_code: str
    moving_step_code: str
    reference_band_index: int
    moving_band_index: int
    resampling_method: str
    initial_shift_x_pixels: float
    initial_shift_y_pixels: float
    initial_offset_pixels: float
    residual_shift_x_pixels: float
    residual_shift_y_pixels: float
    residual_offset_pixels: float
    overlap_ratio: float
    peak_to_sidelobe_ratio: float
    residual_threshold_pixels: float
    output_crs: str
    output_resolution_x: float
    output_resolution_y: float
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
    artifact_verified: bool
    artifact_error: str | None
    download_url: str | None


class ImageryRegistrationOverviewResponse(BaseModel):
    """配准可用来源、项目规则和历史成果总览。"""

    max_output_pixels: int
    project_positional_accuracy_pixels: float
    available_sources: list[ImageryRegistrationSourceResponse]
    jobs: list[ImageryRegistrationJobResponse]
