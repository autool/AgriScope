"""专题图模板、实体渲染、批量生成和校验测试。"""

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import rasterio
from PIL import Image
from pydantic import ValidationError
from rasterio.transform import from_bounds

from app.core.imagery_files import calculate_sha256
from app.models.thematic_map import ThematicMapProduct
from app.schemas.thematic_map import ThematicMapBatchGenerateRequest
from app.services.thematic_map_renderer import ThematicMapRenderer
from app.services.thematic_map_service import ThematicMapService


def write_band_product_raster(path: Path) -> None:
    """写出带真彩色、假彩色和 NDVI 描述的实体产品栈。"""
    width = 120
    height = 90
    x = np.arange(width, dtype="float32")[None, :]
    y = np.arange(height, dtype="float32")[:, None]
    red = np.broadcast_to(0.15 + x / 1000, (height, width))
    green = np.broadcast_to(0.12 + y / 1000, (height, width))
    blue = 0.08 + (x + y) / 2000
    nir = 0.45 + (x + y) / 1300
    ndvi = (nir - red) / (nir + red)
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
        transform=from_bounds(126.5, 45.7, 126.8, 45.95, width, height),
        nodata=np.nan,
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


def build_template() -> SimpleNamespace:
    """构造完整横版专题图模板。"""
    return SimpleNamespace(
        id=3,
        project_id=7,
        template_code="HLJ-LANDSCAPE",
        template_name="黑龙江农业遥感横版",
        title_pattern="{map_name}",
        producer="黑龙江省农业农村厅遥感监测项目组",
        page_width_px=1600,
        page_height_px=1100,
        dpi=150,
        margin_px=50,
        legend_position="bottom_right",
        include_neatline=True,
        include_north_arrow=True,
        include_scale_bar=True,
        created_by="赵志远",
        created_by_code="manager-zhao-zhiyuan",
        created_by_role="project_manager",
        created_at=datetime(2026, 7, 22, tzinfo=UTC),
        updated_at=datetime(2026, 7, 22, tzinfo=UTC),
    )


def test_renderer_generates_complete_png_and_pdf_from_physical_raster(
    tmp_path: Path,
) -> None:
    """验证 PNG/PDF 均直接读取实体栅格并包含完整版式清单。"""
    source_path = tmp_path / "products.tif"
    write_band_product_raster(source_path)
    renderer = ThematicMapRenderer()
    template = build_template()

    png = renderer.render(
        source_path,
        "ndvi",
        "png",
        template,
        "哈尔滨市农作物 NDVI 专题图",
        "HLJ-NDVI-2026-001",
        date(2026, 7, 22),
        "公开数据 · 非法定调查成果",
    )
    pdf = renderer.render(
        source_path,
        "true_color",
        "pdf",
        template,
        "哈尔滨市真彩色影像专题图",
        "HLJ-RGB-2026-001",
        date(2026, 7, 22),
        "公开数据 · 非法定调查成果",
    )

    assert png.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert pdf.content.startswith(b"%PDF-")
    with Image.open(__import__("io").BytesIO(png.content)) as image:
        assert image.size == (1600, 1100)
    assert png.manifest["title"] == "哈尔滨市农作物 NDVI 专题图"
    assert png.manifest["classification_label"] == "公开数据 · 非法定调查成果"
    assert png.manifest["north_arrow"] is True
    assert png.manifest["scale_bar"]["ground_length_m"] > 0
    assert png.manifest["legend"]["type"] == "continuous"
    assert png.manifest["source_band_descriptions"] == ["ndvi"]
    assert pdf.media_type == "application/pdf"


def test_batch_request_rejects_duplicate_business_key() -> None:
    """验证同批次重复图号、产品和格式被请求模型拒绝。"""
    duplicate = {
        "source_product_code": "ndvi",
        "output_format": "png",
        "map_name": "NDVI 专题图",
        "map_number": "HLJ-NDVI-001",
        "map_date": "2026-07-22",
    }
    with __import__("pytest").raises(ValidationError, match="重复图号"):
        ThematicMapBatchGenerateRequest(
            template_code="HLJ-LANDSCAPE",
            asset_code="S2B-HRB-20260716-PUBLIC",
            operator_code="manager-zhao-zhiyuan",
            comment="批量生成真实专题图成果",
            items=[duplicate, duplicate],
        )


