"""独立监理计划、检查、问题整改、复检、县区评价和报告协议。"""

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SamplingMethod = Literal["systematic", "stratified_random"]
PlanStatus = Literal["active", "completed", "cancelled"]
InspectionStage = Literal[
    "imagery_processing",
    "plot_interpretation",
    "quality_control",
    "field_verification",
    "review_delivery",
]
InspectionConclusion = Literal["passed", "conditional", "failed"]
FindingSeverity = Literal["minor", "major", "critical"]
FindingStatus = Literal[
    "open",
    "rectification_submitted",
    "rework_required",
    "closed",
]
ReinspectionResult = Literal["passed", "failed"]


class SupervisionPlanCreateRequest(BaseModel):
    """创建绑定任务快照和真实图斑样本的监理计划。"""

    plan_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    plan_name: str = Field(min_length=1, max_length=200)
    sampling_method: SamplingMethod
    sample_ratio: float = Field(ge=0.1, le=100)
    minimum_per_region: int = Field(default=3, ge=1, le=500)
    region_codes: list[str] = Field(min_length=1, max_length=122)
    planned_start_date: date
    planned_end_date: date
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("plan_name", "operator_code", "comment")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理计划文本字段。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("监理计划文本不得为空")
        return normalized

    @field_validator("region_codes")
    @classmethod
    def normalize_regions(cls, values: list[str]) -> list[str]:
        """去重并校验县区编码。

        Args:
            values: 原始县区编码。

        Returns:
            list[str]: 保持输入顺序的唯一县区编码。
        """
        normalized = [value.strip() for value in values if value.strip()]
        if not normalized:
            raise ValueError("至少选择一个县区")
        if len(normalized) != len(set(normalized)):
            raise ValueError("监理计划县区不得重复")
        return normalized

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        """校验监理计划日期顺序。

        Returns:
            Self: 校验通过的请求。
        """
        if self.planned_end_date < self.planned_start_date:
            raise ValueError("监理计划结束日期不得早于开始日期")
        return self


