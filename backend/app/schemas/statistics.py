"""种植面积统计分析请求与响应模型。"""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AreaGroupItem(BaseModel):
    """单个统计分组面积指标。"""

    label: str
    code: str | None = None
    parent_label: str | None = None
    plot_count: int
    area_ha: float
    area_mu: float
    percentage: float


class AreaTrendItem(BaseModel):
    """年度面积变化趋势指标。"""

    year: int
    area_ha: float
    year_over_year: float | None
    source_name: str
    source_version: str | None
    recorded_at: datetime
    is_current: bool


class AreaStatisticsSnapshotImportItem(BaseModel):
    """单个历史年度面积统计快照。"""

    monitor_year: int = Field(ge=1900, le=2100)
    total_area_ha: Decimal = Field(ge=0)
    farmland_area_ha: Decimal = Field(ge=0)
    crop_area_ha: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_area_relationships(self) -> Self:
        """校验总面积、耕地面积和作物面积的包含关系。

        Returns:
            Self: 通过面积逻辑校验的快照。
        """
        if self.farmland_area_ha > self.total_area_ha:
            raise ValueError("耕地面积不得大于总面积")
        if self.crop_area_ha > self.farmland_area_ha:
            raise ValueError("作物面积不得大于耕地面积")
        return self


class AreaStatisticsSnapshotImportMetadata(BaseModel):
    """历史年度统计 CSV 导入元数据。"""

    source_name: str = Field(min_length=1, max_length=120)
    source_uri: str = Field(min_length=1, max_length=500)
    source_version: str = Field(min_length=1, max_length=80)
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=1, max_length=500)
    conflict_strategy: Literal["reject", "replace"] = "reject"

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "source_name",
        "source_uri",
        "source_version",
        "operator_code",
        "comment",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理历史统计来源和审计文本。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("历史统计来源和审计说明不得为空")
        return normalized


class AreaStatisticsSnapshotImportResponse(BaseModel):
    """历史年度统计快照导入结果。"""

    task_code: str
    batch_code: str
    imported_count: int
    replaced_count: int
    years: list[int]
    source_checksum_sha256: str
    imported_by: str
    imported_by_code: str
    imported_by_role: str
    imported_at: datetime


class AreaStatisticsResponse(BaseModel):
    """任务面积统计分析聚合响应。"""

    task_code: str
    monitor_year: int
    generated_at: datetime
    total_plot_count: int
    total_area_ha: float
    total_area_mu: float
    average_plot_area_ha: float
    farmland_area_ha: float
    crop_assigned_plot_count: int
    crop_assignment_rate: float
    by_land_class: list[AreaGroupItem]
    by_crop_type: list[AreaGroupItem]
    by_planting_mode: list[AreaGroupItem]
    by_city: list[AreaGroupItem]
    by_district: list[AreaGroupItem]
    by_village: list[AreaGroupItem]
    annual_trend: list[AreaTrendItem]
