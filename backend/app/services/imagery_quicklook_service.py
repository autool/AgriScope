"""实体源影像和已校验波段产品快视图缓存与读取服务。"""

import asyncio
import json
import os
import secrets
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.imagery_dao import ImageryDAO
from app.schemas.imagery import (
    ImageryQuicklookProductResponse,
    ImageryQuicklookResponse,
)
from app.services.imagery_quicklook_renderer import ImageryQuicklookRenderer
from app.services.imagery_service import ImageryService

PRODUCT_NAMES = {
    "source": "实体源影像",
    "true_color": "真彩色产品",
    "false_color": "标准假彩色",
    "ndvi": "NDVI 植被指数",
}


class ImageryQuicklookService:
    """从已校验实体文件生成快视图，且不改变处理完成状态。"""

    def __init__(
        self,
        dao: ImageryDAO | None = None,
        imagery_service: ImageryService | None = None,
        renderer: ImageryQuicklookRenderer | None = None,
    ) -> None:
        """初始化影像快视图服务。

        Args:
            dao: 影像数据访问对象。
            imagery_service: 实体文件校验和处理步骤服务。
            renderer: Rasterio 快视图渲染器。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ImageryDAO()
        self.imagery_service = imagery_service or ImageryService(dao=self.dao)
        self.renderer = renderer or ImageryQuicklookRenderer()
        self.cache_root = self.imagery_service.storage_dir / "quicklooks"

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        """临时写入后原子替换快视图或缓存清单。

        Args:
            path: 最终缓存路径。
            content: 文件字节。

        Returns:
            None: 无返回值。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.part")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _cache_paths(
        self,
        asset_code: str,
        source_checksum: str,
        product_code: str,
    ) -> tuple[Path, Path]:
        """构造来源校验值隔离的 PNG 和清单路径。

        Args:
            asset_code: 影像资产编号。
            source_checksum: 实体来源 SHA256。
            product_code: 快视图产品编码。

        Returns:
            tuple[Path, Path]: PNG 和 JSON 清单路径。
        """
        directory = self.cache_root / asset_code / source_checksum
        return directory / f"{product_code}.png", directory / f"{product_code}.json"

    @staticmethod
    def _unavailable(
        product_code: str,
        reason: str,
    ) -> ImageryQuicklookProductResponse:
        """构造不伪造预览的产品不可用响应。

        Args:
            product_code: 产品编码。
            reason: 不可用原因。

        Returns:
            ImageryQuicklookProductResponse: 明确空状态。
        """
        return ImageryQuicklookProductResponse(
            product_code=product_code,
            product_name=PRODUCT_NAMES[product_code],
            available=False,
            unavailable_reason=reason,
            source_kind=None,
            source_uri=None,
            source_checksum_sha256=None,
            preview_url=None,
            preview_checksum_sha256=None,
            bounds_wgs84=None,
            width=None,
            height=None,
            band_indexes=(),
            band_descriptions=(),
            stretch_ranges=(),
            value_range=None,
            renderer_version=None,
            generated_at=None,
        )

    @staticmethod
    def _response_from_manifest(
        asset_code: str,
        manifest: dict,
    ) -> ImageryQuicklookProductResponse:
        """将缓存清单转换为类型化快视图响应。

        Args:
            asset_code: 影像资产编号。
            manifest: 已验证缓存清单。

        Returns:
            ImageryQuicklookProductResponse: 快视图证据。
        """
        product_code = manifest["product_code"]
        preview_checksum = manifest["preview_checksum_sha256"]
        return ImageryQuicklookProductResponse(
            product_code=product_code,
            product_name=PRODUCT_NAMES[product_code],
            available=True,
            unavailable_reason=None,
            source_kind=manifest["source_kind"],
            source_uri=manifest["source_uri"],
            source_checksum_sha256=manifest["source_checksum_sha256"],
            preview_url=(
                f"/api/v1/imagery-assets/{asset_code}/quicklooks/"
                f"{product_code}.png?v={preview_checksum[:12]}"
            ),
            preview_checksum_sha256=preview_checksum,
            bounds_wgs84=tuple(manifest["bounds_wgs84"]),
            width=manifest["width"],
            height=manifest["height"],
            band_indexes=tuple(manifest["band_indexes"]),
            band_descriptions=tuple(manifest["band_descriptions"]),
            stretch_ranges=tuple(
                tuple(item) for item in manifest["stretch_ranges"]
            ),
            value_range=(
                tuple(manifest["value_range"])
                if manifest.get("value_range") is not None
                else None
            ),
            renderer_version=manifest["renderer_version"],
            generated_at=datetime.fromisoformat(manifest["generated_at"]),
        )

    async def _load_cached_manifest(
        self,
        png_path: Path,
        manifest_path: Path,
        source_checksum: str,
        source_size_bytes: int,
        product_code: str,
    ) -> dict | None:
        """验证缓存来源、配置和 PNG 校验值后复用清单。

        Args:
            png_path: PNG 缓存路径。
            manifest_path: JSON 清单路径。
            source_checksum: 当前实体来源 SHA256。
            source_size_bytes: 当前实体来源大小。
            product_code: 产品编码。

        Returns:
            dict | None: 有效清单或 None。
        """
        if not png_path.is_file() or not manifest_path.is_file():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if (
            manifest.get("product_code") != product_code
            or manifest.get("source_checksum_sha256") != source_checksum
            or manifest.get("source_size_bytes") != source_size_bytes
            or manifest.get("renderer_version") != self.renderer.renderer_version
            or manifest.get("max_dimension")
            != settings.imagery_quicklook_max_dimension
            or manifest.get("preview_size_bytes") != png_path.stat().st_size
        ):
            return None
        actual_preview_checksum = await asyncio.to_thread(
            calculate_sha256,
            png_path,
        )
        if actual_preview_checksum != manifest.get("preview_checksum_sha256"):
            return None
        return manifest

    async def _render_product(
        self,
        asset_code: str,
        product_code: str,
        source_path: Path,
        source_uri: str,
        source_kind: str,
        source_checksum: str,
    ) -> ImageryQuicklookProductResponse:
        """生成或复用单个来源校验值隔离的快视图。

        Args:
            asset_code: 影像资产编号。
            product_code: 产品编码。
            source_path: 已校验实体栅格路径。
            source_uri: 数据库记录的受控来源 URI。
            source_kind: 原始资产或已校验波段产品。
            source_checksum: 已重新核验的实体 SHA256。

        Returns:
            ImageryQuicklookProductResponse: 可追溯快视图。
        """
        source_size_bytes = source_path.stat().st_size
        png_path, manifest_path = self._cache_paths(
            asset_code,
            source_checksum,
            product_code,
        )
        cached = await self._load_cached_manifest(
            png_path,
            manifest_path,
            source_checksum,
            source_size_bytes,
            product_code,
        )
        if cached is not None:
            return self._response_from_manifest(asset_code, cached)
        try:
            rendered = await asyncio.to_thread(
                self.renderer.render,
                source_path,
                product_code,
                settings.imagery_quicklook_max_dimension,
            )
        except ValueError as exc:
            raise ValidationException(f"实体影像快视图生成失败：{exc}") from exc
        preview_checksum = sha256(rendered.png).hexdigest()
        generated_at = datetime.now(UTC)
        manifest = {
            "product_code": product_code,
            "source_kind": source_kind,
            "source_uri": source_uri,
            "source_checksum_sha256": source_checksum,
            "source_size_bytes": source_size_bytes,
            "preview_checksum_sha256": preview_checksum,
            "preview_size_bytes": len(rendered.png),
            "bounds_wgs84": rendered.bounds_wgs84,
            "width": rendered.width,
            "height": rendered.height,
            "band_indexes": rendered.band_indexes,
            "band_descriptions": rendered.band_descriptions,
            "stretch_ranges": rendered.stretch_ranges,
            "value_range": rendered.value_range,
            "renderer_version": self.renderer.renderer_version,
            "max_dimension": settings.imagery_quicklook_max_dimension,
            "generated_at": generated_at.isoformat(),
        }
        manifest_bytes = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        await asyncio.to_thread(self._write_atomic, png_path, rendered.png)
        await asyncio.to_thread(self._write_atomic, manifest_path, manifest_bytes)
        return self._response_from_manifest(asset_code, manifest)

    async def get_quicklooks(
        self,
        db: AsyncSession,
        asset_code: str,
    ) -> ImageryQuicklookResponse:
        """查询实体源影像和已校验波段产品快视图集合。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。

        Returns:
            ImageryQuicklookResponse: 真实快视图及来源证据。
        """
        asset = await self.dao.get_asset_by_code(db, asset_code)
        if asset is None:
            raise NotFoundException(f"未找到影像资产 {asset_code}")
        source_path = self.imagery_service.resolve_verified_asset_source_path(asset)
        source_checksum = await asyncio.to_thread(calculate_sha256, source_path)
        if source_checksum != asset.checksum_sha256:
            raise ValidationException("实体源影像 SHA256 与资产记录不一致")
        products: list[ImageryQuicklookProductResponse] = [
            await self._render_product(
                asset.asset_code,
                "source",
                source_path,
                asset.file_uri,
                "source_asset",
                source_checksum,
            )
        ]
        band_step = await self.dao.get_step(db, asset.id, "band_products")
        if band_step is None:
            reason = "当前资产未配置波段产品步骤"
            products.extend(
                self._unavailable(code, reason)
                for code in ("true_color", "false_color", "ndvi")
            )
        else:
            try:
                product_path, evidence = (
                    self.imagery_service.resolve_verified_step_artifact_path(
                        band_step
                    )
                )
            except ValidationException as exc:
                products.extend(
                    self._unavailable(code, exc.message)
                    for code in ("true_color", "false_color", "ndvi")
                )
            else:
                product_checksum = await asyncio.to_thread(
                    calculate_sha256,
                    product_path,
                )
                product_source_uri = str(band_step.output_uri or "")
                for code in ("true_color", "false_color", "ndvi"):
                    try:
                        product = await self._render_product(
                            asset.asset_code,
                            code,
                            product_path,
                            product_source_uri,
                            "verified_band_products",
                            product_checksum,
                        )
                    except ValidationException as exc:
                        product = self._unavailable(code, exc.message)
                    products.append(product)
        return ImageryQuicklookResponse(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            data_status=asset.data_status,
            products=products,
        )

    async def get_image(
        self,
        db: AsyncSession,
        asset_code: str,
        product_code: str,
    ) -> tuple[bytes, str]:
        """读取已校验快视图 PNG 并返回 ETag。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。
            product_code: 快视图产品编码。

        Returns:
            tuple[bytes, str]: PNG 字节和预览 SHA256。
        """
        quicklooks = await self.get_quicklooks(db, asset_code)
        product = next(
            (item for item in quicklooks.products if item.product_code == product_code),
            None,
        )
        if product is None or not product.available:
            reason = product.unavailable_reason if product else "未知快视图产品"
            raise ValidationException(reason or "快视图不可用")
        if not product.source_checksum_sha256 or not product.preview_checksum_sha256:
            raise ValidationException("快视图缓存证据不完整")
        png_path, _ = self._cache_paths(
            asset_code,
            product.source_checksum_sha256,
            product_code,
        )
        if not png_path.is_file():
            raise NotFoundException("快视图实体文件不存在")
        actual_checksum = await asyncio.to_thread(calculate_sha256, png_path)
        if actual_checksum != product.preview_checksum_sha256:
            raise ValidationException("快视图 PNG SHA256 校验失败")
        return await asyncio.to_thread(png_path.read_bytes), actual_checksum
