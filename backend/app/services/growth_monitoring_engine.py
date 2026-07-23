"""真实多时相 NDVI 差值分级与异常连通区矢量化引擎。"""

import os
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
import rasterio
from affine import Affine
from rasterio.errors import RasterioIOError
from rasterio.features import bounds as geometry_bounds
from rasterio.features import geometry_mask, shapes
from rasterio.transform import array_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling, transform_bounds, transform_geom
from rasterio.windows import Window, from_bounds
from rasterio.windows import transform as window_transform

from app.core.exceptions import ValidationException


@dataclass(frozen=True)
class GrowthRasterSource:
    """一个已经过物理实体和 SHA-256 校验的 NDVI 产品来源。"""

    path: Path
    asset_code: str
    source_uri: str
    source_size_bytes: int
    source_sha256: str
    ndvi_band_index: int


@dataclass(frozen=True)
class RawGrowthZone:
    """栅格连通域转出的待 PostGIS 裁切异常区。"""

    geometry: dict
    baseline_mean: float
    current_mean: float
    delta_mean: float
    pixel_count: int


@dataclass(frozen=True)
class GrowthExecutionResult:
    """长势分级栅格、质量指标和异常区候选。"""

    width: int
    height: int
    crs: str
    resolution_x: float
    resolution_y: float
    bounds_wgs84: list[float]
    common_footprint_mask_pixel_count: int
    valid_pixel_count: int
    valid_pixel_ratio: float
    poor_pixel_count: int
    normal_pixel_count: int
    good_pixel_count: int
    raw_zones: list[RawGrowthZone]
    manifest: dict


