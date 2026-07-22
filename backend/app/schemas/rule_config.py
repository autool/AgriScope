"""项目级业务规则配置请求与响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RuleConfigResponse(BaseModel):
    """项目当前生效的规则配置。"""

    project_code: str
    field_offset_threshold_m: float
    field_search_radius_m: float
    positional_accuracy_pixels: float
    max_capture_image_days: int
    construction_min_area_sqm: float
    other_agricultural_min_area_sqm: float
    completeness_rate_min: float
    boundary_agreement_rate_min: float
    land_class_accuracy_min: float
    key_field_accuracy_min: float
    max_cloud_cover_percent: float | None
    output_crs: str
    output_projection: str
    version: int
    updated_by: str
    updated_by_code: str | None
    updated_by_role: str | None
    updated_at: datetime


class RuleConfigUpdateRequest(BaseModel):
    """项目业务规则配置更新请求。"""

    field_offset_threshold_m: float = Field(ge=0.1, le=500)
    field_search_radius_m: float = Field(ge=1, le=50_000)
    positional_accuracy_pixels: float = Field(ge=0.1, le=20)
    max_capture_image_days: int = Field(ge=1, le=365)
    construction_min_area_sqm: float = Field(ge=1, le=1_000_000)
    other_agricultural_min_area_sqm: float = Field(ge=1, le=1_000_000)
    completeness_rate_min: float = Field(ge=0, le=100)
    boundary_agreement_rate_min: float = Field(ge=0, le=100)
    land_class_accuracy_min: float = Field(ge=0, le=100)
    key_field_accuracy_min: float = Field(ge=0, le=100)
    max_cloud_cover_percent: float | None = Field(default=None, ge=0, le=100)
    output_crs: str = Field(min_length=1, max_length=100)
    output_projection: str = Field(min_length=1, max_length=200)
    operator_code: str = Field(min_length=1, max_length=50)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "output_crs", "output_projection")
    @classmethod
    def validate_operator_code(cls, value: str) -> str:
        """清理并校验操作人编码。

        Args:
            value: 项目用户编码。

        Returns:
            str: 去除首尾空格的用户编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人编码不得为空")
        return normalized

    @model_validator(mode="after")
    def validate_field_thresholds(self) -> "RuleConfigUpdateRequest":
        """校验最近邻搜索半径必须大于偏移阈值。

        Returns:
            RuleConfigUpdateRequest: 校验通过的请求对象。
        """
        if self.field_search_radius_m <= self.field_offset_threshold_m:
            raise ValueError("搜索半径必须大于偏移判定阈值")
        if self.other_agricultural_min_area_sqm < self.construction_min_area_sqm:
            raise ValueError("其他农用地最小图斑面积不得小于建设类阈值")
        return self
