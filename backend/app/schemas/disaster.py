"""灾害斑块监测与受灾范围评估请求响应模型。"""

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DISASTER_TYPES = {"洪涝", "干旱", "冻害", "病虫害", "风雹", "其他"}
DISASTER_SEVERITIES = {"轻度", "中度", "重度", "绝收"}


class DisasterPolygonGeometry(BaseModel):
    """灾害模型输出的 WGS84 Polygon 几何。"""

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[tuple[float, float]]]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_polygon(self) -> Self:
        """校验灾害斑块环闭合、节点数量和坐标范围。

        Returns:
            Self: 通过基础几何校验的灾害 Polygon。
        """
        if not self.coordinates:
            raise ValueError("灾害斑块至少包含一个外环")
        if sum(len(ring) for ring in self.coordinates) > 10000:
            raise ValueError("单个灾害斑块节点数不得超过 10000")
        for ring in self.coordinates:
            if len(ring) < 4:
                raise ValueError("灾害斑块环至少包含 4 个坐标点")
            if ring[0] != ring[-1]:
                raise ValueError("灾害斑块环必须闭合")
            for lon, lat in ring:
                if not -180 <= lon <= 180 or not -90 <= lat <= 90:
                    raise ValueError("灾害斑块坐标超出 WGS84 合法范围")
        return self


class DisasterImportProperties(BaseModel):
    """单个灾害模型斑块的标准属性。"""

    patch_code: str = Field(min_length=1, max_length=60, pattern=r"^[\w-]+$")
    source_feature_id: str = Field(min_length=1, max_length=100)
    disaster_type: str
    severity: str
    crop_type: str | None = Field(default=None, max_length=50)
    detected_at: date
    ndvi_change: float | None = Field(default=None, ge=-1, le=1)

    model_config = ConfigDict(extra="ignore")

    @field_validator(
        "patch_code",
        "source_feature_id",
        "disaster_type",
        "severity",
        "crop_type",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """清理模型属性文本。

        Args:
            value: 原始属性文本。

        Returns:
            str | None: 去除首尾空格后的文本。
        """
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("disaster_type")
    @classmethod
    def validate_disaster_type(cls, value: str) -> str:
        """校验平台支持的灾害类型。

        Args:
            value: 灾害类型。

        Returns:
            str: 合法灾害类型。
        """
        if value not in DISASTER_TYPES:
            raise ValueError("灾害类型不合法")
        return value

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        """校验平台支持的灾害等级。

        Args:
            value: 灾害等级。

        Returns:
            str: 合法灾害等级。
        """
        if value not in DISASTER_SEVERITIES:
            raise ValueError("灾害等级不合法")
        return value


class DisasterImportFeature(BaseModel):
    """灾害模型 GeoJSON Feature。"""

    type: Literal["Feature"] = "Feature"
    geometry: DisasterPolygonGeometry
    properties: DisasterImportProperties

    model_config = ConfigDict(extra="ignore")


class DisasterGeoJsonImportRequest(BaseModel):
    """灾害模型 GeoJSON 批量导入请求。"""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    source_name: str = Field(min_length=1, max_length=120)
    source_uri: str = Field(min_length=1, max_length=500)
    source_version: str = Field(min_length=1, max_length=80)
    operator_code: str = Field(min_length=1, max_length=50)
    conflict_policy: Literal["reject", "replace"] = "reject"
    comment: str = Field(min_length=1, max_length=500)
    features: list[DisasterImportFeature] = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "source_name",
        "source_uri",
        "source_version",
        "operator_code",
        "comment",
    )
    @classmethod
    def normalize_import_text(cls, value: str) -> str:
        """清理导入来源与操作审计文本。

        Args:
            value: 原始文本。

        Returns:
            str: 非空标准化文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("灾害导入来源和操作说明不得为空")
        return normalized

    @model_validator(mode="after")
    def validate_collection(self) -> Self:
        """校验批次编号唯一性和总节点上限。

        Returns:
            Self: 通过批次约束的 FeatureCollection。
        """
        patch_codes = [item.properties.patch_code for item in self.features]
        if len(patch_codes) != len(set(patch_codes)):
            raise ValueError("同一导入批次中灾害斑块编号不得重复")
        source_ids = [item.properties.source_feature_id for item in self.features]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("同一导入批次中来源要素编号不得重复")
        total_vertices = sum(
            len(ring)
            for feature in self.features
            for ring in feature.geometry.coordinates
        )
        if total_vertices > 50000:
            raise ValueError("单次灾害导入总节点数不得超过 50000")
        return self


class DisasterGeoJsonImportResponse(BaseModel):
    """灾害模型 GeoJSON 批量导入结果。"""

    task_code: str
    batch_code: str
    imported_count: int
    created_count: int
    replaced_count: int
    patch_codes: list[str]
    source_checksum_sha256: str
    imported_by: str
    imported_by_code: str
    imported_by_role: str
    imported_at: datetime


class DisasterPatchResponse(BaseModel):
    """单个灾害斑块响应。"""

    patch_code: str
    disaster_type: str
    severity: str
    affected_area_ha: float
    crop_type: str | None
    detected_at: date
    ndvi_change: float | None
    status: str
    source: str
    source_uri: str | None
    source_version: str | None
    source_feature_id: str | None
    source_checksum_sha256: str | None
    import_batch_code: str | None
    imported_by: str | None
    imported_by_code: str | None
    imported_by_role: str | None
    reviewed_by: str | None
    reviewed_by_code: str | None
    reviewed_by_role: str | None
    review_comment: str | None
    reviewed_at: datetime | None
    geometry: dict


class DisasterGroupItem(BaseModel):
    """灾害类型或等级聚合指标。"""

    label: str
    patch_count: int
    area_ha: float
    percentage: float


class DisasterSummaryResponse(BaseModel):
    """任务灾害斑块和受灾面积汇总。"""

    task_code: str
    generated_at: datetime
    total_patches: int
    affected_area_ha: float
    pending_count: int
    confirmed_count: int
    by_severity: list[DisasterGroupItem]
    by_type: list[DisasterGroupItem]
    items: list[DisasterPatchResponse]
    feature_collection: dict


class DisasterPatchUpdateRequest(BaseModel):
    """人工修正灾害等级和确认状态请求。"""

    severity: str
    status: str
    reviewer_code: str
    comment: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        """校验灾害等级。

        Args:
            value: 灾害等级。

        Returns:
            str: 合法灾害等级。
        """
        if value not in DISASTER_SEVERITIES:
            raise ValueError("灾害等级不合法")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """校验斑块确认状态。

        Args:
            value: 确认状态。

        Returns:
            str: 合法确认状态。
        """
        if value not in {"pending", "confirmed", "excluded"}:
            raise ValueError("灾害确认状态不合法")
        return value

    @field_validator("reviewer_code")
    @classmethod
    def validate_reviewer_code(cls, value: str) -> str:
        """校验灾害复核人编码。

        Args:
            value: 项目用户编码。

        Returns:
            str: 清理后的用户编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("复核人编码不得为空")
        return normalized
