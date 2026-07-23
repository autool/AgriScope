"""真实遥感影像文件入库、元数据提取与资产目录服务。"""

import asyncio
import json
import math
import os
import re
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import rasterio
from geoalchemy2.elements import WKTElement
from rasterio.errors import RasterioIOError
from rasterio.warp import transform_bounds
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256, has_supported_raster_signature
from app.dao.imagery_dao import ImageryDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.imagery_import import ImageryImportBatch, ImageryImportBatchItem
from app.models.workbench import ImageryAsset, ImageryProcessingStep, ReviewRecord
from app.schemas.imagery import (
    ImageryAssetBatchCreateRequest,
    ImageryAssetBatchResponse,
    ImageryAssetCreateRequest,
    ImageryAssetListResponse,
    ImageryAssetResponse,
)
from app.services.project_user_service import ProjectUserService


@dataclass(frozen=True)
class RasterInspection:
    """从真实栅格文件读取的标准化元数据。"""

    driver: str
    width: int
    height: int
    band_count: int
    crs: str
    bounds_wgs84: tuple[float, float, float, float]
    resolution_m: float
    metadata: dict
    business_metadata: "RasterBusinessMetadata"


@dataclass(frozen=True)
class ExtractedRasterValue:
    """从单个或组合栅格标签解析出的业务值。"""

    value: str | float | datetime | None
    source_tag: str | None = None
    raw_value: str | None = None
    precision: str | None = None
    timezone_assumption: str | None = None


@dataclass(frozen=True)
class RasterBusinessMetadata:
    """栅格文件中可用于业务入库的标准字段。"""

    sensor_type: ExtractedRasterValue
    acquired_at: ExtractedRasterValue
    processing_level: ExtractedRasterValue
    cloud_cover: ExtractedRasterValue


@dataclass(frozen=True)
class ResolvedBusinessMetadata:
    """文件标签与人工补录完成核对后的最终业务元数据。"""

    sensor_type: str
    acquired_at: datetime
    processing_level: str | None
    cloud_cover: float | None
    audit: dict[str, dict[str, object | None]]


@dataclass(frozen=True)
class ImageryBatchUploadFile:
    """一个批量上传文件名和二进制流。"""

    filename: str
    file_handle: BinaryIO


@dataclass(frozen=True)
class PreparedImageryUpload:
    """已完成临时落盘、栅格检查和元数据核对的待发布影像。"""

    request: ImageryAssetCreateRequest
    safe_filename: str
    temporary_path: Path
    final_path: Path
    relative_path: Path
    file_size: int
    checksum_sha256: str
    inspection: RasterInspection
    resolved_metadata: ResolvedBusinessMetadata


