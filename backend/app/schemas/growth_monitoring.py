"""多时相 NDVI 长势监测请求与响应模型。"""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GrowthMonitoringCreateRequest(BaseModel):
    """创建并执行一次真实多时相 NDVI 长势监测。"""

    run_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    run_name: str = Field(min_length=1, max_length=200)
    baseline_asset_code: str = Field(min_length=1, max_length=80)
    current_asset_code: str = Field(min_length=1, max_length=80)
    poor_delta_threshold: float = Field(default=-0.05, ge=-1, lt=0)
    good_delta_threshold: float = Field(default=0.05, gt=0, le=1)
    minimum_zone_area_ha: float = Field(default=1, gt=0, le=500)
    minimum_spatial_coverage_ratio: float = Field(default=0.8, gt=0, le=1)
    minimum_valid_pixel_ratio: float = Field(default=0.8, gt=0, le=1)
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=10, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "run_code",
        "run_name",
        "baseline_asset_code",
        "current_asset_code",
        "operator_code",
        "comment",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理长势监测必填文本。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空格后的文本。
        """
        return value.strip()

    @model_validator(mode="after")
    def validate_temporal_pair(self) -> Self:
        """确保前后时相使用两个不同影像资产。

        Returns:
            Self: 校验通过的请求。
        """
        if self.baseline_asset_code == self.current_asset_code:
            raise ValueError("基准期与监测期必须选择两个不同影像资产")
        return self


class GrowthMonitoringSourceResponse(BaseModel):
    """可参与长势监测的 NDVI 实体来源及资格。"""

    asset_code: str
    asset_name: str
    acquired_at: datetime
    data_status: str
    source_uri: str | None
    source_size_bytes: int | None
    source_sha256: str | None
    ndvi_band_index: int | None
    eligible: bool
    unavailable_reason: str | None


class GrowthMonitoringRunResponse(BaseModel):
    """长势监测任务、质量指标和物理成果摘要。"""

    run_code: str
    run_name: str
    baseline_asset_code: str
    baseline_asset_name: str
    baseline_acquired_at: datetime
    current_asset_code: str
    current_asset_name: str
    current_acquired_at: datetime
    poor_delta_threshold: float
    good_delta_threshold: float
    minimum_zone_area_ha: float
    minimum_spatial_coverage_ratio: float
    minimum_valid_pixel_ratio: float
    algorithm_code: str
    algorithm_version: str
    task_plot_count: int
    task_updated_at: datetime
    output_crs: str
    output_resolution_x: float
    output_resolution_y: float
    raster_width: int
    raster_height: int
    bounds_wgs84: list[float]
    task_farmland_area_ha: float
    common_footprint_farmland_area_ha: float
    spatial_coverage_ratio: float
    common_footprint_mask_pixel_count: int
    valid_pixel_count: int
    valid_pixel_ratio: float
    poor_pixel_count: int
    normal_pixel_count: int
    good_pixel_count: int
    anomaly_zone_count: int
    anomaly_area_ha: float
    classification_filename: str
    classification_size_bytes: int
    classification_sha256: str
    anomaly_filename: str
    anomaly_size_bytes: int
    anomaly_sha256: str
    manifest: dict
    created_by: str
    created_by_code: str
    created_by_role: str
    comment: str
    created_at: datetime
    task_snapshot_current: bool
    stale_reason: str | None
    classification_verified: bool
    anomaly_verified: bool
    source_verified: bool
    source_error: str | None
    artifact_error: str | None
    classification_download_url: str | None
    anomaly_download_url: str | None


class GrowthMonitoringOverviewResponse(BaseModel):
    """长势监测来源、历史任务和当前异常区总览。"""

    project_code: str
    task_code: str
    max_output_pixels: int
    sources: list[GrowthMonitoringSourceResponse]
    runs: list[GrowthMonitoringRunResponse]
    selected_run_code: str | None
    feature_collection: dict


class GrowthMonitoringZoneCollectionResponse(BaseModel):
    """指定长势监测任务的异常区 GeoJSON。"""

    run_code: str
    zone_count: int
    anomaly_area_ha: float
    feature_collection: dict


GrowthArtifactType = Literal["classification", "anomalies"]
