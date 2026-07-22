"""从 Earth Search 公共 STAC 裁取 Sentinel-2 L2A 四波段实体影像并入库。"""

import argparse
import asyncio
import json
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from app.core.database import AsyncSessionLocal
from app.schemas.imagery import ImageryAssetCreateRequest
from app.services.imagery_asset_service import ImageryAssetService

STAC_SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
STAC_COLLECTION = "sentinel-2-l2a"
BAND_ASSETS = (
    ("blue", "Blue"),
    ("green", "Green"),
    ("red", "Red"),
    ("nir", "NIR"),
)


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    """解析 WGS84 左、下、右、上包围盒。

    Args:
        value: 逗号分隔的四个坐标。

    Returns:
        tuple[float, float, float, float]: 合法 WGS84 包围盒。
    """
    try:
        values = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bbox 必须为四个数值") from exc
    if len(values) != 4:
        raise argparse.ArgumentTypeError("bbox 必须为 left,bottom,right,top")
    left, bottom, right, top = values
    if not (-180 <= left < right <= 180 and -90 <= bottom < top <= 90):
        raise argparse.ArgumentTypeError("bbox 超出 WGS84 合法范围或顺序错误")
    return left, bottom, right, top


def select_item(features: list[dict[str, Any]]) -> dict[str, Any]:
    """从 STAC 候选中选择具备四个目标波段的最新低云量条目。

    Args:
        features: STAC Feature 列表。

    Returns:
        dict[str, Any]: 选中的 STAC Feature。
    """
    candidates = [
        feature
        for feature in features
        if all(
            feature.get("assets", {}).get(asset_name, {}).get("href")
            for asset_name, _ in BAND_ASSETS
        )
    ]
    if not candidates:
        raise RuntimeError("公共 STAC 未找到满足日期、云量和波段要求的影像")

    def cloud_cover(feature: dict[str, Any]) -> float:
        value = feature.get("properties", {}).get("eo:cloud_cover")
        return 100.0 if value is None else float(value)

    candidates.sort(
        key=lambda feature: (
            feature.get("properties", {}).get("datetime") or "",
            -cloud_cover(feature),
        ),
        reverse=True,
    )
    return candidates[0]