class ImageryAssetService:
    """负责影像文件受控落盘、Rasterio 解析和资产入库。"""

    PLATFORM_TAG_ALIASES = (
        "SATELLITE",
        "PLATFORM",
        "SPACECRAFT_NAME",
        "SPACECRAFT_ID",
    )
    SENSOR_TAG_ALIASES = (
        "SENSOR",
        "INSTRUMENT",
        "SENSOR_ID",
        "INSTRUMENT_NAME",
    )
    ACQUIRED_AT_TAG_ALIASES = (
        "ACQUIRED",
        "ACQUISITION_TIME",
        "ACQUISITION_DATE",
        "DATE_ACQUIRED",
        "TIFFTAG_DATETIME",
        "SENSING_TIME",
        "DATATAKE_SENSING_START",
    )
    PROCESSING_LEVEL_TAG_ALIASES = (
        "PROCESSING_LEVEL",
        "PRODUCT_LEVEL",
        "LEVEL",
    )
    CLOUD_COVER_TAG_ALIASES = (
        "CLOUD_COVER",
        "CLOUDY_PIXEL_PERCENTAGE",
        "CLOUD_COVERAGE_ASSESSMENT",
    )

    def __init__(
        self,
        dao: ImageryDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
    ) -> None:
        """初始化影像资产服务。

        Args:
            dao: 影像资产 DAO。
            workbench_dao: 项目、任务和审计 DAO。
            project_user_service: 项目成员能力服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ImageryDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()
        self.storage_dir = (
            Path(__file__).resolve().parents[2] / "storage" / "imagery"
        )

    def _store_temporary_upload(
        self,
        file_handle: BinaryIO,
        suffix: str,
    ) -> tuple[Path, int, str]:
        """将上传流写入临时文件并计算大小和 SHA256。

        Args:
            file_handle: 上传文件二进制流。
            suffix: 已校验扩展名。

        Returns:
            tuple[Path, int, str]: 临时路径、文件大小和 SHA256。
        """
        upload_dir = self.storage_dir / ".uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = upload_dir / f"{uuid4().hex}{suffix}.part"
        file_size = 0
        file_handle.seek(0)
        try:
            with temporary_path.open("wb") as output:
                while chunk := file_handle.read(1024 * 1024):
                    file_size += len(chunk)
                    if file_size > settings.max_imagery_upload_bytes:
                        raise ValidationException("影像文件超过平台允许的最大上传大小")
                    output.write(chunk)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
        if file_size == 0:
            temporary_path.unlink(missing_ok=True)
            raise ValidationException("上传影像文件为空")
        return temporary_path, file_size, calculate_sha256(temporary_path)

    @staticmethod
    def _resolution_m(
        dataset: rasterio.io.DatasetReader,
        bounds_wgs84: tuple[float, float, float, float],
    ) -> float:
        """将栅格分辨率统一估算为米。

        Args:
            dataset: Rasterio 数据集。
            bounds_wgs84: WGS84 包围盒。

        Returns:
            float: 像元空间分辨率米值。
        """
        if dataset.crs and dataset.crs.is_projected:
            _, factor = dataset.crs.linear_units_factor
            return round(max(abs(value) for value in dataset.res) * factor, 4)
        left, bottom, right, top = bounds_wgs84
        center_latitude = math.radians((bottom + top) / 2)
        x_resolution = abs(right - left) / max(dataset.width, 1)
        y_resolution = abs(top - bottom) / max(dataset.height, 1)
        x_metres = x_resolution * 111_320 * math.cos(center_latitude)
        y_metres = y_resolution * 110_540
        return round(max(x_metres, y_metres), 4)

    @staticmethod
    def _safe_tags(tags: dict[str, str]) -> dict[str, str]:
        """限制写入数据库的栅格标签数量和文本长度。

        Args:
            tags: Rasterio 读取的原始标签。

        Returns:
            dict[str, str]: 可安全序列化的精简标签。
        """
        return {
            str(key)[:100]: str(value)[:1000]
            for key, value in list(tags.items())[:100]
        }

    @staticmethod
    def _normalized_tag_index(
        tags: dict[str, str],
    ) -> dict[str, tuple[str, str]]:
        """建立大小写无关的栅格标签索引。

        Args:
            tags: 已限制长度的栅格标签。

        Returns:
            dict[str, tuple[str, str]]: 大写键到原始键和值的索引。
        """
        index: dict[str, tuple[str, str]] = {}
        for key, value in tags.items():
            normalized_key = key.rsplit(":", maxsplit=1)[-1].strip().upper()
            normalized_value = value.strip()
            if normalized_key and normalized_value and normalized_key not in index:
                index[normalized_key] = (key, normalized_value)
        return index

    @staticmethod
    def _find_tag(
        index: dict[str, tuple[str, str]],
        aliases: tuple[str, ...],
    ) -> tuple[str, str] | None:
        """按优先级查找第一个非空业务标签。

        Args:
            index: 大小写无关标签索引。
            aliases: 允许的标准标签别名。

        Returns:
            tuple[str, str] | None: 原始标签名和值。
        """
        for alias in aliases:
            matched = index.get(alias)
            if matched is not None:
                return matched
        return None

    @staticmethod
    def _normalize_business_text(value: str) -> str:
        """标准化业务文本用于冲突比较。

        Args:
            value: 文件或人工提供的业务文本。

        Returns:
            str: 移除空白和标点后的大小写无关文本。
        """
        return re.sub(r"[^\w]+", "", value, flags=re.UNICODE).casefold()

    @classmethod
    def _extract_sensor_type(
        cls,
        index: dict[str, tuple[str, str]],
    ) -> ExtractedRasterValue:
        """从平台和传感器标签组合业务传感器名称。

        Args:
            index: 大小写无关标签索引。

        Returns:
            ExtractedRasterValue: 文件内传感器值和来源标签。
        """
        platform = cls._find_tag(index, cls.PLATFORM_TAG_ALIASES)
        sensor = cls._find_tag(index, cls.SENSOR_TAG_ALIASES)
        matched = [item for item in (platform, sensor) if item is not None]
        if not matched:
            return ExtractedRasterValue(value=None)
        values: list[str] = []
        sources: list[str] = []
        for source, value in matched:
            if cls._normalize_business_text(value) not in {
                cls._normalize_business_text(item) for item in values
            }:
                values.append(value)
            sources.append(source)
        combined = " ".join(values)
        return ExtractedRasterValue(
            value=combined,
            source_tag="+".join(sources),
            raw_value=" | ".join(value for _, value in matched),
        )

    @staticmethod
    def _parse_acquired_at_tag(tag_name: str, raw_value: str) -> ExtractedRasterValue:
        """解析常见卫星采集日期和时间格式并统一为带时区时间。

        Args:
            tag_name: 原始标签名。
            raw_value: 标签原始值。

        Returns:
            ExtractedRasterValue: 带时区采集时间和解析假设。
        """
        value = raw_value.strip()
        date_formats = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d")
        for date_format in date_formats:
            try:
                parsed = datetime.strptime(value, date_format).replace(tzinfo=UTC)
                return ExtractedRasterValue(
                    value=parsed,
                    source_tag=tag_name,
                    raw_value=raw_value,
                    precision="date",
                    timezone_assumption="UTC",
                )
            except ValueError:
                continue
        try:
            if re.fullmatch(r"\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}", value):
                parsed = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
            else:
                normalized = value.replace("Z", "+00:00")
                normalized = re.sub(r"\s+UTC$", "+00:00", normalized)
                parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValidationException(
                f"影像标签 {tag_name} 的采集时间格式无效"
            ) from exc
        timezone_assumption = None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=UTC)
            timezone_assumption = "UTC"
        return ExtractedRasterValue(
            value=parsed,
            source_tag=tag_name,
            raw_value=raw_value,
            precision="datetime",
            timezone_assumption=timezone_assumption,
        )

    @classmethod
    def _extract_business_metadata(
        cls,
        tags: dict[str, str],
    ) -> RasterBusinessMetadata:
        """从栅格标签提取传感器、采集时间、级别和云量。

        Args:
            tags: Rasterio 读取的根标签。

        Returns:
            RasterBusinessMetadata: 可用于入库核对的文件业务元数据。
        """
        index = cls._normalized_tag_index(tags)
        acquired_tag = cls._find_tag(index, cls.ACQUIRED_AT_TAG_ALIASES)
        processing_tag = cls._find_tag(index, cls.PROCESSING_LEVEL_TAG_ALIASES)
        cloud_tag = cls._find_tag(index, cls.CLOUD_COVER_TAG_ALIASES)
        acquired_at = (
            cls._parse_acquired_at_tag(*acquired_tag)
            if acquired_tag is not None
            else ExtractedRasterValue(value=None)
        )
        processing_level = ExtractedRasterValue(
            value=processing_tag[1] if processing_tag else None,
            source_tag=processing_tag[0] if processing_tag else None,
            raw_value=processing_tag[1] if processing_tag else None,
        )
        cloud_cover = ExtractedRasterValue(value=None)
        if cloud_tag is not None:
            raw_cloud = cloud_tag[1].strip().removesuffix("%").strip()
            try:
                parsed_cloud = float(raw_cloud)
            except ValueError as exc:
                raise ValidationException(
                    f"影像标签 {cloud_tag[0]} 的云量不是有效数字"
                ) from exc
            if not math.isfinite(parsed_cloud) or not 0 <= parsed_cloud <= 100:
                raise ValidationException(
                    f"影像标签 {cloud_tag[0]} 的云量必须位于 0 到 100"
                )
            cloud_cover = ExtractedRasterValue(
                value=parsed_cloud,
                source_tag=cloud_tag[0],
                raw_value=cloud_tag[1],
            )
        return RasterBusinessMetadata(
            sensor_type=cls._extract_sensor_type(index),
            acquired_at=acquired_at,
            processing_level=processing_level,
            cloud_cover=cloud_cover,
        )

    @staticmethod
    def _serialize_audit_value(
        value: str | float | datetime | None,
    ) -> str | float | None:
        """将业务值转换为 JSON 可持久化形式。

        Args:
            value: 文本、数值或时间。

        Returns:
            str | float | None: JSON 可序列化值。
        """
        return value.isoformat() if isinstance(value, datetime) else value

    @classmethod
    def _audit_field(
        cls,
        value: str | float | datetime | None,
        source: str,
        raster_value: ExtractedRasterValue,
        user_value: str | float | datetime | None,
    ) -> dict[str, object | None]:
        """生成单个业务元数据字段的来源审计。

        Args:
            value: 最终采用值。
            source: 最终值来源说明。
            raster_value: 文件标签解析结果。
            user_value: 人工补录或核对值。

        Returns:
            dict[str, object | None]: 可写入 raster_metadata 的审计结构。
        """
        return {
            "value": cls._serialize_audit_value(value),
            "source": source,
            "raster_tag": raster_value.source_tag,
            "raster_value": cls._serialize_audit_value(raster_value.value),
            "raster_raw_value": raster_value.raw_value,
            "user_value": cls._serialize_audit_value(user_value),
            "precision": raster_value.precision,
            "timezone_assumption": raster_value.timezone_assumption,
        }

    @classmethod
    def _resolve_text_field(
        cls,
        field_label: str,
        raster_value: ExtractedRasterValue,
        user_value: str | None,
        *,
        required: bool,
        allow_user_refinement: bool,
    ) -> tuple[str | None, str]:
        """核对文件文本标签与人工补录值。

        Args:
            field_label: 中文字段名称。
            raster_value: 文件标签解析结果。
            user_value: 人工补录值。
            required: 最终值是否必填。
            allow_user_refinement: 是否允许人工提供更具体文本。

        Returns:
            tuple[str | None, str]: 最终文本和值来源。
        """
        file_text = raster_value.value if isinstance(raster_value.value, str) else None
        if file_text is None and user_value is None:
            if required:
                raise ValidationException(
                    f"影像文件未包含{field_label}元数据，请人工补录{field_label}"
                )
            return None, "missing"
        if file_text is None:
            return user_value, "user_fallback"
        if user_value is None:
            return file_text, f"raster_tag:{raster_value.source_tag}"
        file_normalized = cls._normalize_business_text(file_text)
        user_normalized = cls._normalize_business_text(user_value)
        if file_normalized == user_normalized:
            return file_text, f"raster_tag:{raster_value.source_tag}"
        if allow_user_refinement and file_normalized in user_normalized:
            return (
                user_value,
                f"user_refinement:raster_tag:{raster_value.source_tag}",
            )
        if allow_user_refinement and user_normalized in file_normalized:
            return file_text, f"raster_tag:{raster_value.source_tag}"
        raise ValidationException(
            f"人工填写的{field_label}与影像标签 {raster_value.source_tag} 不一致"
        )

    @classmethod
    def _resolve_business_metadata(
        cls,
        raster_metadata: RasterBusinessMetadata,
        request: ImageryAssetCreateRequest,
    ) -> ResolvedBusinessMetadata:
        """以文件标签优先规则核对并确定最终业务元数据。

        Args:
            raster_metadata: 文件标签解析结果。
            request: 人工补录和资产标识。

        Returns:
            ResolvedBusinessMetadata: 最终值和逐字段来源审计。
        """
        sensor_type, sensor_source = cls._resolve_text_field(
            "传感器",
            raster_metadata.sensor_type,
            request.sensor_type,
            required=True,
            allow_user_refinement=True,
        )
        processing_level, processing_source = cls._resolve_text_field(
            "处理级别",
            raster_metadata.processing_level,
            request.processing_level,
            required=False,
            allow_user_refinement=False,
        )
        file_acquired_at = raster_metadata.acquired_at.value
        user_acquired_at = request.acquired_at
        if not isinstance(file_acquired_at, datetime) and user_acquired_at is None:
            raise ValidationException(
                "影像文件未包含采集时间元数据，请人工补录采集时间"
            )
        if not isinstance(file_acquired_at, datetime):
            acquired_at = user_acquired_at
            acquired_source = "user_fallback"
        elif user_acquired_at is None:
            acquired_at = file_acquired_at
            acquired_source = (
                f"raster_tag:{raster_metadata.acquired_at.source_tag}"
            )
        else:
            file_utc = file_acquired_at.astimezone(UTC)
            user_utc = user_acquired_at.astimezone(UTC)
            if raster_metadata.acquired_at.precision == "date":
                if file_acquired_at.date() != user_acquired_at.date():
                    raise ValidationException(
                        "人工填写的采集时间与影像日期标签不一致"
                    )
                acquired_at = user_acquired_at
                acquired_source = (
                    "user_refinement:raster_tag:"
                    f"{raster_metadata.acquired_at.source_tag}"
                )
            elif abs((file_utc - user_utc).total_seconds()) <= 1:
                acquired_at = file_acquired_at
                acquired_source = (
                    f"raster_tag:{raster_metadata.acquired_at.source_tag}"
                )
            else:
                raise ValidationException(
                    "人工填写的采集时间与影像时间标签不一致"
                )
        file_cloud = raster_metadata.cloud_cover.value
        user_cloud = request.cloud_cover
        if isinstance(file_cloud, float) and user_cloud is not None:
            if abs(file_cloud - user_cloud) > 0.01:
                raise ValidationException(
                    "人工填写的云量与影像云量标签不一致"
                )
            cloud_cover = file_cloud
            cloud_source = f"raster_tag:{raster_metadata.cloud_cover.source_tag}"
        elif isinstance(file_cloud, float):
            cloud_cover = file_cloud
            cloud_source = f"raster_tag:{raster_metadata.cloud_cover.source_tag}"
        elif user_cloud is not None:
            cloud_cover = user_cloud
            cloud_source = "user_fallback"
        else:
            cloud_cover = None
            cloud_source = "missing"
        if sensor_type is None or acquired_at is None:
            raise ValidationException("影像传感器和采集时间不得为空")
        audit = {
            "sensor_type": cls._audit_field(
                sensor_type,
                sensor_source,
                raster_metadata.sensor_type,
                request.sensor_type,
            ),
            "acquired_at": cls._audit_field(
                acquired_at,
                acquired_source,
                raster_metadata.acquired_at,
                request.acquired_at,
            ),
            "processing_level": cls._audit_field(
                processing_level,
                processing_source,
                raster_metadata.processing_level,
                request.processing_level,
            ),
            "cloud_cover": cls._audit_field(
                cloud_cover,
                cloud_source,
                raster_metadata.cloud_cover,
                request.cloud_cover,
            ),
        }
        return ResolvedBusinessMetadata(
            sensor_type=sensor_type,
            acquired_at=acquired_at,
            processing_level=processing_level,
            cloud_cover=cloud_cover,
            audit=audit,
        )

    def _inspect_raster(self, path: Path, original_suffix: str) -> RasterInspection:
        """使用 Rasterio 读取栅格结构、CRS、范围、波段和标签。

        Args:
            path: 已落盘临时文件。
            original_suffix: 原始文件扩展名。

        Returns:
            RasterInspection: 标准化栅格元数据。
        """
        inspection_path = path.with_suffix(original_suffix)
        os.replace(path, inspection_path)
        try:
            if not has_supported_raster_signature(inspection_path):
                raise ValidationException("文件头与影像格式扩展名不一致")
            with ExitStack() as stack:
                root_dataset = stack.enter_context(rasterio.open(inspection_path))
                nested_dataset = None
                if root_dataset.count <= 0 and root_dataset.subdatasets:
                    nested_dataset = stack.enter_context(
                        rasterio.open(root_dataset.subdatasets[0])
                    )
                dataset = nested_dataset or root_dataset
                if dataset.width <= 0 or dataset.height <= 0 or dataset.count <= 0:
                    raise ValidationException("影像尺寸或波段数量无效")
                rpc_model = dataset.rpcs
                if dataset.crs is None and rpc_model is None:
                    raise ValidationException(
                        "影像缺少 CRS 且没有 RPC，无法统一到 WGS84"
                    )
                if dataset.crs is not None:
                    bounds_wgs84 = transform_bounds(
                        dataset.crs,
                        "EPSG:4326",
                        *dataset.bounds,
                        densify_pts=21,
                    )
                    crs_name = dataset.crs.to_string()
                else:
                    bounds_wgs84 = (
                        rpc_model.long_off - abs(rpc_model.long_scale),
                        rpc_model.lat_off - abs(rpc_model.lat_scale),
                        rpc_model.long_off + abs(rpc_model.long_scale),
                        rpc_model.lat_off + abs(rpc_model.lat_scale),
                    )
                    crs_name = "RPC:WGS84"
                left, bottom, right, top = bounds_wgs84
                if not (
                    -180 <= left < right <= 180
                    and -90 <= bottom < top <= 90
                ):
                    raise ValidationException("影像转换后的 WGS84 范围无效")
                safe_tags = self._safe_tags(dataset.tags())
                tag_namespaces: dict[str, dict[str, str]] = {}
                business_tags = dict(safe_tags)
                for namespace in list(dataset.tag_namespaces())[:20]:
                    if not namespace or namespace.upper() == "DERIVED_SUBDATASETS":
                        continue
                    namespace_tags = self._safe_tags(dataset.tags(ns=namespace))
                    if not namespace_tags:
                        continue
                    tag_namespaces[namespace] = namespace_tags
                    for key, value in namespace_tags.items():
                        business_tags.setdefault(f"{namespace}:{key}", value)
                business_metadata = self._extract_business_metadata(business_tags)
                metadata = {
                    "driver": dataset.driver,
                    "dtypes": list(dataset.dtypes),
                    "nodatavals": [
                        value
                        if value is None or math.isfinite(float(value))
                        else None
                        for value in dataset.nodatavals
                    ],
                    "descriptions": list(dataset.descriptions),
                    "color_interpretations": [
                        item.name for item in dataset.colorinterp
                    ],
                    "block_shapes": [list(item) for item in dataset.block_shapes],
                    "transform": [
                        float(value) for value in list(dataset.transform)[:6]
                    ],
                    "tags": safe_tags,
                    "tag_namespaces": tag_namespaces,
                    "has_rpc": rpc_model is not None,
                    "rpc_summary": (
                        {
                            "error_bias": rpc_model.err_bias,
                            "error_random": rpc_model.err_rand,
                            "longitude_offset": rpc_model.long_off,
                            "longitude_scale": rpc_model.long_scale,
                            "latitude_offset": rpc_model.lat_off,
                            "latitude_scale": rpc_model.lat_scale,
                            "height_offset": rpc_model.height_off,
                            "height_scale": rpc_model.height_scale,
                        }
                        if rpc_model is not None
                        else None
                    ),
                    "subdataset": dataset.name
                    if nested_dataset is not None
                    else None,
                }
                return RasterInspection(
                    driver=dataset.driver,
                    width=dataset.width,
                    height=dataset.height,
                    band_count=dataset.count,
                    crs=crs_name,
                    bounds_wgs84=(left, bottom, right, top),
                    resolution_m=self._resolution_m(dataset, bounds_wgs84),
                    metadata=metadata,
                    business_metadata=business_metadata,
                )
        except RasterioIOError as exc:
            raise ValidationException("影像格式无法识别或文件已损坏") from exc
        finally:
            if inspection_path.exists() and not path.exists():
                os.replace(inspection_path, path)

    @staticmethod
    def _default_steps(asset_id: int) -> list[ImageryProcessingStep]:
        """创建新影像资产的标准必选步骤与可选增强步骤。

        Args:
            asset_id: 影像资产主键。

        Returns:
            list[ImageryProcessingStep]: 待处理步骤列表。
        """
        definitions = [
            ("radiometric", "辐射定标", {"output": "TOA reflectance"}, True),
            ("atmospheric", "大气校正", {"model": "待配置"}, True),
            ("geometric", "几何精校正", {"method": "RPC/GCP"}, True),
            ("clip", "行政区裁剪", {"boundary": "待选择"}, True),
            ("enhancement", "影像增强", {"method": "optional"}, False),
            (
                "band_products",
                "波段与指数产品",
                {"products": ["true_color", "false_color", "NDVI"]},
                True,
            ),
        ]
        return [
            ImageryProcessingStep(
                asset_id=asset_id,
                step_code=step_code,
                step_name=step_name,
                sequence=index,
                is_required=is_required,
                status="pending",
                progress=0,
                parameters=parameters,
            )
            for index, (step_code, step_name, parameters, is_required) in enumerate(
                definitions,
                start=1,
            )
        ]

    def resolve_verified_asset_path(self, asset: ImageryAsset) -> Path:
        """解析并校验影像资产受控实体路径、大小和格式签名。

        Args:
            asset: 影像资产 ORM 对象。

        Returns:
            Path: 已确认位于影像存储根目录内的实体路径。
        """
        if not asset.file_uri or not asset.file_uri.startswith("storage://imagery/"):
            raise ValidationException("仅有元数据，未关联实体文件")
        relative_path = asset.file_uri.removeprefix("storage://imagery/")
        path = (self.storage_dir / relative_path).resolve()
        if not path.is_relative_to(self.storage_dir.resolve()) or not path.is_file():
            raise ValidationException("实体影像文件不存在")
        if path.stat().st_size != asset.file_size_bytes:
            raise ValidationException("实体文件大小与资产记录不一致")
        if not has_supported_raster_signature(path):
            raise ValidationException("实体文件格式签名不合法")
        return path

    def verify_asset_file(self, asset: ImageryAsset) -> tuple[bool, str | None]:
        """返回影像实体文件是否满足受控路径、大小和格式要求。

        Args:
            asset: 影像资产 ORM 对象。

        Returns:
            tuple[bool, str | None]: 是否有效和失败原因。
        """
        try:
            self.resolve_verified_asset_path(asset)
        except ValidationException as exc:
            return False, exc.message
        return True, None

    def _to_response(
        self,
        asset: ImageryAsset,
        footprint_text: str | None,
    ) -> ImageryAssetResponse:
        """组装影像资产目录响应。

        Args:
            asset: 影像资产 ORM 对象。
            footprint_text: WGS84 GeoJSON 范围文本。

        Returns:
            ImageryAssetResponse: 文件和栅格元数据响应。
        """
        file_verified, file_error = self.verify_asset_file(asset)
        return ImageryAssetResponse(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            sensor_type=asset.sensor_type,
            acquired_at=asset.acquired_at,
            cloud_cover=(
                float(asset.cloud_cover) if asset.cloud_cover is not None else None
            ),
            resolution_m=(
                float(asset.resolution_m) if asset.resolution_m is not None else None
            ),
            processing_level=asset.processing_level,
            data_status=asset.data_status,
            calibration_status=asset.calibration_status,
            correction_status=asset.correction_status,
            original_filename=asset.original_filename,
            file_uri=asset.file_uri,
            file_format=asset.file_format,
            file_size_bytes=asset.file_size_bytes,
            checksum_sha256=asset.checksum_sha256,
            band_count=asset.band_count,
            raster_width=asset.raster_width,
            raster_height=asset.raster_height,
            crs=asset.crs,
            raster_metadata=asset.raster_metadata or {},
            imported_by=asset.imported_by,
            footprint=json.loads(footprint_text) if footprint_text else None,
            file_verified=file_verified,
            file_error=file_error,
            created_at=asset.created_at,
        )

    async def list_assets(
        self,
        db: AsyncSession,
        project_code: str,
    ) -> ImageryAssetListResponse:
        """查询项目真实影像资产目录。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。

        Returns:
            ImageryAssetListResponse: 影像资产统计和目录。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        rows = await self.dao.list_assets(db, project.id)
        items = [
            self._to_response(row[ImageryAsset], row["footprint"])
            for row in rows
        ]
        return ImageryAssetListResponse(
            project_code=project_code,
            total=len(items),
            available=sum(item.file_verified for item in items),
            metadata_only=sum(not item.file_verified for item in items),
            items=items,
        )

    async def _prepare_upload(
        self,
        db: AsyncSession,
        request: ImageryAssetCreateRequest,
        original_filename: str,
        file_handle: BinaryIO,
        batch_checksums: set[str],
    ) -> PreparedImageryUpload:
        """临时保存并完整校验一个批次成员，但不发布文件或写数据库。

        Args:
            db: 异步数据库会话。
            request: 单个影像业务元数据。
            original_filename: 上传原始文件名。
            file_handle: 上传二进制流。
            batch_checksums: 当前批次已经出现的 SHA-256 集合。

        Returns:
            PreparedImageryUpload: 已完成全部前置校验的影像成员。
        """
        if await self.dao.get_asset_by_code(db, request.asset_code):
            raise ValidationException(f"影像资产编号 {request.asset_code} 已存在")
        safe_filename = Path(original_filename).name
        suffix = Path(safe_filename).suffix.lower()
        if suffix not in {".tif", ".tiff", ".img", ".hdf"}:
            raise ValidationException(
                f"文件 {safe_filename} 仅支持 GeoTIFF、IMG 或 HDF"
            )
        temporary_path, file_size, checksum = await asyncio.to_thread(
            self._store_temporary_upload,
            file_handle,
            suffix,
        )
        try:
            if checksum in batch_checksums:
                raise ValidationException(
                    f"文件 {safe_filename} 与同批其他文件内容重复"
                )
            inspection = await asyncio.to_thread(
                self._inspect_raster,
                temporary_path,
                suffix,
            )
            resolved_metadata = self._resolve_business_metadata(
                inspection.business_metadata,
                request,
            )
            duplicate = await self.dao.get_asset_by_checksum(db, checksum)
            if duplicate is not None:
                raise ValidationException(
                    f"文件 {safe_filename} 已入库为 {duplicate.asset_code}"
                )
            relative_path = Path("assets") / request.asset_code / safe_filename
            final_path = (self.storage_dir / relative_path).resolve()
            if not final_path.is_relative_to(self.storage_dir.resolve()):
                raise ValidationException("影像资产存储路径不合法")
            if final_path.exists():
                raise ValidationException(
                    f"资产 {request.asset_code} 的目标文件已存在"
                )
            batch_checksums.add(checksum)
            return PreparedImageryUpload(
                request=request,
                safe_filename=safe_filename,
                temporary_path=temporary_path,
                final_path=final_path,
                relative_path=relative_path,
                file_size=file_size,
                checksum_sha256=checksum,
                inspection=inspection,
                resolved_metadata=resolved_metadata,
            )
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _footprint_geojson(inspection: RasterInspection) -> dict:
        """把影像 WGS84 范围转换为闭合 Polygon GeoJSON。

        Args:
            inspection: 栅格检查结果。

        Returns:
            dict: WGS84 Polygon。
        """
        left, bottom, right, top = inspection.bounds_wgs84
        return {
            "type": "Polygon",
            "coordinates": [[
                [left, bottom],
                [right, bottom],
                [right, top],
                [left, top],
                [left, bottom],
            ]],
        }

    @staticmethod
    def _manifest_sha256(
        request: ImageryAssetBatchCreateRequest,
        prepared: list[PreparedImageryUpload],
    ) -> str:
        """计算包含文件实体证据和业务元数据的规范化清单 SHA-256。

        Args:
            request: 原始批量请求。
            prepared: 已校验批次成员。

        Returns:
            str: 64 位十六进制清单 SHA-256。
        """
        payload = {
            "batch_code": request.batch_code,
            "operator_code": request.operator_code,
            "comment": request.comment,
            "items": [
                {
                    "sequence": index,
                    "filename": item.safe_filename,
                    "asset_code": item.request.asset_code,
                    "asset_name": item.request.asset_name,
                    "data_status": item.request.data_status,
                    "file_size_bytes": item.file_size,
                    "checksum_sha256": item.checksum_sha256,
                    "business_metadata": item.resolved_metadata.audit,
                }
                for index, item in enumerate(prepared, start=1)
            ],
        }
        content = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(content).hexdigest()

    @staticmethod
    def _publish_prepared_file(item: PreparedImageryUpload) -> None:
        """以不覆盖既有实体的方式原子发布一个已校验文件。

        临时目录和资产目录都位于同一影像存储根目录，因此使用硬链接可以在
        目标已存在时原子失败，避免并发批次互相覆盖文件。发布成功后移除临时名。

        Args:
            item: 已完成临时落盘和栅格检查的批次成员。

        Returns:
            None: 发布成功后无返回值。
        """
        item.final_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(item.temporary_path, item.final_path)
        except FileExistsError as exc:
            raise ValidationException(
                f"资产 {item.request.asset_code} 的目标文件已存在"
            ) from exc
        except OSError as exc:
            raise ValidationException(
                f"资产 {item.request.asset_code} 的实体文件发布失败"
            ) from exc
        try:
            item.temporary_path.unlink()
        except OSError as exc:
            item.final_path.unlink(missing_ok=True)
            raise ValidationException(
                f"资产 {item.request.asset_code} 的临时文件清理失败"
            ) from exc

    @staticmethod
    def _remove_published_files(paths: list[Path]) -> None:
        """尝试删除当前批次已发布的全部实体文件。

        Args:
            paths: 当前批次已经发布成功的目标路径。

        Returns:
            None: 全部文件删除后无返回值。
        """
        cleanup_errors: list[OSError] = []
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            raise ValidationException("影像批次回滚时实体文件清理失败") from (
                cleanup_errors[0]
            )

    async def upload_assets_batch(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: ImageryAssetBatchCreateRequest,
        files: list[ImageryBatchUploadFile],
    ) -> ImageryAssetBatchResponse:
        """原子校验、发布并登记 1–20 个真实影像文件。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 审计记录所属作业任务。
            request: 批次编号、成员清单、操作人和入库依据。
            files: multipart 上传的文件名和二进制流。

        Returns:
            ImageryAssetBatchResponse: 已提交批次及全部影像资产。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        if task is None or task.project_id != project.id:
            raise ValidationException("作业任务不属于当前项目")
        operator = await self.project_user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_imagery",
        )
        if await self.dao.get_import_batch_by_code(db, request.batch_code):
            raise ValidationException(f"影像入库批次 {request.batch_code} 已存在")
        if len(files) != len(request.items):
            raise ValidationException("上传文件数量与批次清单不一致")
        file_by_name = {item.filename.casefold(): item for item in files}
        if len(file_by_name) != len(files):
            raise ValidationException("上传文件名不得重复")
        manifest_names = {item.filename.casefold() for item in request.items}
        if set(file_by_name) != manifest_names:
            raise ValidationException("上传文件名与批次清单不完全一致")

        prepared: list[PreparedImageryUpload] = []
        published_paths: list[Path] = []
        assets: list[ImageryAsset] = []
        batch_checksums: set[str] = set()
        try:
            for item in request.items:
                source = file_by_name[item.filename.casefold()]
                create_request = ImageryAssetCreateRequest(
                    asset_code=item.asset_code,
                    asset_name=item.asset_name,
                    sensor_type=item.sensor_type,
                    acquired_at=item.acquired_at,
                    cloud_cover=item.cloud_cover,
                    processing_level=item.processing_level,
                    data_status=item.data_status,
                    operator_code=request.operator_code,
                )
                prepared_item = await self._prepare_upload(
                    db,
                    create_request,
                    source.filename,
                    source.file_handle,
                    batch_checksums,
                )
                prepared.append(prepared_item)
                if sum(entry.file_size for entry in prepared) > (
                    settings.max_imagery_batch_upload_bytes
                ):
                    raise ValidationException("影像批次总大小超过平台允许上限")

            manifest_checksum = self._manifest_sha256(request, prepared)
            for item in prepared:
                await asyncio.to_thread(self._publish_prepared_file, item)
                published_paths.append(item.final_path)
                left, bottom, right, top = item.inspection.bounds_wgs84
                footprint_wkt = (
                    f"POLYGON(({left} {bottom},{right} {bottom},"
                    f"{right} {top},{left} {top},{left} {bottom}))"
                )
                asset = await self.dao.add_asset(
                    db,
                    ImageryAsset(
                        project_id=project.id,
                        asset_code=item.request.asset_code,
                        asset_name=item.request.asset_name,
                        sensor_type=item.resolved_metadata.sensor_type,
                        acquired_at=item.resolved_metadata.acquired_at,
                        cloud_cover=item.resolved_metadata.cloud_cover,
                        resolution_m=item.inspection.resolution_m,
                        processing_level=item.resolved_metadata.processing_level,
                        data_status=item.request.data_status,
                        calibration_status="pending",
                        correction_status="pending",
                        original_filename=item.safe_filename,
                        file_uri=(
                            "storage://imagery/"
                            f"{item.relative_path.as_posix()}"
                        ),
                        file_format=item.inspection.driver,
                        file_size_bytes=item.file_size,
                        checksum_sha256=item.checksum_sha256,
                        band_count=item.inspection.band_count,
                        raster_width=item.inspection.width,
                        raster_height=item.inspection.height,
                        crs=item.inspection.crs,
                        raster_metadata={
                            **item.inspection.metadata,
                            "business_metadata": item.resolved_metadata.audit,
                            "import_batch_code": request.batch_code,
                            "import_manifest_sha256": manifest_checksum,
                        },
                        imported_by=operator.display_name,
                        spatial_extent=WKTElement(footprint_wkt, srid=4326),
                    ),
                )
                assets.append(asset)
                await self.dao.add_steps(db, self._default_steps(asset.id))

            batch = await self.dao.add_import_batch(
                db,
                ImageryImportBatch(
                    project_id=project.id,
                    task_id=task.id,
                    batch_code=request.batch_code,
                    item_count=len(prepared),
                    total_size_bytes=sum(item.file_size for item in prepared),
                    manifest_sha256=manifest_checksum,
                    imported_by=operator.display_name,
                    imported_by_code=operator.user_code,
                    imported_by_role=operator.role_code,
                    import_comment=request.comment,
                ),
            )
            await self.dao.add_import_batch_items(
                db,
                [
                    ImageryImportBatchItem(
                        batch_id=batch.id,
                        asset_id=asset.id,
                        sequence=index,
                        original_filename=item.safe_filename,
                        file_size_bytes=item.file_size,
                        checksum_sha256=item.checksum_sha256,
                    )
                    for index, (item, asset) in enumerate(
                        zip(prepared, assets, strict=True),
                        start=1,
                    )
                ],
            )
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="imagery_processing",
                    action="imagery_asset_batch_imported",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"原子导入影像批次 {request.batch_code}，共 "
                        f"{len(prepared)} 个文件、"
                        f"{sum(item.file_size for item in prepared)} 字节，"
                        f"清单 SHA256 {manifest_checksum}；{request.comment}"
                    ),
                ),
            )
            response = ImageryAssetBatchResponse(
                batch_code=batch.batch_code,
                item_count=batch.item_count,
                total_size_bytes=batch.total_size_bytes,
                manifest_sha256=batch.manifest_sha256,
                imported_by=batch.imported_by,
                imported_by_code=batch.imported_by_code,
                imported_by_role=batch.imported_by_role,
                comment=batch.import_comment,
                created_at=batch.created_at,
                items=[
                    self._to_response(
                        asset,
                        json.dumps(self._footprint_geojson(item.inspection)),
                    )
                    for item, asset in zip(prepared, assets, strict=True)
                ],
            )
            await db.commit()
            return response
        except IntegrityError as exc:
            try:
                await db.rollback()
            finally:
                await asyncio.to_thread(
                    self._remove_published_files,
                    published_paths,
                )
            raise ValidationException(
                "影像批次、资产编号或文件校验和已存在"
            ) from exc
        except BaseException:
            try:
                await db.rollback()
            finally:
                await asyncio.to_thread(
                    self._remove_published_files,
                    published_paths,
                )
            raise
        finally:
            for item in prepared:
                item.temporary_path.unlink(missing_ok=True)

    async def upload_asset(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: ImageryAssetCreateRequest,
        original_filename: str,
        file_handle: BinaryIO,
    ) -> ImageryAssetResponse:
        """通过统一原子批次流程接收一个真实影像文件。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 审计记录所属作业任务。
            request: 影像业务元数据。
            original_filename: 上传原始文件名。
            file_handle: 上传二进制流。

        Returns:
            ImageryAssetResponse: 已入库影像资产。
        """
        batch_request = ImageryAssetBatchCreateRequest.model_validate({
            "batch_code": f"IMB-SINGLE-{uuid4().hex.upper()}",
            "operator_code": request.operator_code,
            "comment": f"单文件影像入库：{request.asset_code}",
            "items": [
                {
                    "filename": Path(original_filename).name,
                    "asset_code": request.asset_code,
                    "asset_name": request.asset_name,
                    "sensor_type": request.sensor_type,
                    "acquired_at": request.acquired_at,
                    "cloud_cover": request.cloud_cover,
                    "processing_level": request.processing_level,
                    "data_status": request.data_status,
                }
            ],
        })
        response = await self.upload_assets_batch(
            db,
            project_code,
            task_code,
            batch_request,
            [ImageryBatchUploadFile(Path(original_filename).name, file_handle)],
        )
        return response.items[0]
