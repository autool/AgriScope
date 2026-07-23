"""多时相变化检测任务、候选导入与人工判读请求响应模型。"""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.imagery_registration import ImageryRegistrationJobResponse

ChangeClass = Literal[
    "suspected_construction",
    "farmland_outflow",
    "construction_facility_change",
    "non_farmland_agricultural_change",
    "unused_land_change",
    "farmland_attribute_change",
]
CandidateChangeClass = Literal[
    "unclassified",
    "suspected_construction",
    "farmland_outflow",
    "construction_facility_change",
    "non_farmland_agricultural_change",
    "unused_land_change",
    "farmland_attribute_change",
]
ChangeCandidateStatus = Literal["pending", "confirmed", "excluded"]
ChangeRunStatus = Literal["active", "reviewing", "completed", "cancelled"]
ChangeDiscoveryAlgorithmCode = Literal[
    "rgb_absolute_difference",
    "rgb_change_vector",
]


class ChangePolygonGeometry(BaseModel):
    """变化候选的 WGS84 Polygon 几何。"""

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[tuple[float, float]]]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_polygon(self) -> Self:
        """校验环闭合、节点数量和 WGS84 坐标范围。

        Returns:
            Self: 通过基础几何校验的 Polygon。
        """
        if not self.coordinates:
            raise ValueError("变化候选至少包含一个外环")
        if sum(len(ring) for ring in self.coordinates) > 10000:
            raise ValueError("单个变化候选节点数不得超过 10000")
        for ring in self.coordinates:
            if len(ring) < 4:
                raise ValueError("变化候选环至少包含 4 个坐标点")
            if ring[0] != ring[-1]:
                raise ValueError("变化候选环必须闭合")
            for lon, lat in ring:
                if not -180 <= lon <= 180 or not -90 <= lat <= 90:
                    raise ValueError("变化候选坐标超出 WGS84 合法范围")
        return self


class ChangeRunCreateRequest(BaseModel):
    """创建绑定两期真实影像和配准证据的变化检测任务。"""

    run_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    run_name: str = Field(min_length=1, max_length=200)
    baseline_asset_code: str = Field(min_length=1, max_length=80)
    target_asset_code: str = Field(min_length=1, max_length=80)
    registration_job_code: str = Field(min_length=1, max_length=80)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "run_name",
        "baseline_asset_code",
        "target_asset_code",
        "registration_job_code",
        "operator_code",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理变化检测任务文本。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("变化检测任务字段不得为空")
        return normalized

    @model_validator(mode="after")
    def validate_assets(self) -> Self:
        """确保前后时相影像编号不同。

        Returns:
            Self: 校验通过的任务请求。
        """
        if self.baseline_asset_code == self.target_asset_code:
            raise ValueError("前后时相影像不能相同")
        return self


class ChangeCandidateImportProperties(BaseModel):
    """单个外部变化候选的来源属性。"""

    candidate_code: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    source_feature_id: str = Field(min_length=1, max_length=100)
    change_class: ChangeClass
    confidence: float = Field(ge=0, le=1)
    evidence_uri: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="ignore")

    @field_validator("source_feature_id", "evidence_uri")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理来源要素和证据地址。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("候选来源与证据不得为空")
        return normalized


class ChangeCandidateImportFeature(BaseModel):
    """变化候选 GeoJSON Feature。"""

    type: Literal["Feature"] = "Feature"
    geometry: ChangePolygonGeometry
    properties: ChangeCandidateImportProperties

    model_config = ConfigDict(extra="ignore")


