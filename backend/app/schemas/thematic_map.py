"""专题制图模板、批量生成、成果清单和下载响应模型。"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ThematicMapTemplateCreateRequest(BaseModel):
    """创建持久化专题图版式模板请求。"""

    template_code: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    template_name: str = Field(min_length=2, max_length=150)
    title_pattern: str = Field(min_length=2, max_length=200)
    producer: str = Field(min_length=2, max_length=150)
    page_width_px: int = Field(default=1800, ge=800, le=8000)
    page_height_px: int = Field(default=1200, ge=600, le=8000)
    dpi: int = Field(default=150, ge=72, le=600)
    margin_px: int = Field(default=60, ge=20, le=800)
    legend_position: Literal["bottom_right", "bottom_left"] = "bottom_right"
    include_neatline: bool = True
    include_north_arrow: bool = True
    include_scale_bar: bool = True
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=5, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "template_code",
        "template_name",
        "title_pattern",
        "producer",
        "operator_code",
        "comment",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """清理模板必填文本。

        Args:
            value: 原始字符串。

        Returns:
            str: 去除首尾空白后的字符串。
        """
        return value.strip()


class ThematicMapTemplateResponse(BaseModel):
    """专题图模板响应。"""

    template_code: str
    template_name: str
    title_pattern: str
    producer: str
    page_width_px: int
    page_height_px: int
    dpi: int
    margin_px: int
    legend_position: str
    include_neatline: bool
    include_north_arrow: bool
    include_scale_bar: bool
    created_by: str
    created_by_code: str
    created_by_role: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ThematicMapGenerationItem(BaseModel):
    """批量生成中的单张专题图定义。"""

    source_product_code: Literal["true_color", "false_color", "ndvi"]
    output_format: Literal["png", "pdf"]
    map_name: str = Field(min_length=2, max_length=200)
    map_number: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    map_date: date

    model_config = ConfigDict(extra="forbid")

    @field_validator("map_name", "map_number")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """清理单张专题图名称和图号。

        Args:
            value: 原始文本。

        Returns:
            str: 规范文本。
        """
        return value.strip()


class ThematicMapBatchGenerateRequest(BaseModel):
    """从同一已校验影像资产批量生成专题图请求。"""

    template_code: str = Field(min_length=1, max_length=80)
    asset_code: str = Field(min_length=1, max_length=80)
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=5, max_length=500)
    items: list[ThematicMapGenerationItem] = Field(min_length=1, max_length=12)

    model_config = ConfigDict(extra="forbid")

    @field_validator("template_code", "asset_code", "operator_code", "comment")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """清理批量生成必填文本。

        Args:
            value: 原始文本。

        Returns:
            str: 规范文本。
        """
        return value.strip()

    @field_validator("items")
    @classmethod
    def validate_unique_items(
        cls,
        value: list[ThematicMapGenerationItem],
    ) -> list[ThematicMapGenerationItem]:
        """禁止批次内重复图号、产品和格式。

        Args:
            value: 批量成图定义。

        Returns:
            list[ThematicMapGenerationItem]: 唯一批次项。
        """
        keys = [
            (item.map_number, item.source_product_code, item.output_format)
            for item in value
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("同一批次存在重复图号、产品和格式")
        return value


class ThematicMapSourceResponse(BaseModel):
    """可用于制图的实体影像产品来源。"""

    asset_code: str
    asset_name: str
    acquired_at: datetime
    data_status: str
    source_uri: str | None
    source_checksum_sha256: str | None
    available_products: list[str]
    eligible: bool
    unavailable_reason: str | None


class ThematicMapProductResponse(BaseModel):
    """专题图实体成果及来源校验响应。"""

    product_code: str
    template_code: str
    asset_code: str
    map_name: str
    map_number: str
    map_date: date
    source_product_code: str
    output_format: str
    status: str
    file_size_bytes: int
    checksum_sha256: str
    page_width_px: int
    page_height_px: int
    dpi: int
    source_uri: str
    source_checksum_sha256: str
    source_bounds_wgs84: list[float]
    render_manifest: dict
    generated_by: str
    generated_by_code: str
    generated_by_role: str
    generated_at: datetime
    download_url: str
    preview_url: str | None


class ThematicMapAtlasGenerateRequest(BaseModel):
    """将当前任务全部有效 PNG 专题图按指定顺序编排为图集。"""

    atlas_name: str = Field(min_length=2, max_length=200)
    atlas_number: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    product_codes: list[
        Annotated[
            str,
            Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"),
        ]
    ] = Field(min_length=2, max_length=50)
    operator_code: str = Field(min_length=1, max_length=50)
    comment: str = Field(min_length=10, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("atlas_name", "atlas_number", "operator_code", "comment")
    @classmethod
    def normalize_atlas_text(cls, value: str) -> str:
        """清理图集生成必填文本。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空白后的文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("图集名称、编号、操作人和编排说明不得为空")
        return normalized

    @field_validator("product_codes")
    @classmethod
    def validate_unique_product_codes(cls, value: list[str]) -> list[str]:
        """校验图集成员编号非空且不重复。

        Args:
            value: 按页序排列的专题图编号。

        Returns:
            list[str]: 保持用户顺序的唯一编号。
        """
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("图集专题图编号不得为空")
        if len(normalized) != len(set(normalized)):
            raise ValueError("图集专题图编号不得重复")
        return normalized


class ThematicMapAtlasItemResponse(BaseModel):
    """图集内一页专题图的不可变来源快照。"""

    sequence: int
    product_code: str
    map_name: str
    map_number: str
    map_date: date
    product_size_bytes: int
    product_checksum_sha256: str
    member_path: str


class ThematicMapAtlasResponse(BaseModel):
    """专题图集实体包、PDF 与当前性响应。"""

    atlas_code: str
    atlas_name: str
    atlas_number: str
    version: int
    status: str
    package_size_bytes: int
    package_checksum_sha256: str
    pdf_filename: str
    pdf_size_bytes: int
    pdf_checksum_sha256: str
    pdf_page_count: int
    member_count: int
    product_count_snapshot: int
    product_latest_at_snapshot: datetime
    source_snapshot_sha256: str
    atlas_manifest: dict
    generated_by: str
    generated_by_code: str
    generated_by_role: str
    generated_at: datetime
    superseded_at: datetime | None
    members: list[ThematicMapAtlasItemResponse]
    is_current: bool
    stale_reason: str | None
    download_url: str | None


class ThematicMapOverviewResponse(BaseModel):
    """专题制图模板、可用来源和实体成果总览。"""

    project_code: str
    task_code: str
    template_count: int
    eligible_source_count: int
    product_count: int
    atlas_eligible_product_count: int
    atlas_count: int
    templates: list[ThematicMapTemplateResponse]
    sources: list[ThematicMapSourceResponse]
    products: list[ThematicMapProductResponse]
    atlases: list[ThematicMapAtlasResponse]


class ThematicMapBatchGenerateResponse(BaseModel):
    """批量专题图生成结果。"""

    generated_count: int
    products: list[ThematicMapProductResponse]


class ThematicMapAtlasGenerateResponse(BaseModel):
    """图集生成结果。"""

    atlas: ThematicMapAtlasResponse
