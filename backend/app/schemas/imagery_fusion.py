"""多光谱与全色影像融合请求响应模型。"""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ImageryFusionCreateRequest(BaseModel):
    """创建并执行一次服务端全色融合。"""

    job_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    job_name: str = Field(min_length=1, max_length=200)
    multispectral_asset_code: str = Field(min_length=1, max_length=80)
    panchromatic_asset_code: str = Field(min_length=1, max_length=80)
    multispectral_band_indexes: list[int] = Field(min_length=3, max_length=3)
    panchromatic_band_index: int = Field(default=1, ge=1, le=256)
    resampling_method: Literal["bilinear", "cubic"] = "cubic"
    minimum_overlap_ratio: float = Field(default=0.95, gt=0, le=1)
    minimum_spectral_correlation: float = Field(default=0.8, ge=0, le=1)
    minimum_spatial_detail_gain: float = Field(default=1.05, gt=0, le=10)
    gain_limit: float = Field(default=4, ge=1.1, le=10)
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=10, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "job_code",
        "job_name",
        "multispectral_asset_code",
        "panchromatic_asset_code",
        "operator_code",
        "comment",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理融合任务必填文本。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空格后的文本。
        """
        return value.strip()

    @model_validator(mode="after")
    def validate_sources_and_bands(self) -> Self:
        """确保输入资产不同且三个多光谱波段互不重复。

        Returns:
            Self: 校验通过的请求。
        """
        if self.multispectral_asset_code == self.panchromatic_asset_code:
            raise ValueError("多光谱影像与全色影像必须是两个不同资产")
        if len(set(self.multispectral_band_indexes)) != 3:
            raise ValueError("三个多光谱波段必须互不相同")
        if any(index < 1 or index > 256 for index in self.multispectral_band_indexes):
            raise ValueError("多光谱波段编号必须位于 1–256")
        return self


class ImageryFusionSourceResponse(BaseModel):
    """可参与全色融合的真实影像源及资格。"""

    asset_code: str
    asset_name: str
    sensor_type: str
    acquired_at: datetime
    data_status: str
    source_uri: str | None
    source_size_bytes: int | None
    source_sha256: str | None
    source_crs: str | None
    source_width: int | None
    source_height: int | None
    source_band_count: int | None
    resolution_x: float | None
    resolution_y: float | None
    band_descriptions: list[str | None]
    product_identity: str | None
    reflectance_quantity: str | None
    radiometric_calibration_applied: bool
    multispectral_eligible: bool
    multispectral_reason: str | None
    panchromatic_eligible: bool
    panchromatic_reason: str | None


class ImageryFusionJobResponse(BaseModel):
    """已完成全色融合任务、质量指标和实体成果。"""

    job_code: str
    job_name: str
    multispectral_asset_code: str
    multispectral_asset_name: str
    panchromatic_asset_code: str
    panchromatic_asset_name: str
    multispectral_band_indexes: list[int]
    panchromatic_band_index: int
    algorithm_code: str
    algorithm_version: str
    resampling_method: str
    overlap_ratio: float
    spectral_correlations: list[float]
    minimum_spectral_correlation: float
    mean_spectral_correlation: float
    spatial_detail_gain: float
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


class ImageryFusionOverviewResponse(BaseModel):
    """全色融合来源资格、输出上限和历史成果总览。"""

    max_output_pixels: int
    sources: list[ImageryFusionSourceResponse]
    jobs: list[ImageryFusionJobResponse]
