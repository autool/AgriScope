"""内外业联动核查请求与响应模型。"""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FieldVerificationRecordInput(BaseModel):
    """单条外业核查采集数据，坐标为 WGS84。"""

    verification_code: str = Field(
        min_length=1,
        max_length=60,
        pattern=r"^[\w-]+$",
    )
    source_record_id: str = Field(min_length=1, max_length=100)
    lon: float
    lat: float
    location_accuracy_m: float | None = Field(default=None, gt=0, le=10000)
    observed_land_class: str | None = Field(default=None, max_length=50)
    observed_crop_type: str | None = Field(default=None, max_length=50)
    photo_urls: list[str] = Field(default_factory=list, max_length=20)
    voice_url: str | None = Field(default=None, max_length=500)
    remark: str | None = Field(default=None, max_length=1000)
    captured_at: datetime

    model_config = ConfigDict(extra="forbid")

    @field_validator("lon")
    @classmethod
    def validate_lon(cls, value: float) -> float:
        """校验 WGS84 经度。

        Args:
            value: 经度。

        Returns:
            float: 合法经度。
        """
        if not -180 <= value <= 180:
            raise ValueError("经度必须位于 -180 到 180 之间")
        return value

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, value: float) -> float:
        """校验 WGS84 纬度。

        Args:
            value: 纬度。

        Returns:
            float: 合法纬度。
        """
        if not -90 <= value <= 90:
            raise ValueError("纬度必须位于 -90 到 90 之间")
        return value

    @field_validator(
        "verification_code",
        "source_record_id",
        "observed_land_class",
        "observed_crop_type",
        "voice_url",
        "remark",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """清理外业采集文本。

        Args:
            value: 原始文本。

        Returns:
            str | None: 标准化文本。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("photo_urls")
    @classmethod
    def validate_photo_urls(cls, values: list[str]) -> list[str]:
        """校验现场照片引用非空、唯一且长度受控。

        Args:
            values: 照片 URI 列表。

        Returns:
            list[str]: 标准化且去重的照片 URI。
        """
        normalized = []
        for value in values:
            uri = value.strip()
            if not uri:
                continue
            if len(uri) > 500:
                raise ValueError("单个照片 URI 不得超过 500 个字符")
            if uri not in normalized:
                normalized.append(uri)
        return normalized

    @field_validator("captured_at")
    @classmethod
    def validate_captured_at(cls, value: datetime) -> datetime:
        """要求外业采集时间包含明确时区。

        Args:
            value: 外业采集时间。

        Returns:
            datetime: 带时区采集时间。
        """
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("外业采集时间必须包含时区")
        return value

    @model_validator(mode="after")
    def validate_land_crop_logic(self) -> Self:
        """校验外业地类和作物调查逻辑。

        Returns:
            Self: 通过业务逻辑校验的记录。
        """
        if self.observed_land_class == "耕地" and not self.observed_crop_type:
            raise ValueError("外业判定为耕地时必须填写现场作物")
        if self.observed_land_class != "耕地" and self.observed_crop_type:
            raise ValueError("非耕地外业记录不得填写作物类型")
        return self


class FieldVerificationCreateRequest(FieldVerificationRecordInput):
    """单条外业核查记录创建请求。"""

    investigator_code: str = Field(min_length=1, max_length=50)
    source_name: str = Field(default="平台单条录入", max_length=120)
    source_uri: str = Field(default="api://field-verifications/direct", max_length=500)
    source_version: str = Field(default="v1", max_length=80)

    @field_validator(
        "investigator_code",
        "source_name",
        "source_uri",
        "source_version",
    )
    @classmethod
    def validate_source_text(cls, value: str) -> str:
        """校验采集人编码与来源信息。

        Args:
            value: 项目用户编码或来源文本。

        Returns:
            str: 清理后的非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("外业采集人编码和来源信息不得为空")
        return normalized


class FieldVerificationImportItem(FieldVerificationRecordInput):
    """CSV 批量导入中的外业记录。"""

    @model_validator(mode="after")
    def validate_field_evidence(self) -> Self:
        """要求批量导入记录至少包含一张现场照片。

        Returns:
            Self: 具有现场照片证据的记录。
        """
        if not self.photo_urls:
            raise ValueError("批量导入的外业记录至少需要一张现场照片")
        return self


class FieldVerificationBatchImportRequest(BaseModel):
    """外业核查 CSV 批量导入请求。"""

    source_name: str = Field(min_length=1, max_length=120)
    source_uri: str = Field(min_length=1, max_length=500)
    source_version: str = Field(min_length=1, max_length=80)
    uploader_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=1, max_length=500)
    records: list[FieldVerificationImportItem] = Field(
        min_length=1,
        max_length=500,
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "source_name",
        "source_uri",
        "source_version",
        "uploader_code",
        "comment",
    )
    @classmethod
    def normalize_import_text(cls, value: str) -> str:
        """清理批量导入来源和操作审计文本。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("批量导入来源和操作说明不得为空")
        return normalized

    @model_validator(mode="after")
    def validate_batch_uniqueness(self) -> Self:
        """校验批次内记录编号和来源记录编号唯一。

        Returns:
            Self: 通过唯一性校验的批次。
        """
        verification_codes = [item.verification_code for item in self.records]
        if len(verification_codes) != len(set(verification_codes)):
            raise ValueError("同一批次外业记录编号不得重复")
        source_record_ids = [item.source_record_id for item in self.records]
        if len(source_record_ids) != len(set(source_record_ids)):
            raise ValueError("同一批次来源记录编号不得重复")
        return self


class FieldVerificationFileImportMetadata(BaseModel):
    """外业核查实体文件导入元数据。"""

    source_name: str = Field(min_length=1, max_length=120)
    source_uri: str = Field(min_length=1, max_length=500)
    source_version: str = Field(min_length=1, max_length=80)
    uploader_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "source_name",
        "source_uri",
        "source_version",
        "uploader_code",
        "comment",
    )
    @classmethod
    def normalize_file_import_text(cls, value: str) -> str:
        """清理实体文件导入来源和审计文本。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("文件导入来源和操作说明不得为空")
        return normalized


