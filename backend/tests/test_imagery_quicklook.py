"""真实实体影像与已校验波段产品快视图测试。"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import rasterio
from rasterio.transform import from_bounds

from app.core.imagery_files import calculate_sha256
from app.services.imagery_quicklook_renderer import (
    ImageryQuicklookRenderer,
    ImageryQuicklookRenderResult,
)
from app.services.imagery_quicklook_service import ImageryQuicklookService


def write_source_raster(path: Path) -> None:
    """写入带真实空间参考和四波段描述的测试源影像。"""
    width = 80
    height = 60
    x = np.arange(width, dtype="float32")[None, :]
    y = np.arange(height, dtype="float32")[:, None]
    data = np.zeros((4, height, width), dtype="float32")
    data[0] = 20 + x
    data[1] = 30 + y
    data[2] = 40 + x + y
    data[3] = 60 + x * 0.5 + y
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=4,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_bounds(126.0, 45.0, 127.0, 46.0, width, height),
    ) as dataset:
        dataset.write(data)
        dataset.descriptions = ("Blue", "Green", "Red", "NIR")


def write_band_product_raster(path: Path) -> None:
    """写入与平台七波段产品栈一致的测试产物。"""
    width = 80
    height = 60
    x = np.arange(width, dtype="float32")[None, :]
    y = np.arange(height, dtype="float32")[:, None]
    red = 0.2 + x / 500
    red = np.broadcast_to(red, (height, width))
    green = 0.15 + y / 500
    green = np.broadcast_to(green, (height, width))
    blue = 0.1 + (x + y) / 1000
    nir = 0.5 + (x + y) / 700
    denominator = nir + red
    ndvi = (nir - red) / denominator
    stack = np.stack([red, green, blue, nir, red, green, ndvi]).astype(
        "float32"
    )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=7,
        dtype="float32",
        crs="EPSG:4490",
        transform=from_bounds(126.0, 45.0, 127.0, 46.0, width, height),
    ) as dataset:
        dataset.write(stack)
        dataset.descriptions = (
            "true_color_red",
            "true_color_green",
            "true_color_blue",
            "false_color_nir",
            "false_color_red",
            "false_color_green",
            "ndvi",
        )


def test_renderer_uses_source_rgb_descriptions_and_wgs84_bounds(
    tmp_path: Path,
) -> None:
    """验证源影像按波段描述渲染并返回真实 WGS84 范围。"""
    source_path = tmp_path / "source.tif"
    write_source_raster(source_path)

    result = ImageryQuicklookRenderer().render(source_path, "source", 512)

    assert result.png.startswith(b"\x89PNG\r\n\x1a\n")
    assert result.band_indexes == (3, 2, 1)
    assert result.band_descriptions == ("red", "green", "blue")
    assert result.bounds_wgs84 == (126.0, 45.0, 127.0, 46.0)
    assert result.width == 80
    assert result.height == 60


def test_renderer_reads_verified_product_stack_and_ndvi_values(
    tmp_path: Path,
) -> None:
    """验证真彩色、假彩色和 NDVI 使用七波段产物的明确描述。"""
    product_path = tmp_path / "products.tif"
    write_band_product_raster(product_path)
    renderer = ImageryQuicklookRenderer()

    true_color = renderer.render(product_path, "true_color", 512)
    false_color = renderer.render(product_path, "false_color", 512)
    ndvi = renderer.render(product_path, "ndvi", 512)

    assert true_color.band_indexes == (1, 2, 3)
    assert false_color.band_indexes == (4, 5, 6)
    assert ndvi.band_indexes == (7,)
    assert ndvi.value_range is not None
    assert -1 <= ndvi.value_range[0] <= ndvi.value_range[1] <= 1
    assert ndvi.stretch_ranges == ()


class CountingQuicklookRenderer(ImageryQuicklookRenderer):
    """记录快视图实际渲染次数的测试渲染器。"""

    def __init__(self) -> None:
        """初始化渲染计数。"""
        self.render_count = 0

    def render(
        self,
        source_path: Path,
        product_code: str,
        max_dimension: int,
    ) -> ImageryQuicklookRenderResult:
        """计数后调用真实渲染器。"""
        self.render_count += 1
        return super().render(source_path, product_code, max_dimension)


def test_service_persists_sha_manifest_and_reuses_cache(tmp_path: Path) -> None:
    """验证源/预览 SHA 清单、产品来源和缓存复用。"""
    source_path = tmp_path / "source.tif"
    product_path = tmp_path / "products.tif"
    write_source_raster(source_path)
    write_band_product_raster(product_path)
    source_checksum = calculate_sha256(source_path)
    product_checksum = calculate_sha256(product_path)
    asset = SimpleNamespace(
        id=10,
        asset_code="IMG-001",
        asset_name="实体测试影像",
        data_status="demo",
        file_uri="storage://imagery/assets/IMG-001/source.tif",
        checksum_sha256=source_checksum,
    )
    band_step = SimpleNamespace(
        output_uri="storage://imagery/processed/IMG-001/products.tif"
    )
    dao = AsyncMock()
    dao.get_asset_by_code.return_value = asset
    dao.get_step.return_value = band_step
    imagery_service = MagicMock()
    imagery_service.storage_dir = tmp_path
    imagery_service.resolve_verified_asset_source_path.return_value = source_path
    imagery_service.resolve_verified_step_artifact_path.return_value = (
        product_path,
        {"checksum_sha256": product_checksum},
    )
    renderer = CountingQuicklookRenderer()
    service = ImageryQuicklookService(
        dao=dao,
        imagery_service=imagery_service,
        renderer=renderer,
    )
    service.cache_root = tmp_path / "cache"

    first = asyncio.run(service.get_quicklooks(AsyncMock(), "IMG-001"))
    second = asyncio.run(service.get_quicklooks(AsyncMock(), "IMG-001"))
    image, etag = asyncio.run(
        service.get_image(AsyncMock(), "IMG-001", "ndvi")
    )

    assert renderer.render_count == 4
    assert all(product.available for product in first.products)
    assert first.products[0].source_kind == "source_asset"
    assert all(
        product.source_kind == "verified_band_products"
        for product in first.products[1:]
    )
    assert first.products[0].preview_checksum_sha256 == (
        second.products[0].preview_checksum_sha256
    )
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert etag == next(
        product.preview_checksum_sha256
        for product in first.products
        if product.product_code == "ndvi"
    )
    assert len(list((tmp_path / "cache").rglob("*.json"))) == 4


def test_service_does_not_fake_products_without_verified_artifact(
    tmp_path: Path,
) -> None:
    """验证波段产物缺失时只返回实体源影像，不用源文件冒充产品。"""
    source_path = tmp_path / "source.tif"
    write_source_raster(source_path)
    asset = SimpleNamespace(
        id=10,
        asset_code="IMG-001",
        asset_name="实体测试影像",
        data_status="demo",
        file_uri="storage://imagery/assets/IMG-001/source.tif",
        checksum_sha256=calculate_sha256(source_path),
    )
    dao = AsyncMock()
    dao.get_asset_by_code.return_value = asset
    dao.get_step.return_value = None
    imagery_service = MagicMock()
    imagery_service.storage_dir = tmp_path
    imagery_service.resolve_verified_asset_source_path.return_value = source_path
    renderer = CountingQuicklookRenderer()
    service = ImageryQuicklookService(dao, imagery_service, renderer)
    service.cache_root = tmp_path / "cache"

    response = asyncio.run(service.get_quicklooks(AsyncMock(), "IMG-001"))

    assert response.products[0].available is True
    assert all(product.available is False for product in response.products[1:])
    assert renderer.render_count == 1
