"""遥感影像预处理流水线请求响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImageryAssetCreateRequest(BaseModel):
    """影像文件入库业务元数据。"""

    asset_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    asset_name: str = Field(min_length=1, max_length=200)
    sensor_type: str | None = Field(default=None, max_length=80)
    acquired_at: datetime | None = None
    cloud_cover: float | None = Field(default=None, ge=0, le=100)
    processing_level: str | None = Field(default=None, max_length=30)
    data_status: Literal["operational", "demo"] = "operational"
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("asset_code", "asset_name", "operator_code")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """清理影像资产必填文本。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空格后的文本。
        """
        return value.strip()

    @field_validator("sensor_type", "processing_level")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """清理可选业务元数据补录值。

        Args:
            value: 原始可选文本。

        Returns:
            str | None: 去除首尾空白后的文本。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("acquired_at")
    @classmethod
    def validate_acquired_at(cls, value: datetime | None) -> datetime | None:
        """校验影像采集时间必须包含时区。

        Args:
            value: 影像采集时间。

        Returns:
            datetime | None: 带时区采集时间或空补录值。
        """
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("影像采集时间必须包含时区")
        return value


class ImageryAssetResponse(BaseModel):
    """影像文件和栅格元数据响应。"""

    asset_code: str
    asset_name: str
    sensor_type: str
    acquired_at: datetime
    cloud_cover: float | None
    resolution_m: float | None
    processing_level: str | None
    data_status: str
    calibration_status: str
    correction_status: str
    original_filename: str | None
    file_uri: str | None
    file_format: str | None
    file_size_bytes: int | None
    checksum_sha256: str | None
    band_count: int | None
    raster_width: int | None
    raster_height: int | None
    crs: str | None
    raster_metadata: dict
    imported_by: str | None
    footprint: dict | None
    file_verified: bool
    file_error: str | None
    created_at: datetime


class ImageryAssetListResponse(BaseModel):
    """项目影像资产目录响应。"""

    project_code: str
    total: int
    available: int
    metadata_only: int
    items: list[ImageryAssetResponse]


class ImageryProcessingStepResponse(BaseModel):
    """单个影像预处理步骤响应。"""

    step_code: str
    step_name: str
    sequence: int
    status: str
    progress: int
    parameters: dict
    output_uri: str | None
    output_verified: bool
    output_size_bytes: int | None
    output_checksum_sha256: str | None
    processor_name: str | None
    processor_version: str | None
    artifact_error: str | None
    started_at: datetime | None
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ImageryProcessingResponse(BaseModel):
    """影像元数据和处理流水线聚合响应。"""

    asset_code: str
    asset_name: str
    sensor_type: str
    acquired_at: datetime
    cloud_cover: float | None
    resolution_m: float | None
    processing_level: str | None
    completion_rate: float
    completed_steps: int
    total_steps: int
    steps: list[ImageryProcessingStepResponse]


class ImageryQuicklookProductResponse(BaseModel):
    """单个真实源影像或波段产品快视图证据。"""

    product_code: Literal["source", "true_color", "false_color", "ndvi"]
    product_name: str
    available: bool
    unavailable_reason: str | None
    source_kind: Literal["source_asset", "verified_band_products"] | None
    source_uri: str | None
    source_checksum_sha256: str | None
    preview_url: str | None
    preview_checksum_sha256: str | None
    bounds_wgs84: tuple[float, float, float, float] | None
    width: int | None
    height: int | None
    band_indexes: tuple[int, ...]
    band_descriptions: tuple[str, ...]
    stretch_ranges: tuple[tuple[float, float], ...]
    value_range: tuple[float, float] | None
    renderer_version: str | None
    generated_at: datetime | None


class ImageryQuicklookResponse(BaseModel):
    """当前实体影像及已校验波段产品快视图集合。"""

    asset_code: str
    asset_name: str
    data_status: Literal["operational", "demo"]
    products: list[ImageryQuicklookProductResponse]


class ImageryStepRunRequest(BaseModel):
    """登记并完成影像预处理步骤请求。"""

    operator_code: str = Field(min_length=1, max_length=50)
    output_relative_path: str = Field(min_length=1, max_length=500)
    processor_name: str = Field(min_length=1, max_length=100)
    processor_version: str = Field(min_length=1, max_length=80)
    comment: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "operator_code",
        "output_relative_path",
        "processor_name",
        "processor_version",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """清理影像产物登记必填文本。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空格后的文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("必填字段不得为空")
        return normalized


class ImageryStepExecuteRequest(BaseModel):
    """由平台内置处理器执行影像步骤请求。"""

    operator_code: str = Field(min_length=1, max_length=50)
    parameters: dict = Field(default_factory=dict)
    comment: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code")
    @classmethod
    def validate_operator_code(cls, value: str) -> str:
        """清理平台处理操作人编码。

        Args:
            value: 项目用户稳定编码。

        Returns:
            str: 去除首尾空格的用户编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人编码不得为空")
        return normalized


class ImagerySourceLevelAcceptRequest(BaseModel):
    """使用已验证源产品级别满足处理步骤的受控承认请求。"""

    operator_code: str = Field(min_length=1, max_length=50)
    expected_processing_level: Literal["L2A"] = "L2A"
    confirm_no_algorithm_execution: bool
    justification: str = Field(min_length=10, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "justification")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """清理操作人和承认依据。

        Args:
            value: 原始文本。

        Returns:
            str: 非空规范文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("必填字段不得为空")
        return normalized

    @field_validator("confirm_no_algorithm_execution")
    @classmethod
    def validate_confirmation(cls, value: bool) -> bool:
        """要求操作人明确确认本动作不会执行或伪造算法。

        Args:
            value: 客户端确认值。

        Returns:
            bool: 仅允许明确确认值。
        """
        if value is not True:
            raise ValueError("必须确认本动作不执行重复算法")
        return value
