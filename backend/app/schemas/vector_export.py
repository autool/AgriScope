"""多格式矢量成果导出请求与响应模型。"""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VectorExportFormat = Literal["geojson", "shapefile", "kml", "filegdb"]
LandClass = Literal["耕地", "园地", "林地", "草地", "水域", "建设用地"]


class VectorExportGenerateRequest(BaseModel):
    """生成任务作用域多格式矢量成果包请求。"""

    operator_code: str = Field(min_length=1, max_length=50)
    export_title: str = Field(min_length=2, max_length=80)
    formats: list[VectorExportFormat] = Field(min_length=1, max_length=4)
    district_codes: list[str] = Field(default_factory=list, max_length=122)
    land_classes: list[LandClass] = Field(default_factory=list, max_length=6)
    comment: str = Field(min_length=4, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "export_title", "comment")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理操作人、标题和生成依据。

        Args:
            value: 原始文本。

        Returns:
            str: 标准化非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("导出操作人、标题和生成依据不得为空")
        return normalized

    @field_validator("district_codes")
    @classmethod
    def validate_district_codes(cls, values: list[str]) -> list[str]:
        """校验并去重六位县区编码。

        Args:
            values: 原始县区编码。

        Returns:
            list[str]: 排序后的唯一编码。
        """
        normalized = sorted({value.strip() for value in values})
        if any(len(value) != 6 or not value.isdigit() for value in normalized):
            raise ValueError("县区编码必须是六位数字")
        return normalized

    @model_validator(mode="after")
    def normalize_choices(self) -> Self:
        """去重并按稳定顺序保存格式和地类筛选。

        Returns:
            Self: 已标准化请求。
        """
        format_order = ("geojson", "shapefile", "kml", "filegdb")
        selected_formats = set(self.formats)
        self.formats = [
            item for item in format_order if item in selected_formats
        ]
        self.land_classes = sorted(set(self.land_classes))
        return self


class VectorExportManifestFile(BaseModel):
    """导出 ZIP 内单个真实格式文件证据。"""

    path: str
    format: str
    file_size_bytes: int
    checksum_sha256: str


class VectorExportPackageResponse(BaseModel):
    """多格式矢量成果导出包摘要。"""

    export_code: str
    export_title: str
    version: int
    status: Literal["completed", "superseded", "invalid"]
    formats: list[VectorExportFormat]
    district_codes: list[str]
    land_classes: list[LandClass]
    feature_count: int
    task_plot_count: int
    task_updated_at_snapshot: datetime
    file_size_bytes: int
    checksum_sha256: str
    files: list[VectorExportManifestFile]
    generation_comment: str
    generated_by: str
    generated_by_code: str
    generated_by_role: str
    generated_at: datetime
    download_url: str | None
    is_current: bool
    stale_reason: str | None


class VectorExportListResponse(BaseModel):
    """任务矢量成果导出版本列表。"""

    task_code: str
    items: list[VectorExportPackageResponse]


class VectorExportFilterOption(BaseModel):
    """县区或地类导出筛选项。"""

    code: str | None = None
    label: str
    parent_label: str | None = None
    feature_count: int


class VectorExportOptionsResponse(BaseModel):
    """任务矢量导出格式能力和真实筛选范围。"""

    task_code: str
    total_feature_count: int
    max_feature_count: int
    supported_formats: list[VectorExportFormat]
    districts: list[VectorExportFilterOption]
    land_classes: list[VectorExportFilterOption]
