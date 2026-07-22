"""从 Google Cloud 公开 Landsat 8 数据构建同景多光谱/全色实体并入库。"""

import argparse
import asyncio
import json
import math
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from app.core.database import AsyncSessionLocal
from app.core.exceptions import ValidationException
from app.core.imagery_files import calculate_sha256
from app.schemas.imagery import ImageryAssetCreateRequest, ImageryAssetResponse
from app.services.imagery_asset_service import ImageryAssetService

PUBLIC_BUCKET_ROOT = (
    "https://storage.googleapis.com/gcp-public-data-landsat"
)
SCENE_PATTERN = re.compile(
    r"^(?P<platform>LC08)_(?P<level>L1(?:GT|GS|TP))_"
    r"(?P<path>\d{3})(?P<row>\d{3})_"
    r"(?P<acquired>\d{8})_(?P<processed>\d{8})_"
    r"(?P<collection>01)_(?P<tier>T1|T2|RT)$"
)
MULTISPECTRAL_BANDS = (
    (2, "Blue"),
    (3, "Green"),
    (4, "Red"),
)
PANCHROMATIC_BAND = 8


@dataclass(frozen=True)
class LandsatScene:
    """可从公开 Collection 1 路径安全解析的 Landsat 8 场景。"""

    scene_id: str
    platform: str
    processing_level: str
    path: str
    row: str
    acquisition_date: str
    processing_date: str
    collection: str
    tier: str

    @property
    def source_root(self) -> str:
        """返回固定公开桶内的场景目录。

        Returns:
            str: 不包含用户可控主机的公开场景目录。
        """
        return (
            f"{PUBLIC_BUCKET_ROOT}/{self.platform}/{self.collection}/"
            f"{self.path}/{self.row}/{self.scene_id}"
        )

    def band_url(self, band: int) -> str:
        """返回一个场景波段的公开 GeoTIFF 地址。

        Args:
            band: Landsat 波段编号。

        Returns:
            str: 固定公开桶中的实体地址。
        """
        if band not in {2, 3, 4, 8}:
            raise ValueError("公开全色融合导入仅支持 B2/B3/B4/B8")
        return f"{self.source_root}/{self.scene_id}_B{band}.TIF"

    @property
    def mtl_url(self) -> str:
        """返回场景 MTL 文本地址。

        Returns:
            str: 固定公开桶中的 MTL 地址。
        """
        return f"{self.source_root}/{self.scene_id}_MTL.txt"


@dataclass(frozen=True)
class LandsatCalibration:
    """从物理 MTL 文件读取的 TOA 反射率标定证据。"""

    product_id: str
    spacecraft_id: str
    sensor_id: str
    acquisition_time: str
    cloud_cover: float
    sun_elevation: float
    coefficients: dict[int, tuple[float, float]]


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


