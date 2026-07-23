"""无人机航空器、任务、实体成果、疑点和状态协议。"""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AircraftStatus = Literal["active", "maintenance", "retired"]
ArtifactType = Literal[
    "raw_imagery",
    "flight_log",
    "photo",
    "video",
    "orthomosaic",
    "dem",
    "report",
]
MissionAction = Literal[
    "start",
    "complete_capture",
    "complete_processing",
    "complete_review",
    "cancel",
]
FindingSeverity = Literal["minor", "major", "critical"]
FindingDecision = Literal["confirm", "dismiss"]


def require_timezone(value: datetime) -> datetime:
    """要求时间包含时区。

    Args:
        value: 待校验时间。

    Returns:
        datetime: 带时区时间。
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("无人机业务时间必须包含时区")
    return value


class AircraftCreateRequest(BaseModel):
    """登记航空器和挂载传感器身份。"""

    aircraft_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    aircraft_name: str = Field(min_length=2, max_length=200)
    manufacturer: str = Field(min_length=1, max_length=150)
    model_number: str = Field(min_length=1, max_length=100)
    serial_number: str = Field(min_length=1, max_length=120)
    registration_number: str = Field(min_length=1, max_length=120)
    sensor_name: str = Field(min_length=1, max_length=150)
    sensor_model: str = Field(min_length=1, max_length=120)
    sensor_serial_number: str = Field(min_length=1, max_length=120)
    owner_department: str = Field(min_length=2, max_length=200)
    status: AircraftStatus = "active"
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")


class MissionCreateRequest(BaseModel):
    """创建带真实县区范围和飞手资质的无人机任务。"""

    mission_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    mission_name: str = Field(min_length=2, max_length=200)
    aircraft_code: str = Field(min_length=1, max_length=80)
    district_code: str = Field(min_length=1, max_length=50)
    flight_boundary: dict
    pilot_name: str = Field(min_length=2, max_length=100)
    pilot_license_number: str = Field(min_length=1, max_length=120)
    planned_start_at: datetime
    planned_end_at: datetime
    altitude_m: float = Field(gt=0, le=10_000)
    expected_resolution_cm: float = Field(gt=0, le=1000)
    forward_overlap_percent: float = Field(ge=0, le=100)
    side_overlap_percent: float = Field(ge=0, le=100)
    weather_note: str = Field(min_length=2, max_length=2000)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("planned_start_at", "planned_end_at")
    @classmethod
    def validate_times(cls, value: datetime) -> datetime:
        """校验计划时间包含时区。

        Args:
            value: 计划时间。

        Returns:
            datetime: 带时区计划时间。
        """
        return require_timezone(value)

    @field_validator("flight_boundary")
    @classmethod
    def validate_boundary(cls, value: dict) -> dict:
        """校验 WGS84 单 Polygon 飞行范围。

        Args:
            value: GeoJSON 几何对象。

        Returns:
            dict: 校验通过的 Polygon。
        """
        if value.get("type") != "Polygon":
            raise ValueError("飞行范围必须是 GeoJSON Polygon")
        coordinates = value.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 1:
            raise ValueError("飞行范围当前只接受一个无内环 Polygon")
        ring = coordinates[0]
        if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("飞行范围外环必须闭合且至少包含四个坐标")
        for coordinate in ring:
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                raise ValueError("飞行范围坐标结构不合法")
            longitude, latitude = coordinate[:2]
            if not isinstance(longitude, int | float) or not isinstance(
                latitude,
                int | float,
            ):
                raise ValueError("飞行范围坐标必须是数值")
            if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                raise ValueError("飞行范围必须使用合法 WGS84 经纬度")
        return value

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        """校验计划时间和航向/旁向重叠度。

        Returns:
            Self: 校验通过的任务。
        """
        if self.planned_end_at <= self.planned_start_at:
            raise ValueError("计划结束时间必须晚于开始时间")
        if self.forward_overlap_percent < 50 or self.side_overlap_percent < 30:
            raise ValueError("航向重叠度不得低于 50%，旁向重叠度不得低于 30%")
        return self


class ArtifactUploadRequest(BaseModel):
    """上传并登记无人机任务实体成果。"""

    artifact_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    artifact_type: ArtifactType
    captured_at: datetime | None = None
    source_name: str = Field(min_length=1, max_length=120)
    source_version: str = Field(min_length=1, max_length=80)
    metadata: dict = Field(default_factory=dict)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("captured_at")
    @classmethod
    def validate_captured_at(cls, value: datetime | None) -> datetime | None:
        """校验可选采集时间。

        Args:
            value: 采集时间或空值。

        Returns:
            datetime | None: 带时区时间或空值。
        """
        return require_timezone(value) if value else None


class MissionStatusRequest(BaseModel):
    """请求执行受控无人机任务状态动作。"""

    action: MissionAction
    comment: str = Field(min_length=2, max_length=2000)
    actual_time: datetime | None = None
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("actual_time")
    @classmethod
    def validate_actual_time(cls, value: datetime | None) -> datetime | None:
        """校验可选实际时间。

        Args:
            value: 实际时间或空值。

        Returns:
            datetime | None: 带时区时间或空值。
        """
        return require_timezone(value) if value else None

    @model_validator(mode="after")
    def validate_cancel_reason(self) -> Self:
        """要求取消动作提供明确原因。

        Returns:
            Self: 校验通过的状态请求。
        """
        if self.action == "cancel" and len(self.comment.strip()) < 8:
            raise ValueError("取消任务必须填写不少于 8 个字符的原因")
        return self


class FindingCreateRequest(BaseModel):
    """登记无人机影像或现场证据发现的空间疑点。"""

    finding_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    artifact_code: str = Field(min_length=1, max_length=80)
    finding_type: str = Field(min_length=2, max_length=60)
    severity: FindingSeverity
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    plot_code: str | None = Field(default=None, max_length=50)
    description: str = Field(min_length=4, max_length=3000)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("plot_code")
    @classmethod
    def normalize_plot_code(cls, value: str | None) -> str | None:
        """清理可选图斑编号。

        Args:
            value: 原始编号。

        Returns:
            str | None: 标准化编号或空值。
        """
        return value.strip() or None if value is not None else None


class MobileUavCaptureRequest(BaseModel):
    """移动端一次提交 GPS、现场照片和空间疑点。"""

    capture_code: str = Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    captured_at: datetime
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    location_accuracy_m: float = Field(gt=0, le=10_000)
    finding_type: str = Field(min_length=2, max_length=60)
    severity: FindingSeverity
    plot_code: str | None = Field(default=None, max_length=50)
    description: str = Field(min_length=4, max_length=3000)
    device_label: str = Field(default="浏览器移动终端", min_length=1, max_length=100)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("captured_at")
    @classmethod
    def validate_mobile_capture_time(cls, value: datetime) -> datetime:
        """校验移动采集时间包含时区。

        Args:
            value: 终端采集时间。

        Returns:
            datetime: 带时区采集时间。
        """
        return require_timezone(value)

    @field_validator("finding_type", "description", "device_label", "operator_code")
    @classmethod
    def normalize_mobile_text(cls, value: str) -> str:
        """清理移动采集文本。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空白的文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("移动采集文本不得为空")
        return normalized

    @field_validator("plot_code")
    @classmethod
    def normalize_mobile_plot_code(cls, value: str | None) -> str | None:
        """清理移动端可选图斑编号。

        Args:
            value: 原始图斑编号。

        Returns:
            str | None: 标准化编号或空值。
        """
        return value.strip() or None if value is not None else None


