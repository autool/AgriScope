"""任务地块属性 Excel 导入导出请求与响应模型。"""

import re
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LandClass = Literal["耕地", "园地", "林地", "草地", "水域", "建设用地"]


class PlotAttributeWorkbookRow(BaseModel):
    """工作簿中一条带乐观并发版本的图斑属性。"""

    plot_code: str = Field(min_length=1, max_length=50)
    expected_version: int = Field(ge=1)
    owner_village: str = Field(min_length=1, max_length=100)
    land_class: LandClass
    crop_type: str | None = Field(default=None, max_length=50)
    planting_mode: str | None = Field(default=None, max_length=50)
    irrigation_condition: str | None = Field(default=None, max_length=20)
    custom_attributes: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "plot_code",
        "owner_village",
        "land_class",
        "crop_type",
        "planting_mode",
        "irrigation_condition",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """清理工作簿文本单元格。

        Args:
            value: 原始单元格文本。

        Returns:
            str | None: 去除首尾空白后的值。
        """
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("plot_code")
    @classmethod
    def validate_plot_code(cls, value: str) -> str:
        """校验图斑业务编号格式。

        Args:
            value: 已清理图斑编号。

        Returns:
            str: 合法图斑编号。
        """
        if not re.fullmatch(r"[\w-]+", value):
            raise ValueError("图斑编号只允许字母、数字、下划线和短横线")
        return value

    @model_validator(mode="after")
    def validate_land_crop_logic(self) -> Self:
        """校验地类与作物类型逻辑。

        Returns:
            Self: 通过业务校验的工作簿行。
        """
        if self.land_class == "耕地" and not self.crop_type:
            raise ValueError("耕地图斑必须填写作物类型")
        if self.land_class != "耕地" and self.crop_type:
            raise ValueError("非耕地图斑不得填写作物类型")
        return self


class PlotAttributeWorkbookExportRequest(BaseModel):
    """任务地块属性工作簿导出请求。"""

    operator_code: str = Field(min_length=1, max_length=50)
    plot_codes: list[str] | None = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code")
    @classmethod
    def normalize_operator_code(cls, value: str) -> str:
        """清理导出操作人编码。

        Args:
            value: 项目用户稳定编码。

        Returns:
            str: 非空操作人编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人编码不得为空")
        return normalized

    @field_validator("plot_codes")
    @classmethod
    def validate_plot_codes(cls, values: list[str] | None) -> list[str] | None:
        """校验显式导出图斑编号唯一且格式合法。

        Args:
            values: 可选图斑编号列表。

        Returns:
            list[str] | None: 保持顺序的标准化编号。
        """
        if values is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_value in values:
            plot_code = raw_value.strip()
            if not plot_code or len(plot_code) > 50:
                raise ValueError("图斑编号长度必须为 1 到 50 个字符")
            if not re.fullmatch(r"[\w-]+", plot_code):
                raise ValueError(f"图斑编号 {plot_code} 格式不合法")
            if plot_code in seen:
                raise ValueError(f"导出图斑编号 {plot_code} 重复")
            seen.add(plot_code)
            normalized.append(plot_code)
        if not normalized:
            raise ValueError("显式导出范围至少包含一个图斑")
        return normalized


class PlotAttributeWorkbookImportMetadata(BaseModel):
    """地块属性 Excel 实体导入元数据。"""

    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=2, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "comment")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理导入操作人和人工证据说明。

        Args:
            value: 原始表单文本。

        Returns:
            str: 去除首尾空白后的非空文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人编码和导入依据不得为空")
        return normalized


class PlotAttributeImportBatchResponse(BaseModel):
    """地块属性工作簿导入批次响应。"""

    batch_code: str
    task_code: str
    original_filename: str
    file_size_bytes: int
    checksum_sha256: str
    definition_snapshot: list[dict]
    definition_digest: str
    row_count: int
    changed_count: int
    unchanged_count: int
    updated_plot_codes: list[str] = Field(default_factory=list)
    imported_by: str
    imported_by_code: str
    imported_by_role: str
    import_comment: str
    imported_at: datetime
    quality_recheck_required: bool


class PlotAttributeImportBatchListResponse(BaseModel):
    """任务地块属性 Excel 历史导入批次列表。"""

    task_code: str
    items: list[PlotAttributeImportBatchResponse]
