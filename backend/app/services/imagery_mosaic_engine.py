"""基于 Rasterio 的多景重投影、全局匀色、镶嵌和覆盖验收引擎。"""

import os
from contextlib import ExitStack
from dataclasses import dataclass
from math import ceil, floor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import array_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds, transform_geom

from app.core.exceptions import ValidationException


@dataclass(frozen=True)
class MosaicSource:
    """一个已通过大小和 SHA-256 复核的镶嵌输入。"""

    asset_code: str
    asset_name: str
    step_code: str
    step_name: str
    path: Path
    source_uri: str
    source_size_bytes: int
    source_sha256: str


@dataclass(frozen=True)
class MosaicSourceEvidence:
    """输入空间结构和全局匀色统计。"""

    source: MosaicSource
    crs: str
    width: int
    height: int
    band_count: int
    band_descriptions: list[str | None]
    balance_statistics: dict[str, Any]


@dataclass(frozen=True)
class MosaicExecutionResult:
    """镶嵌实体及覆盖率验收结果。"""

    width: int
    height: int
    band_count: int
    dtype: str
    crs: str
    bounds_wgs84: list[float]
    boundary_pixel_count: int
    covered_pixel_count: int
    coverage_ratio: float
    inputs: list[MosaicSourceEvidence]
    manifest: dict[str, Any]