class FindingReviewRequest(BaseModel):
    """人工确认或排除无人机疑点。"""

    decision: FindingDecision
    comment: str = Field(min_length=4, max_length=2000)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")


class AircraftResponse(BaseModel):
    """无人机航空器响应。"""

    aircraft_code: str
    aircraft_name: str
    manufacturer: str
    model_number: str
    serial_number: str
    registration_number: str
    sensor_name: str
    sensor_model: str
    sensor_serial_number: str
    owner_department: str
    certificate_uri: str
    certificate_filename: str
    certificate_size_bytes: int
    certificate_sha256: str
    status: str
    registered_by: str
    registered_by_code: str
    registered_by_role: str
    created_at: datetime


class MissionResponse(BaseModel):
    """无人机飞行任务响应。"""

    mission_code: str
    mission_name: str
    task_code: str
    aircraft_code: str
    aircraft_name: str
    district_code: str
    district_name: str
    flight_boundary: dict
    planned_area_ha: float
    pilot_name: str
    pilot_license_number: str
    pilot_license_uri: str
    pilot_license_filename: str
    pilot_license_size_bytes: int
    pilot_license_sha256: str
    planned_start_at: datetime
    planned_end_at: datetime
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    altitude_m: float
    expected_resolution_cm: float
    forward_overlap_percent: float
    side_overlap_percent: float
    weather_note: str
    status: str
    cancellation_reason: str | None
    created_by: str
    created_by_code: str
    created_by_role: str
    created_at: datetime


class ArtifactResponse(BaseModel):
    """无人机实体成果响应。"""

    mission_code: str
    artifact_code: str
    artifact_type: str
    original_filename: str
    file_uri: str
    file_size_bytes: int
    checksum_sha256: str
    captured_at: datetime | None
    file_format: str
    crs: str | None
    resolution_cm: float | None
    raster_width: int | None
    raster_height: int | None
    footprint: dict | None
    metadata: dict
    verification_status: str
    uploaded_by: str
    uploaded_by_code: str
    uploaded_by_role: str
    created_at: datetime


class FindingResponse(BaseModel):
    """无人机空间疑点及人工复核响应。"""

    mission_code: str
    artifact_code: str
    finding_code: str
    finding_type: str
    severity: str
    longitude: float
    latitude: float
    plot_code: str | None
    description: str
    status: str
    created_by: str
    created_by_code: str
    created_by_role: str
    review_comment: str | None
    reviewed_by: str | None
    reviewed_by_code: str | None
    reviewed_by_role: str | None
    reviewed_at: datetime | None
    created_at: datetime


class MobileUavCaptureResponse(BaseModel):
    """原子移动采集结果。"""

    capture_code: str
    artifact: ArtifactResponse
    finding: FindingResponse
    idempotent_replay: bool


class MobileUavCaptureOverviewResponse(BaseModel):
    """移动端可执行飞行任务轻量总览。"""

    project_code: str
    mission_count: int
    missions: list[MissionResponse]


class UavEventResponse(BaseModel):
    """无人机不可变审计事件响应。"""

    entity_type: str
    entity_code: str
    event_type: str
    detail: dict
    actor: str
    actor_code: str
    actor_role: str
    created_at: datetime


class UavOverviewResponse(BaseModel):
    """无人机任务工作台总览。"""

    aircraft_count: int
    mission_count: int
    active_mission_count: int
    pending_processing_count: int
    pending_finding_count: int
    verified_artifact_count: int
    aircraft: list[AircraftResponse]
    missions: list[MissionResponse]
    artifacts: list[ArtifactResponse]
    findings: list[FindingResponse]
    events: list[UavEventResponse]