def parse_scene_id(scene_id: str) -> LandsatScene:
    """解析受控的 Landsat 8 Collection 1 场景编号。

    Args:
        scene_id: USGS Landsat 产品编号。

    Returns:
        LandsatScene: 可安全构造公开数据 URL 的场景信息。
    """
    match = SCENE_PATTERN.fullmatch(scene_id.strip())
    if match is None:
        raise argparse.ArgumentTypeError(
            "scene-id 必须是 Landsat 8 Collection 1 L1 产品编号"
        )
    values = match.groupdict()
    try:
        datetime.strptime(values["acquired"], "%Y%m%d")
        datetime.strptime(values["processed"], "%Y%m%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("scene-id 包含无效日期") from exc
    return LandsatScene(
        scene_id=scene_id.strip(),
        platform=values["platform"],
        processing_level=values["level"],
        path=values["path"],
        row=values["row"],
        acquisition_date=values["acquired"],
        processing_date=values["processed"],
        collection=values["collection"],
        tier=values["tier"],
    )


def _mtl_value(content: str, name: str) -> str:
    """从 MTL 文本中读取一个必填值。

    Args:
        content: 完整 MTL 文本。
        name: 字段名称。

    Returns:
        str: 去除引号和空白的字段值。
    """
    match = re.search(
        rf'^\s*{re.escape(name)}\s*=\s*"?([^"\n]+?)"?\s*$',
        content,
        re.MULTILINE,
    )
    if match is None:
        raise RuntimeError(f"Landsat MTL 缺少 {name}")
    return match.group(1).strip()


def parse_mtl(content: str, expected_scene_id: str) -> LandsatCalibration:
    """解析并核对 Landsat TOA 反射率系数与场景身份。

    Args:
        content: 公开 MTL 文本。
        expected_scene_id: URL 所属的预期产品编号。

    Returns:
        LandsatCalibration: 经过范围和身份校验的标定参数。
    """
    product_id = _mtl_value(content, "LANDSAT_PRODUCT_ID")
    if product_id != expected_scene_id:
        raise RuntimeError("Landsat MTL 产品编号与请求场景不一致")
    spacecraft_id = _mtl_value(content, "SPACECRAFT_ID")
    sensor_id = _mtl_value(content, "SENSOR_ID")
    if spacecraft_id.upper().replace("_", "-") != "LANDSAT-8":
        raise RuntimeError("当前公开全色融合导入仅支持 Landsat 8")
    if "OLI" not in sensor_id.upper():
        raise RuntimeError("Landsat 场景不包含 OLI 载荷")
    sun_elevation = float(_mtl_value(content, "SUN_ELEVATION"))
    cloud_cover = float(_mtl_value(content, "CLOUD_COVER"))
    if not 0 < sun_elevation <= 90:
        raise RuntimeError("Landsat 太阳高度角超出合法范围")
    if not 0 <= cloud_cover <= 100:
        raise RuntimeError("Landsat 云量超出 0–100")
    acquisition_date = _mtl_value(content, "DATE_ACQUIRED")
    scene_center_time = _mtl_value(content, "SCENE_CENTER_TIME")
    if not scene_center_time.endswith("Z"):
        raise RuntimeError("Landsat 场景中心时间缺少 UTC 标识")
    acquisition_time = f"{acquisition_date}T{scene_center_time}"
    try:
        datetime.fromisoformat(acquisition_time.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("Landsat 采集日期时间格式不合法") from exc
    coefficients = {
        band: (
            float(_mtl_value(content, f"REFLECTANCE_MULT_BAND_{band}")),
            float(_mtl_value(content, f"REFLECTANCE_ADD_BAND_{band}")),
        )
        for band in (2, 3, 4, 8)
    }
    return LandsatCalibration(
        product_id=product_id,
        spacecraft_id=spacecraft_id,
        sensor_id=sensor_id,
        acquisition_time=acquisition_time,
        cloud_cover=cloud_cover,
        sun_elevation=sun_elevation,
        coefficients=coefficients,
    )


def fetch_mtl(scene: LandsatScene) -> str:
    """从固定公开主机下载场景 MTL 文本。

    Args:
        scene: 已校验场景。

    Returns:
        str: ASCII MTL 文本。
    """
    request = Request(
        scene.mtl_url,
        headers={"User-Agent": "AgriScope-public-landsat-import/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("ascii")


def _window_for_bbox(
    dataset: rasterio.io.DatasetReader,
    bbox_wgs84: tuple[float, float, float, float],
) -> Window:
    """把 WGS84 范围转换为完全位于源影像内的像元窗口。

    Args:
        dataset: 单波段 Landsat 数据集。
        bbox_wgs84: WGS84 裁取范围。

    Returns:
        Window: 取整后的有效窗口。
    """
    if dataset.crs is None:
        raise RuntimeError("公开 Landsat 波段缺少 CRS")
    projected = transform_bounds(
        "EPSG:4326",
        dataset.crs,
        *bbox_wgs84,
        densify_pts=21,
    )
    window = from_bounds(*projected, transform=dataset.transform)
    window = window.round_offsets().round_lengths()
    full_window = Window(0, 0, dataset.width, dataset.height)
    clipped = window.intersection(full_window)
    if clipped != window or window.width <= 0 or window.height <= 0:
        raise RuntimeError("目标范围未完整落在 Landsat 场景内")
    return window


def _toa_reflectance(
    raw: np.ndarray,
    coefficient: tuple[float, float],
    sun_elevation: float,
) -> np.ndarray:
    """按 USGS MTL 系数把量化 DN 转换为 TOA 反射率。

    Args:
        raw: 原始 DN 数组。
        coefficient: 乘法和加法系数。
        sun_elevation: 太阳高度角（度）。

    Returns:
        np.ndarray: 以 NaN 表示无数据的 float32 TOA 反射率。
    """
    multiplier, additive = coefficient
    result = (
        raw.astype("float32") * multiplier + additive
    ) / math.sin(math.radians(sun_elevation))
    result[raw == 0] = np.nan
    return result


@contextmanager
def _atomic_raster_path(output_path: Path) -> Iterator[Path]:
    """提供同目录临时路径并在成功后原子发布。

    Args:
        output_path: 最终输出路径。

    Yields:
        Path: 仅供本次写入的临时路径。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(
        f".{output_path.stem}-{uuid4().hex}.tmp.tif"
    )
    try:
        yield temporary
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)


def _output_profile(
    source: rasterio.io.DatasetReader,
    window: Window,
    count: int,
) -> dict:
    """构造浮点反射率子集的 GeoTIFF 配置。

    Args:
        source: 参考源数据集。
        window: 裁取窗口。
        count: 输出波段数。

    Returns:
        dict: Rasterio 输出配置。
    """
    width = int(window.width)
    height = int(window.height)
    profile = source.profile.copy()
    profile.update(
        driver="GTiff",
        count=count,
        dtype="float32",
        nodata=np.nan,
        width=width,
        height=height,
        transform=source.window_transform(window),
        compress="deflate",
        predictor=3,
        tiled=width >= 256 and height >= 256,
        BIGTIFF="IF_SAFER",
    )
    if profile["tiled"]:
        profile.update(blockxsize=256, blockysize=256)
    return profile


def _lineage_tags(
    scene: LandsatScene,
    calibration: LandsatCalibration,
    bbox_wgs84: tuple[float, float, float, float],
    role: str,
) -> dict[str, str]:
    """生成两个输出共同使用的公开来源和标定标签。

    Args:
        scene: 公开场景身份。
        calibration: MTL 标定参数。
        bbox_wgs84: 裁取范围。
        role: multispectral 或 panchromatic。

    Returns:
        dict[str, str]: 可由入库服务持久化的栅格标签。
    """
    coefficient_manifest = [
        {
            "band": band,
            "multiplier": calibration.coefficients[band][0],
            "additive": calibration.coefficients[band][1],
        }
        for band in (2, 3, 4, 8)
    ]
    return {
        "PLATFORM": calibration.spacecraft_id.replace("_", "-"),
        "INSTRUMENT": calibration.sensor_id,
        "ACQUISITION_TIME": calibration.acquisition_time,
        "PROCESSING_LEVEL": f"{scene.processing_level}_TOA_REFLECTANCE",
        "CLOUD_COVER": str(calibration.cloud_cover),
        "SOURCE_PROVIDER": "USGS Landsat / Google Cloud Public Datasets",
        "SOURCE_LICENSE": "USGS Landsat public domain data",
        "SOURCE_LICENSE_URL": (
            "https://www.usgs.gov/landsat-missions/landsat-data-access"
        ),
        "SOURCE_COLLECTION": "Landsat Collection 1 Level-1",
        "SOURCE_PRODUCT_URI": scene.scene_id,
        "LANDSAT_PRODUCT_ID": scene.scene_id,
        "SOURCE_MTL_URL": scene.mtl_url,
        "SOURCE_B02_URL": scene.band_url(2),
        "SOURCE_B03_URL": scene.band_url(3),
        "SOURCE_B04_URL": scene.band_url(4),
        "SOURCE_B08_URL": scene.band_url(8),
        "SOURCE_CALIBRATION_JSON": json.dumps(
            coefficient_manifest,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "SOURCE_SCALE_APPLIED": "true",
        "RADIOMETRIC_CALIBRATION_APPLIED": "true",
        "REFLECTANCE_QUANTITY": "TOA_REFLECTANCE",
        "SUN_ELEVATION": str(calibration.sun_elevation),
        "SECURITY_CLASSIFICATION": "public",
        "SUBSET_BBOX_WGS84": ",".join(str(value) for value in bbox_wgs84),
        "PANSHARPENING_SOURCE_ROLE": role,
    }


def build_pansharpening_sources(
    scene: LandsatScene,
    calibration: LandsatCalibration,
    bbox_wgs84: tuple[float, float, float, float],
    multispectral_output: Path,
    panchromatic_output: Path,
    *,
    band_sources: dict[int, str] | None = None,
) -> None:
    """构建同景三波段多光谱和单波段全色 TOA 反射率实体。

    Args:
        scene: 公开 Landsat 场景。
        calibration: 场景 MTL 标定证据。
        bbox_wgs84: 两类输出共同的 WGS84 裁取范围。
        multispectral_output: 30 米三波段输出路径。
        panchromatic_output: 15 米单波段输出路径。
        band_sources: 测试或受控镜像使用的波段地址覆盖。

    Returns:
        None: 两个输出均原子发布后返回。
    """
    sources = band_sources or {
        band: scene.band_url(band) for band in (2, 3, 4, 8)
    }
    if set(sources) != {2, 3, 4, 8}:
        raise RuntimeError("Landsat 导入必须提供 B2/B3/B4/B8 四个实体")
    rasterio_options = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".TIF,.tif",
        "GDAL_HTTP_MULTIRANGE": "YES",
    }
    with rasterio.Env(**rasterio_options), ExitStack() as stack:
        datasets = {
            band: stack.enter_context(rasterio.open(source))
            for band, source in sources.items()
        }
        reference = datasets[2]
        if reference.count != 1 or reference.crs is None:
            raise RuntimeError("Landsat B2 必须是带 CRS 的单波段实体")
        for band in (3, 4):
            dataset = datasets[band]
            if dataset.count != 1:
                raise RuntimeError(f"Landsat B{band} 不是单波段实体")
            if (
                dataset.crs != reference.crs
                or dataset.transform != reference.transform
                or dataset.width != reference.width
                or dataset.height != reference.height
            ):
                raise RuntimeError("Landsat B2/B3/B4 不在同一像元网格")
        pan = datasets[8]
        if pan.count != 1 or pan.crs != reference.crs:
            raise RuntimeError("Landsat B8 必须是与多光谱同 CRS 的单波段实体")
        multispectral_resolution = max(abs(reference.res[0]), abs(reference.res[1]))
        panchromatic_resolution = max(abs(pan.res[0]), abs(pan.res[1]))
        if multispectral_resolution / panchromatic_resolution < 1.5:
            raise RuntimeError("Landsat B8 分辨率必须至少优于多光谱 1.5 倍")
        multispectral_window = _window_for_bbox(reference, bbox_wgs84)
        panchromatic_window = _window_for_bbox(pan, bbox_wgs84)
        multispectral_data = np.stack([
            _toa_reflectance(
                datasets[band].read(1, window=multispectral_window),
                calibration.coefficients[band],
                calibration.sun_elevation,
            )
            for band, _ in MULTISPECTRAL_BANDS
        ])
        pan_data = _toa_reflectance(
            pan.read(1, window=panchromatic_window),
            calibration.coefficients[8],
            calibration.sun_elevation,
        )
        with _atomic_raster_path(multispectral_output) as temporary:
            with rasterio.open(
                temporary,
                "w",
                **_output_profile(reference, multispectral_window, 3),
            ) as output:
                output.write(multispectral_data)
                output.descriptions = tuple(
                    description for _, description in MULTISPECTRAL_BANDS
                )
                output.update_tags(**_lineage_tags(
                    scene,
                    calibration,
                    bbox_wgs84,
                    "multispectral",
                ))
        try:
            with _atomic_raster_path(panchromatic_output) as temporary:
                with rasterio.open(
                    temporary,
                    "w",
                    **_output_profile(pan, panchromatic_window, 1),
                ) as output:
                    output.write(pan_data, 1)
                    output.descriptions = ("Panchromatic",)
                    output.update_tags(**_lineage_tags(
                        scene,
                        calibration,
                        bbox_wgs84,
                        "panchromatic",
                    ))
        except BaseException:
            multispectral_output.unlink(missing_ok=True)
            raise


async def _upload_asset(
    service: ImageryAssetService,
    project_code: str,
    task_code: str,
    operator_code: str,
    asset_code: str,
    asset_name: str,
    data_status: str,
    path: Path,
) -> ImageryAssetResponse:
    """通过现有业务服务上传一个生成后的实体。

    Args:
        service: 影像资产业务服务。
        project_code: 项目编号。
        task_code: 任务编号。
        operator_code: 稳定操作人编码。
        asset_code: 资产编号。
        asset_name: 资产名称。
        data_status: operational 或 demo。
        path: 生成后的 GeoTIFF。

    Returns:
        ImageryAssetResponse: 已入库资产。
    """
    request = ImageryAssetCreateRequest(
        asset_code=asset_code,
        asset_name=asset_name,
        sensor_type=None,
        acquired_at=None,
        cloud_cover=None,
        processing_level=None,
        data_status=data_status,
        operator_code=operator_code,
    )
    async with AsyncSessionLocal() as db:
        with path.open("rb") as file_object:
            return await service.upload_asset(
                db,
                project_code,
                task_code,
                request,
                path.name,
                file_object,
            )


async def import_pair(args: argparse.Namespace) -> dict:
    """下载、标定、构建并入库一对可用于全色融合的公开实体。

    Args:
        args: 已校验命令行参数。

    Returns:
        dict: 两个资产及来源场景摘要。
    """
    scene: LandsatScene = args.scene_id
    mtl_content = await asyncio.to_thread(fetch_mtl, scene)
    calibration = parse_mtl(mtl_content, scene.scene_id)
    service = ImageryAssetService()
    async with AsyncSessionLocal() as db:
        project = await service.workbench_dao.get_project_by_code(
            db,
            args.project_code,
        )
        if project is None:
            raise ValidationException(f"未找到项目 {args.project_code}")
        for code in (
            args.multispectral_asset_code,
            args.panchromatic_asset_code,
        ):
            if await service.dao.get_asset_by_code(db, code) is not None:
                raise ValidationException(f"影像资产编号 {code} 已存在")
    with tempfile.TemporaryDirectory(prefix="agriscope-landsat-pan-") as directory:
        root = Path(directory)
        multispectral_path = root / f"{scene.scene_id}_RGB_TOA_subset.tif"
        panchromatic_path = root / f"{scene.scene_id}_B8_TOA_subset.tif"
        await asyncio.to_thread(
            build_pansharpening_sources,
            scene,
            calibration,
            args.bbox,
            multispectral_path,
            panchromatic_path,
        )
        output_checksums = {
            args.multispectral_asset_code: calculate_sha256(multispectral_path),
            args.panchromatic_asset_code: calculate_sha256(panchromatic_path),
        }
        async with AsyncSessionLocal() as db:
            for code, checksum in output_checksums.items():
                duplicate = await service.dao.get_asset_by_checksum(db, checksum)
                if duplicate is not None:
                    raise ValidationException(
                        f"资产 {code} 的实体已入库为 {duplicate.asset_code}"
                    )
        multispectral = await _upload_asset(
            service,
            args.project_code,
            args.task_code,
            args.operator_code,
            args.multispectral_asset_code,
            args.multispectral_asset_name,
            args.data_status,
            multispectral_path,
        )
        panchromatic = await _upload_asset(
            service,
            args.project_code,
            args.task_code,
            args.operator_code,
            args.panchromatic_asset_code,
            args.panchromatic_asset_name,
            args.data_status,
            panchromatic_path,
        )
    return {
        "scene_id": scene.scene_id,
        "source_mtl_url": scene.mtl_url,
        "cloud_cover": calibration.cloud_cover,
        "acquisition_time": calibration.acquisition_time,
        "multispectral": _response_summary(multispectral),
        "panchromatic": _response_summary(panchromatic),
    }


def _response_summary(response: ImageryAssetResponse) -> dict:
    """压缩影像资产响应为命令行摘要。

    Args:
        response: 完整资产响应。

    Returns:
        dict: 关键实体和栅格证据。
    """
    return {
        "asset_code": response.asset_code,
        "asset_name": response.asset_name,
        "data_status": response.data_status,
        "resolution_m": response.resolution_m,
        "band_count": response.band_count,
        "raster_width": response.raster_width,
        "raster_height": response.raster_height,
        "file_size_bytes": response.file_size_bytes,
        "checksum_sha256": response.checksum_sha256,
    }


def build_parser() -> argparse.ArgumentParser:
    """创建公开 Landsat 全色融合来源导入参数。

    Returns:
        argparse.ArgumentParser: 参数解析器。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-id", type=parse_scene_id, required=True)
    parser.add_argument("--bbox", type=parse_bbox, required=True)
    parser.add_argument("--multispectral-asset-code", required=True)
    parser.add_argument("--panchromatic-asset-code", required=True)
    parser.add_argument("--multispectral-asset-name", required=True)
    parser.add_argument("--panchromatic-asset-name", required=True)
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
    """执行公开 Landsat 同景多光谱/全色实体入库。"""
    args = build_parser().parse_args()
    if args.multispectral_asset_code == args.panchromatic_asset_code:
        raise SystemExit("多光谱和全色资产编号必须不同")
    result = asyncio.run(import_pair(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
