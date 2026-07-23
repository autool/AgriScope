"""遥感监测工作台请求与响应模型。"""

import re
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PolygonGeometry(BaseModel):
    """WGS84 GeoJSON Polygon 几何。"""

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[tuple[float, float]]]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_polygon(self) -> Self:
        """校验多边形环闭合、坐标范围和最小节点数。

        Returns:
            Self: 通过基础几何校验的 Polygon。
        """
        if not self.coordinates:
            raise ValueError("多边形至少包含一个外环")
        total_vertices = sum(len(ring) for ring in self.coordinates)
        if total_vertices > 10000:
            raise ValueError("单个图斑节点数不得超过 10000")
        for ring in self.coordinates:
            if len(ring) < 4:
                raise ValueError("多边形环至少包含 4 个坐标点")
            if ring[0] != ring[-1]:
                raise ValueError("多边形环必须闭合")
            for lon, lat in ring:
                if not -180 <= lon <= 180 or not -90 <= lat <= 90:
                    raise ValueError("多边形坐标超出 WGS84 合法范围")
        return self


class LineStringGeometry(BaseModel):
    """WGS84 GeoJSON LineString 分割线。"""

    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_line(self) -> Self:
        """校验分割线节点、坐标范围和有效长度。

        Returns:
            Self: 通过基础校验的 LineString。
        """
        if not 2 <= len(self.coordinates) <= 1000:
            raise ValueError("分割线必须包含 2 到 1000 个坐标点")
        if len(set(self.coordinates)) < 2:
            raise ValueError("分割线至少需要两个不同坐标点")
        for lon, lat in self.coordinates:
            if not -180 <= lon <= 180 or not -90 <= lat <= 90:
                raise ValueError("分割线坐标超出 WGS84 合法范围")
        return self


class PlotAttributeUpdateRequest(BaseModel):
    """解译图斑属性更新请求。"""

    land_class: str
    crop_type: str | None = None
    planting_mode: str | None = None
    irrigation_condition: str | None = None
    custom_attributes: dict[str, object] | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "land_class",
        "crop_type",
        "planting_mode",
        "irrigation_condition",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """清理属性文本两端空白。

        Args:
            value: 原始属性值。

        Returns:
            str | None: 清理后的属性值。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_land_crop_logic(self) -> Self:
        """校验地类与作物类型逻辑关系。

        Returns:
            Self: 通过业务逻辑校验的请求。
        """
        if self.land_class == "耕地" and not self.crop_type:
            raise ValueError("耕地图斑必须填写作物类型")
        if self.land_class != "耕地" and self.crop_type:
            raise ValueError("非耕地图斑不得填写作物类型")
        return self


class PlotAttributeMutationRequest(PlotAttributeUpdateRequest):
    """携带稳定操作人编码的单图属性更新请求。"""

    operator_code: str = Field(min_length=1, max_length=50)
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("operator_code", "comment")
    @classmethod
    def normalize_mutation_text(cls, value: str | None) -> str | None:
        """清理属性修改操作人编码和说明。

        Args:
            value: 原始文本。

        Returns:
            str | None: 去除首尾空格后的文本。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class BatchPlotAttributeUpdateRequest(BaseModel):
    """显式选择图斑后的批量属性赋值请求。"""

    plot_codes: list[str] = Field(min_length=1, max_length=1000)
    attributes: PlotAttributeUpdateRequest
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("plot_codes")
    @classmethod
    def validate_plot_codes(cls, values: list[str]) -> list[str]:
        """校验图斑编号格式、长度和唯一性。

        Args:
            values: 用户显式选择的图斑编号。

        Returns:
            list[str]: 保持用户顺序的唯一编号列表。
        """
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            plot_code = value.strip()
            if not plot_code or len(plot_code) > 50:
                raise ValueError("图斑编号长度必须为 1 到 50 个字符")
            if not re.fullmatch(r"[\w-]+", plot_code):
                raise ValueError(f"图斑编号 {plot_code} 格式不合法")
            if plot_code not in seen:
                normalized.append(plot_code)
                seen.add(plot_code)
        return normalized

    @field_validator("operator_code", "comment")
    @classmethod
    def normalize_batch_text(cls, value: str | None) -> str | None:
        """清理操作人和批量赋值说明。

        Args:
            value: 原始文本。

        Returns:
            str | None: 清理后的文本。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_operator(self) -> Self:
        """校验批量赋值操作人和判读依据必填。

        Returns:
            Self: 通过校验的请求。
        """
        if not self.operator_code:
            raise ValueError("操作人编码不得为空")
        if not self.comment:
            raise ValueError("批量赋值说明不得为空")
        return self


class BatchPlotAttributeUpdateResponse(BaseModel):
    """批量属性赋值和版本生成结果。"""

    task_code: str
    updated_count: int
    updated_plot_codes: list[str]
    total_plot_count: int
    completed_plot_count: int
    quality_recheck_required: bool


class PlotCreateRequest(PlotAttributeUpdateRequest):
    """新建解译图斑请求。"""

    plot_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        pattern=r"^[\w-]+$",
    )
    owner_village: str
    geometry: PolygonGeometry
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str | None = None

    @field_validator("plot_code", "owner_village", "operator_code", "comment")
    @classmethod
    def normalize_create_text(cls, value: str | None) -> str | None:
        """清理新建图斑文本字段。

        Args:
            value: 原始文本。

        Returns:
            str | None: 清理后的文本。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_create_required_fields(self) -> Self:
        """校验权属村和操作人必填。

        Returns:
            Self: 通过创建业务校验的请求。
        """
        if not self.owner_village:
            raise ValueError("权属村不得为空")
        if not self.operator_code:
            raise ValueError("操作人编码不得为空")
        return self