def search_item(
    bbox: tuple[float, float, float, float],
    datetime_range: str,
    max_cloud_cover: float,
) -> dict[str, Any]:
    """查询覆盖目标范围且具备四个 10 米波段的最新低云量条目。

    Args:
        bbox: WGS84 裁取范围。
        datetime_range: STAC 时间范围。
        max_cloud_cover: 最大云量百分比。

    Returns:
        dict[str, Any]: 选中的 STAC Feature。
    """
    payload = json.dumps(
        {
            "collections": [STAC_COLLECTION],
            "bbox": bbox,
            "datetime": datetime_range,
            "limit": 100,
            "query": {"eo:cloud_cover": {"lt": max_cloud_cover}},
        }
    ).encode()
    request = Request(
        STAC_SEARCH_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "AgriScope-public-imagery-import/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        body = json.load(response)
    return select_item(body.get("features", []))


def _display_platform(properties: dict[str, Any]) -> str:
    """把 STAC 平台编码转换为可读且不丢失真实型号的名称。

    Args:
        properties: STAC Feature 属性。

    Returns:
        str: 例如 Sentinel-2A、Sentinel-2B 或 Sentinel-2C。
    """
    raw_platform = str(properties.get("platform") or "sentinel-2").strip()
    parts = raw_platform.lower().split("-")
    if len(parts) == 2 and parts[0] == "sentinel" and parts[1].startswith("2"):
        return f"Sentinel-{parts[1].upper()}"
    return raw_platform


def _display_instrument(properties: dict[str, Any]) -> str:
    """读取 STAC 载荷名称。

    Args:
        properties: STAC Feature 属性。

    Returns:
        str: 首个载荷名称；缺失时按 Sentinel-2 L2A 约定返回 MSI。
    """
    instruments = properties.get("instruments")
    if isinstance(instruments, list) and instruments:
        return str(instruments[0]).upper()
    return "MSI"


def _band_calibration(
    asset_name: str,
    asset: dict[str, Any],
) -> tuple[float, float, float | None]:
    """读取 STAC Raster Extension 中的波段比例、偏移和无效值。

    Args:
        asset_name: Earth Search 波段资产名称。
        asset: STAC Asset 对象。

    Returns:
        tuple[float, float, float | None]: 比例、偏移和无效值。
    """
    raster_bands = asset.get("raster:bands")
    if not isinstance(raster_bands, list) or not raster_bands:
        raise RuntimeError(f"Sentinel 波段 {asset_name} 缺少 raster:bands 标度")
    metadata = raster_bands[0]
    if not isinstance(metadata, dict):
        raise RuntimeError(f"Sentinel 波段 {asset_name} 的标度结构不合法")
    scale = metadata.get("scale")
    offset = metadata.get("offset")
    if isinstance(scale, bool) or not isinstance(scale, int | float):
        raise RuntimeError(f"Sentinel 波段 {asset_name} 缺少数值 scale")
    if isinstance(offset, bool) or not isinstance(offset, int | float):
        raise RuntimeError(f"Sentinel 波段 {asset_name} 缺少数值 offset")
    nodata = metadata.get("nodata")
    if nodata is not None and (
        isinstance(nodata, bool) or not isinstance(nodata, int | float)
    ):
        raise RuntimeError(f"Sentinel 波段 {asset_name} 的 nodata 不合法")
    return float(scale), float(offset), None if nodata is None else float(nodata)


def _window_for_bbox(
    dataset: rasterio.io.DatasetReader,
    bbox_wgs84: tuple[float, float, float, float],
) -> Window:
    """把 WGS84 包围盒转换为完全位于 COG 内部的像元窗口。

    Args:
        dataset: Sentinel COG 数据集。
        bbox_wgs84: WGS84 裁取范围。

    Returns:
        Window: 取整后的有效像元窗口。
    """
    if dataset.crs is None:
        raise RuntimeError("公共 Sentinel COG 缺少 CRS")
    projected_bbox = transform_bounds(
        "EPSG:4326",
        dataset.crs,
        *bbox_wgs84,
        densify_pts=21,
    )
    window = from_bounds(*projected_bbox, transform=dataset.transform)
    window = window.round_offsets().round_lengths()
    full_window = Window(0, 0, dataset.width, dataset.height)
    clipped = window.intersection(full_window)
    if clipped != window or window.width <= 0 or window.height <= 0:
        raise RuntimeError("目标范围未完整落在选中 Sentinel 条目内")
    return window


def build_multiband_geotiff(
    item: dict[str, Any],
    bbox_wgs84: tuple[float, float, float, float],
    output_path: Path,
) -> None:
    """从四个公共 COG 读取同一窗口并生成四波段 GeoTIFF。

    Args:
        item: 选中的 STAC Feature。
        bbox_wgs84: WGS84 裁取范围。
        output_path: 临时输出文件。

    Returns:
        None: 生成完成后返回。
    """
    assets = item["assets"]
    calibrations = [
        _band_calibration(asset_name, assets[asset_name])
        for asset_name, _ in BAND_ASSETS
    ]
    rasterio_options = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "GDAL_HTTP_MULTIRANGE": "YES",
    }
    with rasterio.Env(**rasterio_options), ExitStack() as stack:
        datasets = [
            stack.enter_context(rasterio.open(assets[asset_name]["href"]))
            for asset_name, _ in BAND_ASSETS
        ]
        reference = datasets[0]
        window = _window_for_bbox(reference, bbox_wgs84)
        transform = reference.window_transform(window)
        width = int(window.width)
        height = int(window.height)
        arrays: list[np.ndarray] = []
        for dataset, (scale, offset, nodata) in zip(
            datasets,
            calibrations,
            strict=True,
        ):
            if (
                dataset.crs != reference.crs
                or dataset.transform != reference.transform
                or dataset.width != reference.width
                or dataset.height != reference.height
            ):
                raise RuntimeError("Sentinel 四个波段不在同一像元网格")
            raw_data = dataset.read(1, window=window)
            reflectance = raw_data.astype("float32") * scale + offset
            if nodata is not None:
                reflectance[raw_data == nodata] = np.nan
            arrays.append(reflectance)
        stack_data = np.stack(arrays)
        profile = reference.profile.copy()
        profile.update(
            driver="GTiff",
            count=4,
            dtype="float32",
            nodata=np.nan,
            width=width,
            height=height,
            transform=transform,
            compress="deflate",
            predictor=3,
            tiled=width >= 256 and height >= 256,
            BIGTIFF="IF_SAFER",
        )
        if profile["tiled"]:
            profile.update(blockxsize=256, blockysize=256)
        properties = item.get("properties", {})
        item_id = item["id"]
        platform = _display_platform(properties)
        instrument = _display_instrument(properties)
        item_url = (
            "https://earth-search.aws.element84.com/v1/collections/"
            f"{STAC_COLLECTION}/items/{item_id}"
        )
        with rasterio.open(output_path, "w", **profile) as output:
            output.write(stack_data)
            output.descriptions = tuple(
                description for _, description in BAND_ASSETS
            )
            output.update_tags(
                PLATFORM=platform,
                INSTRUMENT=instrument,
                ACQUISITION_TIME=str(properties.get("datetime") or ""),
                PROCESSING_LEVEL="L2A",
                CLOUD_COVER=str(properties.get("eo:cloud_cover") or ""),
                STAC_COLLECTION=STAC_COLLECTION,
                STAC_ITEM_ID=item_id,
                STAC_ITEM_URL=item_url,
                SOURCE_PROVIDER="AWS Open Data / Element 84 Earth Search",
                SOURCE_LICENSE=(
                    "Copernicus Sentinel Data Legal Notice"
                ),
                SOURCE_LICENSE_URL=(
                    "https://sentinels.copernicus.eu/documents/247904/690755/"
                    "Sentinel_Data_Legal_Notice"
                ),
                SOURCE_B02_URL=assets["blue"]["href"],
                SOURCE_B03_URL=assets["green"]["href"],
                SOURCE_B04_URL=assets["red"]["href"],
                SOURCE_B08_URL=assets["nir"]["href"],
                SOURCE_PRODUCT_URI=str(
                    properties.get("s2:product_uri") or item_id
                ),
                SOURCE_PROCESSING_BASELINE=str(
                    properties.get("s2:processing_baseline") or ""
                ),
                SOURCE_RASTER_BANDS_JSON=json.dumps(
                    [
                        {
                            "asset": asset_name,
                            "description": description,
                            "scale": scale,
                            "offset": offset,
                            "nodata": nodata,
                        }
                        for (
                            (asset_name, description),
                            (scale, offset, nodata),
                        ) in zip(BAND_ASSETS, calibrations, strict=True)
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                SOURCE_SCALE_APPLIED="true",
                REFLECTANCE_QUANTITY="BOA_REFLECTANCE",
                SECURITY_CLASSIFICATION="public",
                SUBSET_BBOX_WGS84=",".join(str(value) for value in bbox_wgs84),
            )


async def import_asset(args: argparse.Namespace) -> dict:
    """构建公共实体影像并通过现有入库服务持久化。

    Args:
        args: 命令行参数。

    Returns:
        dict: 入库影像摘要。
    """
    item = await asyncio.to_thread(
        search_item,
        args.bbox,
        args.datetime_range,
        args.max_cloud_cover,
    )
    with tempfile.TemporaryDirectory(prefix="agriscope-sentinel-") as directory:
        output_path = Path(directory) / f"{item['id']}_subset.tif"
        await asyncio.to_thread(
            build_multiband_geotiff,
            item,
            args.bbox,
            output_path,
        )
        request = ImageryAssetCreateRequest(
            asset_code=args.asset_code,
            asset_name=args.asset_name,
            sensor_type=None,
            acquired_at=None,
            cloud_cover=None,
            processing_level=None,
            data_status=args.data_status,
            operator_code=args.operator_code,
        )
        async with AsyncSessionLocal() as db:
            with output_path.open("rb") as file_object:
                response = await ImageryAssetService().upload_asset(
                    db,
                    args.project_code,
                    args.task_code,
                    request,
                    output_path.name,
                    file_object,
                )
    return {
        "asset_code": response.asset_code,
        "asset_name": response.asset_name,
        "data_status": response.data_status,
        "sensor_type": response.sensor_type,
        "acquired_at": response.acquired_at.isoformat(),
        "cloud_cover": response.cloud_cover,
        "processing_level": response.processing_level,
        "file_size_bytes": response.file_size_bytes,
        "checksum_sha256": response.checksum_sha256,
        "band_count": response.band_count,
        "raster_width": response.raster_width,
        "raster_height": response.raster_height,
        "crs": response.crs,
        "stac_item_id": item["id"],
        "stac_datetime": item.get("properties", {}).get("datetime"),
        "stac_cloud_cover": item.get("properties", {}).get("eo:cloud_cover"),
    }


def build_parser() -> argparse.ArgumentParser:
    """创建公共 Sentinel 导入命令参数。

    Returns:
        argparse.ArgumentParser: 参数解析器。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-code", required=True)
    parser.add_argument("--asset-name", required=True)
    parser.add_argument("--bbox", type=parse_bbox, required=True)
    parser.add_argument("--datetime-range", required=True)
    parser.add_argument("--max-cloud-cover", type=float, default=10)
    parser.add_argument("--operator-code", required=True)
    parser.add_argument("--project-code", default="RS-2026")
    parser.add_argument("--task-code", default="RS-2026-045")
    parser.add_argument(
        "--data-status",
        choices=("operational", "demo"),
        default="operational",
    )
    return parser


def main() -> None:
    """执行公共 Sentinel 实体影像入库。"""
    args = build_parser().parse_args()
    if not 0 <= args.max_cloud_cover <= 100:
        raise SystemExit("max-cloud-cover 必须位于 0–100")
    result = asyncio.run(import_asset(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
