"""多源数据目录、生产批次与县区作业包请求响应模型。"""

import re
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DatasetAssetType = Literal[
    "imagery",
    "vector",
    "table",
    "dem",
    "control",
    "weather",
    "management",
    "uav",
    "iot",
]
SecurityClassification = Literal["public", "internal", "restricted", "confidential"]
DataStatus = Literal["operational", "demo"]
BatchStatus = Literal[
    "draft",
    "planned",
    "in_progress",
    "reconciling",
    "completed",
    "cancelled",
]
PackageStatus = Literal["pending", "in_progress", "blocked", "completed"]
ReconciliationStatus = Literal["pending", "checking", "passed", "conflict"]
PackageDeliveryStatus = Literal["pending", "submitted", "accepted", "returned"]


class DatasetAssetCommonMetadata(BaseModel):
    """不含操作人字段的数据资产来源、范围、密级和血缘元数据。"""

    asset_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    asset_name: str = Field(min_length=1, max_length=200)
    asset_type: DatasetAssetType
    source_name: str = Field(min_length=1, max_length=120)
    source_uri: str = Field(min_length=1, max_length=500)
    source_version: str = Field(min_length=1, max_length=80)
    crs: str | None = Field(default=None, max_length=100)
    extent_bbox: tuple[float, float, float, float] | None = None
    time_start: datetime | None = None
    time_end: datetime | None = None
    security_classification: SecurityClassification
    data_status: DataStatus = "operational"
    parent_asset_codes: list[str] = Field(default_factory=list, max_length=50)
    lineage_relation_type: str = Field(
        default="derived_from",
        min_length=1,
        max_length=40,
    )
    process_code: str | None = Field(default=None, max_length=80)
    metadata: dict = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "asset_name",
        "source_name",
        "source_uri",
        "source_version",
        "lineage_relation_type",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """清理资产必填文本。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空格后的非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("数据资产必填文本不得为空")
        return normalized

    @field_validator("crs", "process_code")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """清理资产可选文本。

        Args:
            value: 原始文本或空值。

        Returns:
            str | None: 标准化文本或空值。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("parent_asset_codes")
    @classmethod
    def validate_parent_codes(cls, values: list[str]) -> list[str]:
        """校验并去重父资产编号。

        Args:
            values: 父资产编号列表。

        Returns:
            list[str]: 保持输入顺序的唯一编号列表。
        """
        result: list[str] = []
        for value in values:
            code = value.strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", code):
                raise ValueError("父资产编号格式不合法")
            if code not in result:
                result.append(code)
        return result

    @model_validator(mode="after")
    def validate_temporal_and_spatial_range(self) -> Self:
        """校验资产时间范围和 WGS84 包围盒。

        Returns:
            Self: 校验通过的资产登记请求。
        """
        if self.time_start and self.time_end and self.time_end < self.time_start:
            raise ValueError("数据结束时间不得早于开始时间")
        if self.extent_bbox:
            min_lon, min_lat, max_lon, max_lat = self.extent_bbox
            if not (-180 <= min_lon < max_lon <= 180):
                raise ValueError("数据范围经度不合法")
            if not (-90 <= min_lat < max_lat <= 90):
                raise ValueError("数据范围纬度不合法")
        if self.asset_code in self.parent_asset_codes:
            raise ValueError("资产不能把自身登记为父资产")
        return self


class DatasetAssetMetadataRequest(DatasetAssetCommonMetadata):
    """包含稳定操作人编码的单资产请求。"""

    operator_code: str = Field(min_length=1, max_length=50)

    @field_validator("operator_code")
    @classmethod
    def normalize_operator_code(cls, value: str) -> str:
        """清理单资产操作人编码。

        Args:
            value: 原始操作人编码。

        Returns:
            str: 去除首尾空格后的操作人编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人编码不得为空")
        return normalized


class DatasetAssetCreateRequest(DatasetAssetMetadataRequest):
    """仅登记外部多源数据资产及调用方提供的校验值。"""

    checksum_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class DatasetAssetUploadRequest(DatasetAssetMetadataRequest):
    """上传实体并由服务端计算校验值的数据资产登记清单。"""

    verification_comment: str = Field(min_length=10, max_length=500)

    @field_validator("verification_comment")
    @classmethod
    def normalize_verification_comment(cls, value: str) -> str:
        """清理实体核验依据。

        Args:
            value: 原始核验依据。

        Returns:
            str: 去除首尾空格后的核验依据。
        """
        normalized = value.strip()
        if len(normalized) < 10:
            raise ValueError("实体核验依据至少填写 10 个字符")
        return normalized


class DatasetAssetBatchItemRequest(DatasetAssetCommonMetadata):
    """原子批量入库清单中的一个文件和业务元数据。"""

    filename: str = Field(min_length=1, max_length=255)

    @field_validator("filename")
    @classmethod
    def normalize_filename(cls, value: str) -> str:
        """清理批次清单原始文件名。

        Args:
            value: 浏览器选择的原始文件名。

        Returns:
            str: 去除首尾空格后的文件名。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("批次文件名不得为空")
        if "/" in normalized or "\\" in normalized:
            raise ValueError("批次文件名不得包含路径片段")
        return normalized