class SupervisionInspectionCreateRequest(BaseModel):
    """登记独立监理过程检查及实体证据引用。"""

    inspection_code: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    inspection_stage: InspectionStage
    inspected_at: datetime
    conclusion: InspectionConclusion
    evidence_uri: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=2000)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("evidence_uri", "summary", "operator_code")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理检查证据和说明。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("检查证据和说明不得为空")
        return normalized

    @field_validator("inspected_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """要求检查时间包含时区。

        Args:
            value: 检查时间。

        Returns:
            datetime: 带时区检查时间。
        """
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("检查时间必须包含时区")
        return value


class SupervisionFindingCreateRequest(BaseModel):
    """为过程检查登记需闭环的监理问题。"""

    finding_code: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    plot_code: str | None = Field(default=None, max_length=50)
    region_code: str = Field(min_length=1, max_length=50)
    issue_type: str = Field(min_length=1, max_length=60)
    severity: FindingSeverity
    description: str = Field(min_length=1, max_length=2000)
    evidence_uri: str = Field(min_length=1, max_length=500)
    rework_deadline: date
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("plot_code")
    @classmethod
    def normalize_optional_plot_code(cls, value: str | None) -> str | None:
        """清理可选样本图斑编号。

        Args:
            value: 原始图斑编号。

        Returns:
            str | None: 标准化图斑编号。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator(
        "region_code",
        "issue_type",
        "description",
        "evidence_uri",
        "operator_code",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """清理问题描述和证据字段。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("监理问题字段不得为空")
        return normalized


class SupervisionRectificationRequest(BaseModel):
    """生产团队提交监理问题整改证据。"""

    rectification_comment: str = Field(min_length=1, max_length=2000)
    rectification_evidence_uri: str = Field(min_length=1, max_length=500)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "rectification_comment",
        "rectification_evidence_uri",
        "operator_code",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理整改说明和证据。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("整改说明和证据不得为空")
        return normalized


class SupervisionReinspectionRequest(BaseModel):
    """独立监理对已提交整改的问题执行逐轮复检。"""

    result: ReinspectionResult
    comment: str = Field(min_length=1, max_length=2000)
    evidence_uri: str = Field(min_length=1, max_length=500)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("comment", "evidence_uri", "operator_code")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理复检说明和证据。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("复检说明和证据不得为空")
        return normalized


class SupervisionCountyEvaluationRequest(BaseModel):
    """独立监理提交县区量化评价。"""

    quality_score: float = Field(ge=0, le=100)
    timeliness_score: float = Field(ge=0, le=100)
    compliance_score: float = Field(ge=0, le=100)
    comment: str = Field(min_length=1, max_length=2000)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("comment", "operator_code")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理县区评价说明。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("县区评价说明不得为空")
        return normalized


class SupervisionReportGenerateRequest(BaseModel):
    """生成不可变监理实体报告。"""

    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "comment")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理报告生成操作审计字段。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("报告生成操作人和说明不得为空")
        return normalized


class SupervisionSampleResponse(BaseModel):
    """单个真实任务图斑监理样本。"""

    plot_code: str
    region_code: str
    region_name: str
    plot_version_snapshot: int
    selection_rank: int
    selected_at: datetime


class SupervisionSamplePageResponse(BaseModel):
    """监理样本分页响应。"""

    plan_code: str
    total: int
    page: int
    page_size: int
    items: list[SupervisionSampleResponse]


class SupervisionReinspectionResponse(BaseModel):
    """监理问题单轮复检记录。"""

    round_no: int
    result: ReinspectionResult
    comment: str
    evidence_uri: str
    inspector: str
    inspector_code: str
    inspector_role: str
    created_at: datetime


class SupervisionFindingResponse(BaseModel):
    """监理问题当前状态和全部复检轮次。"""

    finding_code: str
    plot_code: str | None
    region_code: str
    region_name: str
    issue_type: str
    severity: FindingSeverity
    description: str
    evidence_uri: str
    rework_deadline: date
    overdue: bool
    status: FindingStatus
    rectification_comment: str | None
    rectification_evidence_uri: str | None
    rectified_by: str | None
    rectified_by_code: str | None
    rectified_by_role: str | None
    rectified_at: datetime | None
    created_by: str
    created_by_code: str
    created_by_role: str
    created_at: datetime
    reinspections: list[SupervisionReinspectionResponse]


class SupervisionInspectionResponse(BaseModel):
    """独立监理过程检查及问题清单。"""

    inspection_code: str
    inspection_stage: InspectionStage
    inspected_at: datetime
    conclusion: InspectionConclusion
    evidence_uri: str
    summary: str
    inspector: str
    inspector_code: str
    inspector_role: str
    created_at: datetime
    findings: list[SupervisionFindingResponse]


class SupervisionCountyEvaluationResponse(BaseModel):
    """县区量化监理评价。"""

    region_code: str
    region_name: str
    quality_score: float
    timeliness_score: float
    compliance_score: float
    overall_score: float
    grade: str
    comment: str
    evaluated_by: str
    evaluated_by_code: str
    evaluated_by_role: str
    evaluated_at: datetime


class SupervisionReportResponse(BaseModel):
    """不可变监理报告文件证据。"""

    report_code: str
    file_uri: str
    file_size_bytes: int
    checksum_sha256: str
    evidence_manifest: dict
    generated_by: str
    generated_by_code: str
    generated_by_role: str
    generated_at: datetime
    download_url: str


class SupervisionEventResponse(BaseModel):
    """监理业务不可变事件。"""

    entity_type: str
    entity_code: str
    action: str
    previous_values: dict
    new_values: dict
    comment: str
    operator: str
    operator_code: str
    operator_role: str
    created_at: datetime


class SupervisionPlanResponse(BaseModel):
    """监理计划聚合状态。"""

    plan_code: str
    plan_name: str
    sampling_method: SamplingMethod
    sample_ratio: float
    minimum_per_region: int
    region_codes: list[str]
    region_sample_counts: dict[str, int]
    sample_count: int
    task_plot_count_snapshot: int
    task_updated_at_snapshot: datetime
    planned_start_date: date
    planned_end_date: date
    status: PlanStatus
    inspection_count: int
    finding_count: int
    open_finding_count: int
    overdue_finding_count: int
    evaluation_count: int
    created_by: str
    created_by_code: str
    created_by_role: str
    created_at: datetime
    updated_at: datetime
    inspections: list[SupervisionInspectionResponse]
    county_evaluations: list[SupervisionCountyEvaluationResponse]
    report: SupervisionReportResponse | None
    recent_events: list[SupervisionEventResponse]


class SupervisionMetricsResponse(BaseModel):
    """独立监理工作台实时指标。"""

    plan_count: int
    active_plan_count: int
    sampled_plot_count: int
    inspection_count: int
    open_finding_count: int
    overdue_finding_count: int
    completed_report_count: int


class SupervisionWorkAreaResponse(BaseModel):
    """可纳入监理计划的真实县区任务范围。"""

    city_code: str
    city_name: str
    region_code: str
    region_name: str
    plot_count: int
    area_ha: float


class SupervisionOverviewResponse(BaseModel):
    """独立监理计划、证据和真实空状态聚合。"""

    project_code: str
    task_code: str
    blockers: list[str]
    metrics: SupervisionMetricsResponse
    work_areas: list[SupervisionWorkAreaResponse]
    plans: list[SupervisionPlanResponse]
