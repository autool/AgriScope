"""遥感影像预处理流水线业务服务。"""

import asyncio
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import numpy as np
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.warp import transform_bounds
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import (
    calculate_sha256,
    has_supported_raster_signature,
    resolve_imagery_path,
)
from app.dao.imagery_dao import ImageryDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.workbench import (
    ImageryAsset,
    ImageryProcessingStep,
    ReviewRecord,
)
from app.schemas.imagery import (
    ImageryProcessingBatchExecuteRequest,
    ImageryProcessingBatchExecuteResponse,
    ImageryProcessingBatchItemResponse,
    ImageryProcessingResponse,
    ImageryProcessingStepResponse,
    ImagerySourceLevelAcceptRequest,
    ImagerySourceLevelBatchAcceptRequest,
    ImagerySourceLevelBatchAcceptResponse,
    ImagerySourceLevelBatchItemResponse,
    ImageryStepExecuteRequest,
    ImageryStepRunRequest,
)
from app.services.imagery_processing_engine import (
    ImageryProcessingEngine,
    ProcessingExecutionResult,
)
from app.services.project_user_service import ProjectUserService


@dataclass(frozen=True)
class PreparedSourceLevelAcceptance:
    """一个已完成实体证据预检且尚未写入步骤状态的影像。"""

    asset: object
    steps: list[object]
    radiometric_step: object
    atmospheric_step: object
    source_path: Path
    source_evidence: dict
    source_profile: str
    processor_version: str
    expected_processing_level: str


@dataclass(frozen=True)
class PreparedImageryBatchExecution:
    """一个已锁定并完成上游实体预检的批次处理成员。"""

    asset: ImageryAsset
    steps: list[ImageryProcessingStep]
    step: ImageryProcessingStep
    source_path: Path
    source_checksum_sha256: str
    output_path: Path
    output_relative_path: str
    parameters: dict
    boundary_geometry: dict | None


@dataclass(frozen=True)
class ExecutedImageryBatchItem:
    """一个已生成物理产物但尚未提交数据库状态的批次成员。"""

    prepared: PreparedImageryBatchExecution
    result: ProcessingExecutionResult
    output_file_size_bytes: int
    output_checksum_sha256: str