class PlotGeometryUpdateRequest(BaseModel):
    """图斑边界更新请求。"""

    geometry: PolygonGeometry
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "comment")
    @classmethod
    def normalize_geometry_text(cls, value: str | None) -> str | None:
        """清理几何编辑说明和操作人。

        Args:
            value: 原始文本。

        Returns:
            str | None: 清理后的文本。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_operator(self) -> Self:
        """校验几何编辑操作人必填。

        Returns:
            Self: 通过校验的请求。
        """
        if not self.operator_code:
            raise ValueError("操作人编码不得为空")
        return self


class PlotDeleteRequest(BaseModel):
    """图斑软删除请求。"""

    operator_code: str = Field(min_length=1, max_length=50)
    comment: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "comment")
    @classmethod
    def validate_delete_text(cls, value: str) -> str:
        """校验删除操作人和原因。

        Args:
            value: 原始文本。

        Returns:
            str: 非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("删除操作人和原因不得为空")
        return normalized


class PlotSplitRequest(BaseModel):
    """使用 WGS84 分割线拆分单个任务图斑。"""

    cutter: LineStringGeometry
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "comment")
    @classmethod
    def normalize_split_text(cls, value: str) -> str:
        """清理并校验分割操作人和判读依据。

        Args:
            value: 原始文本。

        Returns:
            str: 非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("分割操作人和判读依据不得为空")
        return normalized


class PlotAttributesResponse(BaseModel):
    """解译图斑业务属性响应。"""

    plot_code: str
    owner_village: str | None
    area_ha: float | None
    land_class: str | None
    crop_type: str | None
    planting_mode: str | None
    irrigation_condition: str | None
    custom_attributes: dict[str, object]
    source_name: str | None = None
    source_feature_id: str | None = None
    source_uri: str | None = None
    source_version: str | None = None
    source_updated_at: datetime | None = None
    province_name: str | None = None
    city_name: str | None = None
    district_name: str | None = None
    district_code: str | None = None
    interpretation_status: str
    version: int
    updated_at: datetime


class PlotSplitResponse(BaseModel):
    """图斑分割事务结果。"""

    operation_code: str
    task_code: str
    source_plot_code: str
    result_plots: list[PlotAttributesResponse]
    source_area_ha: float
    result_area_ha: float
    area_difference_ha: float
    total_plot_count: int
    completed_plot_count: int
    quality_recheck_required: bool = True


class PlotMergeRequest(PlotAttributeUpdateRequest):
    """显式选择多个任务图斑并确认合并后属性。"""

    plot_codes: list[str] = Field(min_length=2, max_length=20)
    owner_village: str = Field(min_length=1, max_length=100)
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=1, max_length=500)

    @field_validator("plot_codes")
    @classmethod
    def validate_merge_plot_codes(cls, values: list[str]) -> list[str]:
        """校验合并图斑编号格式并保持显式选择顺序。

        Args:
            values: 用户选择的图斑编号。

        Returns:
            list[str]: 去重后的合法图斑编号。
        """
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            plot_code = value.strip()
            if not plot_code or len(plot_code) > 50:
                raise ValueError("合并图斑编号长度必须为 1 到 50 个字符")
            if not re.fullmatch(r"[\w-]+", plot_code):
                raise ValueError(f"图斑编号 {plot_code} 格式不合法")
            if plot_code not in seen:
                normalized.append(plot_code)
                seen.add(plot_code)
        if len(normalized) < 2:
            raise ValueError("合并至少需要两个不同图斑")
        return normalized

    @field_validator("owner_village", "operator_code", "comment")
    @classmethod
    def normalize_merge_text(cls, value: str) -> str:
        """清理并校验合并属性和操作依据文本。

        Args:
            value: 原始文本。

        Returns:
            str: 非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("合并权属村、操作人和依据不得为空")
        return normalized


