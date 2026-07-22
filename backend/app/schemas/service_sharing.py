"""受控地图与数据共享服务请求和响应模型。"""

from datetime import date, datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ServiceType = Literal["stac", "wms", "wmts", "wfs", "rest", "download"]
ResourceType = Literal[
    "external_api",
    "imagery",
    "vector",
    "thematic_map",
    "delivery",
    "statistics",
    "other",
]
DataClassification = Literal["public", "internal", "confidential"]
ExposureScope = Literal["public", "project", "restricted"]
AuthMode = Literal["none", "api_key", "oauth2", "network_whitelist"]
ServiceReviewDecision = Literal["approve", "reject"]
AccessReviewDecision = Literal["approve", "reject"]


def validate_http_url(value: str) -> str:
    """校验并规范化 HTTP(S) 地址。

    Args:
        value: 待校验地址。

    Returns:
        str: 去除首尾空白的地址。
    """
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("地址必须是完整的 HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("地址中禁止包含用户名或密码")
    return normalized


class ServiceRegistrationRequest(BaseModel):
    """登记待甲方审批的地图或数据服务。"""

    service_code: str = Field(min_length=3, max_length=80)
    service_name: str = Field(min_length=2, max_length=200)
    service_type: ServiceType
    endpoint_url: str
    health_check_url: str
    documentation_url: str
    resource_type: ResourceType
    resource_code: str = Field(min_length=1, max_length=100)
    resource_checksum_sha256: str | None = None
    data_classification: DataClassification
    exposure_scope: ExposureScope
    auth_mode: AuthMode
    owner_department: str = Field(min_length=2, max_length=150)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("endpoint_url", "health_check_url", "documentation_url")
    @classmethod
    def validate_urls(cls, value: str) -> str:
        """校验服务、健康和文档 URL。

        Args:
            value: URL 文本。

        Returns:
            str: 已规范化 URL。
        """
        return validate_http_url(value)

    @field_validator("service_code", "resource_code", "operator_code")
    @classmethod
    def strip_codes(cls, value: str) -> str:
        """清理服务、资源和操作人编码。

        Args:
            value: 编码文本。

        Returns:
            str: 清理后的编码。
        """
        return value.strip()

    @field_validator("resource_checksum_sha256")
    @classmethod
    def validate_checksum(cls, value: str | None) -> str | None:
        """校验可选资源 SHA-256。

        Args:
            value: 十六进制校验值或空值。

        Returns:
            str | None: 小写校验值或空值。
        """
        if value is None:
            return None
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(
            char not in "0123456789abcdef" for char in normalized
        ):
            raise ValueError("资源 SHA-256 必须是 64 位十六进制字符串")
        return normalized

    @model_validator(mode="after")
    def validate_security_rules(self) -> "ServiceRegistrationRequest":
        """执行公开范围、密级、鉴权和实体校验业务规则。

        Returns:
            ServiceRegistrationRequest: 通过安全校验的请求。
        """
        if (
            self.data_classification == "confidential"
            and self.exposure_scope == "public"
        ):
            raise ValueError("涉密数据禁止登记为公共服务")
        if self.exposure_scope == "public" and not self.endpoint_url.startswith(
            "https://"
        ):
            raise ValueError("公共服务必须使用 HTTPS 地址")
        if self.exposure_scope != "public" and self.auth_mode == "none":
            raise ValueError("非公共服务必须配置访问鉴权")
        if self.resource_type != "external_api" and not self.resource_checksum_sha256:
            raise ValueError("内部成果发布必须绑定资源 SHA-256")
        return self


class ServiceReviewRequest(BaseModel):
    """甲方对服务登记执行审批。"""

    decision: ServiceReviewDecision
    comment: str = Field(min_length=4, max_length=1000)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")


class ServiceAccessRequestCreate(BaseModel):
    """项目成员申请服务访问。"""

    applicant_organization: str = Field(min_length=2, max_length=200)
    purpose: str = Field(min_length=8, max_length=2000)
    requested_until: date
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("requested_until")
    @classmethod
    def validate_requested_until(cls, value: date) -> date:
        """确保访问期限晚于当前日期。

        Args:
            value: 请求截止日期。

        Returns:
            date: 合法截止日期。
        """
        if value <= date.today():
            raise ValueError("访问截止日期必须晚于今天")
        return value


class ServiceAccessReviewRequest(BaseModel):
    """项目负责人审批访问申请并按需签发凭证。"""

    decision: AccessReviewDecision
    comment: str = Field(min_length=4, max_length=1000)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")


class ServiceHealthCheckRequest(BaseModel):
    """触发一次服务端真实健康探测。"""

    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")


class ServiceRevokeRequest(BaseModel):
    """撤销服务或单个访问凭证。"""

    reason: str = Field(min_length=8, max_length=1000)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")


class ServiceUsageRecordRequest(BaseModel):
    """由项目成员或 API Key 持有人上报一次真实调用结果。"""

    operator_code: str | None = Field(default=None, max_length=50)
    credential_code: str | None = Field(default=None, max_length=100)
    credential_secret: str | None = Field(default=None, max_length=500)
    request_method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
    request_path: str = Field(min_length=1, max_length=1000)
    response_status: int = Field(ge=100, le=599)
    duration_ms: int = Field(ge=0, le=3_600_000)
    response_bytes: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_identity(self) -> "ServiceUsageRecordRequest":
        """要求项目用户身份或完整 API Key 二选一。

        Returns:
            ServiceUsageRecordRequest: 身份字段完整的请求。
        """
        has_user = bool(self.operator_code)
        has_credential = bool(self.credential_code and self.credential_secret)
        if has_user == has_credential:
            raise ValueError("必须且只能提供项目用户身份或完整 API Key")
        return self


class ServiceHealthResponse(BaseModel):
    """单次服务健康检查响应。"""

    status: str
    http_status: int | None
    response_time_ms: int
    detail: str
    checked_by: str
    checked_at: datetime


class ServiceCredentialResponse(BaseModel):
    """不暴露密钥明文的访问凭证摘要。"""

    credential_code: str
    secret_last_four: str
    status: str
    issued_at: datetime
    expires_at: datetime


class ServiceAccessRequestResponse(BaseModel):
    """访问申请及其凭证摘要。"""

    request_code: str
    service_code: str
    applicant_organization: str
    purpose: str
    requested_until: date
    status: str
    applicant: str
    applicant_code: str
    applicant_role: str
    decision_comment: str | None
    created_at: datetime
    decided_at: datetime | None
    credential: ServiceCredentialResponse | None


class ServiceAccessReviewResponse(BaseModel):
    """访问审批结果；新密钥只在批准瞬间返回一次。"""

    request: ServiceAccessRequestResponse
    credential_secret: str | None


class SharedServiceResponse(BaseModel):
    """共享服务目录项。"""

    service_code: str
    service_name: str
    service_type: str
    endpoint_url: str
    health_check_url: str
    documentation_url: str
    resource_type: str
    resource_code: str
    resource_checksum_sha256: str | None
    data_classification: str
    exposure_scope: str
    auth_mode: str
    status: str
    owner_department: str
    registered_by: str
    registered_by_code: str
    registered_by_role: str
    reviewed_by: str | None
    review_comment: str | None
    created_at: datetime
    updated_at: datetime
    latest_health: ServiceHealthResponse | None
    access_request_count: int
    active_credential_count: int
    usage_count: int


class ServiceUsageEventResponse(BaseModel):
    """共享服务不可变审计事件。"""

    event_type: str
    service_code: str
    actor: str
    actor_code: str
    actor_role: str
    request_method: str | None
    request_path: str | None
    response_status: int | None
    duration_ms: int | None
    response_bytes: int | None
    detail: dict
    created_at: datetime


class ServiceSharingOverviewResponse(BaseModel):
    """共享服务、申请、凭证、健康和审计总览。"""

    project_code: str
    service_count: int
    active_service_count: int
    pending_approval_count: int
    pending_access_count: int
    healthy_service_count: int
    services: list[SharedServiceResponse]
    access_requests: list[ServiceAccessRequestResponse]
    events: list[ServiceUsageEventResponse]
