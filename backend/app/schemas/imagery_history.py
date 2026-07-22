"""历史影像覆盖矩阵与处理问题追溯响应模型。"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class ImageryHistoryBoundaryResponse(BaseModel):
    """覆盖矩阵使用的真实行政区目录。"""

    boundary_code: str
    boundary_name: str
    boundary_level: Literal["city", "district"]
    parent_code: str | None
    source_name: str
    source_version: str | None
    source_updated_at: date | None


class ImageryHistoryAssetResponse(BaseModel):
    """一个历史影像时相及其当前实体和处理质量摘要。"""

    asset_code: str
    asset_name: str
    sensor_type: str
    acquired_at: datetime
    cloud_cover: float | None
    resolution_m: float | None
    processing_level: str | None
    data_status: Literal["operational", "demo"]
    file_verified: bool
    file_error: str | None
    checksum_sha256: str | None
    crs: str | None
    required_step_count: int
    verified_required_step_count: int
    processing_completion_rate: float
    covered_prefecture_count: int
    covered_county_count: int
    province_coverage_percent: float
    issue_count: int
    is_latest_operational: bool


class ImageryCoverageCellResponse(BaseModel):
    """单景影像与单个县区真实边界的覆盖关系。"""

    asset_code: str
    prefecture_code: str
    prefecture_name: str
    county_code: str
    county_name: str
    county_area_ha: float
    covered_area_ha: float
    coverage_percent: float
    coverage_status: Literal["none", "partial", "complete"]


class ImageryTraceEventResponse(BaseModel):
    """影像入库、处理、替换或问题状态的可追溯事件。"""

    event_code: str
    asset_code: str
    asset_name: str
    occurred_at: datetime
    event_type: Literal[
        "asset_imported",
        "demo_notice",
        "source_file_invalid",
        "cloud_threshold_exceeded",
        "required_step_pending",
        "step_completed",
        "step_artifact_invalid",
        "artifact_superseded",
    ]
    severity: Literal["success", "info", "warning", "error"]
    title: str
    detail: str
    step_code: str | None
    evidence_uri: str | None
    evidence_sha256: str | None


class ImageryHistoryOverviewResponse(BaseModel):
    """项目历史影像覆盖矩阵、时相质量和问题追溯总览。"""

    project_code: str
    generated_at: datetime
    asset_count: int
    operational_asset_count: int
    verified_operational_asset_count: int
    prefecture_count: int
    county_count: int
    time_start: datetime | None
    time_end: datetime | None
    boundaries: list[ImageryHistoryBoundaryResponse]
    assets: list[ImageryHistoryAssetResponse]
    coverage_cells: list[ImageryCoverageCellResponse]
    trace_events: list[ImageryTraceEventResponse]