class ChangeCandidateGeoJsonImportRequest(BaseModel):
    """外部模型候选 GeoJSON 原子导入请求。"""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    source_name: str = Field(min_length=1, max_length=120)
    source_uri: str = Field(min_length=1, max_length=500)
    source_version: str = Field(min_length=1, max_length=80)
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=1, max_length=500)
    features: list[ChangeCandidateImportFeature] = Field(
        min_length=1,
        max_length=500,
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "source_name",
        "source_uri",
        "source_version",
        "operator_code",
        "comment",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理候选批次来源和操作说明。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("变化候选导入来源和说明不得为空")
        return normalized

    @model_validator(mode="after")
    def validate_collection(self) -> Self:
        """校验批次内候选编号、来源编号和总节点上限。

        Returns:
            Self: 通过批次校验的 FeatureCollection。
        """
        candidate_codes = [
            feature.properties.candidate_code for feature in self.features
        ]
        if len(candidate_codes) != len(set(candidate_codes)):
            raise ValueError("同一批次候选编号不得重复")
        source_ids = [
            feature.properties.source_feature_id for feature in self.features
        ]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("同一批次来源要素编号不得重复")
        vertex_count = sum(
            len(ring)
            for feature in self.features
            for ring in feature.geometry.coordinates
        )
        if vertex_count > 50000:
            raise ValueError("单次变化候选导入总节点数不得超过 50000")
        return self


class ChangeCandidateReviewRequest(BaseModel):
    """人工确认、重分类或排除变化候选请求。"""

    decision: Literal["confirmed", "excluded"]
    change_class: ChangeClass | None = None
    exclusion_reason: str | None = Field(default=None, max_length=500)
    evidence_comment: str = Field(min_length=1, max_length=1000)
    reviewer_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "exclusion_reason",
        "evidence_comment",
        "reviewer_code",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """清理人工判读依据和用户编码。

        Args:
            value: 原始文本。

        Returns:
            str | None: 标准化文本。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        """校验排除原因和确认状态字段组合。

        Returns:
            Self: 校验通过的人工判读请求。
        """
        if not self.evidence_comment:
            raise ValueError("人工判读必须填写证据说明")
        if self.decision == "excluded" and not self.exclusion_reason:
            raise ValueError("排除变化候选必须填写排除原因")
        if self.decision == "confirmed" and self.exclusion_reason:
            raise ValueError("确认变化候选时不得填写排除原因")
        return self


class ChangeImageryResponse(BaseModel):
    """变化检测可选影像及实体、预处理资格。"""

    asset_code: str
    asset_name: str
    sensor_type: str
    acquired_at: datetime
    resolution_m: float | None
    cloud_cover: float | None
    checksum_sha256: str | None
    crs: str | None
    footprint: dict | None
    file_verified: bool
    eligible: bool
    eligibility_reason: str | None


class ChangeDetectionEventResponse(BaseModel):
    """候选判读或检测任务操作审计。"""

    event_type: str
    previous_values: dict
    new_values: dict
    comment: str
    operator: str
    operator_code: str
    operator_role: str
    created_at: datetime


class ChangeCandidateResponse(BaseModel):
    """变化候选当前状态与不可变审计历史。"""

    candidate_code: str
    source_name: str
    source_uri: str
    source_version: str
    source_feature_id: str
    source_checksum_sha256: str
    import_batch_code: str
    change_class: CandidateChangeClass
    confidence: float
    area_ha: float
    evidence_uri: str
    status: ChangeCandidateStatus
    exclusion_reason: str | None
    review_comment: str | None
    reviewed_by: str | None
    reviewed_by_code: str | None
    reviewed_by_role: str | None
    reviewed_at: datetime | None
    imported_by: str
    imported_by_code: str
    imported_by_role: str
    created_at: datetime
    geometry: dict
    history: list[ChangeDetectionEventResponse]


class ChangeDetectionRunResponse(BaseModel):
    """变化检测任务、来源快照和候选判读汇总。"""

    run_code: str
    run_name: str
    baseline_asset_code: str
    target_asset_code: str
    registration_job_code: str
    rule_config_version: int
    rule_profile_snapshot: dict
    source_snapshot: dict
    task_plot_count: int
    task_updated_at_snapshot: datetime
    alignment_method: str
    alignment_offset_pixels: float
    alignment_overlap_ratio: float
    alignment_evidence_uri: str
    status: ChangeRunStatus
    candidate_count: int
    pending_count: int
    confirmed_count: int
    excluded_count: int
    class_counts: dict[str, int]
    created_by: str
    created_by_code: str
    created_by_role: str
    created_at: datetime
    updated_at: datetime
    candidates: list[ChangeCandidateResponse]
    feature_collection: dict


class ChangeDiscoveryAlgorithmResponse(BaseModel):
    """服务端已注册自动候选算法及阈值能力。"""

    code: ChangeDiscoveryAlgorithmCode
    name: str
    version: str
    description: str
    score_formula: str
    default_threshold: float
    threshold_min: float
    threshold_max: float


class ChangeDetectionOverviewResponse(BaseModel):
    """变化检测页面真实影像资格、阻断项和任务列表。"""

    project_code: str
    task_code: str
    blockers: list[str]
    discovery_algorithms: list[ChangeDiscoveryAlgorithmResponse]
    imagery: list[ChangeImageryResponse]
    registrations: list[ImageryRegistrationJobResponse]
    runs: list[ChangeDetectionRunResponse]


class ChangeCandidateImportResponse(BaseModel):
    """变化候选 GeoJSON 原子导入结果。"""

    run_code: str
    batch_code: str
    imported_count: int
    candidate_codes: list[str]
    source_checksum_sha256: str
    imported_by: str
    imported_by_code: str
    imported_by_role: str
    imported_at: datetime


class ChangeCandidateDiscoveryRequest(BaseModel):
    """内置多算法自动候选发现参数。"""

    algorithm_code: ChangeDiscoveryAlgorithmCode = "rgb_absolute_difference"
    difference_threshold: float | None = Field(default=None, ge=0.01, le=1)
    min_component_pixels: int = Field(default=9, ge=1, le=100000)
    max_candidates: int = Field(default=200, ge=1, le=500)
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "comment")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理自动候选操作人和运行说明。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("自动候选发现操作人和说明不得为空")
        return normalized


class ChangeCandidateDiscoveryResponse(BaseModel):
    """内置注册算法实体成果、过滤统计和审计结果。"""

    run_code: str
    batch_code: str
    algorithm_code: str
    algorithm_name: str
    algorithm_version: str
    score_formula: str
    parameters: dict
    detected_count: int
    imported_count: int
    filtered_below_area_count: int
    changed_pixel_count: int
    valid_pixel_count: int
    candidate_codes: list[str]
    artifact_uri: str
    artifact_sha256: str
    generated_by: str
    generated_by_code: str
    generated_by_role: str
    generated_at: datetime


class ChangeComparisonSourceResponse(BaseModel):
    """双时相对比单期影像来源与渲染证据。"""

    asset_code: str
    asset_name: str
    acquired_at: datetime
    checksum_sha256: str
    file_size_bytes: int
    band_indexes: tuple[int, int, int]


class ChangeComparisonMetadataResponse(BaseModel):
    """公共网格双时相预览地址、来源和渲染清单。"""

    run_code: str
    baseline: ChangeComparisonSourceResponse
    target: ChangeComparisonSourceResponse
    baseline_url: str
    target_url: str
    bounds_wgs84: tuple[float, float, float, float]
    width: int
    height: int
    renderer_version: str
    stretch_ranges: tuple[tuple[float, float], ...]
    baseline_preview_sha256: str
    target_preview_sha256: str
    generated_at: datetime
