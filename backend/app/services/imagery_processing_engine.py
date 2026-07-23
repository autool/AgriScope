"""基于 Rasterio 的受控影像预处理执行引擎。"""

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from math import hypot, isfinite
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import rasterio
from rasterio.control import GroundControlPoint
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError, WindowError
from rasterio.features import geometry_window
from rasterio.mask import mask
from rasterio.transform import from_gcps
from rasterio.warp import (
    calculate_default_transform,
    reproject,
    transform,
    transform_geom,
)

from app.core.exceptions import ValidationException


@dataclass(frozen=True)
class ProcessingExecutionResult:
    """内置处理器输出的可审计栅格信息。"""

    parameters: dict[str, Any]
    width: int
    height: int
    band_count: int
    dtype: str
    crs: str


class ImageryProcessingEngine:
    """执行参数明确、可重复的基础遥感栅格处理步骤。"""

    processor_name = "平台内置 Rasterio 处理器"
    processor_version = rasterio.__version__

    resampling_methods = {
        "nearest": Resampling.nearest,
        "bilinear": Resampling.bilinear,
        "cubic": Resampling.cubic,
    }

    @staticmethod
    def _copy_source_tags(
        source: rasterio.io.DatasetReader,
        output: rasterio.io.DatasetWriter,
        *,
        excluded_namespaces: set[str] | None = None,
    ) -> None:
        """复制来源标签和命名空间，保持产品血缘与 RPC 模型。

        Args:
            source: 上游栅格。
            output: 当前输出栅格。
            excluded_namespaces: 不应继续传播的标签命名空间。

        Returns:
            None: 无返回值。
        """
        output.update_tags(**source.tags())
        excluded = excluded_namespaces or set()
        for namespace in source.tag_namespaces():
            if not namespace or namespace in excluded:
                continue
            namespace_tags = source.tags(ns=namespace)
            if namespace_tags:
                output.update_tags(ns=namespace, **namespace_tags)

    @staticmethod
    def _number(
        parameters: dict[str, Any],
        key: str,
        default: float,
        minimum: float,
        maximum: float,
    ) -> float:
        """读取并限制数值处理参数。

        Args:
            parameters: 用户提交的步骤参数。
            key: 参数名称。
            default: 缺省值。
            minimum: 允许的最小值。
            maximum: 允许的最大值。

        Returns:
            float: 已通过范围校验的数值。
        """
        raw_value = parameters.get(key, default)
        if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
            raise ValidationException(f"处理参数 {key} 必须为数值")
        value = float(raw_value)
        if not minimum <= value <= maximum:
            raise ValidationException(
                f"处理参数 {key} 必须位于 {minimum} 到 {maximum} 之间"
            )
        return value

    @staticmethod
    def _band_index(
        parameters: dict[str, Any],
        key: str,
        default: int,
        band_count: int,
    ) -> int:
        """读取并校验一基波段编号。

        Args:
            parameters: 用户提交的步骤参数。
            key: 波段参数名称。
            default: 默认波段编号。
            band_count: 输入影像总波段数。

        Returns:
            int: 合法的一基波段编号。
        """
        raw_value = parameters.get(key, default)
        if isinstance(raw_value, bool) or not isinstance(raw_value, int):
            raise ValidationException(f"处理参数 {key} 必须为整数波段编号")
        if not 1 <= raw_value <= band_count:
            raise ValidationException(
                f"处理参数 {key} 超出输入影像的 {band_count} 个波段"
            )
        return raw_value

    @staticmethod
    def _output_profile(source: rasterio.io.DatasetReader) -> dict[str, Any]:
        """构造统一的 GeoTIFF 输出配置。

        Args:
            source: 输入栅格数据集。

        Returns:
            dict[str, Any]: 可供 Rasterio 写出的基础配置。
        """
        profile = source.profile.copy()
        profile.update(driver="GTiff", compress="deflate", BIGTIFF="IF_SAFER")
        return profile

    def _radiometric(
        self,
        source: rasterio.io.DatasetReader,
        output_path: Path,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """按显式比例系数和偏移量将 DN 转换为浮点反射率。

        Args:
            source: 输入栅格。
            output_path: 临时输出路径。
            parameters: `scale_factor` 与 `add_offset` 参数。

        Returns:
            dict[str, Any]: 实际执行参数。
        """
        scale_factor = self._number(parameters, "scale_factor", 0.0001, 1e-12, 10)
        add_offset = self._number(parameters, "add_offset", 0, -1000, 1000)
        data = source.read().astype("float32")
        data = data * scale_factor + add_offset
        profile = self._output_profile(source)
        profile.update(dtype="float32", nodata=None)
        with rasterio.open(output_path, "w", **profile) as output:
            output.write(data)
            output.descriptions = source.descriptions
            self._copy_source_tags(source, output)
            output.update_tags(
                PROCESSING_STEP="radiometric",
                SCALE_FACTOR=str(scale_factor),
                ADD_OFFSET=str(add_offset),
            )
        return {"scale_factor": scale_factor, "add_offset": add_offset}

    def _atmospheric(
        self,
        source: rasterio.io.DatasetReader,
        output_path: Path,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """执行可复现的 DOS1 暗目标大气校正。

        Args:
            source: 上一步反射率栅格。
            output_path: 临时输出路径。
            parameters: `dark_percentile` 参数。

        Returns:
            dict[str, Any]: 暗目标百分位和各波段扣除值。
        """
        dark_percentile = self._number(
            parameters,
            "dark_percentile",
            1,
            0,
            10,
        )
        data = source.read(masked=True).astype("float32")
        corrected = np.zeros(data.shape, dtype="float32")
        dark_values: list[float] = []
        for index in range(source.count):
            band = data[index]
            valid_values = band.compressed()
            if valid_values.size == 0:
                raise ValidationException(f"第 {index + 1} 波段没有有效像元")
            dark_value = float(np.percentile(valid_values, dark_percentile))
            dark_values.append(dark_value)
            corrected[index] = np.maximum(band.filled(dark_value) - dark_value, 0)
        profile = self._output_profile(source)
        profile.update(dtype="float32", nodata=None)
        with rasterio.open(output_path, "w", **profile) as output:
            output.write(corrected)
            output.descriptions = source.descriptions
            self._copy_source_tags(source, output)
            output.update_tags(
                PROCESSING_STEP="atmospheric",
                ATMOSPHERIC_MODEL="DOS1",
                DARK_PERCENTILE=str(dark_percentile),
            )
        return {
            "model": "DOS1",
            "dark_percentile": dark_percentile,
            "dark_values": dark_values,
        }

    def _geometric(
        self,
        source: rasterio.io.DatasetReader,
        output_path: Path,
        parameters: dict[str, Any],
        rpc_dem_path: Path | None,
        dem_evidence: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """执行普通重投影或基于地面控制点的仿射精校正。

        Args:
            source: 输入栅格。
            output_path: 临时输出路径。
            parameters: 目标坐标系、重采样方法及可选 GCP 参数。

        Returns:
            dict[str, Any]: 实际目标坐标系、尺寸和分辨率。
        """
        method = str(parameters.get("method") or "reproject").strip().lower()
        if method not in {"reproject", "gcp", "rpc_dem"}:
            raise ValidationException(
                "几何校正方法仅支持 reproject、gcp 或 rpc_dem"
            )
        target_crs = str(parameters.get("target_crs") or "EPSG:4490").strip()
        if not target_crs:
            raise ValidationException("几何校正必须指定目标坐标系")
        try:
            target_crs_value = CRS.from_string(target_crs)
        except rasterio.errors.CRSError as exc:
            raise ValidationException("几何校正目标坐标系不合法") from exc
        resampling_code = str(
            parameters.get("resampling") or "bilinear"
        ).strip().lower()
        resampling = self.resampling_methods.get(resampling_code)
        if resampling is None:
            raise ValidationException("重采样方法仅支持 nearest、bilinear 或 cubic")
        raw_resolution = parameters.get("target_resolution")
        resolution = None
        if raw_resolution is not None:
            resolution = self._number(
                parameters,
                "target_resolution",
                0,
                1e-12,
                1_000_000,
            )
        if method == "gcp":
            return self._geometric_with_gcps(
                source,
                output_path,
                parameters,
                target_crs_value,
                resolution,
                resampling_code,
                resampling,
            )
        if method == "rpc_dem":
            return self._geometric_with_rpc_dem(
                source,
                output_path,
                parameters,
                target_crs_value,
                resolution,
                resampling_code,
                resampling,
                rpc_dem_path,
                dem_evidence,
            )
        if source.crs is None:
            raise ValidationException("普通重投影要求上游影像具有 CRS")
        try:
            output_transform, width, height = calculate_default_transform(
                source.crs,
                target_crs_value,
                source.width,
                source.height,
                *source.bounds,
                resolution=resolution,
            )
        except (ValueError, RasterioIOError) as exc:
            raise ValidationException("目标坐标系或分辨率无法用于重投影") from exc
        profile = self._output_profile(source)
        profile.update(
            crs=target_crs_value,
            transform=output_transform,
            width=width,
            height=height,
        )
        with rasterio.open(output_path, "w", **profile) as output:
            for band_index in range(1, source.count + 1):
                reproject(
                    source=rasterio.band(source, band_index),
                    destination=rasterio.band(output, band_index),
                    src_transform=source.transform,
                    src_crs=source.crs,
                    dst_transform=output_transform,
                    dst_crs=target_crs_value,
                    resampling=resampling,
                )
            output.descriptions = source.descriptions
            self._copy_source_tags(source, output, excluded_namespaces={"RPC"})
            output.update_tags(
                PROCESSING_STEP="geometric",
                GEOMETRIC_METHOD="reproject",
                TARGET_CRS=target_crs_value.to_string(),
                RESAMPLING=resampling_code,
            )
        return {
            "method": f"reproject_{resampling_code}",
            "target_crs": target_crs_value.to_string(),
            "target_resolution": resolution,
            "resampling": resampling_code,
            "width": width,
            "height": height,
        }

    @staticmethod
    def _control_point_number(
        raw_point: dict[str, Any],
        key: str,
        point_id: str,
    ) -> float:
        """读取控制点有限数值字段。

        Args:
            raw_point: 原始控制点对象。
            key: 数值字段名。
            point_id: 控制点编号。

        Returns:
            float: 合法有限数值。
        """
        raw_value = raw_point.get(key)
        if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
            raise ValidationException(f"控制点 {point_id} 的 {key} 必须为数值")
        value = float(raw_value)
        if not isfinite(value):
            raise ValidationException(f"控制点 {point_id} 的 {key} 必须为有限数值")
        return value

    @staticmethod
    def _require_non_collinear(
        coordinates: Sequence[tuple[float, float]],
        label: str,
    ) -> None:
        """校验二维控制点集合具有可解算的两个方向。

        Args:
            coordinates: 二维坐标集合。
            label: 错误提示中的坐标类型。

        Returns:
            None: 校验通过无返回值。
        """
        matrix = np.asarray(coordinates, dtype="float64")
        centered = matrix - matrix.mean(axis=0)
        if np.linalg.matrix_rank(centered) < 2:
            raise ValidationException(f"GCP {label}不能全部共线")

    def _parse_gcps(
        self,
        source: rasterio.io.DatasetReader,
        parameters: dict[str, Any],
    ) -> tuple[list[GroundControlPoint], list[dict[str, Any]], CRS, float]:
        """解析并校验 GCP 点位、来源和残差门槛。

        Args:
            source: 输入栅格。
            parameters: GCP 几何校正参数。

        Returns:
            tuple: Rasterio 控制点、可审计点位、GCP CRS 和 RMSE 门槛。
        """
        raw_points = parameters.get("control_points")
        if not isinstance(raw_points, list) or not 3 <= len(raw_points) <= 100:
            raise ValidationException("GCP 精校正必须提供 3 到 100 个控制点")
        gcp_crs_text = str(parameters.get("gcp_crs") or "EPSG:4326").strip()
        try:
            gcp_crs = CRS.from_string(gcp_crs_text)
        except rasterio.errors.CRSError as exc:
            raise ValidationException("GCP 坐标系不合法") from exc
        max_rmse_pixels = self._number(
            parameters,
            "max_rmse_pixels",
            2,
            0,
            100,
        )
        parsed: list[dict[str, Any]] = []
        gcps: list[GroundControlPoint] = []
        point_ids: set[str] = set()
        image_positions: set[tuple[float, float]] = set()
        ground_positions: set[tuple[float, float]] = set()
        for index, raw_point in enumerate(raw_points, start=1):
            if not isinstance(raw_point, dict):
                raise ValidationException(f"第 {index} 个 GCP 必须为对象")
            point_id = str(raw_point.get("point_id") or f"GCP-{index}").strip()
            source_name = str(raw_point.get("source") or "").strip()
            if not point_id or len(point_id) > 80:
                raise ValidationException(f"第 {index} 个 GCP 编号不合法")
            if point_id in point_ids:
                raise ValidationException(f"GCP 编号 {point_id} 重复")
            if not source_name or len(source_name) > 200:
                raise ValidationException(f"控制点 {point_id} 必须填写真实来源")
            column = self._control_point_number(raw_point, "pixel_column", point_id)
            row = self._control_point_number(raw_point, "pixel_row", point_id)
            x = self._control_point_number(raw_point, "x", point_id)
            y = self._control_point_number(raw_point, "y", point_id)
            z = (
                self._control_point_number(raw_point, "z", point_id)
                if raw_point.get("z") is not None
                else 0.0
            )
            if not 0 <= column <= source.width - 1 or not 0 <= row <= source.height - 1:
                raise ValidationException(f"控制点 {point_id} 超出影像像素范围")
            image_position = (column, row)
            ground_position = (x, y)
            if image_position in image_positions:
                raise ValidationException(f"控制点 {point_id} 的像素位置重复")
            if ground_position in ground_positions:
                raise ValidationException(f"控制点 {point_id} 的地面坐标重复")
            point_ids.add(point_id)
            image_positions.add(image_position)
            ground_positions.add(ground_position)
            parsed.append({
                "point_id": point_id,
                "pixel_column": column,
                "pixel_row": row,
                "x": x,
                "y": y,
                "z": z,
                "source": source_name,
            })
            gcps.append(
                GroundControlPoint(
                    row=row,
                    col=column,
                    x=x,
                    y=y,
                    z=z,
                    id=point_id,
                    info=source_name,
                )
            )
        self._require_non_collinear(list(image_positions), "像素坐标")
        self._require_non_collinear(list(ground_positions), "地面坐标")
        return gcps, parsed, gcp_crs, max_rmse_pixels

    @staticmethod
    def _gcp_residuals(
        gcps: Sequence[GroundControlPoint],
        gcp_crs: CRS,
        target_crs: CRS,
    ) -> tuple[list[float], float, float]:
        """以目标网格仿射拟合计算每个 GCP 的像素残差。

        Args:
            gcps: 已校验控制点。
            gcp_crs: 控制点坐标系。
            target_crs: 输出坐标系。

        Returns:
            tuple: 单点像素残差、RMSE 和最大残差。
        """
        projected_x, projected_y = transform(
            gcp_crs,
            target_crs,
            [point.x for point in gcps],
            [point.y for point in gcps],
        )
        projected_gcps = [
            GroundControlPoint(
                row=point.row,
                col=point.col,
                x=x,
                y=y,
                z=point.z,
                id=point.id,
                info=point.info,
            )
            for point, x, y in zip(gcps, projected_x, projected_y, strict=True)
        ]
        fitted_transform = from_gcps(projected_gcps)
        inverse_transform = ~fitted_transform
        residuals = []
        for point in projected_gcps:
            predicted_column, predicted_row = inverse_transform * (point.x, point.y)
            residuals.append(
                hypot(predicted_column - point.col, predicted_row - point.row)
            )
        rmse = float(np.sqrt(np.mean(np.square(residuals))))
        return residuals, rmse, max(residuals)

    def _geometric_with_gcps(
        self,
        source: rasterio.io.DatasetReader,
        output_path: Path,
        parameters: dict[str, Any],
        target_crs: CRS,
        resolution: float | None,
        resampling_code: str,
        resampling: Resampling,
    ) -> dict[str, Any]:
        """使用真实 GCP 解算一阶仿射几何精校正。

        Args:
            source: 输入栅格。
            output_path: 临时输出路径。
            parameters: GCP、坐标系、残差门槛和重采样参数。
            target_crs: 输出坐标系。
            resolution: 可选输出分辨率。
            resampling_code: 重采样编码。
            resampling: Rasterio 重采样枚举。

        Returns:
            dict[str, Any]: 控制点、残差和输出网格证据。
        """
        gcps, parsed_points, gcp_crs, max_rmse_pixels = self._parse_gcps(
            source,
            parameters,
        )
        residuals, rmse_pixels, maximum_residual_pixels = self._gcp_residuals(
            gcps,
            gcp_crs,
            target_crs,
        )
        if rmse_pixels > max_rmse_pixels:
            raise ValidationException(
                f"GCP 像素残差 RMSE {rmse_pixels:.4f} 超过门槛 "
                f"{max_rmse_pixels:.4f}"
            )
        try:
            output_transform, width, height = calculate_default_transform(
                gcp_crs,
                target_crs,
                source.width,
                source.height,
                gcps=gcps,
                resolution=resolution,
                MAX_GCP_ORDER=1,
            )
        except (ValueError, RasterioIOError) as exc:
            raise ValidationException("GCP 无法解算目标像元网格") from exc
        profile = self._output_profile(source)
        profile.update(
            crs=target_crs,
            transform=output_transform,
            width=width,
            height=height,
        )
        with rasterio.open(output_path, "w", **profile) as output:
            for band_index in range(1, source.count + 1):
                reproject(
                    source=rasterio.band(source, band_index),
                    destination=rasterio.band(output, band_index),
                    gcps=gcps,
                    src_crs=gcp_crs,
                    dst_transform=output_transform,
                    dst_crs=target_crs,
                    resampling=resampling,
                    MAX_GCP_ORDER=1,
                )
            output.descriptions = source.descriptions
            self._copy_source_tags(source, output, excluded_namespaces={"RPC"})
            output.update_tags(
                PROCESSING_STEP="geometric",
                GEOMETRIC_METHOD="gcp_affine",
                GCP_CRS=gcp_crs.to_string(),
                GCP_COUNT=str(len(gcps)),
                GCP_RMSE_PIXELS=f"{rmse_pixels:.8f}",
                GCP_MAX_RESIDUAL_PIXELS=f"{maximum_residual_pixels:.8f}",
                TARGET_CRS=target_crs.to_string(),
                RESAMPLING=resampling_code,
            )
        point_evidence = [
            {**point, "residual_pixels": residual}
            for point, residual in zip(parsed_points, residuals, strict=True)
        ]
        return {
            "method": "gcp_affine",
            "polynomial_order": 1,
            "gcp_crs": gcp_crs.to_string(),
            "target_crs": target_crs.to_string(),
            "target_resolution": resolution,
            "resampling": resampling_code,
            "gcp_count": len(gcps),
            "rmse_pixels": rmse_pixels,
            "maximum_residual_pixels": maximum_residual_pixels,
            "max_rmse_pixels": max_rmse_pixels,
            "control_points": point_evidence,
            "width": width,
            "height": height,
        }

    def _geometric_with_rpc_dem(
        self,
        source: rasterio.io.DatasetReader,
        output_path: Path,
        parameters: dict[str, Any],
        target_crs: CRS,
        resolution: float | None,
        resampling_code: str,
        resampling: Resampling,
        rpc_dem_path: Path | None,
        dem_evidence: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """使用影像内嵌 RPC 与受控 DEM 执行严格正射纠正。

        Args:
            source: 带 RPC 模型的原始或上游栅格。
            output_path: 临时输出路径。
            parameters: 目标网格及正射参数。
            target_crs: 输出坐标系。
            resolution: 可选输出分辨率。
            resampling_code: 重采样编码。
            resampling: Rasterio 重采样枚举。
            rpc_dem_path: 已由业务层校验的受控 DEM 实体。
            dem_evidence: DEM 大小、SHA-256、范围和结构证据。

        Returns:
            dict[str, Any]: RPC、DEM 和输出网格执行证据。
        """
        rpc_model = source.rpcs
        if rpc_model is None:
            raise ValidationException("RPC/DEM 正射要求源影像内嵌 RPC 模型")
        if rpc_dem_path is None or not rpc_dem_path.is_file() or not dem_evidence:
            raise ValidationException("RPC/DEM 正射缺少已校验受控 DEM")
        height_offset = self._number(
            parameters,
            "rpc_height_offset_m",
            0,
            -10_000,
            10_000,
        )
        rpc_options: dict[str, str | float] = {
            "RPC_DEM": str(rpc_dem_path),
            "RPC_HEIGHT": height_offset,
        }
        try:
            output_transform, width, height = calculate_default_transform(
                "EPSG:4326",
                target_crs,
                source.width,
                source.height,
                rpcs=rpc_model,
                resolution=resolution,
                **rpc_options,
            )
        except (ValueError, RasterioIOError) as exc:
            raise ValidationException("RPC 模型与 DEM 无法解算正射输出网格") from exc
        profile = self._output_profile(source)
        profile.update(
            crs=target_crs,
            transform=output_transform,
            width=width,
            height=height,
        )
        with rasterio.open(output_path, "w", **profile) as output:
            for band_index in range(1, source.count + 1):
                reproject(
                    source=rasterio.band(source, band_index),
                    destination=rasterio.band(output, band_index),
                    rpcs=rpc_model,
                    src_crs="EPSG:4326",
                    dst_transform=output_transform,
                    dst_crs=target_crs,
                    resampling=resampling,
                    **rpc_options,
                )
            output.descriptions = source.descriptions
            self._copy_source_tags(source, output, excluded_namespaces={"RPC"})
            output.update_tags(
                PROCESSING_STEP="geometric",
                GEOMETRIC_METHOD="rpc_dem_orthorectification",
                RPC_DEM_SHA256=str(dem_evidence["checksum_sha256"]),
                RPC_HEIGHT_OFFSET_M=str(height_offset),
                TARGET_CRS=target_crs.to_string(),
                RESAMPLING=resampling_code,
                ORTHORECTIFIED="true",
            )
        rpc_payload = rpc_model.to_gdal()
        rpc_checksum = hashlib.sha256(
            json.dumps(rpc_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "method": "rpc_dem_orthorectification",
            "target_crs": target_crs.to_string(),
            "target_resolution": resolution,
            "resampling": resampling_code,
            "rpc_height_offset_m": height_offset,
            "rpc_checksum_sha256": rpc_checksum,
            "rpc_error_bias": rpc_model.err_bias,
            "rpc_error_random": rpc_model.err_rand,
            "rpc_normalization": {
                "longitude_offset": rpc_model.long_off,
                "longitude_scale": rpc_model.long_scale,
                "latitude_offset": rpc_model.lat_off,
                "latitude_scale": rpc_model.lat_scale,
                "height_offset": rpc_model.height_off,
                "height_scale": rpc_model.height_scale,
            },
            "dem_evidence": dem_evidence,
            "width": width,
            "height": height,
        }

    def _clip(
        self,
        source: rasterio.io.DatasetReader,
        output_path: Path,
        parameters: dict[str, Any],
        boundary_geometry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """按数据库中的真实行政区边界裁剪影像。

        Args:
            source: 输入栅格。
            output_path: 临时输出路径。
            parameters: 包含 `boundary_code` 的参数。
            boundary_geometry: EPSG:4326 行政区 GeoJSON 几何。

        Returns:
            dict[str, Any]: 裁剪边界和输出尺寸。
        """
        boundary_code = str(parameters.get("boundary_code") or "").strip()
        if not boundary_code or boundary_geometry is None:
            raise ValidationException("行政区裁剪必须选择真实边界编码")
        try:
            projected_geometry = transform_geom(
                "EPSG:4326",
                source.crs,
                boundary_geometry,
                precision=12,
            )
            clipped, transform = mask(
                source,
                [projected_geometry],
                crop=True,
                all_touched=False,
            )
        except (ValueError, RasterioIOError) as exc:
            raise ValidationException("行政区边界与当前影像没有可裁剪交集") from exc
        profile = self._output_profile(source)
        profile.update(
            height=clipped.shape[1],
            width=clipped.shape[2],
            transform=transform,
        )
        with rasterio.open(output_path, "w", **profile) as output:
            output.write(clipped)
            output.descriptions = source.descriptions
            self._copy_source_tags(source, output)
            output.update_tags(
                PROCESSING_STEP="clip",
                BOUNDARY_CODE=boundary_code,
            )
        return {
            "boundary_code": boundary_code,
            "width": clipped.shape[2],
            "height": clipped.shape[1],
        }

    def _enhancement(
        self,
        source: rasterio.io.DatasetReader,
        output_path: Path,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """执行百分位对比度拉伸或逐波段直方图均衡化。

        Args:
            source: 已完成裁剪或几何校正的上游栅格。
            output_path: 临时输出路径。
            parameters: 增强方法、百分位或直方图分箱数。

        Returns:
            dict[str, Any]: 每波段输入范围和实际增强参数。
        """
        method = str(
            parameters.get("method") or "percentile_stretch"
        ).strip().lower()
        if method not in {"percentile_stretch", "histogram_equalization"}:
            raise ValidationException(
                "影像增强仅支持 percentile_stretch 或 histogram_equalization"
            )
        lower_percentile = self._number(
            parameters,
            "lower_percentile",
            2,
            0,
            49.999,
        )
        upper_percentile = self._number(
            parameters,
            "upper_percentile",
            98,
            50.001,
            100,
        )
        if lower_percentile >= upper_percentile:
            raise ValidationException("拉伸下限百分位必须小于上限百分位")
        raw_bins = parameters.get("histogram_bins", 256)
        if isinstance(raw_bins, bool) or not isinstance(raw_bins, int):
            raise ValidationException("直方图分箱数必须为整数")
        if not 32 <= raw_bins <= 4096:
            raise ValidationException("直方图分箱数必须位于 32 到 4096 之间")
        data = source.read(masked=True).astype("float32")
        enhanced = np.full(data.shape, np.nan, dtype="float32")
        band_evidence: list[dict[str, float | int]] = []
        for index in range(source.count):
            band = data[index]
            mask_array = np.ma.getmaskarray(band)
            valid_values = band.compressed()
            if valid_values.size == 0:
                raise ValidationException(f"第 {index + 1} 波段没有有效像元")
            input_min = float(valid_values.min())
            input_max = float(valid_values.max())
            if input_max <= input_min:
                raise ValidationException(f"第 {index + 1} 波段没有可增强动态范围")
            if method == "percentile_stretch":
                lower_value = float(
                    np.percentile(valid_values, lower_percentile)
                )
                upper_value = float(
                    np.percentile(valid_values, upper_percentile)
                )
                if upper_value <= lower_value:
                    raise ValidationException(
                        f"第 {index + 1} 波段百分位范围无法拉伸"
                    )
                normalized = np.clip(
                    (band.filled(lower_value) - lower_value)
                    / (upper_value - lower_value),
                    0,
                    1,
                )
                band_evidence.append({
                    "band": index + 1,
                    "input_min": input_min,
                    "input_max": input_max,
                    "lower_value": lower_value,
                    "upper_value": upper_value,
                })
            else:
                histogram, bin_edges = np.histogram(
                    valid_values,
                    bins=raw_bins,
                    range=(input_min, input_max),
                )
                cumulative = histogram.cumsum().astype("float64")
                nonzero = cumulative[cumulative > 0]
                if nonzero.size == 0 or cumulative[-1] <= nonzero[0]:
                    raise ValidationException(
                        f"第 {index + 1} 波段直方图无法均衡化"
                    )
                normalized_cdf = (cumulative - nonzero[0]) / (
                    cumulative[-1] - nonzero[0]
                )
                normalized = np.interp(
                    band.filled(input_min),
                    bin_edges[:-1],
                    normalized_cdf,
                )
                normalized = np.clip(normalized, 0, 1)
                band_evidence.append({
                    "band": index + 1,
                    "input_min": input_min,
                    "input_max": input_max,
                    "histogram_bins": raw_bins,
                })
            normalized = np.asarray(normalized, dtype="float32")
            normalized[mask_array] = np.nan
            enhanced[index] = normalized
        profile = self._output_profile(source)
        profile.update(dtype="float32", nodata=np.nan, predictor=3)
        with rasterio.open(output_path, "w", **profile) as output:
            output.write(enhanced)
            output.descriptions = source.descriptions
            self._copy_source_tags(source, output)
            output.update_tags(
                PROCESSING_STEP="enhancement",
                ENHANCEMENT_METHOD=method,
                OUTPUT_RANGE="0,1",
            )
        return {
            "method": method,
            "lower_percentile": (
                lower_percentile if method == "percentile_stretch" else None
            ),
            "upper_percentile": (
                upper_percentile if method == "percentile_stretch" else None
            ),
            "histogram_bins": (
                raw_bins if method == "histogram_equalization" else None
            ),
            "output_range": [0, 1],
            "bands": band_evidence,
        }

    def _band_products(
        self,
        source: rasterio.io.DatasetReader,
        output_path: Path,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """生成真彩色、标准假彩色和 NDVI 七波段产品栈。

        Args:
            source: 至少四波段的输入栅格。
            output_path: 临时输出路径。
            parameters: 红、绿、蓝、近红外波段编号。

        Returns:
            dict[str, Any]: 波段映射和产品清单。
        """
        if source.count < 4:
            raise ValidationException("波段产品至少需要四波段影像")
        red_index = self._band_index(parameters, "red_band", 1, source.count)
        green_index = self._band_index(parameters, "green_band", 2, source.count)
        blue_index = self._band_index(parameters, "blue_band", 3, source.count)
        nir_index = self._band_index(parameters, "nir_band", 4, source.count)
        selected_indexes = {red_index, green_index, blue_index, nir_index}
        if len(selected_indexes) != 4:
            raise ValidationException("红、绿、蓝和近红外必须选择四个不同波段")
        source_bands = source.read(masked=True).astype("float32").filled(np.nan)
        red = source_bands[red_index - 1]
        green = source_bands[green_index - 1]
        blue = source_bands[blue_index - 1]
        nir = source_bands[nir_index - 1]
        denominator = nir + red
        valid_ndvi = (
            np.isfinite(red)
            & np.isfinite(nir)
            & (red >= 0)
            & (nir >= 0)
            & (denominator > 1e-12)
        )
        ndvi = np.divide(
            nir - red,
            denominator,
            out=np.full_like(denominator, np.nan, dtype="float32"),
            where=valid_ndvi,
        )
        ndvi = np.clip(ndvi, -1, 1)
        product_stack = np.stack(
            [red, green, blue, nir, red, green, ndvi],
        ).astype("float32")
        descriptions = (
            "true_color_red",
            "true_color_green",
            "true_color_blue",
            "false_color_nir",
            "false_color_red",
            "false_color_green",
            "ndvi",
        )
        profile = self._output_profile(source)
        profile.update(count=7, dtype="float32", nodata=np.nan, predictor=3)
        with rasterio.open(output_path, "w", **profile) as output:
            output.write(product_stack)
            output.descriptions = descriptions
            self._copy_source_tags(source, output)
            output.update_tags(
                PROCESSING_STEP="band_products",
                PRODUCTS="true_color,false_color,NDVI",
            )
        return {
            "products": ["true_color", "false_color", "NDVI"],
            "red_band": red_index,
            "green_band": green_index,
            "blue_band": blue_index,
            "nir_band": nir_index,
            "output_band_descriptions": list(descriptions),
        }

    def validate_batch_parameters(
        self,
        step_code: str,
        source_path: Path,
        parameters: dict[str, Any],
        boundary_geometry: dict[str, Any] | None = None,
    ) -> None:
        """在多景批次写出任何产物前校验当前成员参数。

        批量几何处理只允许统一坐标系重投影；每景独立 GCP 控制网和 RPC/DEM
        正射继续使用单景流程，避免把不同模型隐藏在一个公共批次参数中。

        Args:
            step_code: 标准处理步骤编码。
            source_path: 已通过业务层实体校验的上游栅格。
            parameters: 当前成员明确提交的算法参数。
            boundary_geometry: 裁剪使用的 WGS84 行政区几何。

        Returns:
            None: 参数与源栅格结构均可执行时返回。
        """
        try:
            with rasterio.open(source_path) as source:
                if step_code == "radiometric":
                    self._number(parameters, "scale_factor", 0.0001, 1e-12, 10)
                    self._number(parameters, "add_offset", 0, -1000, 1000)
                    return
                if step_code == "atmospheric":
                    self._number(parameters, "dark_percentile", 1, 0, 10)
                    return
                if step_code == "geometric":
                    method = str(
                        parameters.get("method") or "reproject"
                    ).strip().lower()
                    if method != "reproject":
                        raise ValidationException(
                            "多景几何批处理只支持统一坐标系重投影；"
                            "GCP 或 RPC/DEM 请使用单景流程"
                        )
                    if source.crs is None:
                        raise ValidationException("普通重投影要求上游影像具有 CRS")
                    target_crs = str(
                        parameters.get("target_crs") or "EPSG:4490"
                    ).strip()
                    if not target_crs:
                        raise ValidationException("几何校正必须指定目标坐标系")
                    try:
                        target_crs_value = CRS.from_string(target_crs)
                    except rasterio.errors.CRSError as exc:
                        raise ValidationException(
                            "几何校正目标坐标系不合法"
                        ) from exc
                    resampling_code = str(
                        parameters.get("resampling") or "bilinear"
                    ).strip().lower()
                    if resampling_code not in self.resampling_methods:
                        raise ValidationException(
                            "重采样方法仅支持 nearest、bilinear 或 cubic"
                        )
                    raw_resolution = parameters.get("target_resolution")
                    resolution = None
                    if raw_resolution is not None:
                        resolution = self._number(
                            parameters,
                            "target_resolution",
                            0,
                            1e-12,
                            1_000_000,
                        )
                    try:
                        calculate_default_transform(
                            source.crs,
                            target_crs_value,
                            source.width,
                            source.height,
                            *source.bounds,
                            resolution=resolution,
                        )
                    except (ValueError, RasterioIOError) as exc:
                        raise ValidationException(
                            "目标坐标系或分辨率无法用于重投影"
                        ) from exc
                    return
                if step_code == "clip":
                    boundary_code = str(
                        parameters.get("boundary_code") or ""
                    ).strip()
                    if not boundary_code or boundary_geometry is None:
                        raise ValidationException(
                            "行政区裁剪必须选择真实边界编码"
                        )
                    if source.crs is None:
                        raise ValidationException("上游影像缺少 CRS，无法执行处理")
                    projected_geometry = transform_geom(
                        "EPSG:4326",
                        source.crs,
                        boundary_geometry,
                        precision=12,
                    )
                    try:
                        geometry_window(source, [projected_geometry])
                    except (ValueError, WindowError) as exc:
                        raise ValidationException(
                            "行政区边界与当前影像没有可裁剪交集"
                        ) from exc
                    return
                if step_code == "enhancement":
                    method = str(
                        parameters.get("method") or "percentile_stretch"
                    ).strip().lower()
                    if method not in {
                        "percentile_stretch",
                        "histogram_equalization",
                    }:
                        raise ValidationException(
                            "影像增强仅支持 percentile_stretch 或 "
                            "histogram_equalization"
                        )
                    lower = self._number(
                        parameters,
                        "lower_percentile",
                        2,
                        0,
                        49.999,
                    )
                    upper = self._number(
                        parameters,
                        "upper_percentile",
                        98,
                        50.001,
                        100,
                    )
                    if lower >= upper:
                        raise ValidationException(
                            "拉伸下限百分位必须小于上限百分位"
                        )
                    bins = parameters.get("histogram_bins", 256)
                    if isinstance(bins, bool) or not isinstance(bins, int):
                        raise ValidationException("直方图分箱数必须为整数")
                    if not 32 <= bins <= 4096:
                        raise ValidationException(
                            "直方图分箱数必须位于 32 到 4096 之间"
                        )
                    return
                if step_code == "band_products":
                    if source.count < 4:
                        raise ValidationException("波段产品至少需要四波段影像")
                    indexes = {
                        self._band_index(
                            parameters,
                            "red_band",
                            1,
                            source.count,
                        ),
                        self._band_index(
                            parameters,
                            "green_band",
                            2,
                            source.count,
                        ),
                        self._band_index(
                            parameters,
                            "blue_band",
                            3,
                            source.count,
                        ),
                        self._band_index(
                            parameters,
                            "nir_band",
                            4,
                            source.count,
                        ),
                    }
                    if len(indexes) != 4:
                        raise ValidationException(
                            "红、绿、蓝和近红外必须选择四个不同波段"
                        )
                    return
                raise ValidationException(f"平台不支持执行步骤 {step_code}")
        except RasterioIOError as exc:
            raise ValidationException("上游影像无法由 Rasterio 读取") from exc

    def execute(
        self,
        step_code: str,
        source_path: Path,
        output_path: Path,
        parameters: dict[str, Any],
        boundary_geometry: dict[str, Any] | None = None,
        rpc_dem_path: Path | None = None,
        dem_evidence: dict[str, Any] | None = None,
    ) -> ProcessingExecutionResult:
        """执行指定步骤并以原子替换方式写出有效 GeoTIFF。

        Args:
            step_code: 标准处理步骤编码。
            source_path: 已校验的上游实体栅格。
            output_path: 受控目录中的最终输出路径。
            parameters: 用户明确提交的处理参数。
            boundary_geometry: 裁剪步骤使用的 WGS84 行政区几何。
            rpc_dem_path: RPC 正射步骤使用的受控 DEM 实体。
            dem_evidence: 已校验 DEM 物理证据。

        Returns:
            ProcessingExecutionResult: 输出栅格结构和实际参数。
        """
        processors = {
            "radiometric": self._radiometric,
            "atmospheric": self._atmospheric,
            "enhancement": self._enhancement,
            "geometric": self._geometric,
            "band_products": self._band_products,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_name(
            f".{output_path.stem}-{uuid4().hex}.tmp.tif"
        )
        try:
            with rasterio.open(source_path) as source:
                geometric_method = str(parameters.get("method") or "reproject")
                crs_required = step_code == "clip" or (
                    step_code == "geometric"
                    and geometric_method == "reproject"
                )
                if source.crs is None and crs_required:
                    raise ValidationException("上游影像缺少 CRS，无法执行处理")
                if step_code == "clip":
                    actual_parameters = self._clip(
                        source,
                        temporary_path,
                        parameters,
                        boundary_geometry,
                    )
                elif step_code == "geometric":
                    actual_parameters = self._geometric(
                        source,
                        temporary_path,
                        parameters,
                        rpc_dem_path,
                        dem_evidence,
                    )
                else:
                    processor = processors.get(step_code)
                    if processor is None:
                        raise ValidationException(f"平台不支持执行步骤 {step_code}")
                    actual_parameters = processor(
                        source,
                        temporary_path,
                        parameters,
                    )
            with rasterio.open(temporary_path) as output:
                if output.width <= 0 or output.height <= 0 or output.count <= 0:
                    raise ValidationException("处理输出没有有效栅格结构")
                result = ProcessingExecutionResult(
                    parameters=actual_parameters,
                    width=output.width,
                    height=output.height,
                    band_count=output.count,
                    dtype=output.dtypes[0],
                    crs=output.crs.to_string() if output.crs else "",
                )
            os.replace(temporary_path, output_path)
            return result
        except RasterioIOError as exc:
            raise ValidationException("上游影像或处理输出无法由 Rasterio 读取") from exc
        finally:
            temporary_path.unlink(missing_ok=True)
            for sidecar_suffix in (".aux.xml", ".msk", ".ovr"):
                Path(f"{temporary_path}{sidecar_suffix}").unlink(
                    missing_ok=True
                )
