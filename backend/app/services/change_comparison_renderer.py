"""将两期真实栅格重投影到同一网格并生成一致拉伸的 PNG 预览。"""

import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds


@dataclass(frozen=True)
class ChangeComparisonRenderResult:
    """两期栅格公共交集预览和可追溯渲染参数。"""

    baseline_png: bytes
    target_png: bytes
    bounds_wgs84: tuple[float, float, float, float]
    width: int
    height: int
    baseline_band_indexes: tuple[int, int, int]
    target_band_indexes: tuple[int, int, int]
    stretch_ranges: tuple[tuple[float, float], ...]


class ChangeComparisonRenderer:
    """使用 Rasterio 执行公共网格重投影和双时相一致拉伸。"""

    renderer_version = "rasterio-common-grid-v1"

    @staticmethod
    def _rgb_band_indexes(
        dataset: rasterio.io.DatasetReader,
    ) -> tuple[int, int, int]:
        """优先按波段描述识别 RGB，否则使用前三个可用波段。

        Args:
            dataset: 已打开的栅格数据集。

        Returns:
            tuple[int, int, int]: Rasterio 一基波段索引。
        """
        descriptions = [
            (description or "").strip().lower()
            for description in dataset.descriptions
        ]

        def find_band(keywords: tuple[str, ...]) -> int | None:
            for index, description in enumerate(descriptions, start=1):
                if any(keyword in description for keyword in keywords):
                    return index
            return None

        red = find_band(("red", "红"))
        green = find_band(("green", "绿"))
        blue = find_band(("blue", "蓝"))
        if red and green and blue and len({red, green, blue}) == 3:
            return red, green, blue
        if dataset.count >= 3:
            return 1, 2, 3
        if dataset.count == 2:
            return 1, 2, 2
        if dataset.count == 1:
            return 1, 1, 1
        raise ValueError("影像没有可渲染波段")

    @staticmethod
    def _intersection_bounds(
        baseline: rasterio.io.DatasetReader,
        target: rasterio.io.DatasetReader,
    ) -> tuple[float, float, float, float]:
        """计算两期栅格在 WGS84 下的公共覆盖范围。

        Args:
            baseline: 前时相栅格。
            target: 后时相栅格。

        Returns:
            tuple[float, float, float, float]: 公共 WGS84 包围盒。
        """
        if baseline.crs is None or target.crs is None:
            raise ValueError("前后时相影像必须具有 CRS")
        baseline_bounds = transform_bounds(
            baseline.crs,
            "EPSG:4326",
            *baseline.bounds,
            densify_pts=21,
        )
        target_bounds = transform_bounds(
            target.crs,
            "EPSG:4326",
            *target.bounds,
            densify_pts=21,
        )
        bounds = (
            max(baseline_bounds[0], target_bounds[0]),
            max(baseline_bounds[1], target_bounds[1]),
            min(baseline_bounds[2], target_bounds[2]),
            min(baseline_bounds[3], target_bounds[3]),
        )
        if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
            raise ValueError("前后时相影像没有公共覆盖范围")
        return bounds

    @staticmethod
    def _preview_size(
        bounds: tuple[float, float, float, float],
        max_dimension: int,
    ) -> tuple[int, int]:
        """按近似地表长宽比计算预览尺寸。

        Args:
            bounds: WGS84 公共范围。
            max_dimension: 最长边像素上限。

        Returns:
            tuple[int, int]: 预览宽高。
        """
        left, bottom, right, top = bounds
        center_latitude = math.radians((bottom + top) / 2)
        width_metres = max((right - left) * 111_320 * math.cos(center_latitude), 1)
        height_metres = max((top - bottom) * 110_540, 1)
        if width_metres >= height_metres:
            width = max_dimension
            height = max(64, round(max_dimension * height_metres / width_metres))
        else:
            height = max_dimension
            width = max(64, round(max_dimension * width_metres / height_metres))
        return width, height

    @staticmethod
    def _read_on_common_grid(
        dataset: rasterio.io.DatasetReader,
        bounds: tuple[float, float, float, float],
        width: int,
        height: int,
        band_indexes: tuple[int, int, int],
    ) -> np.ndarray:
        """将指定 RGB 波段重投影到公共 WGS84 网格。

        Args:
            dataset: 源栅格。
            bounds: 目标 WGS84 范围。
            width: 目标宽度。
            height: 目标高度。
            band_indexes: RGB 波段索引。

        Returns:
            np.ndarray: 三通道 float32 数组，无数据为 NaN。
        """
        destination = np.full((3, height, width), np.nan, dtype="float32")
        destination_transform = from_bounds(*bounds, width, height)
        for channel, band_index in enumerate(band_indexes):
            reproject(
                source=rasterio.band(dataset, band_index),
                destination=destination[channel],
                src_transform=dataset.transform,
                src_crs=dataset.crs,
                src_nodata=dataset.nodata,
                dst_transform=destination_transform,
                dst_crs="EPSG:4326",
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
                init_dest_nodata=True,
                num_threads=2,
            )
        return destination

    @staticmethod
    def _shared_stretch(
        baseline: np.ndarray,
        target: np.ndarray,
    ) -> tuple[tuple[float, float], ...]:
        """从两期数据共同样本计算逐通道 2%–98% 拉伸范围。

        Args:
            baseline: 前时相公共网格数组。
            target: 后时相公共网格数组。

        Returns:
            tuple[tuple[float, float], ...]: RGB 三通道共同拉伸范围。
        """
        ranges: list[tuple[float, float]] = []
        for channel in range(3):
            baseline_values = baseline[channel][np.isfinite(baseline[channel])]
            target_values = target[channel][np.isfinite(target[channel])]
            if baseline_values.size == 0 or target_values.size == 0:
                raise ValueError("影像公共范围没有可显示像元")

            def sample(values: np.ndarray) -> np.ndarray:
                if values.size <= 200_000:
                    return values
                return values[:: math.ceil(values.size / 200_000)]

            baseline_sample = sample(baseline_values)
            target_sample = sample(target_values)
            baseline_lower, baseline_upper = np.percentile(
                baseline_sample,
                (2, 98),
            )
            target_lower, target_upper = np.percentile(target_sample, (2, 98))
            baseline_span = float(baseline_upper - baseline_lower)
            target_span = float(target_upper - target_lower)
            smaller_span = min(baseline_span, target_span)
            larger_span = max(baseline_span, target_span)
            if (
                larger_span > 0
                and (
                    smaller_span <= 0
                    or larger_span / smaller_span > 50
                )
            ):
                raise ValueError(
                    "前后时相影像辐射量纲差异过大，请使用同处理级别产品"
                )
            values = np.concatenate((baseline_sample, target_sample))
            lower, upper = np.percentile(values, (2, 98))
            if not np.isfinite(lower) or not np.isfinite(upper):
                raise ValueError("影像像元统计无效")
            if upper <= lower:
                lower = float(np.min(values))
                upper = float(np.max(values))
            if upper <= lower:
                upper = lower + 1
            ranges.append((float(lower), float(upper)))
        return tuple(ranges)

    @staticmethod
    def _encode_png(
        array: np.ndarray,
        stretch_ranges: tuple[tuple[float, float], ...],
    ) -> bytes:
        """按共同拉伸范围编码带透明无数据区的 RGBA PNG。

        Args:
            array: 三通道 float32 数组。
            stretch_ranges: 三通道共同拉伸范围。

        Returns:
            bytes: PNG 文件字节。
        """
        rgba = np.zeros((4, array.shape[1], array.shape[2]), dtype="uint8")
        valid_mask = np.any(np.isfinite(array), axis=0)
        for channel, (lower, upper) in enumerate(stretch_ranges):
            scaled = np.clip((array[channel] - lower) / (upper - lower), 0, 1)
            rgba[channel] = np.where(
                np.isfinite(scaled),
                np.rint(scaled * 255),
                0,
            ).astype("uint8")
        rgba[3] = np.where(valid_mask, 255, 0).astype("uint8")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with MemoryFile() as memory:
                with memory.open(
                    driver="PNG",
                    width=array.shape[2],
                    height=array.shape[1],
                    count=4,
                    dtype="uint8",
                ) as dataset:
                    dataset.write(rgba)
                return memory.read()

    def render_pair(
        self,
        baseline_path: Path,
        target_path: Path,
        max_dimension: int,
    ) -> ChangeComparisonRenderResult:
        """生成公共交集网格、共同拉伸和两张同尺寸 PNG。

        Args:
            baseline_path: 前时相受控栅格路径。
            target_path: 后时相受控栅格路径。
            max_dimension: 预览最长边像素上限。

        Returns:
            ChangeComparisonRenderResult: 两期预览和渲染参数。
        """
        if not 256 <= max_dimension <= 4096:
            raise ValueError("变化检测预览尺寸必须为 256–4096 像素")
        with (
            rasterio.open(baseline_path) as baseline,
            rasterio.open(target_path) as target,
        ):
            bounds = self._intersection_bounds(baseline, target)
            width, height = self._preview_size(bounds, max_dimension)
            baseline_indexes = self._rgb_band_indexes(baseline)
            target_indexes = self._rgb_band_indexes(target)
            baseline_array = self._read_on_common_grid(
                baseline,
                bounds,
                width,
                height,
                baseline_indexes,
            )
            target_array = self._read_on_common_grid(
                target,
                bounds,
                width,
                height,
                target_indexes,
            )
        stretch_ranges = self._shared_stretch(baseline_array, target_array)
        return ChangeComparisonRenderResult(
            baseline_png=self._encode_png(baseline_array, stretch_ranges),
            target_png=self._encode_png(target_array, stretch_ranges),
            bounds_wgs84=bounds,
            width=width,
            height=height,
            baseline_band_indexes=baseline_indexes,
            target_band_indexes=target_indexes,
            stretch_ranges=stretch_ranges,
        )