def test_service_batch_generation_persists_source_and_file_checksums(
    tmp_path: Path,
) -> None:
    """验证批量生成原子写出实体并保存来源、成图校验和及角色审计。"""
    source_path = tmp_path / "products.tif"
    write_band_product_raster(source_path)
    source_checksum = calculate_sha256(source_path)
    template = build_template()
    asset = SimpleNamespace(
        id=9,
        project_id=7,
        asset_code="S2B-HRB-20260716-PUBLIC",
        asset_name="Sentinel-2B 哈尔滨公开影像",
        data_status="operational",
        acquired_at=datetime(2026, 7, 16, tzinfo=UTC),
        processing_level="L2A",
        raster_metadata={
            "tags": {
                "SECURITY_CLASSIFICATION": "public",
                "STAC_ITEM_ID": "S2B_TEST_L2A",
                "SOURCE_LICENSE_URL": "https://example.test/license",
            }
        },
    )
    step = SimpleNamespace(
        output_uri="storage://imagery/processed/S2B/products.tif",
    )
    dao = AsyncMock()
    dao.get_template_by_code.return_value = template
    dao.find_existing_product.return_value = None

    async def add_products(_: object, products: list[ThematicMapProduct]) -> None:
        for index, product in enumerate(products, start=1):
            product.id = index
            product.generated_at = datetime(2026, 7, 22, tzinfo=UTC)

    dao.add_products.side_effect = add_products
    imagery_dao = AsyncMock()
    imagery_dao.get_asset_by_code.return_value = asset
    imagery_dao.get_step.return_value = step
    workbench_dao = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=7)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=7,
    )
    project_user_service = AsyncMock()
    project_user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    imagery_service = MagicMock()
    imagery_service.resolve_verified_step_artifact_path.return_value = (
        source_path,
        {"checksum_sha256": source_checksum},
    )
    service = ThematicMapService(
        dao=dao,
        imagery_dao=imagery_dao,
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
        imagery_service=imagery_service,
    )
    service.storage_root = tmp_path / "maps"
    db = AsyncMock()

    response = asyncio.run(
        service.generate_batch(
            db,
            "RS-2026",
            "RS-2026-045",
            ThematicMapBatchGenerateRequest(
                template_code="HLJ-LANDSCAPE",
                asset_code="S2B-HRB-20260716-PUBLIC",
                operator_code="manager-zhao-zhiyuan",
                comment="生成真彩色和 NDVI 实体专题图用于成果审核",
                items=[
                    {
                        "source_product_code": "true_color",
                        "output_format": "png",
                        "map_name": "哈尔滨市真彩色专题图",
                        "map_number": "HLJ-RGB-2026-001",
                        "map_date": "2026-07-22",
                    },
                    {
                        "source_product_code": "ndvi",
                        "output_format": "pdf",
                        "map_name": "哈尔滨市 NDVI 专题图",
                        "map_number": "HLJ-NDVI-2026-001",
                        "map_date": "2026-07-22",
                    },
                ],
            ),
        )
    )

    assert response.generated_count == 2
    assert {item.output_format for item in response.products} == {"png", "pdf"}
    for item in response.products:
        files = list((tmp_path / "maps" / "RS-2026-045").glob(
            f"{item.product_code}.*"
        ))
        assert len(files) == 1
        assert item.checksum_sha256 == calculate_sha256(files[0])
        assert item.source_checksum_sha256 == source_checksum
        assert item.render_manifest["source_uri"] == step.output_uri
        assert item.generated_by_code == "manager-zhao-zhiyuan"
    assert dao.add_event.await_count == 2
    project_user_service.require_capability.assert_awaited_once_with(
        db,
        7,
        "manager-zhao-zhiyuan",
        "generate_thematic_maps",
    )
    db.commit.assert_awaited_once()
