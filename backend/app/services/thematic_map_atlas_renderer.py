"""将已校验 PNG 专题图编排为带封面和目录的实体 PDF 图集。"""

from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageOps


@dataclass(frozen=True)
class ThematicMapAtlasSource:
    """一页图集来源专题图及其不可变证据。"""

    product_code: str
    map_name: str
    map_number: str
    map_date: date
    path: Path
    file_size_bytes: int
    checksum_sha256: str


@dataclass(frozen=True)
class ThematicMapAtlasRenderResult:
    """图集 PDF 字节、页数和渲染清单。"""

    pdf_content: bytes
    page_count: int
    manifest: dict


class ThematicMapAtlasRenderer:
    """生成标准横版封面、分页目录和统一图幅专题图页。"""

    renderer_name = "AgriScope Pillow 专题图集编排器"
    renderer_version = "thematic-map-atlas-renderer-v1.1"
    page_width = 1800
    page_height = 1200
    dpi = 150
    toc_items_per_page = 14

    @staticmethod
    def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """加载支持中文的系统字体。

        Args:
            size: 字号像素值。
            bold: 是否优先使用粗体。

        Returns:
            ImageFont.FreeTypeFont: Pillow 字体。
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
        raise RuntimeError("系统缺少可用于专题图集编排的字体")

    @classmethod
    def _base_page(cls) -> Image.Image:
        """创建带细边框的标准横版白底页。

        Returns:
            Image.Image: RGB 图集页面。
        """
        page = Image.new("RGB", (cls.page_width, cls.page_height), "white")
        draw = ImageDraw.Draw(page)
        draw.rectangle(
            (42, 42, cls.page_width - 42, cls.page_height - 42),
            outline=(45, 74, 60),
            width=3,
        )
        return page

    @classmethod
    def _cover_page(
        cls,
        atlas_name: str,
        atlas_number: str,
        task_code: str,
        producer: str,
        generated_at: datetime,
        sources: list[ThematicMapAtlasSource],
    ) -> Image.Image:
        """绘制图集封面。

        Args:
            atlas_name: 图集名称。
            atlas_number: 图集编号。
            task_code: 任务编号。
            producer: 制图单位。
            generated_at: 生成时间。
            sources: 图集专题图来源。

        Returns:
            Image.Image: 封面页。
        """
        page = cls._base_page()
        draw = ImageDraw.Draw(page)
        draw.rectangle(
            (46, 46, 310, cls.page_height - 46),
            fill=(32, 76, 55),
        )
        draw.text(
            (390, 250),
            atlas_name,
            fill=(28, 50, 39),
            font=cls._font(68, bold=True),
        )
        draw.text(
            (394, 360),
            "遥感监测专题图集 · 实体归档版",
            fill=(74, 102, 87),
            font=cls._font(34),
        )
        date_start = min(item.map_date for item in sources).isoformat()
        date_end = max(item.map_date for item in sources).isoformat()
        details = [
            ("图集编号", atlas_number),
            ("任务编号", task_code),
            ("专题图页", f"{len(sources)} 张"),
            ("制图日期", f"{date_start} — {date_end}"),
            ("编制单位", producer),
            (
                "生成时间",
                generated_at.astimezone(ZoneInfo("Asia/Shanghai")).strftime(
                    "%Y-%m-%d %H:%M:%S（北京时间）"
                ),
            ),
        ]
        y = 530
        label_font = cls._font(25)
        value_font = cls._font(28, bold=True)
        for label, value in details:
            draw.text((400, y), label, fill=(110, 126, 117), font=label_font)
            draw.text((570, y - 2), value, fill=(39, 61, 50), font=value_font)
            y += 72
        draw.text(
            (400, cls.page_height - 120),
            "图集成员均来自通过受控路径、大小和 SHA-256 复核的 PNG 专题图实体",
            fill=(116, 80, 22),
            font=cls._font(22),
        )
        return page

    @classmethod
    def _toc_pages(
        cls,
        sources: list[ThematicMapAtlasSource],
    ) -> list[Image.Image]:
        """绘制可分页的图集目录。

        Args:
            sources: 按用户顺序排列的图集成员。

        Returns:
            list[Image.Image]: 一个或多个目录页。
        """
        pages: list[Image.Image] = []
        for start in range(0, len(sources), cls.toc_items_per_page):
            chunk = sources[start : start + cls.toc_items_per_page]
            page = cls._base_page()
            draw = ImageDraw.Draw(page)
            draw.text(
                (100, 88),
                "专题图目录",
                fill=(28, 50, 39),
                font=cls._font(48, bold=True),
            )
            draw.text(
                (100, 158),
                (
                    f"第 {len(pages) + 1} 页 · 共 "
                    f"{(len(sources) - 1) // cls.toc_items_per_page + 1} 页"
                ),
                fill=(116, 130, 122),
                font=cls._font(22),
            )
            y = 235
            for offset, source in enumerate(chunk):
                sequence = start + offset + 1
                fill = (246, 249, 247) if sequence % 2 else (235, 242, 238)
                draw.rounded_rectangle(
                    (95, y, cls.page_width - 95, y + 55),
                    radius=8,
                    fill=fill,
                )
                draw.text(
                    (120, y + 12),
                    f"{sequence:02d}",
                    fill=(44, 104, 73),
                    font=cls._font(22, bold=True),
                )
                draw.text(
                    (200, y + 11),
                    source.map_number,
                    fill=(55, 72, 63),
                    font=cls._font(21, bold=True),
                )
                draw.text(
                    (560, y + 11),
                    source.map_name,
                    fill=(55, 72, 63),
                    font=cls._font(21),
                )
                draw.text(
                    (cls.page_width - 280, y + 12),
                    source.map_date.isoformat(),
                    fill=(102, 119, 110),
                    font=cls._font(20),
                )
                y += 61
            pages.append(page)
        return pages

    @classmethod
    def _map_page(cls, source: ThematicMapAtlasSource) -> Image.Image:
        """把原始专题图无裁切适配到统一图集页面。

        Args:
            source: 已校验 PNG 专题图。

        Returns:
            Image.Image: 统一尺寸图集页。
        """
        with Image.open(source.path) as image:
            original = image.convert("RGB")
            fitted = ImageOps.contain(
                original,
                (cls.page_width, cls.page_height),
                Image.Resampling.LANCZOS,
            )
        page = Image.new("RGB", (cls.page_width, cls.page_height), "white")
        page.paste(
            fitted,
            (
                (cls.page_width - fitted.width) // 2,
                (cls.page_height - fitted.height) // 2,
            ),
        )
        return page

    def render(
        self,
        atlas_name: str,
        atlas_number: str,
        task_code: str,
        producer: str,
        generated_at: datetime,
        sources: list[ThematicMapAtlasSource],
    ) -> ThematicMapAtlasRenderResult:
        """生成图集 PDF 并返回可审计渲染信息。

        Args:
            atlas_name: 图集名称。
            atlas_number: 图集编号。
            task_code: 任务编号。
            producer: 编制单位。
            generated_at: 生成时间。
            sources: 2–50 个已校验 PNG 专题图。

        Returns:
            ThematicMapAtlasRenderResult: PDF 和页数清单。
        """
        if not 2 <= len(sources) <= 50:
            raise ValueError("专题图集必须包含 2–50 张实体专题图")
        pages = [
            self._cover_page(
                atlas_name,
                atlas_number,
                task_code,
                producer,
                generated_at,
                sources,
            ),
            *self._toc_pages(sources),
            *(self._map_page(source) for source in sources),
        ]
        output = BytesIO()
        pages[0].save(
            output,
            format="PDF",
            save_all=True,
            append_images=pages[1:],
            resolution=self.dpi,
            title=atlas_name,
            author=producer,
            subject=f"任务 {task_code} 遥感监测专题图集",
        )
        content = output.getvalue()
        if not content.startswith(b"%PDF-"):
            raise RuntimeError("专题图集 PDF 生成失败")
        return ThematicMapAtlasRenderResult(
            pdf_content=content,
            page_count=len(pages),
            manifest={
                "renderer_name": self.renderer_name,
                "renderer_version": self.renderer_version,
                "page_width_px": self.page_width,
                "page_height_px": self.page_height,
                "dpi": self.dpi,
                "cover_page_count": 1,
                "toc_page_count": len(pages) - len(sources) - 1,
                "map_page_count": len(sources),
                "total_page_count": len(pages),
            },
        )
