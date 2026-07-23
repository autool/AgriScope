"""项目级地块自定义属性字段请求与响应模型。"""

import re
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PlotAttributeFieldType = Literal[
    "text",
    "number",
    "date",
    "boolean",
    "single_select",
]
PlotAttributeFieldStatus = Literal["active", "inactive"]
CustomAttributeScalar = str | int | float | bool | None


class PlotAttributeFieldDefinition(BaseModel):
    """可固化进 Excel 和成果清单的字段定义快照。"""

    field_code: str
    label: str
    field_type: PlotAttributeFieldType
    required: bool
    options: list[str]
    display_order: int
    version: int

    model_config = ConfigDict(extra="forbid")


class PlotAttributeFieldCreateRequest(BaseModel):
    """创建项目级地块自定义属性字段。"""

    field_code: str = Field(min_length=2, max_length=40)
    label: str = Field(min_length=1, max_length=100)
    field_type: PlotAttributeFieldType
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=100)
    display_order: int = Field(default=0, ge=0, le=9999)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("field_code", "label", "operator_code")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理字段编码、名称和操作人编码。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空格后的文本。
        """
        return value.strip()

    @field_validator("field_code")
    @classmethod
    def validate_field_code(cls, value: str) -> str:
        """校验稳定字段编码格式。

        Args:
            value: 已清理字段编码。

        Returns:
            str: 合法的小写字段编码。
        """
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", value):
            raise ValueError("字段编码必须以小写字母开头，仅包含小写字母、数字和下划线")
        return value

    @field_validator("options")
    @classmethod
    def normalize_options(cls, values: list[str]) -> list[str]:
        """清理并去重单选项。

        Args:
            values: 原始选项。

        Returns:
            list[str]: 保持顺序的唯一选项。
        """
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = value.strip()
            if not item:
                raise ValueError("单选项不得为空")
            if len(item) > 100:
                raise ValueError("单个选项不得超过 100 个字符")
            if item in seen:
                raise ValueError(f"单选项 {item} 重复")
            seen.add(item)
            normalized.append(item)
        return normalized

    @model_validator(mode="after")
    def validate_options_by_type(self) -> Self:
        """校验字段类型与选项配置一致。

        Returns:
            Self: 通过校验的创建请求。
        """
        if self.field_type == "single_select" and not self.options:
            raise ValueError("单选字段至少配置一个选项")
        if self.field_type != "single_select" and self.options:
            raise ValueError("只有单选字段可以配置选项")
        if not self.label or not self.operator_code:
            raise ValueError("字段名称和操作人编码不得为空")
        return self


class PlotAttributeFieldUpdateRequest(BaseModel):
    """更新项目级地块自定义属性字段语义。"""

    label: str | None = Field(default=None, min_length=1, max_length=100)
    field_type: PlotAttributeFieldType | None = None
    required: bool | None = None
    options: list[str] | None = Field(default=None, max_length=100)
    display_order: int | None = Field(default=None, ge=0, le=9999)
    status: PlotAttributeFieldStatus | None = None
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("label", "operator_code")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """清理可选文本字段。

        Args:
            value: 原始文本。

        Returns:
            str | None: 清理后的文本。
        """
        if value is None:
            return None
        return value.strip()

    @field_validator("options")
    @classmethod
    def normalize_options(cls, values: list[str] | None) -> list[str] | None:
        """清理并去重更新后的单选项。

        Args:
            values: 原始选项或空值。

        Returns:
            list[str] | None: 标准化选项。
        """
        if values is None:
            return None
        return PlotAttributeFieldCreateRequest.normalize_options(values)

    @model_validator(mode="after")
    def validate_update_payload(self) -> Self:
        """校验更新至少包含一个字段定义变更。

        Returns:
            Self: 通过校验的更新请求。
        """
        if not self.operator_code:
            raise ValueError("操作人编码不得为空")
        changed_fields = self.model_fields_set - {"operator_code"}
        if not changed_fields:
            raise ValueError("至少需要修改一项字段定义")
        return self


class PlotAttributeFieldResponse(PlotAttributeFieldDefinition):
    """项目级地块自定义属性字段响应。"""

    status: PlotAttributeFieldStatus
    created_by: str
    created_by_code: str
    created_by_role: str
    updated_by: str
    updated_by_code: str
    updated_by_role: str
    created_at: datetime
    updated_at: datetime


class PlotAttributeFieldListResponse(BaseModel):
    """项目字段定义列表及当前活动模式摘要。"""

    project_code: str
    schema_digest: str
    active_count: int
    items: list[PlotAttributeFieldResponse]