class PlotMergeResponse(BaseModel):
    """图斑合并事务结果。"""

    operation_code: str
    task_code: str
    source_plot_codes: list[str]
    result_plot: PlotAttributesResponse
    source_area_ha: float
    result_area_ha: float
    area_difference_ha: float
    total_plot_count: int
    completed_plot_count: int
    quality_recheck_required: bool = True


class PlotOperationSummary(BaseModel):
    """工具栏撤销或重做候选操作摘要。"""

    operation_code: str
    operation_type: Literal["split", "merge"]
    source_plot_codes: list[str]
    result_plot_codes: list[str]


class PlotOperationHistoryStateResponse(BaseModel):
    """任务当前可撤销和可重做状态。"""

    can_undo: bool
    can_redo: bool
    undo_operation: PlotOperationSummary | None = None
    redo_operation: PlotOperationSummary | None = None


class PlotHistoryActionRequest(BaseModel):
    """撤销或重做操作请求。"""

    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "comment")
    @classmethod
    def normalize_history_action_text(cls, value: str) -> str:
        """清理撤销/重做操作人和依据文本。

        Args:
            value: 原始文本。

        Returns:
            str: 非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("撤销或重做的操作人和依据不得为空")
        return normalized


class PlotHistoryActionResponse(BaseModel):
    """撤销或重做执行结果。"""

    action: Literal["undo", "redo"]
    operation: PlotOperationSummary
    active_plot_codes: list[str]
    inactive_plot_codes: list[str]
    total_plot_count: int
    completed_plot_count: int
    quality_recheck_required: bool = True


class QualityRuleResult(BaseModel):
    """单条质量规则检查结果。"""

    rule_code: str
    label: str
    status: str
    severity: str
    detail: str
    blocking: bool = False


class QualityCheckResponse(BaseModel):
    """图斑质量检查结果。"""

    plot_code: str
    score: int
    can_submit: bool
    checked_plot_count: int
    total_plot_count: int
    passing_plot_count: int
    rules: list[QualityRuleResult]


class TaskQualityCheckRequest(BaseModel):
    """任务级全量质量检查请求。"""

    operator_code: str = Field(min_length=1, max_length=50)
    comment: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "comment")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """清理操作人和执行说明文本。

        Args:
            value: 原始文本。

        Returns:
            str | None: 清理后的文本。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_operator(self) -> Self:
        """校验任务级质检操作人必填。

        Returns:
            Self: 通过校验的请求。
        """
        if not self.operator_code:
            raise ValueError("操作人编码不得为空")
        return self


class PlotQualityCheckRequest(BaseModel):
    """单图质量检查操作人请求。"""

    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code")
    @classmethod
    def validate_operator_code(cls, value: str) -> str:
        """清理单图质检操作人编码。

        Args:
            value: 项目用户稳定编码。

        Returns:
            str: 去除首尾空格的用户编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人编码不得为空")
        return normalized


class QualityRuleSummary(BaseModel):
    """任务级质量规则汇总。"""

    rule_code: str
    label: str
    pass_count: int
    warning_count: int
    fail_count: int
    blocking_issue_count: int


class TaskQualityCheckResponse(BaseModel):
    """任务级全量质量检查执行结果。"""

    task_code: str
    total_plot_count: int
    checked_plot_count: int
    passing_plot_count: int
    failed_plot_count: int
    average_score: float | None
    issue_count: int
    can_submit: bool
    duration_ms: int
    executed_at: datetime
    rule_summaries: list[QualityRuleSummary]


class QualityIssueItem(BaseModel):
    """任务质量问题及关联图斑上下文。"""

    id: int
    plot_code: str | None
    rule_code: str
    rule_label: str
    issue_type: str
    severity: str
    description: str
    status: str
    source: str
    assignee: str | None
    resolved_by: str | None
    resolved_by_code: str | None
    resolved_by_role: str | None
    resolution_comment: str | None
    created_at: datetime
    resolved_at: datetime | None
    plot_version: int | None
    city_name: str | None
    district_name: str | None
    owner_village: str | None
    land_class: str | None
    crop_type: str | None
    area_ha: float | None


class QualityIssueResolveRequest(BaseModel):
    """人工审核问题确认关闭请求。"""

    operator_code: str
    comment: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "comment")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """校验操作人编码和关闭依据。

        Args:
            value: 待清理文本。

        Returns:
            str: 非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人编码和关闭依据不得为空")
        return normalized


