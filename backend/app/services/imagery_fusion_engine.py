"""多光谱与全色影像的分块 Brovey 融合和质量验收引擎。"""

import os
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.transform import array_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling, transform_bounds
from rasterio.windows import Window

from app.core.exceptions import ValidationException


@dataclass(frozen=True)
class FusionSource:
    """一个经过实体校验的融合输入。"""

    path: Path
    asset_code: str
    source_uri: str
    source_size_bytes: int
    source_sha256: str


@dataclass(frozen=True)
class FusionExecutionResult:
    """融合输出结构、质量指标和物理证据。"""

    width: int
    height: int
    band_count: int
    dtype: str
    crs: str
    resolution_x: float
    resolution_y: float
    bounds_wgs84: list[float]
    overlap_ratio: float
    spectral_correlations: list[float]
    minimum_spectral_correlation: float
    mean_spectral_correlation: float
    spatial_detail_gain: float
    manifest: dict


class ImageryFusionEngine:
    """以全色网格为目标执行分块直方图匹配 Brovey 融合。"""

    processor_name = "平台内置 Brovey 全色融合处理器"
    processor_version = "brovey-histogram-match-v1"
    resampling_methods = {
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
    }

    def __init__(self, max_output_pixels: int = 10_000_000) -> None:
        """初始化融合输出像元门禁。

        Args:
            max_output_pixels: 允许输出的最大像元数。

        Returns:
            None: 无返回值。
        """
        self.max_output_pixels = max_output_pixels

    @staticmethod
    def _windows(width: int, height: int, size: int = 512) -> list[Window]:
        """生成有界内存处理窗口。

        Args:
            width: 栅格宽度。
            height: 栅格高度。
            size: 窗口边长。

        Returns:
            list[Window]: 覆盖完整栅格的窗口。
        """
        return [
            Window(column, row, min(size, width - column), min(size, height - row))
            for row in range(0, height, size)
            for column in range(0, width, size)
        ]

    @staticmethod
    def _correlation(
        count: int,
        sum_x: float,
        sum_y: float,
        sum_x2: float,
        sum_y2: float,
        sum_xy: float,
    ) -> float:
        """由分块累计量计算皮尔逊相关系数。

        Args:
            count: 有效样本数。
            sum_x: 原多光谱值之和。
            sum_y: 融合值之和。
            sum_x2: 原多光谱平方和。
            sum_y2: 融合值平方和。
            sum_xy: 交叉乘积和。

        Returns:
            float: -1 到 1 的相关系数。
        """
        if count <= 1:
            return 0
        numerator = count * sum_xy - sum_x * sum_y
        denominator = np.sqrt(
            max(count * sum_x2 - sum_x * sum_x, 0)
            * max(count * sum_y2 - sum_y * sum_y, 0)
        )
        return float(numerator / denominator) if denominator > 1e-12 else 0

    @staticmethod
    def _gradient_sum(values: np.ndarray, valid: np.ndarray) -> tuple[float, int]:
        """统计窗口内水平和垂直有效梯度绝对值。

        Args:
            values: 二维强度数组。
            valid: 二维有效像元掩膜。

        Returns:
            tuple[float, int]: 梯度绝对值总和与样本数。
        """
        horizontal_valid = valid[:, 1:] & valid[:, :-1]
        vertical_valid = valid[1:, :] & valid[:-1, :]
        horizontal = np.abs(np.diff(values, axis=1))[horizontal_valid]
        vertical = np.abs(np.diff(values, axis=0))[vertical_valid]
        return (
            float(horizontal.sum(dtype="float64") + vertical.sum(dtype="float64")),
            int(horizontal.size + vertical.size),
        )

    def execute(
        self,
        multispectral: FusionSource,
        panchromatic: FusionSource,
        output_path: Path,
        multispectral_band_indexes: list[int],
        panchromatic_band_index: int,
        resampling_method: str,
        minimum_overlap_ratio: float,
        minimum_spectral_correlation: float,
        minimum_spatial_detail_gain: float,
        gain_limit: float,
        job_code: str,
    ) -> FusionExecutionResult:
        """执行三波段 Brovey 全色融合并验收光谱与空间质量。

        Args:
            multispectral: 多光谱实体输入。
            panchromatic: 全色实体输入。
            output_path: 受控最终 GeoTIFF 路径。
            multispectral_band_indexes: 三个不同的多光谱波段编号。
            panchromatic_band_index: 全色波段编号。
            resampling_method: bilinear 或 cubic。
            minimum_overlap_ratio: 多光谱与全色有效像元重叠门槛。
            minimum_spectral_correlation: 各融合波段相关系数门槛。
            minimum_spatial_detail_gain: 融合强度梯度增益门槛。
            gain_limit: Brovey 比值的对称裁剪上限。
            job_code: 融合任务编号。

        Returns:
            FusionExecutionResult: 通过门禁的输出结构和质量指标。
        """
        if len(multispectral_band_indexes) != 3:
            raise ValidationException("全色融合必须选择三个多光谱波段")
        if len(set(multispectral_band_indexes)) != 3:
            raise ValidationException("全色融合的三个多光谱波段必须互不相同")
        resampling = self.resampling_methods.get(resampling_method)
        if resampling is None:
            raise ValidationException("全色融合重采样仅支持 bilinear 或 cubic")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = output_path.with_name(
            f".{output_path.stem}-{uuid4().hex}.tmp.tif"
        )
        try:
            with ExitStack() as stack:
                ms = stack.enter_context(rasterio.open(multispectral.path))
                pan = stack.enter_context(rasterio.open(panchromatic.path))
                if ms.crs is None or pan.crs is None:
                    raise ValidationException("融合输入必须具备可验证 CRS")
                if ms.crs != pan.crs:
                    raise ValidationException("当前全色融合要求两类输入使用相同 CRS")
                if any(
                    index < 1 or index > ms.count
                    for index in multispectral_band_indexes
                ):
                    raise ValidationException("多光谱波段编号超出实体波段范围")
                if not 1 <= panchromatic_band_index <= pan.count:
                    raise ValidationException("全色波段编号超出实体波段范围")
                ms_resolution = max(abs(ms.res[0]), abs(ms.res[1]))
                pan_resolution = max(abs(pan.res[0]), abs(pan.res[1]))
                resolution_ratio = ms_resolution / pan_resolution
                if resolution_ratio < 1.5:
                    raise ValidationException("全色影像分辨率必须至少优于多光谱 1.5 倍")
                if pan.width * pan.height > self.max_output_pixels:
                    raise ValidationException(
                        f"融合输出预计 {pan.width * pan.height} 像元，超过上限 "
                        f"{self.max_output_pixels}"
                    )
                virtual_ms = stack.enter_context(WarpedVRT(
                    ms,
                    crs=pan.crs,
                    transform=pan.transform,
                    width=pan.width,
                    height=pan.height,
                    resampling=resampling,
                    dtype="float32",
                    nodata=np.nan,
                ))
                windows = self._windows(pan.width, pan.height)
                pan_valid_count = 0
                common_valid_count = 0
                pan_sum = 0.0
                pan_sum2 = 0.0
                intensity_sum = 0.0
                intensity_sum2 = 0.0
                band_min = np.full(3, np.inf, dtype="float64")
                band_max = np.full(3, -np.inf, dtype="float64")
                pan_min = np.inf
                pan_max = -np.inf
                for window in windows:
                    pan_block = pan.read(
                        panchromatic_band_index,
                        window=window,
                        masked=True,
                    ).filled(np.nan).astype("float32")
                    ms_block = virtual_ms.read(
                        multispectral_band_indexes,
                        window=window,
                        masked=True,
                    ).filled(np.nan).astype("float32")
                    pan_valid = np.isfinite(pan_block) & (pan_block > 1e-12)
                    valid = pan_valid & np.all(np.isfinite(ms_block), axis=0)
                    intensity = np.mean(ms_block, axis=0)
                    valid &= intensity > 1e-12
                    pan_valid_count += int(pan_valid.sum())
                    count = int(valid.sum())
                    if count == 0:
                        continue
                    common_valid_count += count
                    pan_values = pan_block[valid].astype("float64")
                    intensity_values = intensity[valid].astype("float64")
                    pan_sum += float(pan_values.sum())
                    pan_sum2 += float(np.square(pan_values).sum())
                    intensity_sum += float(intensity_values.sum())
                    intensity_sum2 += float(np.square(intensity_values).sum())
                    pan_min = min(pan_min, float(pan_values.min()))
                    pan_max = max(pan_max, float(pan_values.max()))
                    for band in range(3):
                        values = ms_block[band][valid]
                        band_min[band] = min(band_min[band], float(values.min()))
                        band_max[band] = max(band_max[band], float(values.max()))
                if pan_valid_count <= 0 or common_valid_count <= 0:
                    raise ValidationException("多光谱与全色影像没有共同有效像元")
                overlap_ratio = common_valid_count / pan_valid_count
                if overlap_ratio < minimum_overlap_ratio:
                    raise ValidationException(
                        f"融合有效重叠率 {overlap_ratio:.4f} 低于门槛 "
                        f"{minimum_overlap_ratio:.4f}"
                    )
                if pan_max - pan_min <= 1e-6 or np.any(band_max - band_min <= 1e-6):
                    raise ValidationException("融合输入存在无纹理或常量波段")
                pan_mean = pan_sum / common_valid_count
                intensity_mean = intensity_sum / common_valid_count
                pan_std = np.sqrt(
                    max(pan_sum2 / common_valid_count - pan_mean * pan_mean, 0)
                )
                intensity_std = np.sqrt(
                    max(
                        intensity_sum2 / common_valid_count
                        - intensity_mean * intensity_mean,
                        0,
                    )
                )
                if pan_std <= 1e-12 or intensity_std <= 1e-12:
                    raise ValidationException("融合输入动态范围不足，无法匹配全色强度")

                profile = pan.profile.copy()
                profile.update(
                    driver="GTiff",
                    count=3,
                    dtype="float32",
                    nodata=np.nan,
                    compress="deflate",
                    predictor=3,
                    BIGTIFF="IF_SAFER",
                )
                correlations = [
                    {"count": 0, "x": 0.0, "y": 0.0, "x2": 0.0, "y2": 0.0, "xy": 0.0}
                    for _ in range(3)
                ]
                source_gradient_sum = 0.0
                source_gradient_count = 0
                fused_gradient_sum = 0.0
                fused_gradient_count = 0
                with rasterio.open(temporary_output, "w", **profile) as output:
                    for window in windows:
                        pan_block = pan.read(
                            panchromatic_band_index,
                            window=window,
                            masked=True,
                        ).filled(np.nan).astype("float32")
                        ms_block = virtual_ms.read(
                            multispectral_band_indexes,
                            window=window,
                            masked=True,
                        ).filled(np.nan).astype("float32")
                        intensity = np.mean(ms_block, axis=0)
                        valid = (
                            np.isfinite(pan_block)
                            & (pan_block > 1e-12)
                            & np.all(np.isfinite(ms_block), axis=0)
                            & (intensity > 1e-12)
                        )
                        matched_pan = (
                            (pan_block - pan_mean) / pan_std * intensity_std
                            + intensity_mean
                        )
                        ratio = np.divide(
                            matched_pan,
                            intensity,
                            out=np.ones_like(intensity, dtype="float32"),
                            where=valid,
                        )
                        ratio = np.clip(ratio, 1 / gain_limit, gain_limit)
                        fused = ms_block * ratio[np.newaxis, :, :]
                        fused[:, ~valid] = np.nan
                        output.write(fused.astype("float32"), window=window)
                        fused_intensity = np.mean(fused, axis=0)
                        source_gradient = self._gradient_sum(intensity, valid)
                        fused_gradient = self._gradient_sum(fused_intensity, valid)
                        source_gradient_sum += source_gradient[0]
                        source_gradient_count += source_gradient[1]
                        fused_gradient_sum += fused_gradient[0]
                        fused_gradient_count += fused_gradient[1]
                        for band in range(3):
                            x = ms_block[band][valid].astype("float64")
                            y = fused[band][valid].astype("float64")
                            stats = correlations[band]
                            stats["count"] += int(x.size)
                            stats["x"] += float(x.sum())
                            stats["y"] += float(y.sum())
                            stats["x2"] += float(np.square(x).sum())
                            stats["y2"] += float(np.square(y).sum())
                            stats["xy"] += float((x * y).sum())
                    descriptions = [
                        ms.descriptions[index - 1]
                        or f"multispectral_band_{index}"
                        for index in multispectral_band_indexes
                    ]
                    output.descriptions = tuple(
                        f"pan_sharpened_{description}" for description in descriptions
                    )
                    output.update_tags(
                        PROCESSING_STEP="pan_sharpening",
                        FUSION_JOB_CODE=job_code,
                        FUSION_ALGORITHM="brovey_histogram_match",
                        MULTISPECTRAL_ASSET_CODE=multispectral.asset_code,
                        PANCHROMATIC_ASSET_CODE=panchromatic.asset_code,
                        MULTISPECTRAL_SHA256=multispectral.source_sha256,
                        PANCHROMATIC_SHA256=panchromatic.source_sha256,
                    )
                spectral_correlations = [
                    self._correlation(
                        int(stats["count"]),
                        stats["x"],
                        stats["y"],
                        stats["x2"],
                        stats["y2"],
                        stats["xy"],
                    )
                    for stats in correlations
                ]
                minimum_correlation = min(spectral_correlations)
                if minimum_correlation < minimum_spectral_correlation:
                    raise ValidationException(
                        f"融合最低光谱相关系数 {minimum_correlation:.4f} 低于门槛 "
                        f"{minimum_spectral_correlation:.4f}"
                    )
                source_gradient_mean = (
                    source_gradient_sum / source_gradient_count
                    if source_gradient_count
                    else 0
                )
                fused_gradient_mean = (
                    fused_gradient_sum / fused_gradient_count
                    if fused_gradient_count
                    else 0
                )
                spatial_detail_gain = (
                    fused_gradient_mean / source_gradient_mean
                    if source_gradient_mean > 1e-12
                    else 0
                )
                if spatial_detail_gain < minimum_spatial_detail_gain:
                    raise ValidationException(
                        f"融合空间细节增益 {spatial_detail_gain:.4f} 低于门槛 "
                        f"{minimum_spatial_detail_gain:.4f}"
                    )
                output_bounds = array_bounds(pan.height, pan.width, pan.transform)
                bounds_wgs84 = transform_bounds(
                    pan.crs,
                    "EPSG:4326",
                    *output_bounds,
                    densify_pts=21,
                )
                result = FusionExecutionResult(
                    width=pan.width,
                    height=pan.height,
                    band_count=3,
                    dtype="float32",
                    crs=pan.crs.to_string(),
                    resolution_x=abs(float(pan.res[0])),
                    resolution_y=abs(float(pan.res[1])),
                    bounds_wgs84=[float(value) for value in bounds_wgs84],
                    overlap_ratio=round(overlap_ratio, 6),
                    spectral_correlations=[
                        round(value, 6) for value in spectral_correlations
                    ],
                    minimum_spectral_correlation=round(minimum_correlation, 6),
                    mean_spectral_correlation=round(
                        float(np.mean(spectral_correlations)),
                        6,
                    ),
                    spatial_detail_gain=round(spatial_detail_gain, 6),
                    manifest={
                        "processor_name": self.processor_name,
                        "processor_version": self.processor_version,
                        "algorithm_code": "brovey_histogram_match",
                        "multispectral_band_indexes": multispectral_band_indexes,
                        "panchromatic_band_index": panchromatic_band_index,
                        "resampling_method": resampling_method,
                        "resolution_ratio": resolution_ratio,
                        "gain_limit": gain_limit,
                        "pan_mean": pan_mean,
                        "pan_std": pan_std,
                        "multispectral_intensity_mean": intensity_mean,
                        "multispectral_intensity_std": intensity_std,
                        "minimum_overlap_ratio": minimum_overlap_ratio,
                        "minimum_spectral_correlation_threshold": (
                            minimum_spectral_correlation
                        ),
                        "minimum_spatial_detail_gain_threshold": (
                            minimum_spatial_detail_gain
                        ),
                        "max_output_pixels": self.max_output_pixels,
                    },
                )
            os.replace(temporary_output, output_path)
            return result
        except RasterioIOError as exc:
            raise ValidationException("全色融合输入无法由 Rasterio 读取") from exc
        finally:
            temporary_output.unlink(missing_ok=True)