class ImageryMosaicEngine:
    """执行受像元上限保护的多景影像生产。"""

    processor_name = "平台内置 Rasterio 多景镶嵌处理器"
    processor_version = rasterio.__version__
    resampling_methods = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
    }

    def __init__(self, max_output_pixels: int = 10_000_000) -> None:
        """初始化镶嵌引擎。

        Args:
            max_output_pixels: 单任务允许的最大输出像元数。

        Returns:
            None: 无返回值。
        """
        self.max_output_pixels = max_output_pixels

    @staticmethod
    def _statistics(dataset: Any) -> list[dict[str, float]]:
        """按栅格块计算每波段有限像元均值和标准差。

        Args:
            dataset: Rasterio 数据集或 WarpedVRT。

        Returns:
            list[dict[str, float]]: 逐波段统计。
        """
        counts = np.zeros(dataset.count, dtype="int64")
        sums = np.zeros(dataset.count, dtype="float64")
        squared_sums = np.zeros(dataset.count, dtype="float64")
        minimums = np.full(dataset.count, np.inf, dtype="float64")
        maximums = np.full(dataset.count, -np.inf, dtype="float64")
        for _, window in dataset.block_windows(1):
            block = dataset.read(window=window, masked=True)
            for band_index in range(dataset.count):
                values = block[band_index].compressed().astype("float64")
                values = values[np.isfinite(values)]
                if values.size == 0:
                    continue
                counts[band_index] += values.size
                sums[band_index] += values.sum(dtype="float64")
                squared_sums[band_index] += np.square(values).sum(dtype="float64")
                minimums[band_index] = min(minimums[band_index], values.min())
                maximums[band_index] = max(maximums[band_index], values.max())
        statistics = []
        for band_index in range(dataset.count):
            if counts[band_index] == 0:
                raise ValidationException(
                    f"镶嵌输入第 {band_index + 1} 波段没有有效像元"
                )
            mean = sums[band_index] / counts[band_index]
            variance = max(
                squared_sums[band_index] / counts[band_index] - mean**2,
                0,
            )
            statistics.append({
                "band": band_index + 1,
                "mean": float(mean),
                "std": float(np.sqrt(variance)),
                "min": float(minimums[band_index]),
                "max": float(maximums[band_index]),
            })
        return statistics

    @staticmethod
    def _aligned_bounds(
        datasets: list[WarpedVRT],
        resolution: float,
        required_bounds: tuple[float, float, float, float] | None = None,
    ) -> tuple[float, float, float, float, int, int]:
        """计算按目标分辨率对齐的完整并集网格。

        Args:
            datasets: 已统一目标 CRS 的虚拟数据集。
            resolution: 目标像元大小。
            required_bounds: 必须完整纳入验收网格的行政区边界。

        Returns:
            tuple: 对齐边界、宽度和高度。
        """
        left_values = [item.bounds.left for item in datasets]
        bottom_values = [item.bounds.bottom for item in datasets]
        right_values = [item.bounds.right for item in datasets]
        top_values = [item.bounds.top for item in datasets]
        if required_bounds is not None:
            left_values.append(required_bounds[0])
            bottom_values.append(required_bounds[1])
            right_values.append(required_bounds[2])
            top_values.append(required_bounds[3])
        left = floor(min(left_values) / resolution) * resolution
        bottom = (
            floor(min(bottom_values) / resolution) * resolution
        )
        right = ceil(max(right_values) / resolution) * resolution
        top = ceil(max(top_values) / resolution) * resolution
        width = int(round((right - left) / resolution))
        height = int(round((top - bottom) / resolution))
        return left, bottom, right, top, width, height

    @staticmethod
    def _geometry_bounds(
        geometry: dict[str, Any],
    ) -> tuple[float, float, float, float]:
        """递归读取 GeoJSON Polygon/MultiPolygon 坐标范围。

        Args:
            geometry: 目标 CRS 下的行政区几何。

        Returns:
            tuple[float, float, float, float]: 几何包围盒。
        """
        points: list[tuple[float, float]] = []

        def collect(value: Any) -> None:
            if (
                isinstance(value, list)
                and len(value) >= 2
                and isinstance(value[0], int | float)
                and isinstance(value[1], int | float)
            ):
                points.append((float(value[0]), float(value[1])))
                return
            if isinstance(value, list):
                for child in value:
                    collect(child)

        collect(geometry.get("coordinates"))
        if not points:
            raise ValidationException("行政区几何没有有效坐标")
        return (
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        )

    @staticmethod
    def _write_balanced_source(
        dataset: WarpedVRT,
        output_path: Path,
        source: MosaicSource,
        color_balance_method: str,
        reference_statistics: list[dict[str, float]],
    ) -> dict[str, Any]:
        """写出一个目标 CRS 下的可选全局均值/标准差匀色临时栅格。

        Args:
            dataset: 已重投影虚拟栅格。
            output_path: 临时 GeoTIFF 路径。
            source: 输入身份和校验值。
            color_balance_method: `none` 或 `mean_std`。
            reference_statistics: 首景参考统计。

        Returns:
            dict[str, Any]: 输入与参考统计和实际变换参数。
        """
        source_statistics = ImageryMosaicEngine._statistics(dataset)
        transforms = []
        if color_balance_method == "mean_std":
            for band_index, (source_stat, reference_stat) in enumerate(
                zip(source_statistics, reference_statistics, strict=True)
            ):
                source_std = source_stat["std"]
                reference_std = reference_stat["std"]
                if source_std <= 1e-12 or reference_std <= 1e-12:
                    raise ValidationException(
                        f"{source.asset_code} 第 {band_index + 1} 波段动态范围不足，"
                        "无法执行均值/标准差匀色"
                )
                scale = reference_std / source_std
                offset = reference_stat["mean"] - source_stat["mean"] * scale
                transforms.append({
                    "band": band_index + 1,
                    "scale": scale,
                    "offset": offset,
                })
        profile = {
            "driver": "GTiff",
            "width": dataset.width,
            "height": dataset.height,
            "count": dataset.count,
            "dtype": "float32",
            "crs": dataset.crs,
            "transform": dataset.transform,
            "nodata": np.nan,
            "compress": "deflate",
            "predictor": 3,
            "BIGTIFF": "IF_SAFER",
        }
        with rasterio.open(output_path, "w", **profile) as output:
            for _, window in dataset.block_windows(1):
                adjusted = dataset.read(
                    window=window,
                    masked=True,
                ).filled(np.nan).astype("float32")
                adjusted[~np.isfinite(adjusted)] = np.nan
                for band_index, parameters in enumerate(transforms):
                    adjusted[band_index] = (
                        adjusted[band_index] * parameters["scale"]
                        + parameters["offset"]
                    )
                output.write(adjusted, window=window)
            output.descriptions = dataset.descriptions
            output.update_tags(
                PROCESSING_STEP="mosaic_color_balance",
                SOURCE_ASSET_CODE=source.asset_code,
                SOURCE_STEP_CODE=source.step_code,
                SOURCE_SHA256=source.source_sha256,
                COLOR_BALANCE_METHOD=color_balance_method,
            )
        return {
            "method": color_balance_method,
            "source_statistics": source_statistics,
            "reference_statistics": reference_statistics,
            "transforms": transforms,
        }

    @staticmethod
    def _write_mosaic(
        datasets: list[rasterio.io.DatasetReader],
        output_path: Path,
        profile: dict[str, Any],
        output_transform: Any,
        projected_boundary: dict[str, Any],
        blend_method: str,
        resampling: Resampling,
    ) -> tuple[int, int]:
        """按输出窗口合成镶嵌并统计完整行政区覆盖像元。

        Args:
            datasets: 匀色后的临时栅格。
            output_path: 待写出的临时 GeoTIFF。
            profile: 输出栅格结构。
            output_transform: 对齐后的目标仿射变换。
            projected_boundary: 目标 CRS 下的真实行政区几何。
            blend_method: `first` 或 `mean`。
            resampling: 重采样方法。

        Returns:
            tuple[int, int]: 行政区总像元和有完整波段覆盖像元。
        """
        height = int(profile["height"])
        width = int(profile["width"])
        boundary_mask = rasterize(
            [(projected_boundary, 1)],
            out_shape=(height, width),
            transform=output_transform,
            fill=0,
            dtype="uint8",
            all_touched=False,
        ).astype(bool)
        boundary_pixel_count = int(boundary_mask.sum())
        if boundary_pixel_count <= 0:
            raise ValidationException("目标行政区与镶嵌输出网格没有像元交集")
        covered_pixel_count = 0
        with ExitStack() as stack:
            aligned_datasets = [
                stack.enter_context(WarpedVRT(
                    dataset,
                    crs=profile["crs"],
                    transform=output_transform,
                    width=width,
                    height=height,
                    resampling=resampling,
                    dtype="float32",
                    nodata=np.nan,
                ))
                for dataset in datasets
            ]
            with rasterio.open(output_path, "w", **profile) as output:
                for _, window in output.block_windows(1):
                    block_shape = (
                        int(profile["count"]),
                        int(window.height),
                        int(window.width),
                    )
                    if blend_method == "first":
                        result = np.full(block_shape, np.nan, dtype="float32")
                        for dataset in aligned_datasets:
                            source_block = dataset.read(
                                window=window,
                                masked=True,
                            ).filled(np.nan).astype("float32")
                            valid = np.isfinite(source_block)
                            fill_mask = ~np.isfinite(result) & valid
                            result[fill_mask] = source_block[fill_mask]
                    else:
                        sums = np.zeros(block_shape, dtype="float64")
                        counts = np.zeros(block_shape, dtype="uint16")
                        for dataset in aligned_datasets:
                            source_block = dataset.read(
                                window=window,
                                masked=True,
                            ).filled(np.nan).astype("float32")
                            valid = np.isfinite(source_block)
                            sums[valid] += source_block[valid]
                            counts[valid] += 1
                        result = np.full(block_shape, np.nan, dtype="float32")
                        np.divide(sums, counts, out=result, where=counts > 0)
                    output.write(result, window=window)
                    row_start = int(window.row_off)
                    row_end = row_start + int(window.height)
                    column_start = int(window.col_off)
                    column_end = column_start + int(window.width)
                    boundary_block = boundary_mask[
                        row_start:row_end,
                        column_start:column_end,
                    ]
                    valid_pixels = np.all(np.isfinite(result), axis=0)
                    covered_pixel_count += int((boundary_block & valid_pixels).sum())
        return boundary_pixel_count, covered_pixel_count

    def execute(
        self,
        sources: list[MosaicSource],
        output_path: Path,
        boundary_geometry: dict[str, Any],
        target_crs: str,
        target_resolution: float,
        color_balance_method: str,
        blend_method: str,
        resampling_method: str,
        coverage_threshold: float,
        job_code: str,
    ) -> MosaicExecutionResult:
        """执行完整多景生产并原子写出通过覆盖门禁的 GeoTIFF。

        Args:
            sources: 2–20 个已校验实体来源。
            output_path: 受控最终输出路径。
            boundary_geometry: EPSG:4326 真实行政区几何。
            target_crs: 目标 CRS。
            target_resolution: 目标像元大小。
            color_balance_method: 匀色方法。
            blend_method: 重叠合成方法。
            resampling_method: 重采样方法。
            coverage_threshold: 行政区像元覆盖率门槛。
            job_code: 镶嵌任务编号。

        Returns:
            MosaicExecutionResult: 结构、血缘和验收证据。
        """
        if not 2 <= len(sources) <= 20:
            raise ValidationException("镶嵌任务必须显式选择 2 到 20 个来源")
        if color_balance_method not in {"none", "mean_std"}:
            raise ValidationException("匀色方法仅支持 none 或 mean_std")
        if blend_method not in {"first", "mean"}:
            raise ValidationException("重叠合成仅支持 first 或 mean")
        resampling = self.resampling_methods.get(resampling_method)
        if resampling is None:
            raise ValidationException("重采样仅支持 nearest、bilinear 或 cubic")
        try:
            target_crs_value = CRS.from_string(target_crs)
        except rasterio.errors.CRSError as exc:
            raise ValidationException("镶嵌目标坐标系不合法") from exc
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = output_path.with_name(
            f".{output_path.stem}-{uuid4().hex}.tmp.tif"
        )
        projected_boundary = transform_geom(
            "EPSG:4326",
            target_crs_value,
            boundary_geometry,
            precision=12,
        )
        required_bounds = self._geometry_bounds(projected_boundary)
        try:
            with ExitStack() as stack:
                raw_datasets = [
                    stack.enter_context(rasterio.open(source.path))
                    for source in sources
                ]
                if any(dataset.crs is None for dataset in raw_datasets):
                    raise ValidationException("镶嵌输入必须先完成可验证空间校正")
                band_count = raw_datasets[0].count
                descriptions = list(raw_datasets[0].descriptions)
                for dataset in raw_datasets:
                    if dataset.count != band_count:
                        raise ValidationException("镶嵌输入波段数量不一致")
                    if list(dataset.descriptions) != descriptions:
                        raise ValidationException("镶嵌输入波段描述不一致")
                virtual_datasets = [
                    stack.enter_context(WarpedVRT(
                        dataset,
                        crs=target_crs_value,
                        resolution=target_resolution,
                        resampling=resampling,
                        dtype="float32",
                        nodata=np.nan,
                    ))
                    for dataset in raw_datasets
                ]
                left, _bottom, _right, top, width, height = self._aligned_bounds(
                    virtual_datasets,
                    target_resolution,
                    required_bounds,
                )
                pixel_count = width * height
                if width <= 0 or height <= 0:
                    raise ValidationException("镶嵌输出网格尺寸无效")
                if pixel_count > self.max_output_pixels:
                    raise ValidationException(
                        f"镶嵌输出预计 {pixel_count} 像元，超过上限 "
                        f"{self.max_output_pixels}；请缩小范围或降低分辨率"
                    )
                reference_statistics = self._statistics(virtual_datasets[0])
                with TemporaryDirectory(
                    prefix=f"mosaic-{job_code}-",
                    dir=output_path.parent,
                ) as temporary_dir:
                    balanced_paths = []
                    input_evidence = []
                    for index, (source, dataset) in enumerate(
                        zip(sources, virtual_datasets, strict=True),
                        start=1,
                    ):
                        balanced_path = Path(temporary_dir) / f"{index:02d}.tif"
                        balance_statistics = self._write_balanced_source(
                            dataset,
                            balanced_path,
                            source,
                            color_balance_method,
                            reference_statistics,
                        )
                        balanced_paths.append(balanced_path)
                        input_evidence.append(MosaicSourceEvidence(
                            source=source,
                            crs=dataset.crs.to_string(),
                            width=dataset.width,
                            height=dataset.height,
                            band_count=dataset.count,
                            band_descriptions=list(dataset.descriptions),
                            balance_statistics=balance_statistics,
                        ))
                    with ExitStack() as balanced_stack:
                        balanced_datasets = [
                            balanced_stack.enter_context(rasterio.open(path))
                            for path in balanced_paths
                        ]
                        output_transform = rasterio.transform.from_origin(
                            left,
                            top,
                            target_resolution,
                            target_resolution,
                        )
                        profile = {
                            "driver": "GTiff",
                            "width": width,
                            "height": height,
                            "count": band_count,
                            "dtype": "float32",
                            "crs": target_crs_value,
                            "transform": output_transform,
                            "nodata": np.nan,
                            "compress": "deflate",
                            "predictor": 3,
                            "BIGTIFF": "IF_SAFER",
                        }
                        (
                            boundary_pixel_count,
                            covered_pixel_count,
                        ) = self._write_mosaic(
                            balanced_datasets,
                            temporary_output,
                            profile,
                            output_transform,
                            projected_boundary,
                            blend_method,
                            resampling,
                        )
                coverage_ratio = round(
                    covered_pixel_count / boundary_pixel_count * 100,
                    3,
                )
                if coverage_ratio < coverage_threshold:
                    raise ValidationException(
                        f"镶嵌行政区覆盖率 {coverage_ratio:.3f}% 低于门槛 "
                        f"{coverage_threshold:.3f}%"
                    )
                with rasterio.open(temporary_output, "r+") as output:
                    output.descriptions = descriptions
                    output.update_tags(
                        PROCESSING_STEP="imagery_mosaic",
                        MOSAIC_JOB_CODE=job_code,
                        COLOR_BALANCE_METHOD=color_balance_method,
                        BLEND_METHOD=blend_method,
                        COVERAGE_RATIO=f"{coverage_ratio:.3f}",
                        COVERAGE_THRESHOLD=f"{coverage_threshold:.3f}",
                    )
                output_bounds = array_bounds(height, width, output_transform)
                bounds_wgs84 = transform_bounds(
                    target_crs_value,
                    "EPSG:4326",
                    *output_bounds,
                    densify_pts=21,
                )
                manifest = {
                    "processor_name": self.processor_name,
                    "processor_version": self.processor_version,
                    "target_crs": target_crs_value.to_string(),
                    "target_resolution": target_resolution,
                    "color_balance_method": color_balance_method,
                    "blend_method": blend_method,
                    "resampling_method": resampling_method,
                    "coverage_threshold": coverage_threshold,
                    "coverage_ratio": coverage_ratio,
                    "output_pixel_count": pixel_count,
                    "max_output_pixels": self.max_output_pixels,
                }
                result = MosaicExecutionResult(
                    width=width,
                    height=height,
                    band_count=band_count,
                    dtype="float32",
                    crs=target_crs_value.to_string(),
                    bounds_wgs84=[float(value) for value in bounds_wgs84],
                    boundary_pixel_count=boundary_pixel_count,
                    covered_pixel_count=covered_pixel_count,
                    coverage_ratio=coverage_ratio,
                    inputs=input_evidence,
                    manifest=manifest,
                )
            os.replace(temporary_output, output_path)
            return result
        finally:
            temporary_output.unlink(missing_ok=True)