class GrowthMonitoringEngine:
    """在基准期网格上计算任务耕地范围内的 NDVI 长势变化。"""

    processor_name = "平台内置多时相 NDVI 长势分级处理器"
    processor_version = "ndvi-delta-common-footprint-v2"

    def __init__(
        self,
        max_output_pixels: int = 10_000_000,
        max_raw_zones: int = 2_000,
    ) -> None:
        """初始化长势监测输出门禁。

        Args:
            max_output_pixels: 允许参与计算的最大像元数。
            max_raw_zones: 允许矢量化的最大原始异常连通区数。

        Returns:
            None: 无返回值。
        """
        self.max_output_pixels = max_output_pixels
        self.max_raw_zones = max_raw_zones

    @staticmethod
    def find_ndvi_band(dataset: rasterio.io.DatasetReader) -> int:
        """从实体波段描述中识别唯一 NDVI 波段。

        Args:
            dataset: 已打开的波段产品栅格。

        Returns:
            int: 一基 NDVI 波段编号。
        """
        matches = [
            index
            for index, description in enumerate(dataset.descriptions, start=1)
            if str(description or "").strip().lower() == "ndvi"
        ]
        if len(matches) != 1:
            raise ValidationException("波段产品必须包含唯一且明确描述为 NDVI 的波段")
        return matches[0]

    @staticmethod
    def _bounded_window(
        geometry: dict,
        transform: Affine,
        width: int,
        height: int,
    ) -> Window | None:
        """计算几何在栅格内的最小整数窗口。

        Args:
            geometry: 栅格 CRS 下的 GeoJSON 几何。
            transform: 栅格仿射变换。
            width: 栅格宽度。
            height: 栅格高度。

        Returns:
            Window | None: 与栅格相交的整数窗口。
        """
        left, bottom, right, top = geometry_bounds(geometry)
        raw = from_bounds(left, bottom, right, top, transform=transform)
        column_start = max(int(np.floor(raw.col_off)), 0)
        row_start = max(int(np.floor(raw.row_off)), 0)
        column_end = min(int(np.ceil(raw.col_off + raw.width)), width)
        row_end = min(int(np.ceil(raw.row_off + raw.height)), height)
        if column_end <= column_start or row_end <= row_start:
            return None
        return Window(
            column_start,
            row_start,
            column_end - column_start,
            row_end - row_start,
        )

    def execute(
        self,
        baseline: GrowthRasterSource,
        current: GrowthRasterSource,
        common_coverage_geometry_wgs84: dict,
        output_path: Path,
        poor_delta_threshold: float,
        good_delta_threshold: float,
        minimum_valid_pixel_ratio: float,
        run_code: str,
    ) -> GrowthExecutionResult:
        """执行两期 NDVI 重投影、任务掩膜、分级和异常区矢量化。

        Args:
            baseline: 基准期 NDVI 产品实体。
            current: 监测期 NDVI 产品实体。
            common_coverage_geometry_wgs84: 两期足迹共同覆盖的任务耕地几何。
            output_path: 最终长势分级 GeoTIFF 路径。
            poor_delta_threshold: 转差分类最大 NDVI 差值。
            good_delta_threshold: 转好分类最小 NDVI 差值。
            minimum_valid_pixel_ratio: 共同影像范围内两期有效像元率门槛。
            run_code: 长势监测任务编号。

        Returns:
            GrowthExecutionResult: 通过门禁的物理输出和统计指标。
        """
        if poor_delta_threshold >= 0 or good_delta_threshold <= 0:
            raise ValidationException("长势转差阈值必须小于 0，转好阈值必须大于 0")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = output_path.with_name(
            f".{output_path.stem}-{uuid4().hex}.tmp.tif"
        )
        try:
            with ExitStack() as stack:
                baseline_ds = stack.enter_context(rasterio.open(baseline.path))
                current_ds = stack.enter_context(rasterio.open(current.path))
                if baseline_ds.crs is None or current_ds.crs is None:
                    raise ValidationException("长势监测输入必须具备可验证 CRS")
                if baseline_ds.width * baseline_ds.height > self.max_output_pixels:
                    raise ValidationException(
                        f"长势监测预计 {baseline_ds.width * baseline_ds.height} 像元，"
                        f"超过上限 {self.max_output_pixels}"
                    )
                baseline_band = self.find_ndvi_band(baseline_ds)
                current_band = self.find_ndvi_band(current_ds)
                if baseline_band != baseline.ndvi_band_index:
                    raise ValidationException("基准期 NDVI 波段与来源资格快照不一致")
                if current_band != current.ndvi_band_index:
                    raise ValidationException("监测期 NDVI 波段与来源资格快照不一致")
                common_coverage_geometry = transform_geom(
                    "EPSG:4326",
                    baseline_ds.crs,
                    common_coverage_geometry_wgs84,
                    precision=12,
                )
                task_window = self._bounded_window(
                    common_coverage_geometry,
                    baseline_ds.transform,
                    baseline_ds.width,
                    baseline_ds.height,
                )
                if task_window is None:
                    raise ValidationException(
                        "任务耕地图斑与基准期 NDVI 实体没有空间交集"
                    )
                width = int(task_window.width)
                height = int(task_window.height)
                if width * height > self.max_output_pixels:
                    raise ValidationException(
                        f"任务范围预计 {width * height} 像元，超过上限 "
                        f"{self.max_output_pixels}"
                    )
                target_transform = window_transform(
                    task_window,
                    baseline_ds.transform,
                )
                baseline_values = baseline_ds.read(
                    baseline_band,
                    window=task_window,
                    masked=True,
                ).filled(np.nan).astype("float32")
                virtual_current = stack.enter_context(
                    WarpedVRT(
                        current_ds,
                        crs=baseline_ds.crs,
                        transform=target_transform,
                        width=width,
                        height=height,
                        resampling=Resampling.bilinear,
                        dtype="float32",
                        nodata=np.nan,
                    )
                )
                current_values = virtual_current.read(
                    current_band,
                    masked=True,
                ).filled(np.nan).astype("float32")
                task_mask = geometry_mask(
                    [common_coverage_geometry],
                    out_shape=(height, width),
                    transform=target_transform,
                    invert=True,
                    all_touched=False,
                )
                task_mask_count = int(task_mask.sum())
                if task_mask_count <= 0:
                    raise ValidationException(
                        "两期共同足迹内的任务耕地没有目标网格像元"
                    )
                valid = (
                    task_mask
                    & np.isfinite(baseline_values)
                    & np.isfinite(current_values)
                    & (baseline_values >= -1)
                    & (baseline_values <= 1)
                    & (current_values >= -1)
                    & (current_values <= 1)
                )
                valid_count = int(valid.sum())
                valid_pixel_ratio = valid_count / task_mask_count
                if valid_pixel_ratio < minimum_valid_pixel_ratio:
                    raise ValidationException(
                        f"共同影像范围内两期 NDVI 有效像元率 {valid_pixel_ratio:.4f} "
                        f"低于门槛 {minimum_valid_pixel_ratio:.4f}"
                    )
                delta = current_values - baseline_values
                classification = np.zeros((height, width), dtype="uint8")
                poor_mask = valid & (delta <= poor_delta_threshold)
                good_mask = valid & (delta >= good_delta_threshold)
                normal_mask = valid & ~poor_mask & ~good_mask
                classification[poor_mask] = 1
                classification[normal_mask] = 2
                classification[good_mask] = 3

                profile = baseline_ds.profile.copy()
                profile.update(
                    driver="GTiff",
                    width=width,
                    height=height,
                    transform=target_transform,
                    count=1,
                    dtype="uint8",
                    nodata=0,
                    compress="deflate",
                    predictor=2,
                    BIGTIFF="IF_SAFER",
                )
                with rasterio.open(temporary_output, "w", **profile) as output:
                    output.write(classification, 1)
                    output.set_band_description(1, "growth_class")
                    output.write_colormap(
                        1,
                        {
                            0: (0, 0, 0, 0),
                            1: (204, 62, 57, 255),
                            2: (236, 177, 65, 255),
                            3: (62, 151, 91, 255),
                        },
                    )
                    output.update_tags(
                        ALGORITHM=self.processor_version,
                        RUN_CODE=run_code,
                        BASELINE_ASSET=baseline.asset_code,
                        CURRENT_ASSET=current.asset_code,
                        POOR_DELTA_THRESHOLD=str(poor_delta_threshold),
                        GOOD_DELTA_THRESHOLD=str(good_delta_threshold),
                        VALID_PIXEL_RATIO=f"{valid_pixel_ratio:.8f}",
                        CLASS_VALUES="0:nodata,1:poor,2:normal,3:good",
                    )

                raw_zones: list[RawGrowthZone] = []
                for geometry, value in shapes(
                    classification,
                    mask=poor_mask,
                    transform=target_transform,
                    connectivity=4,
                ):
                    if int(value) != 1:
                        continue
                    if len(raw_zones) >= self.max_raw_zones:
                        raise ValidationException(
                            f"长势转差连通区超过 {self.max_raw_zones} 个，"
                            "请调整阈值或最小异常区面积"
                        )
                    window = self._bounded_window(
                        geometry,
                        target_transform,
                        width,
                        height,
                    )
                    if window is None:
                        continue
                    row_start = int(window.row_off)
                    row_end = row_start + int(window.height)
                    column_start = int(window.col_off)
                    column_end = column_start + int(window.width)
                    local_transform = window_transform(window, target_transform)
                    local_mask = geometry_mask(
                        [geometry],
                        out_shape=(int(window.height), int(window.width)),
                        transform=local_transform,
                        invert=True,
                        all_touched=False,
                    )
                    local_poor = poor_mask[
                        row_start:row_end,
                        column_start:column_end,
                    ] & local_mask
                    pixel_count = int(local_poor.sum())
                    if pixel_count <= 0:
                        continue
                    local_baseline = baseline_values[
                        row_start:row_end,
                        column_start:column_end,
                    ][local_poor]
                    local_current = current_values[
                        row_start:row_end,
                        column_start:column_end,
                    ][local_poor]
                    local_delta = delta[
                        row_start:row_end,
                        column_start:column_end,
                    ][local_poor]
                    geometry_wgs84 = transform_geom(
                        baseline_ds.crs,
                        "EPSG:4326",
                        geometry,
                        precision=10,
                    )
                    raw_zones.append(
                        RawGrowthZone(
                            geometry=geometry_wgs84,
                            baseline_mean=float(local_baseline.mean()),
                            current_mean=float(local_current.mean()),
                            delta_mean=float(local_delta.mean()),
                            pixel_count=pixel_count,
                        )
                    )

                left, bottom, right, top = array_bounds(
                    height,
                    width,
                    target_transform,
                )
                bounds_wgs84 = list(
                    transform_bounds(
                        baseline_ds.crs,
                        "EPSG:4326",
                        left,
                        bottom,
                        right,
                        top,
                        densify_pts=21,
                    )
                )
                manifest = {
                    "processor_name": self.processor_name,
                    "processor_version": self.processor_version,
                    "grid": {
                        "crs": baseline_ds.crs.to_string(),
                        "width": width,
                        "height": height,
                        "resolution": [
                            abs(float(target_transform.a)),
                            abs(float(target_transform.e)),
                        ],
                        "bounds_wgs84": bounds_wgs84,
                    },
                    "classification": {
                        "poor": {
                            "code": 1,
                            "rule": f"delta <= {poor_delta_threshold}",
                            "pixel_count": int(poor_mask.sum()),
                        },
                        "normal": {
                            "code": 2,
                            "rule": (
                                f"{poor_delta_threshold} < delta < "
                                f"{good_delta_threshold}"
                            ),
                            "pixel_count": int(normal_mask.sum()),
                        },
                        "good": {
                            "code": 3,
                            "rule": f"delta >= {good_delta_threshold}",
                            "pixel_count": int(good_mask.sum()),
                        },
                    },
                    "common_footprint_mask_pixel_count": task_mask_count,
                    "valid_pixel_count": valid_count,
                    "valid_pixel_ratio": valid_pixel_ratio,
                    "raw_anomaly_zone_count": len(raw_zones),
                }
            os.replace(temporary_output, output_path)
            return GrowthExecutionResult(
                width=width,
                height=height,
                crs=str(profile["crs"]),
                resolution_x=abs(float(target_transform.a)),
                resolution_y=abs(float(target_transform.e)),
                bounds_wgs84=bounds_wgs84,
                common_footprint_mask_pixel_count=task_mask_count,
                valid_pixel_count=valid_count,
                valid_pixel_ratio=valid_pixel_ratio,
                poor_pixel_count=int(poor_mask.sum()),
                normal_pixel_count=int(normal_mask.sum()),
                good_pixel_count=int(good_mask.sum()),
                raw_zones=raw_zones,
                manifest=manifest,
            )
        except (RasterioIOError, OSError, ValueError) as exc:
            raise ValidationException("长势监测实体栅格处理失败") from exc
        finally:
            temporary_output.unlink(missing_ok=True)