class ImageryService:
    """查询影像处理进度并执行受控流水线步骤。"""

    SOURCE_LEVEL_ACCEPTANCE_BASIS = {
        "sentinel_2_l2a": {
            "radiometric": "源文件已按 STAC 标度转换为 Sentinel-2 L2A BOA 地表反射率",
            "atmospheric": "Sentinel-2 L2A 已完成大气校正并提供 BOA 地表反射率",
        },
        "landsat_collection2_l2": {
            "radiometric": (
                "源文件已按 Raster Extension 标度转换为 "
                "Landsat Collection 2 Level-2 地表反射率"
            ),
            "atmospheric": (
                "USGS Landsat Collection 2 Level-2 已提供"
                "大气校正后的地表反射率"
            ),
        },
    }
    SOURCE_LEVEL_COMMON_REQUIRED_TAGS = (
        "PLATFORM",
        "INSTRUMENT",
        "PROCESSING_LEVEL",
        "SOURCE_PROVIDER",
        "SOURCE_PRODUCT_URI",
    )
    SOURCE_LEVEL_PROCESSOR_VERSIONS = {
        "sentinel_2_l2a": "sentinel-l2a-source-acceptance-v1",
        "landsat_collection2_l2": "landsat-c2-l2-source-acceptance-v1",
    }

    def __init__(
        self,
        dao: ImageryDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
        processing_engine: ImageryProcessingEngine | None = None,
    ) -> None:
        """初始化影像预处理服务。

        Args:
            dao: 影像处理 DAO。
            workbench_dao: 工作台公共 DAO。
            project_user_service: 项目成员能力服务。
            processing_engine: 栅格处理执行引擎。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ImageryDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()
        self.processing_engine = processing_engine or ImageryProcessingEngine()
        self.storage_dir = (
            Path(__file__).resolve().parents[2] / "storage" / "imagery"
        )

    def _resolve_artifact_path(self, relative_path: str) -> Path:
        """将受控相对路径解析到影像存储根目录。

        Args:
            relative_path: 相对于影像存储根目录的产物路径。

        Returns:
            Path: 已确认未越界的绝对路径。
        """
        try:
            return resolve_imagery_path(self.storage_dir, relative_path)
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

    def _inspect_rpc_dem(
        self,
        source_path: Path,
        dem_relative_path: str,
    ) -> tuple[Path, dict]:
        """校验 RPC 源模型及受控 DEM 的结构、范围和物理证据。

        Args:
            source_path: 待正射影像实体。
            dem_relative_path: 影像受控目录内 DEM 相对路径。

        Returns:
            tuple[Path, dict]: DEM 实体路径和可审计证据。
        """
        normalized_path = dem_relative_path.strip()
        prefix = "storage://imagery/"
        if normalized_path.startswith(prefix):
            normalized_path = normalized_path.removeprefix(prefix)
        if not normalized_path:
            raise ValidationException("RPC/DEM 正射必须指定受控 DEM 相对路径")
        dem_path = self._resolve_artifact_path(normalized_path)
        if dem_path == source_path:
            raise ValidationException("RPC 源影像不能同时作为 DEM")
        if not dem_path.is_file():
            raise ValidationException("指定 DEM 实体不存在")
        if not has_supported_raster_signature(dem_path):
            raise ValidationException("DEM 文件头与栅格扩展名不一致")
        try:
            with rasterio.open(source_path) as source:
                rpc_model = source.rpcs
                if rpc_model is None:
                    raise ValidationException("源影像没有可用 RPC 模型")
                rpc_bounds_wgs84 = (
                    rpc_model.long_off - abs(rpc_model.long_scale),
                    rpc_model.lat_off - abs(rpc_model.lat_scale),
                    rpc_model.long_off + abs(rpc_model.long_scale),
                    rpc_model.lat_off + abs(rpc_model.lat_scale),
                )
            with rasterio.open(dem_path) as dem:
                if dem.crs is None:
                    raise ValidationException("DEM 缺少 CRS")
                if dem.width <= 0 or dem.height <= 0 or dem.count <= 0:
                    raise ValidationException("DEM 栅格结构无效")
                dtype = np.dtype(dem.dtypes[0])
                if not np.issubdtype(dtype, np.number) or np.issubdtype(
                    dtype,
                    np.complexfloating,
                ):
                    raise ValidationException("DEM 第一波段必须为实数高程")
                required_bounds = transform_bounds(
                    "EPSG:4326",
                    dem.crs,
                    *rpc_bounds_wgs84,
                    densify_pts=21,
                )
                tolerance = max(abs(value) for value in dem.res) * 0.5
                if not (
                    dem.bounds.left <= required_bounds[0] + tolerance
                    and dem.bounds.bottom <= required_bounds[1] + tolerance
                    and dem.bounds.right >= required_bounds[2] - tolerance
                    and dem.bounds.top >= required_bounds[3] - tolerance
                ):
                    raise ValidationException("DEM 未完整覆盖 RPC 归一化地理范围")
                dem_bounds_wgs84 = transform_bounds(
                    dem.crs,
                    "EPSG:4326",
                    *dem.bounds,
                    densify_pts=21,
                )
                evidence = {
                    "relative_path": normalized_path,
                    "file_size_bytes": dem_path.stat().st_size,
                    "checksum_sha256": calculate_sha256(dem_path),
                    "driver": dem.driver,
                    "crs": dem.crs.to_string(),
                    "width": dem.width,
                    "height": dem.height,
                    "band_count": dem.count,
                    "dtype": dem.dtypes[0],
                    "nodata": dem.nodata,
                    "resolution": [float(value) for value in dem.res],
                    "bounds_wgs84": [float(value) for value in dem_bounds_wgs84],
                    "rpc_required_bounds_wgs84": [
                        float(value) for value in rpc_bounds_wgs84
                    ],
                }
        except RasterioIOError as exc:
            raise ValidationException("RPC 源影像或 DEM 无法由 Rasterio 读取") from exc
        return dem_path, evidence

    def _inspect_step_artifact(
        self,
        step: object,
    ) -> tuple[bool, dict, str | None]:
        """校验步骤登记的实体产物仍存在且校验值一致。

        Args:
            step: 影像处理步骤 ORM 对象。

        Returns:
            tuple[bool, dict, str | None]: 是否有效、证据信息和失败原因。
        """
        try:
            _, evidence = self.resolve_verified_step_artifact_path(step)
        except ValidationException as exc:
            evidence = (step.parameters or {}).get("artifact_evidence") or {}
            return False, evidence, exc.message
        return True, evidence, None

    def resolve_verified_step_artifact_path(
        self,
        step: object,
    ) -> tuple[Path, dict]:
        """解析并校验处理步骤实体产物路径、大小和 SHA256。

        Args:
            step: 影像处理步骤 ORM 对象。

        Returns:
            tuple[Path, dict]: 已校验实体路径和产物证据。
        """
        evidence = (step.parameters or {}).get("artifact_evidence") or {}
        relative_path = evidence.get("relative_path")
        if not relative_path:
            raise ValidationException("尚未登记实体产物")
        try:
            artifact_path = self._resolve_artifact_path(str(relative_path))
        except ValidationException as exc:
            raise ValidationException("登记的产物路径不合法") from exc
        if not artifact_path.is_file():
            raise ValidationException("登记的实体产物不存在")
        if not has_supported_raster_signature(artifact_path):
            raise ValidationException("实体产物文件头与声明格式不一致")
        file_size = artifact_path.stat().st_size
        if file_size != evidence.get("file_size_bytes"):
            raise ValidationException("实体产物大小与登记值不一致")
        checksum = calculate_sha256(artifact_path)
        if checksum != evidence.get("checksum_sha256"):
            raise ValidationException("实体产物 SHA256 与登记值不一致")
        return artifact_path, evidence

    def _to_step_response(self, step: object) -> ImageryProcessingStepResponse:
        """组装包含实体产物校验状态的步骤响应。

        Args:
            step: 影像处理步骤 ORM 对象。

        Returns:
            ImageryProcessingStepResponse: 当前步骤和产物证据。
        """
        verified, evidence, error = self._inspect_step_artifact(step)
        effective_status = (
            "artifact_missing"
            if step.status == "completed" and not verified
            else step.status
        )
        return ImageryProcessingStepResponse(
            step_code=step.step_code,
            step_name=step.step_name,
            sequence=step.sequence,
            is_required=getattr(step, "is_required", True),
            status=effective_status,
            progress=100 if verified else 0,
            parameters=step.parameters or {},
            output_uri=step.output_uri,
            output_verified=verified,
            output_size_bytes=evidence.get("file_size_bytes"),
            output_checksum_sha256=evidence.get("checksum_sha256"),
            processor_name=evidence.get("processor_name"),
            processor_version=evidence.get("processor_version"),
            artifact_error=error,
            started_at=step.started_at,
            completed_at=step.completed_at,
        )

    def resolve_verified_asset_source_path(self, asset: object) -> Path:
        """校验并解析原始影像资产实体文件。

        Args:
            asset: 影像资产 ORM 对象。

        Returns:
            Path: 已通过路径、大小、格式和 SHA256 校验的源文件。
        """
        file_uri = str(getattr(asset, "file_uri", "") or "")
        if not file_uri.startswith("storage://imagery/"):
            raise ValidationException("当前影像资产未关联可处理的实体文件")
        relative_path = file_uri.removeprefix("storage://imagery/")
        source_path = self._resolve_artifact_path(relative_path)
        if not source_path.is_file():
            raise ValidationException("当前影像资产实体文件不存在")
        if not has_supported_raster_signature(source_path):
            raise ValidationException("当前影像资产格式签名不合法")
        expected_size = getattr(asset, "file_size_bytes", None)
        if expected_size is not None and source_path.stat().st_size != expected_size:
            raise ValidationException("当前影像资产文件大小与数据库记录不一致")
        expected_checksum = getattr(asset, "checksum_sha256", None)
        if expected_checksum and calculate_sha256(source_path) != expected_checksum:
            raise ValidationException("当前影像资产 SHA256 与数据库记录不一致")
        return source_path

    def _resolve_step_source_path(
        self,
        asset: object,
        steps: list[object],
        step: object,
    ) -> Path:
        """解析当前步骤应使用的原始影像或上一环节产物。

        Args:
            asset: 影像资产 ORM 对象。
            steps: 资产全部处理步骤。
            step: 当前待执行步骤。

        Returns:
            Path: 已校验的上游实体栅格路径。
        """
        previous_steps = [item for item in steps if item.sequence < step.sequence]
        blockers = [
            item
            for item in previous_steps
            if getattr(item, "is_required", True)
            and not self._inspect_step_artifact(item)[0]
        ]
        if blockers:
            raise ValidationException(
                f"请先完成并校验步骤：{blockers[0].step_name}"
            )
        verified_previous_steps = [
            item for item in previous_steps if self._inspect_step_artifact(item)[0]
        ]
        if not verified_previous_steps:
            return self.resolve_verified_asset_source_path(asset)
        previous_step = max(
            verified_previous_steps,
            key=lambda item: item.sequence,
        )
        evidence = (previous_step.parameters or {}).get("artifact_evidence") or {}
        relative_path = str(evidence.get("relative_path") or "")
        if not relative_path:
            raise ValidationException("上一处理步骤缺少实体产物路径")
        return self._resolve_artifact_path(relative_path)

    @classmethod
    def _inspect_source_level_evidence(
        cls,
        source_path: Path,
        expected_processing_level: str,
    ) -> dict:
        """从实体栅格区分并复核 Sentinel-2 或 Landsat 源级证据。

        Args:
            source_path: 已通过路径、大小和 SHA256 校验的上游实体。
            expected_processing_level: 请求声明的产品级别。

        Returns:
            dict: 从物理文件读取的产品级别、血缘和栅格结构证据。
        """
        try:
            with rasterio.open(source_path) as dataset:
                tags = {
                    str(key).strip().upper(): str(value).strip()
                    for key, value in dataset.tags().items()
                }
                missing_tags = [
                    key
                    for key in cls.SOURCE_LEVEL_COMMON_REQUIRED_TAGS
                    if not tags.get(key)
                ]
                if missing_tags:
                    raise ValidationException(
                        "源产品缺少受控承认标签：" + ", ".join(missing_tags)
                    )
                processing_level = tags["PROCESSING_LEVEL"].upper()
                if processing_level != expected_processing_level.upper():
                    raise ValidationException("源文件处理级别与承认请求不一致")
                source_processing_baseline = (
                    tags.get("SOURCE_PROCESSING_BASELINE")
                    or tags.get("PROCESSING_BASELINE")
                )
                if not source_processing_baseline:
                    raise ValidationException("源产品缺少处理基线证据")
                scale_applied = (
                    tags.get("SOURCE_SCALE_APPLIED")
                    or tags.get("STAC_SCALE_OFFSET_APPLIED")
                    or ""
                ).lower()
                if scale_applied != "true":
                    raise ValidationException("源文件尚未应用 STAC 反射率标度")
                if any(dtype not in {"float32", "float64"} for dtype in dataset.dtypes):
                    raise ValidationException("源文件像元尚未转换为浮点反射率")
                source_profile, reflectance_quantity = (
                    cls._resolve_source_level_profile(
                        tags,
                        processing_level,
                        dataset.count,
                        dataset.descriptions,
                    )
                )
                security_classification = (
                    tags.get("SECURITY_CLASSIFICATION")
                    or tags.get("SOURCE_CLASSIFICATION")
                )
                if str(security_classification or "").lower() in {
                    "public",
                    "public_open_data",
                }:
                    public_missing = [
                        key
                        for key in ("STAC_ITEM_ID", "SOURCE_LICENSE_URL")
                        if not tags.get(key)
                    ]
                    if public_missing:
                        raise ValidationException(
                            "公开源产品缺少来源许可标签："
                            + ", ".join(public_missing)
                        )
                return {
                    "platform": tags["PLATFORM"],
                    "instrument": tags["INSTRUMENT"],
                    "processing_level": processing_level,
                    "source_provider": tags["SOURCE_PROVIDER"],
                    "source_product_uri": tags["SOURCE_PRODUCT_URI"],
                    "source_processing_baseline": source_processing_baseline,
                    "source_profile": source_profile,
                    "stac_item_id": tags.get("STAC_ITEM_ID"),
                    "stac_collection": tags.get("STAC_COLLECTION"),
                    "source_license_url": tags.get("SOURCE_LICENSE_URL"),
                    "security_classification": security_classification,
                    "source_scale_applied": True,
                    "reflectance_quantity": reflectance_quantity,
                    "wrs_path": tags.get("WRS_PATH"),
                    "wrs_row": tags.get("WRS_ROW"),
                    "raster_width": dataset.width,
                    "raster_height": dataset.height,
                    "band_count": dataset.count,
                    "dtypes": list(dataset.dtypes),
                    "crs": dataset.crs.to_string() if dataset.crs else None,
                    "band_descriptions": list(dataset.descriptions),
                }
        except RasterioIOError as exc:
            raise ValidationException("源产品无法由 Rasterio 读取") from exc

    @classmethod
    def _resolve_source_level_profile(
        cls,
        tags: dict[str, str],
        processing_level: str,
        band_count: int,
        band_descriptions: tuple[str | None, ...],
    ) -> tuple[str, str]:
        """按物理标签识别受支持产品族并执行族内严格门禁。

        Args:
            tags: 大写规范化栅格标签。
            processing_level: 已与请求一致的处理级别。
            band_count: 实体波段数量。
            band_descriptions: 实体波段描述。

        Returns:
            tuple[str, str]: 产品族编码和反射率类型。
        """
        platform = tags["PLATFORM"].upper()
        instrument = tags["INSTRUMENT"].upper()
        reflectance_quantity = str(tags.get("REFLECTANCE_QUANTITY") or "").upper()
        if platform.startswith("SENTINEL-2"):
            if processing_level != "L2A" or instrument != "MSI":
                raise ValidationException("Sentinel-2 源级承认要求 MSI L2A 产品")
            if reflectance_quantity != "BOA_REFLECTANCE":
                raise ValidationException("Sentinel-2 源文件不是 L2A BOA 地表反射率")
            return "sentinel_2_l2a", reflectance_quantity
        if platform.startswith("LANDSAT-"):
            if processing_level != "L2":
                raise ValidationException("Landsat 源级承认仅支持 Collection 2 Level-2")
            cls._validate_landsat_source_level_tags(
                tags,
                instrument,
                band_count,
                band_descriptions,
            )
            if reflectance_quantity not in {
                "SURFACE_REFLECTANCE",
                "BOA_REFLECTANCE",
            }:
                if tags.get("SURFACE_REFLECTANCE", "").lower() != "true":
                    raise ValidationException("Landsat 源文件不是地表反射率")
                reflectance_quantity = "SURFACE_REFLECTANCE"
            return "landsat_collection2_l2", reflectance_quantity
        raise ValidationException("当前源产品平台不支持源级承认")

    @classmethod
    def _validate_landsat_source_level_tags(
        cls,
        tags: dict[str, str],
        instrument: str,
        band_count: int,
        band_descriptions: tuple[str | None, ...],
    ) -> None:
        """校验 Landsat Collection 2 Level-2 特有来源和标度证据。

        Args:
            tags: 大写规范化栅格标签。
            instrument: Landsat 载荷名称。
            band_count: 实体波段数量。
            band_descriptions: 实体波段描述。

        Returns:
            None: 全部门禁通过后无返回值。
        """
        if instrument not in {"TM", "ETM", "ETM+", "OLI", "OLI_TIRS", "OLI-TIRS"}:
            raise ValidationException("Landsat 源产品载荷不属于受支持光学传感器")
        if tags.get("STAC_COLLECTION") != "landsat-c2-l2":
            raise ValidationException("Landsat 源产品不属于受控 Collection 2 Level-2")
        missing_tags = [
            key
            for key in (
                "STAC_ITEM_ID",
                "STAC_ITEM_URL",
                "WRS_PATH",
                "WRS_ROW",
                "STAC_CALIBRATION",
                "SOURCE_BLUE_URL",
                "SOURCE_GREEN_URL",
                "SOURCE_RED_URL",
                "SOURCE_NIR_URL",
            )
            if not tags.get(key)
        ]
        if missing_tags:
            raise ValidationException(
                "Landsat 源产品缺少受控证据：" + ", ".join(missing_tags)
            )
        provider = tags["SOURCE_PROVIDER"].upper()
        baseline = (
            tags.get("SOURCE_PROCESSING_BASELINE")
            or tags.get("PROCESSING_BASELINE")
            or ""
        ).upper()
        if "PLANETARY COMPUTER" not in provider or "USGS" not in provider:
            raise ValidationException("Landsat 来源提供方证据不合法")
        if "LANDSAT COLLECTION 2 LEVEL-2" not in baseline:
            raise ValidationException("Landsat 处理基线不是 Collection 2 Level-2")
        if tags["SOURCE_PRODUCT_URI"] != tags["STAC_ITEM_ID"]:
            raise ValidationException("Landsat 产品编号与 STAC Item ID 不一致")
        cls._validate_landsat_public_urls(tags)
        normalized_descriptions = tuple(
            str(description or "").strip().upper()
            for description in band_descriptions
        )
        if band_count < 4 or normalized_descriptions[:4] != (
            "BLUE",
            "GREEN",
            "RED",
            "NIR",
        ):
            raise ValidationException(
                "Landsat 源产品必须提供 Blue/Green/Red/NIR 四波段"
            )
        try:
            calibration = json.loads(tags["STAC_CALIBRATION"])
        except json.JSONDecodeError as exc:
            raise ValidationException("Landsat STAC 标度清单不是合法 JSON") from exc
        if not isinstance(calibration, list) or len(calibration) != 4:
            raise ValidationException("Landsat STAC 标度清单必须完整覆盖四个波段")
        expected_assets = ("blue", "green", "red", "nir08")
        for entry, expected_asset in zip(calibration, expected_assets, strict=True):
            if not isinstance(entry, dict) or entry.get("asset") != expected_asset:
                raise ValidationException("Landsat STAC 标度清单波段顺序不合法")
            for key in ("scale", "offset"):
                value = entry.get(key)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int | float)
                    or not math.isfinite(float(value))
                ):
                    raise ValidationException("Landsat STAC 标度清单缺少数值参数")
            if float(entry["scale"]) <= 0:
                raise ValidationException("Landsat STAC 标度 scale 必须大于 0")

    @staticmethod
    def _validate_landsat_public_urls(tags: dict[str, str]) -> None:
        """校验 Landsat STAC Item 与四个无签名 Azure COG 来源地址。

        Args:
            tags: 大写规范化栅格标签。

        Returns:
            None: 来源地址全部通过后无返回值。
        """
        item_url = urlparse(tags["STAC_ITEM_URL"])
        if (
            item_url.scheme != "https"
            or item_url.hostname != "planetarycomputer.microsoft.com"
            or item_url.query
            or not item_url.path.endswith(f"/{tags['STAC_ITEM_ID']}")
        ):
            raise ValidationException("Landsat STAC Item URL 不属于受控来源")
        for key in (
            "SOURCE_BLUE_URL",
            "SOURCE_GREEN_URL",
            "SOURCE_RED_URL",
            "SOURCE_NIR_URL",
        ):
            parsed = urlparse(tags[key])
            hostname = parsed.hostname or ""
            if (
                parsed.scheme != "https"
                or not hostname.endswith(".blob.core.windows.net")
                or parsed.query
                or not parsed.path.lower().endswith((".tif", ".tiff"))
            ):
                raise ValidationException("Landsat 波段 URL 不属于无签名 Azure COG")

    @staticmethod
    def _update_asset_status(asset: object, step_code: str) -> None:
        """根据真实完成步骤更新资产处理状态。

        Args:
            asset: 影像资产 ORM 对象。
            step_code: 已完成步骤编码。

        Returns:
            None: 无返回值。
        """
        if step_code == "radiometric":
            asset.calibration_status = "completed"
            asset.correction_status = "pending"
        if step_code == "atmospheric":
            asset.correction_status = "in_progress"
        if step_code == "geometric":
            asset.correction_status = "completed"

    @staticmethod
    def _invalidate_downstream_steps(
        asset: object,
        steps: list[object],
        completed_step: object,
    ) -> list[str]:
        """重跑上游步骤时失效下游产物并保留历史证据。

        Args:
            asset: 当前影像资产。
            steps: 资产全部处理步骤。
            completed_step: 本次重新完成的步骤。

        Returns:
            list[str]: 被失效的下游步骤编码。
        """
        invalidated: list[str] = []
        superseded_at = datetime.now(UTC).isoformat()
        for downstream in steps:
            if downstream.sequence <= completed_step.sequence:
                continue
            parameters = dict(downstream.parameters or {})
            old_evidence = parameters.pop("artifact_evidence", None)
            if old_evidence:
                history = list(parameters.get("artifact_history") or [])
                history.append({
                    **old_evidence,
                    "superseded_at": superseded_at,
                    "superseded_by_step": completed_step.step_code,
                })
                parameters["artifact_history"] = history
            downstream.parameters = parameters
            downstream.status = "pending"
            downstream.progress = 0
            downstream.output_uri = None
            downstream.started_at = None
            downstream.completed_at = None
            invalidated.append(downstream.step_code)
        if completed_step.step_code == "radiometric":
            asset.correction_status = "pending"
        elif completed_step.step_code == "atmospheric":
            asset.correction_status = "in_progress"
        return invalidated

    async def _persist_step_completion(
        self,
        db: AsyncSession,
        task: object,
        asset: object,
        step: object,
        relative_path: str,
        processor_name: str,
        processor_version: str,
        operator: object,
        comment: str | None,
        evidence_extra: dict | None = None,
        action: str = "processing_step_completed",
        commit: bool = True,
    ) -> None:
        """保存处理产物证据、状态和不可变审核记录。

        Args:
            db: 异步数据库会话。
            task: 当前作业任务。
            asset: 当前影像资产。
            step: 已完成步骤。
            relative_path: 产物受控相对路径。
            processor_name: 处理器名称。
            processor_version: 处理器版本。
            operator: 已通过能力校验的项目用户。
            comment: 处理说明。
            evidence_extra: 内置处理器输出的附加证据。
            action: 审核动作编码。
            commit: 是否由当前方法立即提交事务。

        Returns:
            None: 完成数据库持久化后返回。
        """
        artifact_path = self._resolve_artifact_path(relative_path)
        file_size_bytes = artifact_path.stat().st_size
        checksum_sha256 = await asyncio.to_thread(calculate_sha256, artifact_path)
        now = datetime.now(UTC)
        step.status = "completed"
        step.progress = 100
        step.started_at = step.started_at or now
        step.completed_at = now
        step.updated_at = now
        step.output_uri = f"storage://imagery/{relative_path}"
        parameters = dict(step.parameters or {})
        previous_evidence = parameters.get("artifact_evidence")
        if previous_evidence:
            history = list(parameters.get("artifact_history") or [])
            history.append({
                **previous_evidence,
                "superseded_at": now.isoformat(),
                "superseded_by_step": step.step_code,
                "superseded_by_operator_code": operator.user_code,
            })
            parameters["artifact_history"] = history
        parameters["artifact_evidence"] = {
            "relative_path": relative_path,
            "file_size_bytes": file_size_bytes,
            "checksum_sha256": checksum_sha256,
            "processor_name": processor_name,
            "processor_version": processor_version,
            "registered_at": now.isoformat(),
            **(evidence_extra or {}),
        }
        step.parameters = parameters
        self._update_asset_status(asset, step.step_code)
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="imagery_processing",
                action=action,
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=(
                    f"{asset.asset_code}/{step.step_name} - "
                    f"产物 {relative_path}，SHA256 {checksum_sha256} - "
                    f"{comment or '处理产物校验完成'}"
                ),
            ),
        )
        if commit:
            await db.commit()

    async def get_processing(
        self,
        db: AsyncSession,
        asset_code: str,
    ) -> ImageryProcessingResponse:
        """获取影像元数据和预处理步骤状态。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。

        Returns:
            ImageryProcessingResponse: 影像处理聚合信息。
        """
        asset = await self.dao.get_asset_by_code(db, asset_code)
        if asset is None:
            raise NotFoundException(f"未找到影像资产 {asset_code}")
        steps = list(await self.dao.get_steps(db, asset.id))
        step_responses = [self._to_step_response(step) for step in steps]
        required_steps = [step for step in step_responses if step.is_required]
        completion_rate = (
            round(
                sum(100 for step in required_steps if step.output_verified)
                / len(required_steps),
                2,
            )
            if required_steps
            else 0
        )
        return ImageryProcessingResponse(
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
            completion_rate=completion_rate,
            completed_steps=sum(step.output_verified for step in required_steps),
            total_steps=len(required_steps),
            steps=step_responses,
        )

    async def run_step(
        self,
        db: AsyncSession,
        asset_code: str,
        step_code: str,
        task_code: str,
        request: ImageryStepRunRequest,
    ) -> ImageryProcessingResponse:
        """校验并登记指定预处理步骤的实体产物与审计日志。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。
            step_code: 处理步骤编号。
            task_code: 作业任务编号。
            request: 操作人和说明。

        Returns:
            ImageryProcessingResponse: 更新后的处理流水线。
        """
        asset = await self.dao.get_asset_by_code_for_update(db, asset_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if asset is None:
            raise NotFoundException(f"未找到影像资产 {asset_code}")
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.project_id != asset.project_id:
            raise ValidationException("作业任务与影像资产不属于同一项目")
        operator = await self.project_user_service.require_capability(
            db,
            asset.project_id,
            request.operator_code,
            "process_imagery",
        )
        step = await self.dao.get_step_for_update(db, asset.id, step_code)
        if step is None:
            raise NotFoundException(f"未找到处理步骤 {step_code}")
        steps = list(await self.dao.get_steps(db, asset.id))
        blockers = [
            item
            for item in steps
            if item.sequence < step.sequence
            and getattr(item, "is_required", True)
            and not self._inspect_step_artifact(item)[0]
        ]
        if blockers:
            raise ValidationException(
                f"请先登记并校验步骤产物：{blockers[0].step_name}"
            )
        artifact_path = self._resolve_artifact_path(request.output_relative_path)
        if not artifact_path.is_file():
            raise ValidationException("指定影像产物不存在，不能标记步骤完成")
        file_size_bytes = artifact_path.stat().st_size
        if file_size_bytes <= 0:
            raise ValidationException("指定影像产物为空文件")
        if not has_supported_raster_signature(artifact_path):
            raise ValidationException("影像产物文件头与扩展名声明的格式不一致")
        invalidated_steps = self._invalidate_downstream_steps(asset, steps, step)
        await self._persist_step_completion(
            db,
            task,
            asset,
            step,
            request.output_relative_path,
            request.processor_name,
            request.processor_version,
            operator,
            request.comment,
            evidence_extra={
                "execution_mode": "external_registration",
                "invalidated_downstream_steps": invalidated_steps,
            },
        )
        return await self.get_processing(db, asset_code)

    async def execute_step(
        self,
        db: AsyncSession,
        asset_code: str,
        step_code: str,
        task_code: str,
        request: ImageryStepExecuteRequest,
    ) -> ImageryProcessingResponse:
        """使用平台内置处理器执行步骤并保存实体产物证据。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。
            step_code: 标准处理步骤编号。
            task_code: 作业任务编号。
            request: 操作人编码、处理参数和说明。

        Returns:
            ImageryProcessingResponse: 执行后的完整流水线状态。
        """
        asset = await self.dao.get_asset_by_code_for_update(db, asset_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if asset is None:
            raise NotFoundException(f"未找到影像资产 {asset_code}")
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.project_id != asset.project_id:
            raise ValidationException("作业任务与影像资产不属于同一项目")
        operator = await self.project_user_service.require_capability(
            db,
            asset.project_id,
            request.operator_code,
            "process_imagery",
        )
        step = await self.dao.get_step_for_update(db, asset.id, step_code)
        if step is None:
            raise NotFoundException(f"未找到处理步骤 {step_code}")
        steps = list(await self.dao.get_steps(db, asset.id))
        source_path = self._resolve_step_source_path(asset, steps, step)
        boundary_geometry = None
        rpc_dem_path = None
        dem_evidence = None
        if step_code == "clip":
            boundary_code = str(request.parameters.get("boundary_code") or "")
            geometry_text = await self.dao.get_boundary_geometry(
                db,
                asset.project_id,
                boundary_code,
            )
            if geometry_text is None:
                raise ValidationException("未找到当前项目的行政区裁剪边界")
            boundary_geometry = json.loads(geometry_text)
        if (
            step_code == "geometric"
            and str(request.parameters.get("method") or "").strip().lower()
            == "rpc_dem"
        ):
            dem_relative_path = str(
                request.parameters.get("dem_relative_path") or ""
            )
            rpc_dem_path, dem_evidence = await asyncio.to_thread(
                self._inspect_rpc_dem,
                source_path,
                dem_relative_path,
            )
        relative_path = (
            Path("processed")
            / asset.asset_code
            / (
                f"{step.sequence:02d}_{step.step_code}_"
                f"{uuid4().hex[:12]}.tif"
            )
        ).as_posix()
        output_path = self._resolve_artifact_path(relative_path)
        source_checksum = await asyncio.to_thread(calculate_sha256, source_path)
        try:
            result = await asyncio.to_thread(
                self.processing_engine.execute,
                step_code,
                source_path,
                output_path,
                request.parameters,
                boundary_geometry,
                rpc_dem_path,
                dem_evidence,
            )
            invalidated_steps = self._invalidate_downstream_steps(
                asset,
                steps,
                step,
            )
            await self._persist_step_completion(
                db,
                task,
                asset,
                step,
                relative_path,
                self.processing_engine.processor_name,
                self.processing_engine.processor_version,
                operator,
                request.comment,
                evidence_extra={
                    "execution_mode": "built_in",
                    "source_relative_path": source_path.relative_to(
                        self.storage_dir
                    ).as_posix(),
                    "source_checksum_sha256": source_checksum,
                    "execution_parameters": result.parameters,
                    "output_width": result.width,
                    "output_height": result.height,
                    "output_band_count": result.band_count,
                    "output_dtype": result.dtype,
                    "output_crs": result.crs,
                    "invalidated_downstream_steps": invalidated_steps,
                },
                action="processing_step_executed",
            )
        except BaseException:
            output_path.unlink(missing_ok=True)
            raise
        return await self.get_processing(db, asset_code)

    async def execute_step_batch(
        self,
        db: AsyncSession,
        task_code: str,
        request: ImageryProcessingBatchExecuteRequest,
    ) -> ImageryProcessingBatchExecuteResponse:
        """原子执行 1–10 景影像的同一个内置预处理步骤。

        服务先锁定全部资产及其步骤，完成项目、业务状态、上游实体、参数所需
        行政区或 DEM 证据校验，再生成全部物理 GeoTIFF。只有全部输出成功后才
        写入步骤状态与审核记录并提交一次事务；任一失败会删除本批新产物。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 同一步骤、逐景参数、稳定操作人和处理依据。

        Returns:
            ImageryProcessingBatchExecuteResponse: 批次编号和逐景实体证据。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "process_imagery",
        )
        prepared_by_code: dict[str, PreparedImageryBatchExecution] = {}
        executed_by_code: dict[str, ExecutedImageryBatchItem] = {}
        generated_paths: list[Path] = []
        batch_code = f"IPB-{uuid4().hex.upper()}"
        created_at = datetime.now(UTC)
        try:
            for request_item in sorted(
                request.items,
                key=lambda item: item.asset_code,
            ):
                asset = await self.dao.get_asset_by_code_for_update(
                    db,
                    request_item.asset_code,
                )
                if asset is None:
                    raise NotFoundException(
                        f"未找到影像资产 {request_item.asset_code}"
                    )
                if asset.project_id != task.project_id:
                    raise ValidationException(
                        f"影像资产 {asset.asset_code} 不属于当前任务项目"
                    )
                if asset.data_status != "operational":
                    raise ValidationException(
                        f"影像资产 {asset.asset_code} 不是可处理的业务数据"
                    )
                steps = list(
                    await self.dao.get_steps_for_update(db, asset.id)
                )
                step = next(
                    (
                        item
                        for item in steps
                        if item.step_code == request.step_code
                    ),
                    None,
                )
                if step is None:
                    raise NotFoundException(
                        f"资产 {asset.asset_code} 缺少步骤 {request.step_code}"
                    )
                if self._inspect_step_artifact(step)[0]:
                    raise ValidationException(
                        f"资产 {asset.asset_code} 的{step.step_name}已完成；"
                        "批量执行仅处理待办步骤，重跑请使用单景流程"
                    )
                source_path = self._resolve_step_source_path(
                    asset,
                    steps,
                    step,
                )
                boundary_geometry = None
                if request.step_code == "clip":
                    boundary_code = str(
                        request_item.parameters.get("boundary_code") or ""
                    )
                    geometry_text = await self.dao.get_boundary_geometry(
                        db,
                        asset.project_id,
                        boundary_code,
                    )
                    if geometry_text is None:
                        raise ValidationException(
                            f"资产 {asset.asset_code} 未找到当前项目的行政区裁剪边界"
                        )
                    boundary_geometry = json.loads(geometry_text)
                relative_path = (
                    Path("processed")
                    / asset.asset_code
                    / (
                        f"{step.sequence:02d}_{step.step_code}_"
                        f"{uuid4().hex[:12]}.tif"
                    )
                ).as_posix()
                prepared_by_code[asset.asset_code] = (
                    PreparedImageryBatchExecution(
                        asset=asset,
                        steps=steps,
                        step=step,
                        source_path=source_path,
                        source_checksum_sha256=await asyncio.to_thread(
                            calculate_sha256,
                            source_path,
                        ),
                        output_path=self._resolve_artifact_path(relative_path),
                        output_relative_path=relative_path,
                        parameters=dict(request_item.parameters),
                        boundary_geometry=boundary_geometry,
                    )
                )

            for request_item in sorted(
                request.items,
                key=lambda item: item.asset_code,
            ):
                prepared = prepared_by_code[request_item.asset_code]
                await asyncio.to_thread(
                    self.processing_engine.validate_batch_parameters,
                    request.step_code,
                    prepared.source_path,
                    prepared.parameters,
                    prepared.boundary_geometry,
                )

            for request_item in sorted(
                request.items,
                key=lambda item: item.asset_code,
            ):
                prepared = prepared_by_code[request_item.asset_code]
                result = await asyncio.to_thread(
                    self.processing_engine.execute,
                    request.step_code,
                    prepared.source_path,
                    prepared.output_path,
                    prepared.parameters,
                    prepared.boundary_geometry,
                    None,
                    None,
                )
                generated_paths.append(prepared.output_path)
                executed_by_code[prepared.asset.asset_code] = (
                    ExecutedImageryBatchItem(
                        prepared=prepared,
                        result=result,
                        output_file_size_bytes=(
                            prepared.output_path.stat().st_size
                        ),
                        output_checksum_sha256=await asyncio.to_thread(
                            calculate_sha256,
                            prepared.output_path,
                        ),
                    )
                )

            response_items: list[ImageryProcessingBatchItemResponse] = []
            for request_item in request.items:
                executed = executed_by_code[request_item.asset_code]
                prepared = executed.prepared
                invalidated_steps = self._invalidate_downstream_steps(
                    prepared.asset,
                    prepared.steps,
                    prepared.step,
                )
                await self._persist_step_completion(
                    db,
                    task,
                    prepared.asset,
                    prepared.step,
                    prepared.output_relative_path,
                    self.processing_engine.processor_name,
                    self.processing_engine.processor_version,
                    operator,
                    f"批次 {batch_code}；{request.comment}",
                    evidence_extra={
                        "execution_mode": "built_in_batch",
                        "batch_code": batch_code,
                        "source_relative_path": prepared.source_path.relative_to(
                            self.storage_dir
                        ).as_posix(),
                        "source_checksum_sha256": (
                            prepared.source_checksum_sha256
                        ),
                        "execution_parameters": executed.result.parameters,
                        "output_width": executed.result.width,
                        "output_height": executed.result.height,
                        "output_band_count": executed.result.band_count,
                        "output_dtype": executed.result.dtype,
                        "output_crs": executed.result.crs,
                        "invalidated_downstream_steps": invalidated_steps,
                    },
                    action="processing_step_batch_executed",
                    commit=False,
                )
                response_items.append(
                    ImageryProcessingBatchItemResponse(
                        asset_code=prepared.asset.asset_code,
                        asset_name=prepared.asset.asset_name,
                        step_code=prepared.step.step_code,
                        step_name=prepared.step.step_name,
                        source_file_uri=(
                            "storage://imagery/"
                            f"{prepared.source_path.relative_to(self.storage_dir).as_posix()}"
                        ),
                        source_checksum_sha256=(
                            prepared.source_checksum_sha256
                        ),
                        output_file_uri=(
                            "storage://imagery/"
                            f"{prepared.output_relative_path}"
                        ),
                        output_file_size_bytes=(
                            executed.output_file_size_bytes
                        ),
                        output_checksum_sha256=(
                            executed.output_checksum_sha256
                        ),
                        output_width=executed.result.width,
                        output_height=executed.result.height,
                        output_band_count=executed.result.band_count,
                        output_dtype=executed.result.dtype,
                        output_crs=executed.result.crs,
                        execution_parameters=executed.result.parameters,
                        invalidated_downstream_steps=invalidated_steps,
                    )
                )
            step_name = response_items[0].step_name
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="imagery_processing",
                    action="processing_batch_executed",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"影像处理批次 {batch_code} 原子执行"
                        f"{len(response_items)} 景{step_name}；{request.comment}"
                    ),
                ),
            )
            await db.commit()
        except BaseException:
            for output_path in generated_paths:
                output_path.unlink(missing_ok=True)
            await db.rollback()
            raise

        return ImageryProcessingBatchExecuteResponse(
            batch_code=batch_code,
            step_code=request.step_code,
            step_name=response_items[0].step_name,
            item_count=len(response_items),
            processor_name=self.processing_engine.processor_name,
            processor_version=self.processing_engine.processor_version,
            executed_by=operator.display_name,
            executed_by_code=operator.user_code,
            executed_by_role=operator.role_code,
            comment=request.comment,
            created_at=created_at,
            items=response_items,
        )

    async def accept_source_level_step(
        self,
        db: AsyncSession,
        asset_code: str,
        step_code: str,
        task_code: str,
        request: ImagerySourceLevelAcceptRequest,
    ) -> ImageryProcessingResponse:
        """用物理 Sentinel-2 L2A 或 Landsat C2 L2 证据满足处理要求。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。
            step_code: 仅允许辐射定标或大气校正。
            task_code: 作业任务编号。
            request: 稳定用户、预期级别、无算法确认和承认依据。

        Returns:
            ImageryProcessingResponse: 承认后的完整流水线状态。
        """
        if step_code not in {"radiometric", "atmospheric"}:
            raise ValidationException("源产品级别只能承认辐射定标或大气校正步骤")
        asset = await self.dao.get_asset_by_code_for_update(db, asset_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if asset is None:
            raise NotFoundException(f"未找到影像资产 {asset_code}")
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.project_id != asset.project_id:
            raise ValidationException("作业任务与影像资产不属于同一项目")
        if str(asset.processing_level or "").upper() != (
            request.expected_processing_level
        ):
            raise ValidationException("资产处理级别与源产品承认请求不一致")
        operator = await self.project_user_service.require_capability(
            db,
            asset.project_id,
            request.operator_code,
            "process_imagery",
        )
        step = await self.dao.get_step_for_update(db, asset.id, step_code)
        if step is None:
            raise NotFoundException(f"未找到处理步骤 {step_code}")
        steps = list(await self.dao.get_steps(db, asset.id))
        source_path = self._resolve_step_source_path(asset, steps, step)
        source_evidence = await asyncio.to_thread(
            self._inspect_source_level_evidence,
            source_path,
            request.expected_processing_level,
        )
        source_profile = str(source_evidence["source_profile"])
        acceptance_basis = self.SOURCE_LEVEL_ACCEPTANCE_BASIS[
            source_profile
        ][step_code]
        processor_version = self.SOURCE_LEVEL_PROCESSOR_VERSIONS[source_profile]
        invalidated_steps = self._invalidate_downstream_steps(asset, steps, step)
        relative_path = source_path.relative_to(self.storage_dir).as_posix()
        await self._persist_step_completion(
            db,
            task,
            asset,
            step,
            relative_path,
            "受控源产品级别承认",
            processor_version,
            operator,
            request.justification,
            evidence_extra={
                "execution_mode": "source_level_acceptance",
                "algorithm_executed": False,
                "expected_processing_level": request.expected_processing_level,
                "source_profile": source_profile,
                "acceptance_basis": acceptance_basis,
                "source_evidence": source_evidence,
                "invalidated_downstream_steps": invalidated_steps,
            },
            action="source_level_accepted",
        )
        return await self.get_processing(db, asset_code)

    async def accept_source_level_batch(
        self,
        db: AsyncSession,
        task_code: str,
        request: ImagerySourceLevelBatchAcceptRequest,
    ) -> ImagerySourceLevelBatchAcceptResponse:
        """原子承认 1–10 景源产品的辐射定标和大气校正要求。

        所有实体、SHA-256、产品族和步骤状态先完成预检，再在一个数据库事务中
        写入双步骤证据。任一成员失败时不会保留部分步骤或审核记录。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 影像清单、稳定操作人、无算法确认和人工依据。

        Returns:
            ImagerySourceLevelBatchAcceptResponse: 统一批次和逐景实体证据。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "process_imagery",
        )
        prepared_by_code: dict[str, PreparedSourceLevelAcceptance] = {}
        try:
            for request_item in sorted(
                request.items,
                key=lambda item: item.asset_code,
            ):
                asset = await self.dao.get_asset_by_code_for_update(
                    db,
                    request_item.asset_code,
                )
                if asset is None:
                    raise NotFoundException(
                        f"未找到影像资产 {request_item.asset_code}"
                    )
                if asset.project_id != task.project_id:
                    raise ValidationException(
                        f"影像资产 {asset.asset_code} 不属于当前任务项目"
                    )
                if str(asset.processing_level or "").upper() != (
                    request_item.expected_processing_level
                ):
                    raise ValidationException(
                        f"资产 {asset.asset_code} 处理级别与批次请求不一致"
                    )
                radiometric_step = await self.dao.get_step_for_update(
                    db,
                    asset.id,
                    "radiometric",
                )
                atmospheric_step = await self.dao.get_step_for_update(
                    db,
                    asset.id,
                    "atmospheric",
                )
                if radiometric_step is None or atmospheric_step is None:
                    raise NotFoundException(
                        f"资产 {asset.asset_code} 缺少定标或大气校正步骤"
                    )
                if self._inspect_step_artifact(radiometric_step)[0]:
                    raise ValidationException(
                        f"资产 {asset.asset_code} 的辐射定标步骤已完成"
                    )
                if self._inspect_step_artifact(atmospheric_step)[0]:
                    raise ValidationException(
                        f"资产 {asset.asset_code} 的大气校正步骤已完成"
                    )
                unlocked_steps = list(await self.dao.get_steps(db, asset.id))
                locked_steps = {
                    "radiometric": radiometric_step,
                    "atmospheric": atmospheric_step,
                }
                steps = [
                    locked_steps.get(step.step_code, step)
                    for step in unlocked_steps
                ]
                source_path = self.resolve_verified_asset_source_path(asset)
                source_evidence = await asyncio.to_thread(
                    self._inspect_source_level_evidence,
                    source_path,
                    request_item.expected_processing_level,
                )
                source_profile = str(source_evidence["source_profile"])
                prepared_by_code[asset.asset_code] = (
                    PreparedSourceLevelAcceptance(
                        asset=asset,
                        steps=steps,
                        radiometric_step=radiometric_step,
                        atmospheric_step=atmospheric_step,
                        source_path=source_path,
                        source_evidence=source_evidence,
                        source_profile=source_profile,
                        processor_version=(
                            self.SOURCE_LEVEL_PROCESSOR_VERSIONS[source_profile]
                        ),
                        expected_processing_level=(
                            request_item.expected_processing_level
                        ),
                    )
                )

            acceptance_code = f"SLA-{uuid4().hex.upper()}"
            created_at = datetime.now(UTC)
            for request_item in request.items:
                prepared = prepared_by_code[request_item.asset_code]
                relative_path = prepared.source_path.relative_to(
                    self.storage_dir
                ).as_posix()
                for step in (
                    prepared.radiometric_step,
                    prepared.atmospheric_step,
                ):
                    acceptance_basis = self.SOURCE_LEVEL_ACCEPTANCE_BASIS[
                        prepared.source_profile
                    ][step.step_code]
                    invalidated_steps = self._invalidate_downstream_steps(
                        prepared.asset,
                        prepared.steps,
                        step,
                    )
                    await self._persist_step_completion(
                        db,
                        task,
                        prepared.asset,
                        step,
                        relative_path,
                        "受控源产品级别承认",
                        prepared.processor_version,
                        operator,
                        f"批次 {acceptance_code}；{request.justification}",
                        evidence_extra={
                            "execution_mode": "source_level_acceptance",
                            "algorithm_executed": False,
                            "acceptance_code": acceptance_code,
                            "expected_processing_level": (
                                prepared.expected_processing_level
                            ),
                            "source_profile": prepared.source_profile,
                            "acceptance_basis": acceptance_basis,
                            "source_evidence": prepared.source_evidence,
                            "invalidated_downstream_steps": invalidated_steps,
                        },
                        action="source_level_accepted",
                        commit=False,
                    )
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="imagery_processing",
                    action="source_level_batch_accepted",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"源级原子承认批次 {acceptance_code}，共 "
                        f"{len(request.items)} 景、{len(request.items) * 2} 个步骤；"
                        f"未执行重复算法；{request.justification}"
                    ),
                ),
            )
            await db.commit()
        except BaseException:
            await db.rollback()
            raise

        return ImagerySourceLevelBatchAcceptResponse(
            acceptance_code=acceptance_code,
            item_count=len(request.items),
            accepted_step_count=len(request.items) * 2,
            imported_by=operator.display_name,
            imported_by_code=operator.user_code,
            imported_by_role=operator.role_code,
            justification=request.justification,
            created_at=created_at,
            items=[
                ImagerySourceLevelBatchItemResponse(
                    asset_code=prepared_by_code[item.asset_code].asset.asset_code,
                    asset_name=prepared_by_code[item.asset_code].asset.asset_name,
                    expected_processing_level=(
                        prepared_by_code[
                            item.asset_code
                        ].expected_processing_level
                    ),
                    source_profile=(
                        prepared_by_code[item.asset_code].source_profile
                    ),
                    processor_version=(
                        prepared_by_code[item.asset_code].processor_version
                    ),
                    accepted_steps=["radiometric", "atmospheric"],
                    source_file_uri=(
                        f"storage://imagery/"
                        f"{prepared_by_code[item.asset_code].source_path.relative_to(self.storage_dir).as_posix()}"
                    ),
                    source_file_size_bytes=(
                        prepared_by_code[item.asset_code].source_path.stat().st_size
                    ),
                    source_checksum_sha256=str(
                        prepared_by_code[item.asset_code].asset.checksum_sha256
                    ),
                )
                for item in request.items
            ],
        )
