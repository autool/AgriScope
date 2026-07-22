"""从真实实体栅格生成源影像与已校验波段产品 PNG 快视图。"""

import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds


@dataclass(frozen=True)
class ImageryQuicklookRenderResult:
    """实体栅格快视图和可追溯渲染参数。"""

    png: bytes
    bounds_wgs84: tuple[float, float, float, float]
    width: int
    height: int
    band_indexes: tuple[int, ...]
    band_descriptions: tuple[str, ...]
    stretch_ranges: tuple[tuple[float, float], ...]
    value_range: tuple[float, float] | None


class ImageryQuicklookRenderer:
    """按栅格波段描述生成不参与处理完成度计算的真实快视图。"""

    renderer_version = "rasterio-imagery-quicklook-v1"

    @staticmethod
    def _preview_size(
        source_width: int,
        source_height: int,
        max_dimension: int,
    ) -> tuple[int, int]:
        """保持栅格像素长宽比计算预览尺寸。

        Args:
            source_width: 源栅格宽度。
            source_height: 源栅格高度。
            max_dimension: 预览最长边上限。

        Returns:
            tuple[int, int]: 预览宽高。
        """
        if source_width >= source_height:
            width = min(source_width, max_dimension)
            height = max(1, round(width * source_height / source_width))
        else:
            height = min(source_height, max_dimension)
            width = max(1, round(height * source_width / source_height))
        return width, height

    @staticmethod
    def _description_index(
        dataset: rasterio.io.DatasetReader,
    ) -> dict[str, int]:
        """建立标准化波段描述到一基索引的映射。

        Args:
            dataset: 已打开栅格。

        Returns:
            dict[str, int]: 小写波段描述索引。
        """
        return {
            (description or "").strip().lower(): index
            for index, description in enumerate(dataset.descriptions, start=1)
            if (description or "").strip()
        }

    @classmethod
    def _resolve_bands(
        cls,
        dataset: rasterio.io.DatasetReader,
        product_code: str,
    ) -> tuple[tuple[int, ...], tuple[str, ...]]:
        """按产品类型解析真实输出波段，缺失时明确拒绝。

        Args:
            dataset: 已打开栅格。
            product_code: source、true_color、false_color 或 ndvi。

        Returns:
            tuple[tuple[int, ...], tuple[str, ...]]: 波段索引和描述。
        """
        descriptions = cls._description_index(dataset)
        if product_code == "true_color":
            required = (
                "true_color_red",
                "true_color_green",
                "true_color_blue",
            )
            if not all(item in descriptions for item in required):
                raise ValueError("波段产品缺少真彩色波段描述")
            return tuple(descriptions[item] for item in required), required
        if product_code == "false_color":
            required = (
                "false_color_nir",
                "false_color_red",
                "false_color_green",
            )
            if not all(item in descriptions for item in required):
                raise ValueError("波段产品缺少标准假彩色波段描述")
            return tuple(descriptions[item] for item in required), required
        if product_code == "ndvi":
            if "ndvi" not in descriptions:
                raise ValueError("波段产品缺少 NDVI 波段描述")
            return (descriptions["ndvi"],), ("ndvi",)
        if product_code != "source":
            raise ValueError(f"不支持快视图产品 {product_code}")
        description_values = [
            (description or "").strip().lower()
            for description in dataset.descriptions
        ]

        def find(keywords: tuple[str, ...]) -> int | None:
            for index, description in enumerate(description_values, start=1):
                if any(keyword in description for keyword in keywords):
                    return index
            return None

        red = find(("red", "红"))
        green = find(("green", "绿"))
        blue = find(("blue", "蓝"))
        if red and green and blue and len({red, green, blue}) == 3:
            return (red, green, blue), ("red", "green", "blue")
        if dataset.count >= 3:
            return (1, 2, 3), ("band_1", "band_2", "band_3")
        if dataset.count == 2:
            return (1, 2, 2), ("band_1", "band_2", "band_2")
        if dataset.count == 1:
            return (1, 1, 1), ("band_1", "band_1", "band_1")
        raise ValueError("影像没有可渲染波段")

    @staticmethod
    def _stretch_ranges(array: np.ndarray) -> tuple[tuple[float, float], ...]:
        """计算逐通道 2%–98% 显示拉伸范围。

        Args:
            array: 通道优先 float32 数组。

        Returns:
            tuple[tuple[float, float], ...]: 每个通道的拉伸范围。
        """
        ranges: list[tuple[float, float]] = []
        for channel in array:
            values = channel[np.isfinite(channel)]
            if values.size == 0:
                raise ValueError("快视图波段没有有效像元")
            if values.size > 200_000:
                values = values[:: math.ceil(values.size / 200_000)]
            lower, upper = np.percentile(values, (2, 98))
            if upper <= lower:
                lower = float(np.min(values))
                upper = float(np.max(values))
            if upper <= lower:
                upper = lower + 1
            ranges.append((float(lower), float(upper)))
        return tuple(ranges)

    @staticmethod
    def _rgb_rgba(
        array: np.ndarray,
        ranges: tuple[tuple[float, float], ...],
    ) -> np.ndarray:
        """将三通道数组按拉伸范围转换为 RGBA。

        Args:
            array: 三通道 float32 数组。
            ranges: 三通道拉伸范围。

        Returns:
            np.ndarray: 四通道 uint8 数组。
        """
        rgba = np.zeros((4, array.shape[1], array.shape[2]), dtype="uint8")
        valid_mask = np.all(np.isfinite(array), axis=0)
        for channel, (lower, upper) in enumerate(ranges):
            scaled = np.clip((array[channel] - lower) / (upper - lower), 0, 1)
            rgba[channel] = np.where(
                np.isfinite(scaled),
                np.rint(scaled * 255),
                0,
            ).astype("uint8")
        rgba[3] = np.where(valid_mask, 255, 0).astype("uint8")
        return rgba

    @staticmethod
    def _ndvi_rgba(array: np.ndarray) -> tuple[np.ndarray, tuple[float, float]]:
        """使用红—黄—绿坡度渲染真实 NDVI 数值。

        Args:
            array: 单通道 NDVI float32 数组。

        Returns:
            tuple[np.ndarray, tuple[float, float]]: RGBA 和实际有效值范围。
        """
        band = array[0]
        valid_mask = np.isfinite(band)
        values = band[valid_mask]
        if values.size == 0:
            raise ValueError("NDVI 波段没有有效像元")
        clipped = np.clip(band, -1, 1)
        normalized = (clipped + 1) / 2
        rgba = np.zeros((4, band.shape[0], band.shape[1]), dtype="uint8")
        lower_half = normalized <= 0.5
        rgba[0] = np.where(
            valid_mask,
            np.where(lower_half, 210, np.rint(210 * (1 - normalized) * 2)),
            0,
        ).astype("uint8")
        rgba[1] = np.where(
            valid_mask,
            np.where(
                lower_half,
                np.rint(180 * normalized * 2),
                np.rint(180 + 65 * (normalized - 0.5) * 2),
            ),
            0,
        ).astype("uint8")
        rgba[2] = np.where(valid_mask, 35, 0).astype("uint8")
        rgba[3] = np.where(valid_mask, 255, 0).astype("uint8")
        return rgba, (float(np.min(values)), float(np.max(values)))

    @staticmethod
    def _encode_png(rgba: np.ndarray) -> bytes:
        """编码透明无数据区的 RGBA PNG。

        Args:
            rgba: 四通道 uint8 数组。

        Returns:
            bytes: PNG 字节。
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with MemoryFile() as memory:
                with memory.open(
                    driver="PNG",
                    width=rgba.shape[2],
                    height=rgba.shape[1],
                    count=4,
                    dtype="uint8",
                ) as dataset:
                    dataset.write(rgba)
                return memory.read()

    def render(
        self,
        source_path: Path,
        product_code: str,
        max_dimension: int,
    ) -> ImageryQuicklookRenderResult:
        """从实体源文件或已校验波段产品生成快视图。

        Args:
            source_path: 受控实体栅格路径。
            product_code: source、true_color、false_color 或 ndvi。
            max_dimension: 预览最长边像素上限。

        Returns:
            ImageryQuicklookRenderResult: PNG 和渲染证据。
        """
        if not 256 <= max_dimension <= 4096:
            raise ValueError("影像快视图尺寸必须为 256–4096 像素")
        with rasterio.open(source_path) as source:
            if source.crs is None:
                raise ValueError("影像缺少 CRS，无法生成空间快视图")
            band_indexes, band_descriptions = self._resolve_bands(
                source,
                product_code,
            )
            width, height = self._preview_size(
                source.width,
                source.height,
                max_dimension,
            )
            masked = source.read(
                list(band_indexes),
                out_shape=(len(band_indexes), height, width),
                resampling=Resampling.bilinear,
                masked=True,
            )
            array = masked.astype("float32").filled(np.nan)
            bounds_wgs84 = transform_bounds(
                source.crs,
                "EPSG:4326",
                *source.bounds,
                densify_pts=21,
            )
        if product_code == "ndvi":
            rgba, value_range = self._ndvi_rgba(array)
            stretch_ranges: tuple[tuple[float, float], ...] = ()
        else:
            stretch_ranges = self._stretch_ranges(array)
            rgba = self._rgb_rgba(array, stretch_ranges)
            value_range = None
        return ImageryQuicklookRenderResult(
            png=self._encode_png(rgba),
            bounds_wgs84=tuple(float(value) for value in bounds_wgs84),
            width=width,
            height=height,
            band_indexes=band_indexes,
            band_descriptions=band_descriptions,
            stretch_ranges=stretch_ranges,
            value_range=value_range,
        )
