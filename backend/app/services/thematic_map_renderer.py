"""从已校验波段产品实体生成带完整制图要素的 PNG/PDF。"""

import math
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.services.imagery_quicklook_renderer import ImageryQuicklookRenderer


@dataclass(frozen=True)
class ThematicMapRenderResult:
    """专题图字节和可审计渲染清单。"""

    content: bytes
    media_type: str
    file_suffix: str
    manifest: dict


class ThematicMapRenderer:
    """组合实体影像、图廓、指北针、比例尺、图例和图面注记。"""

    renderer_name = "AgriScope Pillow 专题制图器"
    renderer_version = "thematic-map-renderer-v1"

    def __init__(
        self,
        raster_renderer: ImageryQuicklookRenderer | None = None,
    ) -> None:
        """初始化专题制图器。

        Args:
            raster_renderer: 从物理栅格读取指定产品的底层渲染器。

        Returns:
            None: 无返回值。
        """
        self.raster_renderer = raster_renderer or ImageryQuicklookRenderer()

    @staticmethod
    def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """加载支持中文的系统字体。

        Args:
            size: 字号像素值。
            bold: 是否优先使用粗体。

        Returns:
            ImageFont.FreeTypeFont: 可用于 Pillow 绘制的字体。
        """
        candidates = [
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
            if bold
            else Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        for path in candidates:
            if path.is_file():
                return ImageFont.truetype(str(path), size=size)
        raise RuntimeError("系统缺少可用于专题制图的字体")

    @staticmethod
    def _fit_size(
        source_width: int,
        source_height: int,
        max_width: int,
        max_height: int,
    ) -> tuple[int, int]:
        """按比例把影像放入图框。

        Args:
            source_width: 源图宽度。
            source_height: 源图高度。
            max_width: 图框最大宽度。
            max_height: 图框最大高度。

        Returns:
            tuple[int, int]: 目标宽高。
        """
        ratio = min(max_width / source_width, max_height / source_height)
        return max(1, round(source_width * ratio)), max(
            1,
            round(source_height * ratio),
        )

    @staticmethod
    def _ground_width_metres(bounds: tuple[float, float, float, float]) -> float:
        """估算 WGS84 范围中心纬度处的东西向地面宽度。

        Args:
            bounds: WGS84 左、下、右、上范围。

        Returns:
            float: 地面宽度米。
        """
        left, bottom, right, top = bounds
        latitude = math.radians((bottom + top) / 2)
        return abs(right - left) * 111_320 * math.cos(latitude)

    @staticmethod
    def _nice_scale_length(target_metres: float) -> float:
        """把目标比例尺长度归整为 1、2、5 倍数量级。

        Args:
            target_metres: 目标地面长度。

        Returns:
            float: 易读比例尺长度米。
        """
        if target_metres <= 0:
            return 1
        magnitude = 10 ** math.floor(math.log10(target_metres))
        normalized = target_metres / magnitude
        factor = 1 if normalized < 2 else 2 if normalized < 5 else 5
        return factor * magnitude

    @staticmethod
    def _ndvi_color(value: float) -> tuple[int, int, int]:
        """复用平台 NDVI 红—黄—绿配色。

        Args:
            value: -1 到 1 的 NDVI。

        Returns:
            tuple[int, int, int]: RGB 颜色。
        """
        normalized = (max(-1, min(1, value)) + 1) / 2
        if normalized <= 0.5:
            return 210, round(180 * normalized * 2), 35
        return (
            round(210 * (1 - normalized) * 2),
            round(180 + 65 * (normalized - 0.5) * 2),
            35,
        )

    def _draw_legend(
        self,
        draw: ImageDraw.ImageDraw,
        product_code: str,
        x: int,
        y: int,
        width: int,
    ) -> dict:
        """绘制产品对应图例。

        Args:
            draw: Pillow 画布。
            product_code: 真彩色、假彩色或 NDVI。
            x: 图例左上角横坐标。
            y: 图例左上角纵坐标。
            width: 图例宽度。

        Returns:
            dict: 图例类型和标签清单。
        """
        label_font = self._font(18)
        title_font = self._font(20, bold=True)
        draw.rounded_rectangle(
            (x, y, x + width, y + 116),
            radius=8,
            fill=(255, 255, 255, 235),
            outline=(50, 67, 59),
            width=2,
        )
        draw.text((x + 14, y + 10), "图例", fill=(30, 44, 37), font=title_font)
        if product_code == "ndvi":
            gradient_left = x + 14
            gradient_top = y + 48
            gradient_width = width - 28
            for offset in range(gradient_width):
                value = -1 + 2 * offset / max(gradient_width - 1, 1)
                draw.line(
                    (
                        gradient_left + offset,
                        gradient_top,
                        gradient_left + offset,
                        gradient_top + 24,
                    ),
                    fill=self._ndvi_color(value),
                )
            for offset, label in ((0, "-1"), (0.5, "0"), (1, "1")):
                text_x = gradient_left + round(gradient_width * offset)
                draw.text(
                    (text_x - 8, gradient_top + 32),
                    label,
                    fill=(42, 55, 49),
                    font=label_font,
                )
            return {"type": "continuous", "labels": ["-1", "0", "1"]}
        label = (
            "真彩色：红 / 绿 / 蓝"
            if product_code == "true_color"
            else "标准假彩色：近红外 / 红 / 绿"
        )
        draw.rectangle((x + 14, y + 50, x + 50, y + 82), fill=(72, 125, 92))
        draw.text((x + 62, y + 53), label, fill=(42, 55, 49), font=label_font)
        return {"type": "band_mapping", "labels": [label]}

    def render(
        self,
        source_path: Path,
        source_product_code: str,
        output_format: str,
        template: object,
        map_name: str,
        map_number: str,
        map_date: date,
        classification_label: str,
    ) -> ThematicMapRenderResult:
        """从物理栅格生成一张完整专题图。

        Args:
            source_path: 已校验 `band_products` 实体路径。
            source_product_code: true_color、false_color 或 ndvi。
            output_format: png 或 pdf。
            template: 持久化版式模板。
            map_name: 专题图名称。
            map_number: 受控图号。
            map_date: 制图日期。
            classification_label: 数据公开/业务属性的可见图面标识。

        Returns:
            ThematicMapRenderResult: 文件字节、媒体类型和渲染清单。
        """
        page_width = int(template.page_width_px)
        page_height = int(template.page_height_px)
        margin = int(template.margin_px)
        header_height = max(110, round(page_height * 0.1))
        footer_height = max(130, round(page_height * 0.12))
        frame_left = margin
        frame_top = header_height
        frame_right = page_width - margin
        frame_bottom = page_height - footer_height
        frame_width = frame_right - frame_left
        frame_height = frame_bottom - frame_top
        raster_result = self.raster_renderer.render(
            source_path,
            source_product_code,
            min(4096, max(frame_width, frame_height) * 2),
        )
        raster_image = Image.open(BytesIO(raster_result.png)).convert("RGBA")
        image_width, image_height = self._fit_size(
            raster_image.width,
            raster_image.height,
            frame_width,
            frame_height,
        )
        raster_image = raster_image.resize(
            (image_width, image_height),
            Image.Resampling.LANCZOS,
        )
        image_left = frame_left + (frame_width - image_width) // 2
        image_top = frame_top + (frame_height - image_height) // 2
        page = Image.new("RGB", (page_width, page_height), "white")
        page.paste(raster_image, (image_left, image_top), raster_image)
        draw = ImageDraw.Draw(page, "RGBA")
        title = str(template.title_pattern).replace("{map_name}", map_name)
        title_font = self._font(max(30, round(page_height * 0.038)), bold=True)
        title_box = draw.textbbox((0, 0), title, font=title_font)
        draw.text(
            ((page_width - (title_box[2] - title_box[0])) / 2, margin // 2),
            title,
            fill=(24, 43, 34),
            font=title_font,
        )
        classification_font = self._font(max(16, round(page_height * 0.016)))
        classification_box = draw.textbbox(
            (0, 0),
            classification_label,
            font=classification_font,
        )
        classification_width = classification_box[2] - classification_box[0]
        draw.rounded_rectangle(
            (
                page_width - margin - classification_width - 28,
                margin // 2,
                page_width - margin,
                margin // 2 + 38,
            ),
            radius=6,
            fill=(245, 229, 189, 235),
            outline=(153, 111, 33),
        )
        draw.text(
            (
                page_width - margin - classification_width - 14,
                margin // 2 + 6,
            ),
            classification_label,
            fill=(111, 74, 13),
            font=classification_font,
        )
        if template.include_neatline:
            draw.rectangle(
                (frame_left, frame_top, frame_right, frame_bottom),
                outline=(25, 48, 37),
                width=max(2, page_width // 900),
            )
        north_arrow_drawn = bool(template.include_north_arrow)
        if north_arrow_drawn:
            arrow_x = frame_right - 54
            arrow_y = frame_top + 34
            draw.text(
                (arrow_x - 8, arrow_y - 28),
                "N",
                fill=(18, 35, 27),
                font=self._font(26, bold=True),
            )
            draw.polygon(
                [
                    (arrow_x, arrow_y),
                    (arrow_x - 16, arrow_y + 52),
                    (arrow_x, arrow_y + 42),
                    (arrow_x + 16, arrow_y + 52),
                ],
                fill=(25, 52, 39),
            )
        scale_manifest = None
        if template.include_scale_bar:
            ground_width = self._ground_width_metres(raster_result.bounds_wgs84)
            metres_per_pixel = ground_width / max(image_width, 1)
            scale_metres = self._nice_scale_length(ground_width / 4)
            scale_pixels = max(40, round(scale_metres / metres_per_pixel))
            scale_x = image_left + 24
            scale_y = image_top + image_height - 42
            draw.rectangle(
                (scale_x - 10, scale_y - 30, scale_x + scale_pixels + 10, scale_y + 24),
                fill=(255, 255, 255, 215),
            )
            draw.line(
                (scale_x, scale_y, scale_x + scale_pixels, scale_y),
                fill=(15, 29, 22),
                width=6,
            )
            draw.line(
                (scale_x, scale_y - 7, scale_x, scale_y + 7),
                fill=(15, 29, 22),
                width=3,
            )
            draw.line(
                (
                    scale_x + scale_pixels,
                    scale_y - 7,
                    scale_x + scale_pixels,
                    scale_y + 7,
                ),
                fill=(15, 29, 22),
                width=3,
            )
            label = (
                f"{scale_metres / 1000:g} km"
                if scale_metres >= 1000
                else f"{scale_metres:g} m"
            )
            draw.text(
                (scale_x, scale_y - 28),
                label,
                fill=(18, 34, 26),
                font=self._font(18),
            )
            scale_manifest = {
                "ground_length_m": scale_metres,
                "pixel_length": scale_pixels,
                "metres_per_pixel": metres_per_pixel,
            }
        legend_width = min(430, max(300, page_width // 4))
        legend_x = (
            frame_right - legend_width - 20
            if template.legend_position == "bottom_right"
            else frame_left + 20
        )
        legend_y = frame_bottom - 136
        legend_manifest = self._draw_legend(
            draw,
            source_product_code,
            legend_x,
            legend_y,
            legend_width,
        )
        footer_font = self._font(max(16, round(page_height * 0.016)))
        footer_y = frame_bottom + 28
        draw.text(
            (margin, footer_y),
            f"制图单位：{template.producer}",
            fill=(46, 62, 54),
            font=footer_font,
        )
        draw.text(
            (margin, footer_y + 32),
            f"制图日期：{map_date.isoformat()}    图号：{map_number}",
            fill=(46, 62, 54),
            font=footer_font,
        )
        coordinate_text = (
            f"数据范围：{raster_result.bounds_wgs84[0]:.5f}, "
            f"{raster_result.bounds_wgs84[1]:.5f} — "
            f"{raster_result.bounds_wgs84[2]:.5f}, "
            f"{raster_result.bounds_wgs84[3]:.5f}（WGS84）"
        )
        draw.text(
            (page_width // 2, footer_y),
            coordinate_text,
            fill=(70, 84, 77),
            font=footer_font,
        )
        manifest = {
            "renderer_name": self.renderer_name,
            "renderer_version": self.renderer_version,
            "source_product_code": source_product_code,
            "source_bounds_wgs84": list(raster_result.bounds_wgs84),
            "source_band_indexes": list(raster_result.band_indexes),
            "source_band_descriptions": list(raster_result.band_descriptions),
            "stretch_ranges": [list(item) for item in raster_result.stretch_ranges],
            "value_range": list(raster_result.value_range)
            if raster_result.value_range
            else None,
            "title": title,
            "map_number": map_number,
            "map_date": map_date.isoformat(),
            "producer": template.producer,
            "classification_label": classification_label,
            "page_width_px": page_width,
            "page_height_px": page_height,
            "dpi": int(template.dpi),
            "neatline": bool(template.include_neatline),
            "north_arrow": north_arrow_drawn,
            "scale_bar": scale_manifest,
            "legend": legend_manifest,
        }
        output = BytesIO()
        if output_format == "png":
            page.save(
                output,
                format="PNG",
                optimize=True,
                dpi=(template.dpi, template.dpi),
            )
            return ThematicMapRenderResult(
                content=output.getvalue(),
                media_type="image/png",
                file_suffix=".png",
                manifest=manifest,
            )
        if output_format == "pdf":
            page.save(output, format="PDF", resolution=template.dpi)
            return ThematicMapRenderResult(
                content=output.getvalue(),
                media_type="application/pdf",
                file_suffix=".pdf",
                manifest=manifest,
            )
        raise ValueError("专题图输出格式仅支持 PNG 或 PDF")
