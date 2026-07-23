"""公开 Landsat COG 校验、反射率标度和四波段裁取引擎。"""

import json
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.features import is_valid_geom
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from app.core.config import settings
from app.core.exceptions import ValidationException
from app.services.public_imagery_client import PublicImageryClient


@dataclass(frozen=True)
class PublicLandsatBand:
    """一个已校验的 Landsat 地表反射率 STAC 波段。"""

    asset_name: str
    description: str
    unsigned_href: str
    scale: float
    offset: float
    nodata: float | None


@dataclass(frozen=True)
class PublicLandsatItem:
    """服务端从固定 STAC Item 解析出的受控业务元数据。"""

    item_id: str
    acquired_at: datetime
    cloud_cover: float | None
    platform: str
    instrument: str
    processing_level: str
    collection_category: str | None
    wrs_path: int | None
    wrs_row: int | None
    product_id: str
    resolution_m: float
    bbox: tuple[float, float, float, float]
    geometry: dict[str, object]
    item_url: str
    bands: tuple[PublicLandsatBand, ...]


class PublicImageryEngine:
    """校验真实 Landsat Item 并生成四波段浮点地表反射率 GeoTIFF。"""

    BAND_DEFINITIONS = (
        ("blue", "Blue"),
        ("green", "Green"),
        ("red", "Red"),
        ("nir08", "NIR"),
    )
    PROVIDER = "Microsoft Planetary Computer / USGS Landsat"
    LICENSE_NAME = "USGS Landsat data are in the public domain"
    LICENSE_URL = "https://www.usgs.gov/landsat-missions/landsat-data-access"
    NON_STATUTORY_NOTICE = "公开遥感语料，仅用于监测分析，不替代法定调查成果"

    @classmethod
    def parse_item(cls, item: dict[str, Any]) -> PublicLandsatItem:
        """解析并严格校验固定 Landsat Collection 2 L2 STAC Item。

        Args:
            item: Planetary Computer 返回的 STAC Feature。

        Returns:
            PublicLandsatItem: 已验证的条目元数据和波段来源。
        """
        item_id = item.get("id")
        collection = item.get("collection")
        properties = item.get("properties")
        assets = item.get("assets")
        bbox = item.get("bbox")
        geometry = item.get("geometry")
        if not isinstance(item_id, str) or not item_id:
            raise ValidationException("公开 STAC 条目缺少 Item ID")
        if collection != PublicImageryClient.COLLECTION:
            raise ValidationException("公开影像条目不属于受控 Landsat collection")
        if not isinstance(properties, dict) or not isinstance(assets, dict):
            raise ValidationException("公开 STAC 条目缺少属性或资产")
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
            or not all(cls._is_number(value) for value in bbox)
        ):
            raise ValidationException("公开 STAC 条目缺少合法 WGS84 bbox")
        normalized_bbox = tuple(float(value) for value in bbox)
        left, bottom, right, top = normalized_bbox
        if not (-180 <= left < right <= 180 and -90 <= bottom < top <= 90):
            raise ValidationException("公开 STAC 条目的 WGS84 bbox 不合法")
        if (
            not isinstance(geometry, dict)
            or geometry.get("type") not in {"Polygon", "MultiPolygon"}
            or not is_valid_geom(geometry)
        ):
            raise ValidationException("公开 STAC 条目缺少合法 Polygon 足迹")

        acquired_at = cls._datetime_property(properties, "datetime")
        cloud_cover = cls._optional_float(properties.get("eo:cloud_cover"))
        platform = str(properties.get("platform") or "landsat").strip()
        instruments = properties.get("instruments")
        instrument = (
            str(instruments[0]).upper()
            if isinstance(instruments, list) and instruments
            else "LANDSAT"
        )
        processing_level = str(
            properties.get("processing:level")
            or properties.get("landsat:processing_level")
            or "L2"
        ).strip()
        category = properties.get("landsat:collection_category")
        collection_category = str(category).strip() if category is not None else None
        wrs_path = cls._optional_int(properties.get("landsat:wrs_path"))
        wrs_row = cls._optional_int(properties.get("landsat:wrs_row"))
        product_id = str(
            properties.get("landsat:product_id") or item_id
        ).strip()
        resolution_m = cls._optional_float(properties.get("gsd")) or 30.0
        bands = tuple(
            cls._parse_band(assets, asset_name, description)
            for asset_name, description in cls.BAND_DEFINITIONS
        )
        return PublicLandsatItem(
            item_id=item_id,
            acquired_at=acquired_at,
            cloud_cover=cloud_cover,
            platform=platform,
            instrument=instrument,
            processing_level=processing_level,
            collection_category=collection_category,
            wrs_path=wrs_path,
            wrs_row=wrs_row,
            product_id=product_id,
            resolution_m=resolution_m,
            bbox=normalized_bbox,
            geometry=geometry,
            item_url=PublicImageryClient.item_url(item_id),
            bands=bands,
        )

    @staticmethod
    def annotate_coverage_evidence(
        output_path: Path,
        *,
        query_bbox: tuple[float, float, float, float],
        subset_bbox: tuple[float, float, float, float],
        item_coverage_ratio: float,
        union_coverage_ratio: float,
        union_scene_count: int,
    ) -> None:
        """把多景联合覆盖校核证据写入已生成的 GeoTIFF。

        Args:
            output_path: 已生成且仍处于临时区的公开影像实体。
            query_bbox: 本批次共同目标 WGS84 范围。
            subset_bbox: 本景与目标范围相交后的实际裁取矩形。
            item_coverage_ratio: 本景真实 STAC 足迹覆盖比例。
            union_coverage_ratio: 全部所选 STAC 足迹联合覆盖比例。
            union_scene_count: 参与联合覆盖的景数。

        Returns:
            None: 标签写入完成后无返回值。
        """
        with rasterio.open(output_path, "r+") as dataset:
            dataset.update_tags(
                PUBLIC_COVERAGE_BASIS="STAC_GEOMETRY_POSTGIS_GEOGRAPHY",
                PUBLIC_QUERY_BBOX_WGS84=json.dumps(
                    query_bbox,
                    separators=(",", ":"),
                ),
                PUBLIC_SUBSET_BBOX_WGS84=json.dumps(
                    subset_bbox,
                    separators=(",", ":"),
                ),
                PUBLIC_ITEM_QUERY_COVERAGE_RATIO=(
                    f"{item_coverage_ratio:.12f}"
                ),
                PUBLIC_UNION_QUERY_COVERAGE_RATIO=(
                    f"{union_coverage_ratio:.12f}"
                ),
                PUBLIC_UNION_SCENE_COUNT=str(union_scene_count),
            )

    def build_reflectance_subset(
        self,
        item: PublicLandsatItem,
        bbox_wgs84: tuple[float, float, float, float],
        signed_urls: dict[str, str],
        output_path: Path,
    ) -> None:
        """读取四个签名 COG 的同一窗口并生成浮点地表反射率实体。

        Args:
            item: 已校验 Landsat 条目。
            bbox_wgs84: 用户选择的 WGS84 裁取范围。
            signed_urls: 服务端临时获取的波段名到 SAS URL 映射。
            output_path: 本地临时 GeoTIFF 路径。

        Returns:
            None: 实体写入完成后无返回值。
        """
        rasterio_options = {
            "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
            "GDAL_HTTP_MULTIRANGE": "YES",
            "GDAL_HTTP_MAX_RETRY": "3",
            "GDAL_HTTP_RETRY_DELAY": "1",
        }
        try:
            with rasterio.Env(**rasterio_options), ExitStack() as stack:
                datasets = [
                    stack.enter_context(rasterio.open(signed_urls[band.asset_name]))
                    for band in item.bands
                ]
                reference = datasets[0]
                window = self._window_for_bbox(reference, bbox_wgs84)
                width = int(window.width)
                height = int(window.height)
                if width * height > settings.max_public_imagery_import_pixels:
                    raise ValidationException(
                        "公开影像裁取像元超过平台上限，请缩小 WGS84 范围"
                    )
                arrays: list[np.ndarray] = []
                for dataset, band in zip(datasets, item.bands, strict=True):
                    if (
                        dataset.crs != reference.crs
                        or dataset.transform != reference.transform
                        or dataset.width != reference.width
                        or dataset.height != reference.height
                    ):
                        raise ValidationException("Landsat 四个波段不在同一像元网格")
                    raw_data = dataset.read(1, window=window)
                    reflectance = raw_data.astype("float32") * band.scale + band.offset
                    if band.nodata is not None:
                        reflectance[raw_data == band.nodata] = np.nan
                    arrays.append(reflectance)
                stack_data = np.stack(arrays)
                self._write_output(
                    reference,
                    window,
                    stack_data,
                    item,
                    output_path,
                )
        except RasterioIOError as exc:
            raise ValidationException("公开 Landsat COG 无法读取或已失效") from exc
        except KeyError as exc:
            raise ValidationException("公开影像临时签名波段不完整") from exc

    @classmethod
    def fully_covers(
        cls,
        item_bbox: tuple[float, float, float, float],
        query_bbox: tuple[float, float, float, float],
    ) -> bool:
        """判断 STAC bbox 是否完整包含检索裁取窗口。

        Args:
            item_bbox: 条目 WGS84 bbox。
            query_bbox: 检索 WGS84 bbox。

        Returns:
            bool: 四边均完整覆盖时返回 True。
        """
        item_left, item_bottom, item_right, item_top = item_bbox
        left, bottom, right, top = query_bbox
        return (
            item_left <= left
            and item_bottom <= bottom
            and item_right >= right
            and item_top >= top
        )

    @classmethod
    def _parse_band(
        cls,
        assets: dict[str, Any],
        asset_name: str,
        description: str,
    ) -> PublicLandsatBand:
        """解析一个 Landsat STAC 反射率波段的来源和标度。

        Args:
            assets: STAC assets 对象。
            asset_name: 固定波段资产名。
            description: 输出波段描述。

        Returns:
            PublicLandsatBand: 已校验波段。
        """
        asset = assets.get(asset_name)
        if not isinstance(asset, dict):
            raise ValidationException(f"Landsat 条目缺少 {asset_name} 波段")
        href = asset.get("href")
        raster_bands = asset.get("raster:bands")
        if not isinstance(href, str) or not href:
            raise ValidationException(f"Landsat {asset_name} 波段缺少来源 URL")
        PublicImageryClient._validate_unsigned_asset_url(href)
        if not isinstance(raster_bands, list) or not raster_bands:
            raise ValidationException(f"Landsat {asset_name} 波段缺少标度")
        metadata = raster_bands[0]
        if not isinstance(metadata, dict):
            raise ValidationException(f"Landsat {asset_name} 波段标度不合法")
        scale = metadata.get("scale")
        offset = metadata.get("offset")
        nodata = metadata.get("nodata")
        if not cls._is_number(scale) or not cls._is_number(offset):
            raise ValidationException(f"Landsat {asset_name} 波段缺少 scale/offset")
        if nodata is not None and not cls._is_number(nodata):
            raise ValidationException(f"Landsat {asset_name} 波段 nodata 不合法")
        return PublicLandsatBand(
            asset_name=asset_name,
            description=description,
            unsigned_href=href,
            scale=float(scale),
            offset=float(offset),
            nodata=None if nodata is None else float(nodata),
        )

    @staticmethod
    def _window_for_bbox(
        dataset: rasterio.io.DatasetReader,
        bbox_wgs84: tuple[float, float, float, float],
    ) -> Window:
        """把 WGS84 bbox 转换为完整落在 COG 内的整数像元窗口。

        Args:
            dataset: 参考 Landsat COG。
            bbox_wgs84: 目标 WGS84 裁取范围。

        Returns:
            Window: 已校验整数窗口。
        """
        if dataset.crs is None:
            raise ValidationException("公开 Landsat COG 缺少 CRS")
        projected_bbox = transform_bounds(
            "EPSG:4326",
            dataset.crs,
            *bbox_wgs84,
            densify_pts=21,
        )
        window = from_bounds(*projected_bbox, transform=dataset.transform)
        window = window.round_offsets().round_lengths()
        if (
            window.width <= 0
            or window.height <= 0
            or window.col_off < 0
            or window.row_off < 0
            or window.col_off + window.width > dataset.width
            or window.row_off + window.height > dataset.height
        ):
            raise ValidationException("目标范围未完整落在选中 Landsat 条目内")
        return window

    @classmethod
    def _write_output(
        cls,
        reference: rasterio.io.DatasetReader,
        window: Window,
        stack_data: np.ndarray,
        item: PublicLandsatItem,
        output_path: Path,
    ) -> None:
        """写出带完整公开来源标签的四波段 GeoTIFF。

        Args:
            reference: 参考波段数据集。
            window: 裁取像元窗口。
            stack_data: 四波段浮点反射率数组。
            item: Landsat 来源元数据。
            output_path: 输出临时路径。

        Returns:
            None: 写出完成后无返回值。
        """
        width = int(window.width)
        height = int(window.height)
        profile = reference.profile.copy()
        profile.update(
            driver="GTiff",
            count=len(item.bands),
            dtype="float32",
            nodata=np.nan,
            width=width,
            height=height,
            transform=reference.window_transform(window),
            compress="deflate",
            predictor=3,
            tiled=width >= 256 and height >= 256,
            BIGTIFF="IF_SAFER",
        )
        if profile["tiled"]:
            profile.update(blockxsize=256, blockysize=256)
        calibrations = [
            {
                "asset": band.asset_name,
                "scale": band.scale,
                "offset": band.offset,
                "nodata": band.nodata,
            }
            for band in item.bands
        ]
        with rasterio.open(output_path, "w", **profile) as output:
            output.write(stack_data)
            output.descriptions = tuple(band.description for band in item.bands)
            output.update_tags(
                PLATFORM=item.platform,
                INSTRUMENT=item.instrument,
                ACQUISITION_TIME=item.acquired_at.isoformat(),
                PROCESSING_LEVEL=item.processing_level,
                PROCESSING_BASELINE="USGS Landsat Collection 2 Level-2",
                SOURCE_PROCESSING_BASELINE="USGS Landsat Collection 2 Level-2",
                CLOUD_COVER=("" if item.cloud_cover is None else str(item.cloud_cover)),
                STAC_COLLECTION=PublicImageryClient.COLLECTION,
                STAC_ITEM_ID=item.item_id,
                STAC_ITEM_URL=item.item_url,
                SOURCE_PRODUCT_URI=item.product_id,
                SOURCE_PROVIDER=cls.PROVIDER,
                SOURCE_LICENSE=cls.LICENSE_NAME,
                SOURCE_LICENSE_URL=cls.LICENSE_URL,
                SOURCE_CLASSIFICATION="public_open_data",
                SECURITY_CLASSIFICATION="public",
                NON_STATUTORY_NOTICE=cls.NON_STATUTORY_NOTICE,
                WRS_PATH="" if item.wrs_path is None else str(item.wrs_path),
                WRS_ROW="" if item.wrs_row is None else str(item.wrs_row),
                STAC_SCALE_OFFSET_APPLIED="true",
                SOURCE_SCALE_APPLIED="true",
                SURFACE_REFLECTANCE="true",
                BOA_REFLECTANCE="true",
                REFLECTANCE_QUANTITY="SURFACE_REFLECTANCE",
                STAC_CALIBRATION=json.dumps(calibrations, separators=(",", ":")),
                SOURCE_BLUE_URL=item.bands[0].unsigned_href,
                SOURCE_GREEN_URL=item.bands[1].unsigned_href,
                SOURCE_RED_URL=item.bands[2].unsigned_href,
                SOURCE_NIR_URL=item.bands[3].unsigned_href,
            )

    @staticmethod
    def _datetime_property(properties: dict[str, Any], key: str) -> datetime:
        """解析 STAC 带时区时间字段。

        Args:
            properties: STAC 属性。
            key: 时间属性名。

        Returns:
            datetime: 带时区采集时间。
        """
        value = properties.get(key)
        if not isinstance(value, str):
            raise ValidationException("公开 STAC 条目缺少采集时间")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationException("公开 STAC 条目采集时间不合法") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValidationException("公开 STAC 条目采集时间缺少时区")
        return parsed

    @staticmethod
    def _is_number(value: object) -> bool:
        """判断值是否为非布尔数值。

        Args:
            value: 待判断值。

        Returns:
            bool: 数值且非布尔时返回 True。
        """
        return isinstance(value, int | float) and not isinstance(value, bool)

    @classmethod
    def _optional_float(cls, value: object) -> float | None:
        """把可选 STAC 数值转换为浮点数。

        Args:
            value: 原始值。

        Returns:
            float | None: 浮点数或空值。
        """
        if value is None:
            return None
        if cls._is_number(value):
            return float(value)
        try:
            return float(str(value))
        except ValueError as exc:
            raise ValidationException("公开 STAC 数值属性不合法") from exc

    @classmethod
    def _optional_int(cls, value: object) -> int | None:
        """把可选 STAC 整数属性转换为整数。

        Args:
            value: 原始值。

        Returns:
            int | None: 整数或空值。
        """
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValidationException("公开 STAC 整数属性不合法")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationException("公开 STAC 整数属性不合法") from exc