class QualityIssueResolveResponse(BaseModel):
    """人工审核问题关闭结果。"""

    issue_id: int
    status: str
    resolved_by: str
    resolved_by_code: str
    resolved_by_role: str
    resolution_comment: str
    resolved_at: datetime


class QualityIssueRuleCount(BaseModel):
    """质量问题按规则的数量汇总。"""

    rule_code: str
    rule_label: str
    total_count: int
    open_count: int


class QualityIssueListResponse(BaseModel):
    """任务质量问题分页响应。"""

    task_code: str
    page: int
    page_size: int
    total_count: int
    open_count: int
    resolved_count: int
    high_count: int
    medium_count: int
    low_count: int
    rule_counts: list[QualityIssueRuleCount]
    items: list[QualityIssueItem]


class ProjectSummary(BaseModel):
    """当前遥感监测项目摘要。"""

    project_code: str
    project_name: str
    province: str
    monitor_year: int
    status: str
    progress: float
    deadline: date | None

    model_config = ConfigDict(from_attributes=True)


class TaskSummary(BaseModel):
    """当前作业任务摘要。"""

    task_code: str
    task_name: str
    administrative_region: str
    assignee: str | None
    status: str
    total_plots: int
    completed_plots: int
    quality_score: float | None
    deadline: date | None

    model_config = ConfigDict(from_attributes=True)


class ImagerySummary(BaseModel):
    """当前遥感影像元数据摘要。"""

    asset_code: str
    asset_name: str
    sensor_type: str
    acquired_at: datetime
    cloud_cover: float | None
    resolution_m: float | None
    processing_level: str | None
    calibration_status: str
    correction_status: str

    model_config = ConfigDict(from_attributes=True)


class ReviewRecordResponse(BaseModel):
    """审核与操作历史响应。"""

    review_level: str
    action: str
    reviewer: str
    reviewer_code: str | None
    reviewer_role: str | None
    comment: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkbenchStatistics(BaseModel):
    """工作台业务统计。"""

    plot_count: int
    interpreted_count: int
    open_issue_count: int
    review_record_count: int
    current_cycle_review_count: int
    operational_imagery_count: int
    pending_disaster_count: int
    pending_field_verification_count: int


class WorkflowStageResponse(BaseModel):
    """项目总览中的可验证业务阶段。"""

    code: Literal[
        "imagery",
        "interpretation",
        "quality",
        "field",
        "review",
        "delivery",
    ]
    label: str
    status: Literal["pending", "active", "blocked", "completed"]
    progress: float = Field(ge=0, le=100)
    detail: str


class WorkbenchWorkflowResponse(BaseModel):
    """由当前任务证据计算的全流程状态。"""

    progress: float = Field(ge=0, le=100)
    current_stage: str
    stages: list[WorkflowStageResponse]


class WorkbenchOverviewResponse(BaseModel):
    """遥感监测工作台初始化数据。"""

    project: ProjectSummary
    task: TaskSummary
    imagery: ImagerySummary | None
    statistics: WorkbenchStatistics
    workflow: WorkbenchWorkflowResponse
    reviews: list[ReviewRecordResponse]


class TaskSubmitRequest(BaseModel):
    """任务提交自检请求。"""

    reviewer_code: str
    comment: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("reviewer_code")
    @classmethod
    def validate_reviewer_code(cls, value: str) -> str:
        """校验提交人稳定编码。

        Args:
            value: 项目用户编码。

        Returns:
            str: 清理后的提交人姓名。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("提交人编码不得为空")
        return normalized