class DatasetAssetBatchCreateRequest(BaseModel):
    """一次 1–20 个多源实体的原子批量入库清单。"""

    batch_code: str = Field(
        min_length=1,
        max_length=90,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=10, max_length=500)
    items: list[DatasetAssetBatchItemRequest] = Field(min_length=1, max_length=20)

    model_config = ConfigDict(extra="forbid")

    @field_validator("batch_code", "operator_code")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """清理批次编号和操作人编码。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空格后的文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("批次编号和操作人编码不得为空")
        return normalized

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str) -> str:
        """清理并校验批量入库依据。

        Args:
            value: 原始批量入库依据。

        Returns:
            str: 至少 10 个字符的入库依据。
        """
        normalized = value.strip()
        if len(normalized) < 10:
            raise ValueError("批量入库依据至少填写 10 个字符")
        return normalized

    @model_validator(mode="after")
    def validate_unique_items(self) -> Self:
        """校验文件名和资产编号在批次内唯一。

        Returns:
            Self: 校验通过的批次清单。
        """
        filenames = [item.filename.casefold() for item in self.items]
        if len(filenames) != len(set(filenames)):
            raise ValueError("同一批次不得包含重复文件名")
        asset_codes = [item.asset_code for item in self.items]
        if len(asset_codes) != len(set(asset_codes)):
            raise ValueError("同一批次不得包含重复资产编号")
        return self


class DatasetAssetVerifyRequest(BaseModel):
    """为既有数据资产补传实体并执行核验。"""

    operator_code: str = Field(min_length=1, max_length=50)
    verification_comment: str = Field(min_length=10, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code")
    @classmethod
    def normalize_operator_code(cls, value: str) -> str:
        """清理补传操作人编码。

        Args:
            value: 原始操作人编码。

        Returns:
            str: 去除首尾空格后的操作人编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人编码不得为空")
        return normalized

    @field_validator("verification_comment")
    @classmethod
    def normalize_verification_comment(cls, value: str) -> str:
        """清理补传核验依据。

        Args:
            value: 原始核验依据。

        Returns:
            str: 去除首尾空格后的核验依据。
        """
        normalized = value.strip()
        if len(normalized) < 10:
            raise ValueError("实体核验依据至少填写 10 个字符")
        return normalized


class DatasetAssetResponse(BaseModel):
    """多源数据资产目录项。"""

    asset_code: str
    asset_name: str
    asset_type: DatasetAssetType
    source_name: str
    source_uri: str
    source_version: str
    checksum_sha256: str
    crs: str | None
    extent_bbox: tuple[float, float, float, float] | None
    time_start: datetime | None
    time_end: datetime | None
    security_classification: SecurityClassification
    data_status: DataStatus
    verification_status: str
    physical_file_uri: str | None
    physical_original_filename: str | None
    physical_file_size_bytes: int | None
    physical_checksum_sha256: str | None
    physical_media_type: str | None
    verified_at: datetime | None
    verified_by: str | None
    verified_by_code: str | None
    verified_by_role: str | None
    verification_comment: str | None
    parent_asset_codes: list[str]
    metadata: dict
    registered_by: str
    registered_by_code: str
    registered_by_role: str
    created_at: datetime


class DatasetAssetVerificationResponse(BaseModel):
    """多源数据资产实体核验结果。"""

    verification_code: str
    verification_status: Literal["verified", "rejected"]
    checksum_match: bool
    expected_checksum_sha256: str
    computed_checksum_sha256: str
    file_size_bytes: int
    media_type: str
    verification_error: str | None
    created_at: datetime
    asset: DatasetAssetResponse


class DatasetAssetImportBatchSummary(BaseModel):
    """数据资产原子批量入库批次摘要。"""

    batch_code: str
    item_count: int
    total_size_bytes: int
    manifest_sha256: str
    imported_by: str
    imported_by_code: str
    imported_by_role: str
    comment: str
    created_at: datetime


class DatasetAssetBatchResponse(DatasetAssetImportBatchSummary):
    """数据资产批量入库结果和全部成员。"""

    items: list[DatasetAssetResponse]


