"""基于相位相关的双景平移配准、残差复核和实体输出引擎。"""

import os
from dataclasses import dataclass
from math import ceil, floor, hypot
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.transform import array_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from app.core.exceptions import ValidationException


@dataclass(frozen=True)
class RegistrationSource:
    """一个已通过实体大小和 SHA-256 复核的配准来源。"""

    asset_id: int
    asset_code: str
    asset_name: str
    step_code: str
    step_name: str
    path: Path
    source_uri: str
    source_size_bytes: int
    source_sha256: str


@dataclass(frozen=True)
class RegistrationExecutionResult:
    """自动位移、残差门禁和输出栅格结构。"""

    initial_shift_x_pixels: float
    initial_shift_y_pixels: float
    initial_offset_pixels: float
    residual_shift_x_pixels: float
    residual_shift_y_pixels: float
    residual_offset_pixels: float
    overlap_ratio: float
    peak_to_sidelobe_ratio: float
    crs: str
    resolution_x: float
    resolution_y: float
    width: int
    height: int
    band_count: int
    dtype: str
    bounds_wgs84: list[float]
    manifest: dict[str, Any]


class ImageryRegistrationEngine:
    """执行受像元上限保护的平移配准和服务端残差复核。"""

    processor_name = "平台内置相位相关影像配准处理器"
    processor_version = "phase-correlation-translation-v1"
    resampling_methods = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
    }

    def __init__(
        self,
        max_output_pixels: int = 10_000_000,
        preview_max_dimension: int = 2048,
    ) -> None:
        """初始化配准引擎。

        Args:
            max_output_pixels: 参考网格允许的最大像元数。
            preview_max_dimension: 位移估计预览最长边。

        Returns:
            None: 无返回值。
        """
        self.max_output_pixels = max_output_pixels
        self.preview_max_dimension = preview_max_dimension

    @staticmethod
    def _intersection_window(
        reference: rasterio.io.DatasetReader,
        moving: rasterio.io.DatasetReader,
    ) -> Window:
        """计算待配准景投影到参考 CRS 后的公共像素窗口。

        Args:
            reference: 参考栅格。
            moving: 待配准栅格。

        Returns:
            Window: 参考网格内公共窗口。
        """
        moving_bounds = transform_bounds(
            moving.crs,
            reference.crs,
            *moving.bounds,
            densify_pts=21,
        )
        bounds = (
            max(reference.bounds.left, moving_bounds[0]),
            max(reference.bounds.bottom, moving_bounds[1]),
            min(reference.bounds.right, moving_bounds[2]),
            min(reference.bounds.top, moving_bounds[3]),
        )
        if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
            raise ValidationException("参考影像与待配准影像没有公共覆盖范围")
        raw_window = from_bounds(*bounds, transform=reference.transform)
        column_start = max(0, floor(raw_window.col_off))
        row_start = max(0, floor(raw_window.row_off))
        column_end = min(reference.width, ceil(raw_window.col_off + raw_window.width))
        row_end = min(reference.height, ceil(raw_window.row_off + raw_window.height))
        if column_end - column_start < 16 or row_end - row_start < 16:
            raise ValidationException("影像公共范围过小，无法执行可靠配准")
        return Window(
            column_start,
            row_start,
            column_end - column_start,
            row_end - row_start,
        )

    def _preview_shape(self, window: Window) -> tuple[int, int]:
        """按公共窗口长宽比计算位移估计预览尺寸。

        Args:
            window: 参考网格公共窗口。

        Returns:
            tuple[int, int]: 预览高度和宽度。
        """
        width = int(window.width)
        height = int(window.height)
        scale = min(1, self.preview_max_dimension / max(width, height))
        return max(16, round(height * scale)), max(16, round(width * scale))

    @staticmethod
    def _quadratic_peak_offset(
        values: np.ndarray,
        index: int,
    ) -> float:
        """使用峰值相邻三点抛物线拟合亚像素偏移。

        Args:
            values: 一维相关响应。
            index: 整数峰值位置。

        Returns:
            float: `[-0.5, 0.5]` 范围内亚像素修正。
        """
        previous_value = float(values[(index - 1) % values.size])
        center_value = float(values[index])
        next_value = float(values[(index + 1) % values.size])
        denominator = previous_value - 2 * center_value + next_value
        if abs(denominator) <= 1e-12:
            return 0
        return float(np.clip(
            0.5 * (previous_value - next_value) / denominator,
            -0.5,
            0.5,
        ))

    @classmethod
    def _phase_correlation(
        cls,
        reference: np.ndarray,
        moving: np.ndarray,
    ) -> tuple[float, float, float, float]:
        """计算待配准影像应施加的二维平移和峰旁比。

        Args:
            reference: 参考单波段预览。
            moving: 待配准单波段预览。

        Returns:
            tuple: X/Y 平移、峰旁比和联合有效像元比例。
        """
        valid = np.isfinite(reference) & np.isfinite(moving)
        overlap_ratio = float(valid.mean())
        if int(valid.sum()) < max(256, int(valid.size * 0.02)):
            raise ValidationException("影像公共范围有效像元不足，无法执行配准")
        reference_values = reference[valid].astype("float64")
        moving_values = moving[valid].astype("float64")
        reference_std = float(reference_values.std())
        moving_std = float(moving_values.std())
        if reference_std <= 1e-12 or moving_std <= 1e-12:
            raise ValidationException("配准波段缺少可识别纹理或动态范围")
        reference_normalized = np.zeros(reference.shape, dtype="float64")
        moving_normalized = np.zeros(moving.shape, dtype="float64")
        reference_normalized[valid] = (
            reference_values - float(reference_values.mean())
        ) / reference_std
        moving_normalized[valid] = (
            moving_values - float(moving_values.mean())
        ) / moving_std
        window = np.outer(
            np.hanning(reference.shape[0]),
            np.hanning(reference.shape[1]),
        )
        reference_spectrum = np.fft.fft2(reference_normalized * window)
        moving_spectrum = np.fft.fft2(moving_normalized * window)
        cross_power = reference_spectrum * np.conj(moving_spectrum)
        magnitude = np.abs(cross_power)
        cross_power = np.divide(
            cross_power,
            magnitude,
            out=np.zeros_like(cross_power),
            where=magnitude > 1e-12,
        )
        correlation = np.fft.ifft2(cross_power).real
        peak_row, peak_column = np.unravel_index(
            int(np.argmax(correlation)),
            correlation.shape,
        )
        row_profile = correlation[:, peak_column]
        column_profile = correlation[peak_row, :]
        shift_y = float(peak_row)
        shift_x = float(peak_column)
        if shift_y > correlation.shape[0] / 2:
            shift_y -= correlation.shape[0]
        if shift_x > correlation.shape[1] / 2:
            shift_x -= correlation.shape[1]
        shift_y += cls._quadratic_peak_offset(row_profile, peak_row)
        shift_x += cls._quadratic_peak_offset(column_profile, peak_column)
        sidelobe = correlation.copy()
        radius = 5
        row_indexes = [
            (peak_row + offset) % correlation.shape[0]
            for offset in range(-radius, radius + 1)
        ]
        column_indexes = [
            (peak_column + offset) % correlation.shape[1]
            for offset in range(-radius, radius + 1)
        ]
        sidelobe[np.ix_(row_indexes, column_indexes)] = np.nan
        sidelobe_values = sidelobe[np.isfinite(sidelobe)]
        sidelobe_std = float(sidelobe_values.std()) if sidelobe_values.size else 0
        peak_to_sidelobe = (
            (float(correlation[peak_row, peak_column]) - float(sidelobe_values.mean()))
            / sidelobe_std
            if sidelobe_std > 1e-12
            else 0
        )
        return shift_x, shift_y, peak_to_sidelobe, overlap_ratio

    @staticmethod
    def _read_preview(
        dataset: rasterio.io.DatasetReader,
        band_index: int,
        window: Window,
        height: int,
        width: int,
    ) -> np.ndarray:
        """读取一个公共窗口的浮点单波段预览。

        Args:
            dataset: 已对齐参考网格的数据集。
            band_index: 一基波段索引。
            window: 参考网格窗口。
            height: 输出高度。
            width: 输出宽度。

        Returns:
            np.ndarray: 无效像元为 NaN 的数组。
        """
        return dataset.read(
            band_index,
            window=window,
            out_shape=(height, width),
            masked=True,
            resampling=Resampling.bilinear,
        ).filled(np.nan).astype("float32")

    @staticmethod
    def _write_registered_output(
        reference: rasterio.io.DatasetReader,
        moving_aligned: WarpedVRT,
        output_path: Path,
        shift_x_pixels: float,
        shift_y_pixels: float,
        resampling: Resampling,
        reference_source: RegistrationSource,
        moving_source: RegistrationSource,
    ) -> None:
        """把平移修正后的待配准景按参考网格分块写出。

        Args:
            reference: 参考栅格。
            moving_aligned: 初次投影到参考网格的待配准 VRT。
            output_path: 临时输出路径。
            shift_x_pixels: 待配准景 X 平移。
            shift_y_pixels: 待配准景 Y 平移。
            resampling: 输出重采样方法。
            reference_source: 参考来源证据。
            moving_source: 待配准来源证据。

        Returns:
            None: 无返回值。
        """
        corrected_transform = reference.transform * Affine.translation(
            shift_x_pixels,
            shift_y_pixels,
        )
        profile = {
            "driver": "GTiff",
            "width": reference.width,
            "height": reference.height,
            "count": moving_aligned.count,
            "dtype": "float32",
            "crs": reference.crs,
            "transform": reference.transform,
            "nodata": np.nan,
            "compress": "deflate",
            "predictor": 3,
            "BIGTIFF": "IF_SAFER",
        }
        with WarpedVRT(
            moving_aligned,
            src_crs=reference.crs,
            src_transform=corrected_transform,
            src_nodata=np.nan,
            crs=reference.crs,
            transform=reference.transform,
            width=reference.width,
            height=reference.height,
            nodata=np.nan,
            dtype="float32",
            resampling=resampling,
            warp_mem_limit=128,
        ) as corrected:
            with rasterio.open(output_path, "w", **profile) as output:
                for _, window in output.block_windows(1):
                    output.write(
                        corrected.read(
                            window=window,
                            masked=True,
                        ).filled(np.nan).astype("float32"),
                        window=window,
                    )
                output.descriptions = moving_aligned.descriptions
                output.update_tags(
                    PROCESSING_STEP="imagery_registration",
                    REGISTRATION_METHOD="phase_correlation_translation",
                    REFERENCE_ASSET_CODE=reference_source.asset_code,
                    REFERENCE_STEP_CODE=reference_source.step_code,
                    REFERENCE_SHA256=reference_source.source_sha256,
                    MOVING_ASSET_CODE=moving_source.asset_code,
                    MOVING_STEP_CODE=moving_source.step_code,
                    MOVING_SHA256=moving_source.source_sha256,
                    SHIFT_X_PIXELS=f"{shift_x_pixels:.6f}",
                    SHIFT_Y_PIXELS=f"{shift_y_pixels:.6f}",
                )

    def execute(
        self,
        reference_source: RegistrationSource,
        moving_source: RegistrationSource,
        output_path: Path,
        reference_band_index: int,
        moving_band_index: int,
        resampling_method: str,
        max_initial_offset_pixels: float,
        max_residual_pixels: float,
        minimum_overlap_ratio: float,
        minimum_peak_to_sidelobe_ratio: float,
        job_code: str,
    ) -> RegistrationExecutionResult:
        """执行平移配准、相关质量门禁、实体写出和残差复核。

        Args:
            reference_source: 参考景实体来源。
            moving_source: 待配准景实体来源。
            output_path: 受控最终输出路径。
            reference_band_index: 参考景配准波段。
            moving_band_index: 待配准景配准波段。
            resampling_method: 输出重采样方法。
            max_initial_offset_pixels: 可接受的最大初始位移。
            max_residual_pixels: 配准后最大残差。
            minimum_overlap_ratio: 公共窗口最小有效像元比例。
            minimum_peak_to_sidelobe_ratio: 最小相关峰旁比。
            job_code: 配准任务编号。

        Returns:
            RegistrationExecutionResult: 自动位移、残差和实体结构。
        """
        if reference_source.asset_id == moving_source.asset_id:
            raise ValidationException("参考影像与待配准影像不能相同")
        resampling = self.resampling_methods.get(resampling_method)
        if resampling is None:
            raise ValidationException("重采样仅支持 nearest、bilinear 或 cubic")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = output_path.with_name(
            f".{output_path.stem}-{uuid4().hex}.tmp.tif"
        )
        try:
            with rasterio.open(reference_source.path) as reference, rasterio.open(
                moving_source.path
            ) as moving:
                if reference.crs is None or moving.crs is None:
                    raise ValidationException("配准输入必须具有可验证 CRS")
                if not 1 <= reference_band_index <= reference.count:
                    raise ValidationException("参考影像配准波段超出实体范围")
                if not 1 <= moving_band_index <= moving.count:
                    raise ValidationException("待配准影像配准波段超出实体范围")
                pixel_count = reference.width * reference.height
                if pixel_count > self.max_output_pixels:
                    raise ValidationException(
                        f"配准输出预计 {pixel_count} 像元，超过上限 "
                        f"{self.max_output_pixels}；请改用受控裁剪成果"
                    )
                common_window = self._intersection_window(reference, moving)
                preview_height, preview_width = self._preview_shape(common_window)
                with WarpedVRT(
                    moving,
                    crs=reference.crs,
                    transform=reference.transform,
                    width=reference.width,
                    height=reference.height,
                    nodata=np.nan,
                    dtype="float32",
                    resampling=Resampling.bilinear,
                    warp_mem_limit=128,
                ) as moving_aligned:
                    reference_preview = self._read_preview(
                        reference,
                        reference_band_index,
                        common_window,
                        preview_height,
                        preview_width,
                    )
                    moving_preview = self._read_preview(
                        moving_aligned,
                        moving_band_index,
                        common_window,
                        preview_height,
                        preview_width,
                    )
                    (
                        preview_shift_x,
                        preview_shift_y,
                        peak_to_sidelobe,
                        overlap_ratio,
                    ) = self._phase_correlation(
                        reference_preview,
                        moving_preview,
                    )
                    if overlap_ratio < minimum_overlap_ratio:
                        raise ValidationException(
                            f"配准公共窗口有效像元比例 {overlap_ratio:.5f} 低于门槛 "
                            f"{minimum_overlap_ratio:.5f}"
                        )
                    if peak_to_sidelobe < minimum_peak_to_sidelobe_ratio:
                        raise ValidationException(
                            f"配准相关峰旁比 {peak_to_sidelobe:.5f} 低于门槛 "
                            f"{minimum_peak_to_sidelobe_ratio:.5f}"
                        )
                    shift_x = preview_shift_x * common_window.width / preview_width
                    shift_y = preview_shift_y * common_window.height / preview_height
                    initial_offset = hypot(shift_x, shift_y)
                    if initial_offset > max_initial_offset_pixels:
                        raise ValidationException(
                            f"自动估计初始偏移 {initial_offset:.4f} 像素超过上限 "
                            f"{max_initial_offset_pixels:.4f} 像素"
                        )
                    self._write_registered_output(
                        reference,
                        moving_aligned,
                        temporary_output,
                        shift_x,
                        shift_y,
                        resampling,
                        reference_source,
                        moving_source,
                    )
                with rasterio.open(temporary_output) as registered:
                    registered_preview = self._read_preview(
                        registered,
                        moving_band_index,
                        common_window,
                        preview_height,
                        preview_width,
                    )
                    (
                        residual_preview_x,
                        residual_preview_y,
                        residual_peak_to_sidelobe,
                        residual_overlap_ratio,
                    ) = self._phase_correlation(
                        reference_preview,
                        registered_preview,
                    )
                    residual_x = (
                        residual_preview_x * common_window.width / preview_width
                    )
                    residual_y = (
                        residual_preview_y * common_window.height / preview_height
                    )
                    residual_offset = hypot(residual_x, residual_y)
                    if residual_offset > max_residual_pixels:
                        raise ValidationException(
                            f"配准后残差 {residual_offset:.4f} 像素超过门槛 "
                            f"{max_residual_pixels:.4f} 像素"
                        )
                    output_bounds = array_bounds(
                        registered.height,
                        registered.width,
                        registered.transform,
                    )
                    bounds_wgs84 = transform_bounds(
                        registered.crs,
                        "EPSG:4326",
                        *output_bounds,
                        densify_pts=21,
                    )
                    manifest = {
                        "processor_name": self.processor_name,
                        "processor_version": self.processor_version,
                        "job_code": job_code,
                        "method": "phase_correlation_translation",
                        "preview_width": preview_width,
                        "preview_height": preview_height,
                        "common_window": {
                            "column_offset": float(common_window.col_off),
                            "row_offset": float(common_window.row_off),
                            "width": float(common_window.width),
                            "height": float(common_window.height),
                        },
                        "initial_shift_x_pixels": shift_x,
                        "initial_shift_y_pixels": shift_y,
                        "initial_offset_pixels": initial_offset,
                        "residual_shift_x_pixels": residual_x,
                        "residual_shift_y_pixels": residual_y,
                        "residual_offset_pixels": residual_offset,
                        "overlap_ratio": overlap_ratio,
                        "residual_overlap_ratio": residual_overlap_ratio,
                        "peak_to_sidelobe_ratio": peak_to_sidelobe,
                        "residual_peak_to_sidelobe_ratio": residual_peak_to_sidelobe,
                        "max_output_pixels": self.max_output_pixels,
                    }
                    result = RegistrationExecutionResult(
                        initial_shift_x_pixels=shift_x,
                        initial_shift_y_pixels=shift_y,
                        initial_offset_pixels=initial_offset,
                        residual_shift_x_pixels=residual_x,
                        residual_shift_y_pixels=residual_y,
                        residual_offset_pixels=residual_offset,
                        overlap_ratio=overlap_ratio,
                        peak_to_sidelobe_ratio=peak_to_sidelobe,
                        crs=registered.crs.to_string(),
                        resolution_x=abs(float(registered.transform.a)),
                        resolution_y=abs(float(registered.transform.e)),
                        width=registered.width,
                        height=registered.height,
                        band_count=registered.count,
                        dtype=registered.dtypes[0],
                        bounds_wgs84=[float(value) for value in bounds_wgs84],
                        manifest=manifest,
                    )
            os.replace(temporary_output, output_path)
            return result
        finally:
            temporary_output.unlink(missing_ok=True)
