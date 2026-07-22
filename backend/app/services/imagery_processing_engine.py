"""基于 Rasterio 的受控影像预处理执行引擎。"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, transform_geom

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
    ) -> dict[str, Any]:
        """将影像重投影到明确指定的目标坐标系和像元网格。

        Args:
            source: 输入栅格。
            output_path: 临时输出路径。
            parameters: `target_crs` 和可选 `target_resolution`。

        Returns:
            dict[str, Any]: 实际目标坐标系、尺寸和分辨率。
        """
        target_crs = str(parameters.get("target_crs") or "EPSG:4490").strip()
        if not target_crs:
            raise ValidationException("几何校正必须指定目标坐标系")
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
            transform, width, height = calculate_default_transform(
                source.crs,
                target_crs,
                source.width,
                source.height,
                *source.bounds,
                resolution=resolution,
            )
        except (ValueError, RasterioIOError) as exc:
            raise ValidationException("目标坐标系或分辨率无法用于重投影") from exc
        profile = self._output_profile(source)
        profile.update(
            crs=target_crs,
            transform=transform,
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
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=Resampling.bilinear,
                )
            output.descriptions = source.descriptions
            output.update_tags(
                PROCESSING_STEP="geometric",
                TARGET_CRS=target_crs,
            )
        return {
            "method": "reproject_bilinear",
            "target_crs": target_crs,
            "target_resolution": resolution,
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
            output.update_tags(
                PROCESSING_STEP="clip",
                BOUNDARY_CODE=boundary_code,
            )
        return {
            "boundary_code": boundary_code,
            "width": clipped.shape[2],
            "height": clipped.shape[1],
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
        source_bands = source.read().astype("float32")
        red = source_bands[red_index - 1]
        green = source_bands[green_index - 1]
        blue = source_bands[blue_index - 1]
        nir = source_bands[nir_index - 1]
        denominator = nir + red
        ndvi = np.divide(
            nir - red,
            denominator,
            out=np.zeros_like(denominator, dtype="float32"),
            where=np.abs(denominator) > 1e-12,
        )
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
        profile.update(count=7, dtype="float32", nodata=None)
        with rasterio.open(output_path, "w", **profile) as output:
            output.write(product_stack)
            output.descriptions = descriptions
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

    def execute(
        self,
        step_code: str,
        source_path: Path,
        output_path: Path,
        parameters: dict[str, Any],
        boundary_geometry: dict[str, Any] | None = None,
    ) -> ProcessingExecutionResult:
        """执行指定步骤并以原子替换方式写出有效 GeoTIFF。

        Args:
            step_code: 标准处理步骤编码。
            source_path: 已校验的上游实体栅格。
            output_path: 受控目录中的最终输出路径。
            parameters: 用户明确提交的处理参数。
            boundary_geometry: 裁剪步骤使用的 WGS84 行政区几何。

        Returns:
            ProcessingExecutionResult: 输出栅格结构和实际参数。
        """
        processors = {
            "radiometric": self._radiometric,
            "atmospheric": self._atmospheric,
            "geometric": self._geometric,
            "band_products": self._band_products,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_name(
            f".{output_path.stem}-{uuid4().hex}.tmp.tif"
        )
        try:
            with rasterio.open(source_path) as source:
                if source.crs is None:
                    raise ValidationException("上游影像缺少 CRS，无法执行处理")
                if step_code == "clip":
                    actual_parameters = self._clip(
                        source,
                        temporary_path,
                        parameters,
                        boundary_geometry,
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