class FieldVerificationBatchImportResponse(BaseModel):
    """外业核查 CSV 批量导入结果。"""

    task_code: str
    batch_code: str
    imported_count: int
    consistent_count: int
    offset_count: int
    unmatched_count: int
    time_mismatch_count: int
    issue_count: int
    source_checksum_sha256: str
    imported_by: str
    imported_by_code: str
    imported_by_role: str
    imported_at: datetime


class FieldVerificationArtifactUploadRequest(BaseModel):
    """外业核查受控实体证据上传元数据。"""

    artifact_type: Literal["photo", "voice", "form"]
    uploader_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=2, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("uploader_code", "comment")
    @classmethod
    def normalize_upload_text(cls, value: str) -> str:
        """清理上传人编码和证据说明。

        Args:
            value: 原始表单文本。

        Returns:
            str: 标准化非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("上传人编码和证据说明不得为空")
        return normalized


class FieldVerificationArtifactResponse(BaseModel):
    """已通过实体校验的外业核查证据摘要。"""

    artifact_code: str
    artifact_type: Literal["photo", "voice", "form"]
    original_filename: str
    media_type: str
    file_size_bytes: int
    checksum_sha256: str
    description: str
    uploaded_by: str
    uploaded_by_code: str
    uploaded_by_role: str
    created_at: datetime
    download_url: str


class FieldVerificationResponse(BaseModel):
    """外业核查记录响应。"""

    verification_code: str
    investigator: str
    investigator_code: str | None
    lon: float
    lat: float
    location_accuracy_m: float | None
    observed_land_class: str | None
    observed_crop_type: str | None
    photo_urls: list[str]
    voice_url: str | None
    remark: str | None
    captured_at: datetime
    source_name: str | None
    source_uri: str | None
    source_version: str | None
    source_record_id: str | None
    source_checksum_sha256: str | None
    source_file_uri: str | None
    source_file_size_bytes: int | None
    import_batch_code: str | None
    imported_by: str | None
    imported_by_code: str | None
    imported_by_role: str | None
    matched_plot_code: str | None
    offset_distance_m: float | None
    match_status: str
    resolution_status: str
    resolution_decision: str | None
    resolution_comment: str | None
    resolved_by: str | None
    resolved_by_code: str | None
    resolved_by_role: str | None
    verified_artifact_count: int
    artifacts: list[FieldVerificationArtifactResponse]


class FieldVerificationListResponse(BaseModel):
    """外业核查列表及状态统计。"""

    total: int
    consistent: int
    offset: int
    unmatched: int
    time_mismatch: int
    pending_resolution: int
    items: list[FieldVerificationResponse]


class FieldRematchResponse(BaseModel):
    """批量空间重新匹配结果。"""

    matched_count: int
    issue_count: int
    items: list[FieldVerificationResponse]


class FieldRematchRequest(BaseModel):
    """重新匹配外业记录请求。"""

    operator_code: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code")
    @classmethod
    def validate_operator_code(cls, value: str) -> str:
        """校验重新匹配操作人编码。

        Args:
            value: 项目用户编码。

        Returns:
            str: 清理后的用户编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人编码不得为空")
        return normalized


class FieldResolutionRequest(BaseModel):
    """外业疑点人工处置请求。"""

    decision: Literal[
        "keep_internal",
        "use_field",
        "compromise",
        "reject_field",
    ]
    reviewer_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=2, max_length=500)
    target_land_class: str | None = Field(default=None, max_length=50)
    target_crop_type: str | None = Field(default=None, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("reviewer_code", "comment")
    @classmethod
    def validate_reviewer_code(cls, value: str) -> str:
        """校验疑点处置审核人编码。

        Args:
            value: 项目用户编码或处置说明。

        Returns:
            str: 清理后的非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("审核人编码和处置说明不得为空")
        return normalized

    @field_validator("target_land_class", "target_crop_type", mode="before")
    @classmethod
    def normalize_target_text(cls, value: str | None) -> str | None:
        """清理折中方案目标属性。

        Args:
            value: 原始目标地类或作物文本。

        Returns:
            str | None: 标准化文本或 None。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_compromise_target(self) -> Self:
        """校验折中方案必须显式给出合法最终地类和作物。

        Returns:
            Self: 通过业务规则校验的请求。
        """
        if self.decision != "compromise":
            if self.target_land_class or self.target_crop_type:
                raise ValueError("仅折中处置可填写最终目标属性")
            return self
        if not self.target_land_class:
            raise ValueError("折中处置必须填写最终地类")
        if self.target_land_class == "耕地" and not self.target_crop_type:
            raise ValueError("折中处置最终地类为耕地时必须填写作物类型")
        if self.target_land_class != "耕地" and self.target_crop_type:
            raise ValueError("折中处置最终地类非耕地时不得填写作物类型")
        return self


class FieldReopenRequest(BaseModel):
    """重新打开已处置外业疑点的请求。"""

    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=2, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "comment")
    @classmethod
    def normalize_reopen_text(cls, value: str) -> str:
        """清理重新打开操作人和依据文本。

        Args:
            value: 原始表单文本。

        Returns:
            str: 标准化非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人编码和重新打开依据不得为空")
        return normalized