class ProductionBatchCreateRequest(BaseModel):
    """创建遥感生产批次。"""

    batch_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    batch_name: str = Field(min_length=1, max_length=200)
    source_asset_code: str | None = Field(default=None, max_length=80)
    target_asset_code: str | None = Field(default=None, max_length=80)
    planned_start_date: date
    planned_end_date: date
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_batch(self) -> Self:
        """校验批次日期和时相资产。

        Returns:
            Self: 校验通过的批次请求。
        """
        if self.planned_end_date < self.planned_start_date:
            raise ValueError("计划结束日期不得早于开始日期")
        if (
            self.source_asset_code
            and self.target_asset_code
            and self.source_asset_code == self.target_asset_code
        ):
            raise ValueError("前后时相资产不能相同")
        return self


class WorkPackageCreateRequest(BaseModel):
    """按县区批量创建显式图斑作业包。"""

    region_codes: list[str] = Field(min_length=1, max_length=122)
    assignee_code: str = Field(min_length=1, max_length=50)
    deadline: date
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("region_codes")
    @classmethod
    def normalize_region_codes(cls, values: list[str]) -> list[str]:
        """清理并去重县区编码。

        Args:
            values: 县区编码列表。

        Returns:
            list[str]: 保持输入顺序的唯一县区编码。
        """
        result: list[str] = []
        for value in values:
            code = value.strip()
            if not code or len(code) > 50:
                raise ValueError("县区编码不合法")
            if code not in result:
                result.append(code)
        return result


class ProductionBatchStatusUpdateRequest(BaseModel):
    """更新生产批次状态。"""

    status: BatchStatus
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")


class WorkPackageUpdateRequest(BaseModel):
    """更新作业包负责人、期限或交付状态。"""

    assignee_code: str | None = Field(default=None, min_length=1, max_length=50)
    deadline: date | None = None
    status: PackageStatus | None = None
    reconciliation_status: ReconciliationStatus | None = None
    delivery_status: PackageDeliveryStatus | None = None
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        """确保作业包更新包含至少一个业务字段。

        Returns:
            Self: 校验通过的更新请求。
        """
        if all(
            value is None
            for value in (
                self.assignee_code,
                self.deadline,
                self.status,
                self.reconciliation_status,
                self.delivery_status,
            )
        ):
            raise ValueError("至少需要修改一个作业包字段")
        return self


class WorkAreaResponse(BaseModel):
    """当前任务可拆包的县区工作范围。"""

    city_code: str
    city_name: str
    region_code: str
    region_name: str
    plot_count: int
    area_ha: float
    assigned_batch_codes: list[str]


class WorkPackageResponse(BaseModel):
    """作业包及其实时图斑进度。"""

    package_code: str
    package_name: str
    region_code: str
    region_name: str
    region_level: str
    planned_area_ha: float
    planned_plot_count: int
    active_plot_count: int
    completed_plot_count: int
    progress: float
    assignee_code: str
    assignee_name: str
    deadline: date
    overdue: bool
    status: PackageStatus
    reconciliation_status: ReconciliationStatus
    delivery_status: PackageDeliveryStatus
    updated_at: datetime


class ProductionBatchResponse(BaseModel):
    """生产批次及其县区作业包汇总。"""

    batch_code: str
    batch_name: str
    source_asset_code: str | None
    target_asset_code: str | None
    rule_config_version: int
    rule_profile_snapshot: dict
    planned_start_date: date
    planned_end_date: date
    status: BatchStatus
    package_count: int
    planned_plot_count: int
    completed_plot_count: int
    progress: float
    created_by: str
    created_by_code: str
    created_at: datetime
    packages: list[WorkPackageResponse]


class ProductionMetricsResponse(BaseModel):
    """生产调度实时指标。"""

    asset_count: int
    pending_asset_verification_count: int
    dataset_import_batch_count: int
    batch_count: int
    active_batch_count: int
    package_count: int
    overdue_package_count: int
    assigned_plot_count: int
    completed_plot_count: int


class ProductionOverviewResponse(BaseModel):
    """生产调度和多源数据目录聚合响应。"""

    project_code: str
    task_code: str
    metrics: ProductionMetricsResponse
    asset_type_counts: dict[str, int]
    assets: list[DatasetAssetResponse]
    dataset_import_batches: list[DatasetAssetImportBatchSummary]
    work_areas: list[WorkAreaResponse]
    batches: list[ProductionBatchResponse]


class WorkPackageCreateResponse(BaseModel):
    """县区作业包批量创建结果。"""

    batch_code: str
    created_count: int
    assigned_plot_count: int
    packages: list[WorkPackageResponse]
