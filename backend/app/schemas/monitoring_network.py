"""田间监测网络、病虫害识别复核与告警协议。"""

import re
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StationType = Literal["weather", "soil", "crop", "pest", "comprehensive"]
StationStatus = Literal["active", "maintenance", "retired"]
DeviceType = Literal[
    "weather_sensor",
    "soil_sensor",
    "camera",
    "insect_trap",
    "spore_trap",
    "gateway",
    "other",
]
DeviceStatus = Literal["online", "offline", "abnormal", "maintenance", "retired"]
FaultSeverity = Literal["minor", "major", "critical"]
TargetType = Literal["pest", "disease"]
ReviewDecision = Literal["approve", "reject"]
RiskLevel = Literal["low", "medium", "high", "critical"]
AlertChannel = Literal["platform", "sms", "email", "mobile"]


def normalize_checksum(value: str) -> str:
    """校验 SHA-256 文本。

    Args:
        value: 原始十六进制校验值。

    Returns:
        str: 小写 SHA-256。
    """
    normalized = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError("SHA-256 必须是 64 位十六进制字符串")
    return normalized


def require_timezone(value: datetime) -> datetime:
    """要求业务时间包含时区。

    Args:
        value: 待校验时间。

    Returns:
        datetime: 带时区时间。
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("业务时间必须包含时区")
    return value


class StationCreateRequest(BaseModel):
    """登记真实田间监测站。"""

    station_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    station_name: str = Field(min_length=2, max_length=200)
    district_code: str = Field(min_length=1, max_length=50)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    station_type: StationType
    owner_department: str = Field(min_length=2, max_length=200)
    source_name: str = Field(min_length=2, max_length=120)
    source_uri: str = Field(min_length=1, max_length=500)
    source_version: str = Field(min_length=1, max_length=80)
    evidence_uri: str = Field(min_length=1, max_length=500)
    evidence_size_bytes: int = Field(gt=0)
    evidence_sha256: str
    status: StationStatus = "active"
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "station_name",
        "district_code",
        "owner_department",
        "source_name",
        "source_uri",
        "source_version",
        "evidence_uri",
        "operator_code",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理站点文本字段。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("站点字段不得为空")
        return normalized

    @field_validator("evidence_sha256")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        """校验站点实体证据 SHA-256。

        Args:
            value: 原始校验值。

        Returns:
            str: 标准化校验值。
        """
        return normalize_checksum(value)


class DeviceCreateRequest(BaseModel):
    """在真实监测站下登记设备。"""

    device_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    device_name: str = Field(min_length=2, max_length=200)
    device_type: DeviceType
    vendor: str = Field(min_length=1, max_length=150)
    model_number: str = Field(min_length=1, max_length=100)
    serial_number: str = Field(min_length=1, max_length=120)
    owner_department: str = Field(min_length=2, max_length=200)
    installed_at: datetime
    photo_uri: str = Field(min_length=1, max_length=500)
    photo_size_bytes: int = Field(gt=0)
    photo_sha256: str
    status: DeviceStatus = "offline"
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("installed_at")
    @classmethod
    def validate_installed_at(cls, value: datetime) -> datetime:
        """校验设备安装时间。

        Args:
            value: 安装时间。

        Returns:
            datetime: 带时区时间。
        """
        return require_timezone(value)

    @field_validator("photo_sha256")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        """校验设备照片 SHA-256。

        Args:
            value: 原始校验值。

        Returns:
            str: 标准化校验值。
        """
        return normalize_checksum(value)


class TelemetryCreateRequest(BaseModel):
    """幂等写入一条设备遥测或图像观测。"""

    idempotency_key: str = Field(
        min_length=8,
        max_length=120,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    observed_at: datetime
    metric_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    metric_value: float | None = None
    metric_unit: str | None = Field(default=None, max_length=40)
    payload: dict = Field(default_factory=dict)
    evidence_uri: str | None = Field(default=None, max_length=500)
    evidence_size_bytes: int | None = Field(default=None, gt=0)
    evidence_sha256: str | None = None
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        """校验观测时间。

        Args:
            value: 观测时间。

        Returns:
            datetime: 带时区观测时间。
        """
        return require_timezone(value)

    @field_validator("evidence_sha256")
    @classmethod
    def validate_checksum(cls, value: str | None) -> str | None:
        """校验可选遥测证据 SHA-256。

        Args:
            value: 原始校验值或空值。

        Returns:
            str | None: 标准化校验值或空值。
        """
        return normalize_checksum(value) if value else None

    @model_validator(mode="after")
    def validate_payload_and_evidence(self) -> Self:
        """校验数值/载荷和实体证据字段完整性。

        Returns:
            Self: 校验通过的请求。
        """
        if self.metric_value is None and not self.payload:
            raise ValueError("遥测必须提供数值或非空原始载荷")
        evidence_fields = (
            self.evidence_uri,
            self.evidence_size_bytes,
            self.evidence_sha256,
        )
        if any(value is not None for value in evidence_fields) and not all(
            value is not None for value in evidence_fields
        ):
            raise ValueError("遥测实体证据地址、大小和 SHA-256 必须同时提供")
        return self


class FaultCreateRequest(BaseModel):
    """登记设备故障并将设备标记为异常。"""

    fault_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    severity: FaultSeverity
    reason: str = Field(min_length=4, max_length=2000)
    occurred_at: datetime
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        """校验故障发生时间。

        Args:
            value: 故障发生时间。

        Returns:
            datetime: 带时区故障时间。
        """
        return require_timezone(value)


class FaultResolveRequest(BaseModel):
    """提交设备故障处置结论与实体证据。"""

    resolution_comment: str = Field(min_length=4, max_length=2000)
    resolution_evidence_uri: str = Field(min_length=1, max_length=500)
    resolution_evidence_size_bytes: int = Field(gt=0)
    resolution_evidence_sha256: str
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("resolution_evidence_sha256")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        """校验处置证据 SHA-256。

        Args:
            value: 原始校验值。

        Returns:
            str: 标准化校验值。
        """
        return normalize_checksum(value)


class PestModelCreateRequest(BaseModel):
    """登记可审计的病虫害模型实体版本。"""

    model_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    model_version: str = Field(min_length=1, max_length=80)
    model_name: str = Field(min_length=2, max_length=200)
    target_type: TargetType
    deployment_target: str = Field(min_length=2, max_length=120)
    training_source_uri: str = Field(min_length=1, max_length=500)
    evaluation_source_uri: str = Field(min_length=1, max_length=500)
    artifact_uri: str = Field(min_length=1, max_length=500)
    artifact_size_bytes: int = Field(gt=0)
    artifact_sha256: str
    accuracy: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1_score: float = Field(ge=0, le=1)
    roc_auc: float = Field(ge=0, le=1)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("artifact_sha256")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        """校验模型实体 SHA-256。

        Args:
            value: 原始校验值。

        Returns:
            str: 标准化校验值。
        """
        return normalize_checksum(value)


class AssessmentCreateRequest(BaseModel):
    """登记模型识别结果，等待人工复核。"""

    assessment_code: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    device_code: str | None = Field(default=None, max_length=80)
    model_code: str = Field(min_length=1, max_length=80)
    model_version: str = Field(min_length=1, max_length=80)
    observed_at: datetime
    input_uri: str = Field(min_length=1, max_length=500)
    input_size_bytes: int = Field(gt=0)
    input_sha256: str
    input_summary: dict = Field(default_factory=dict)
    target_name: str = Field(min_length=1, max_length=150)
    prediction_label: str = Field(min_length=1, max_length=150)
    confidence: float = Field(ge=0, le=1)
    prediction_basis: str = Field(min_length=8, max_length=3000)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        """校验识别观测时间。

        Args:
            value: 观测时间。

        Returns:
            datetime: 带时区观测时间。
        """
        return require_timezone(value)

    @field_validator("input_sha256")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        """校验模型输入 SHA-256。

        Args:
            value: 原始校验值。

        Returns:
            str: 标准化校验值。
        """
        return normalize_checksum(value)


class AssessmentReviewRequest(BaseModel):
    """人工批准或驳回模型识别结果。"""

    decision: ReviewDecision
    comment: str = Field(min_length=4, max_length=2000)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")


class AlertCreateRequest(BaseModel):
    """基于已批准识别结果创建待发送告警。"""

    alert_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    risk_level: RiskLevel
    message: str = Field(min_length=8, max_length=3000)
    channels: list[AlertChannel] = Field(min_length=1, max_length=4)
    recipients: list[str] = Field(min_length=1, max_length=100)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("channels", "recipients")
    @classmethod
    def unique_values(cls, values: list[str]) -> list[str]:
        """去重告警渠道和接收对象。

        Args:
            values: 原始列表。

        Returns:
            list[str]: 标准化唯一列表。
        """
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        if not result:
            raise ValueError("告警渠道和接收对象不得为空")
        return result


class AlertDeliverRequest(BaseModel):
    """登记告警实际送达回执。"""

    delivery_receipt_uri: str = Field(min_length=1, max_length=500)
    delivery_receipt_size_bytes: int = Field(gt=0)
    delivery_receipt_sha256: str
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("delivery_receipt_sha256")
    @classmethod
    def validate_checksum(cls, value: str) -> str:
        """校验告警送达回执 SHA-256。

        Args:
            value: 原始校验值。

        Returns:
            str: 标准化校验值。
        """
        return normalize_checksum(value)


class StationResponse(BaseModel):
    """田间监测站响应。"""

    station_code: str
    station_name: str
    province_code: str
    province_name: str
    city_code: str
    city_name: str
    district_code: str
    district_name: str
    longitude: float
    latitude: float
    station_type: str
    owner_department: str
    source_name: str
    source_uri: str
    source_version: str
    evidence_uri: str
    evidence_size_bytes: int
    evidence_sha256: str
    status: str
    registered_by: str
    registered_by_code: str
    registered_by_role: str
    created_at: datetime


class DeviceResponse(BaseModel):
    """监测设备响应。"""

    station_code: str
    device_code: str
    device_name: str
    device_type: str
    vendor: str
    model_number: str
    serial_number: str
    owner_department: str
    installed_at: datetime
    photo_uri: str
    photo_size_bytes: int
    photo_sha256: str
    status: str
    last_telemetry_at: datetime | None
    registered_by: str
    registered_by_code: str
    registered_by_role: str
    created_at: datetime


class TelemetryResponse(BaseModel):
    """设备遥测响应。"""

    device_code: str
    idempotency_key: str
    observed_at: datetime
    metric_code: str
    metric_value: float | None
    metric_unit: str | None
    payload: dict
    evidence_uri: str | None
    evidence_size_bytes: int | None
    evidence_sha256: str | None
    ingested_by: str
    ingested_by_code: str
    ingested_by_role: str
    received_at: datetime


class FaultResponse(BaseModel):
    """设备故障响应。"""

    device_code: str
    fault_code: str
    severity: str
    reason: str
    occurred_at: datetime
    status: str
    reported_by: str
    reported_by_code: str
    reported_by_role: str
    resolution_comment: str | None
    resolution_evidence_uri: str | None
    resolved_by: str | None
    resolved_by_code: str | None
    resolved_by_role: str | None
    resolved_at: datetime | None
    created_at: datetime


class PestModelResponse(BaseModel):
    """病虫害模型版本响应。"""

    model_code: str
    model_version: str
    model_name: str
    target_type: str
    deployment_target: str
    training_source_uri: str
    evaluation_source_uri: str
    artifact_uri: str
    artifact_size_bytes: int
    artifact_sha256: str
    accuracy: float
    recall: float
    f1_score: float
    roc_auc: float
    status: str
    superseded_by_version: str | None
    registered_by: str
    registered_by_code: str
    registered_by_role: str
    created_at: datetime


class AssessmentResponse(BaseModel):
    """病虫害识别与复核响应。"""

    assessment_code: str
    device_code: str | None
    model_code: str
    model_version: str
    observed_at: datetime
    input_uri: str
    input_size_bytes: int
    input_sha256: str
    input_summary: dict
    target_name: str
    prediction_label: str
    confidence: float
    prediction_basis: str
    status: str
    submitted_by: str
    submitted_by_code: str
    submitted_by_role: str
    review_comment: str | None
    reviewed_by: str | None
    reviewed_by_code: str | None
    reviewed_by_role: str | None
    reviewed_at: datetime | None
    created_at: datetime


class AlertResponse(BaseModel):
    """病虫害告警响应。"""

    alert_code: str
    assessment_code: str
    risk_level: str
    message: str
    channels: list[str]
    recipients: list[str]
    status: str
    created_by: str
    created_by_code: str
    created_by_role: str
    delivery_receipt_uri: str | None
    delivery_receipt_size_bytes: int | None
    delivery_receipt_sha256: str | None
    delivered_by: str | None
    delivered_by_code: str | None
    delivered_by_role: str | None
    delivered_at: datetime | None
    created_at: datetime


class MonitoringEventResponse(BaseModel):
    """监测网络不可变审计事件响应。"""

    entity_type: str
    entity_code: str
    event_type: str
    detail: dict
    actor: str
    actor_code: str
    actor_role: str
    created_at: datetime


class MonitoringOverviewResponse(BaseModel):
    """田间监测网络与病虫害预警总览。"""

    station_count: int
    device_count: int
    online_device_count: int
    abnormal_device_count: int
    telemetry_count: int
    open_fault_count: int
    active_model_count: int
    pending_assessment_count: int
    pending_alert_count: int
    stations: list[StationResponse]
    devices: list[DeviceResponse]
    telemetry: list[TelemetryResponse]
    faults: list[FaultResponse]
    models: list[PestModelResponse]
    assessments: list[AssessmentResponse]
    alerts: list[AlertResponse]
    events: list[MonitoringEventResponse]
