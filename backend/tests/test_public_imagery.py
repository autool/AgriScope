"""公开 Landsat 历史语料检索、反射率裁取和入库服务测试。"""

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.schemas.imagery import ImageryAssetResponse
from app.schemas.public_imagery import (
    PublicImageryImportRequest,
    PublicImagerySearchRequest,
)
from app.services.public_imagery_engine import PublicImageryEngine
from app.services.public_imagery_service import PublicImageryService


def _stac_item(
    item_id: str = "LT05_L2SP_118028_19861209_02_T1",
    cloud_cover: float = 2,
    bbox: list[float] | None = None,
) -> dict:
    """构造结构与 Planetary Computer Landsat Item 一致的测试条目。"""
    assets = {}
    for asset_name in ("blue", "green", "red", "nir08"):
        assets[asset_name] = {
            "href": (
                "https://landsateuwest.blob.core.windows.net/landsat-c2/"
                f"{item_id}_{asset_name}.TIF"
            ),
            "raster:bands": [{"scale": 0.0000275, "offset": -0.2, "nodata": 0}],
        }
    return {
        "type": "Feature",
        "id": item_id,
        "collection": "landsat-c2-l2",
        "bbox": bbox or [126.0, 45.0, 127.0, 46.0],
        "properties": {
            "datetime": "1986-12-09T01:39:36.799019Z",
            "eo:cloud_cover": cloud_cover,
            "platform": "landsat-5",
            "instruments": ["tm"],
            "processing:level": "L2SP",
            "landsat:collection_category": "T1",
            "landsat:wrs_path": "118",
            "landsat:wrs_row": "028",
            "landsat:product_id": item_id,
            "gsd": 30,
        },
        "assets": assets,
    }


def _asset_response() -> ImageryAssetResponse:
    """构造统一影像资产入库响应。"""
    return ImageryAssetResponse(
        asset_code="LANDSAT_19861209_HRB",
        asset_name="1986 年 Landsat-5 哈尔滨历史影像",
        sensor_type="landsat-5 TM",
        acquired_at=datetime(1986, 12, 9, 1, 39, tzinfo=UTC),
        cloud_cover=2,
        resolution_m=30,
        processing_level="L2SP",
        data_status="operational",
        calibration_status="pending",
        correction_status="pending",
        original_filename="landsat.tif",
        file_uri="storage://imagery/assets/LANDSAT_19861209_HRB/landsat.tif",
        file_format="GTiff",
        file_size_bytes=1024,
        checksum_sha256="a" * 64,
        band_count=4,
        raster_width=10,
        raster_height=10,
        crs="EPSG:4326",
        raster_metadata={},
        imported_by="赵志远",
        footprint=None,
        file_verified=True,
        file_error=None,
        created_at=datetime(2026, 7, 23, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_search_returns_only_valid_four_band_candidates_without_sas() -> None:
    """候选响应仅包含受控来源摘要，缺标度条目被忽略。"""
    valid = _stac_item()
    partial = _stac_item(
        item_id="LT05_L2SP_118028_19851206_02_T1",
        cloud_cover=1,
        bbox=[125.0, 44.0, 126.55, 45.8],
    )
    invalid = _stac_item(item_id="LT05_INVALID")
    invalid["assets"]["nir08"].pop("raster:bands")
    client = SimpleNamespace(
        COLLECTION="landsat-c2-l2",
        search=lambda *_args: [partial, invalid, valid],
    )
    service = PublicImageryService(client=client)

    response = await service.search(PublicImagerySearchRequest(
        bbox=(126.5, 45.7, 126.8, 45.9),
        start_date=date(1984, 1, 1),
        end_date=date(1989, 12, 31),
        max_cloud_cover=10,
    ))

    assert response.total == 2
    assert response.items[0].item_id == valid["id"]
    assert response.items[0].fully_covers_query is True
    assert response.items[1].fully_covers_query is False
    assert "sas" not in response.model_dump_json().lower()
    assert "sig=" not in response.model_dump_json().lower()


def test_engine_applies_stac_scale_offset_and_preserves_public_lineage(
    tmp_path: Path,
) -> None:
    """四波段裁取生成真实浮点反射率并且标签不包含短期 SAS。"""
    transform = from_origin(126, 46, 0.01, 0.01)
    signed_urls: dict[str, str] = {}
    for index, asset_name in enumerate(("blue", "green", "red", "nir08"), start=1):
        band_path = tmp_path / f"{asset_name}.tif"
        with rasterio.open(
            band_path,
            "w",
            driver="GTiff",
            width=100,
            height=100,
            count=1,
            dtype="uint16",
            crs="EPSG:4326",
            transform=transform,
            nodata=0,
        ) as output:
            output.write(np.full((100, 100), 10_000 + index, dtype="uint16"), 1)
        signed_urls[asset_name] = str(band_path)
    engine = PublicImageryEngine()
    item = engine.parse_item(_stac_item())
    output_path = tmp_path / "landsat_subset.tif"

    engine.build_reflectance_subset(
        item,
        (126.2, 45.2, 126.4, 45.4),
        signed_urls,
        output_path,
    )

    with rasterio.open(output_path) as dataset:
        assert dataset.count == 4
        assert dataset.descriptions == ("Blue", "Green", "Red", "NIR")
        assert dataset.dtypes == ("float32",) * 4
        expected = (10_001 * 0.0000275) - 0.2
        assert float(dataset.read(1)[0, 0]) == pytest.approx(expected)
        tags = dataset.tags()
        assert tags["STAC_ITEM_ID"] == item.item_id
        assert tags["STAC_SCALE_OFFSET_APPLIED"] == "true"
        assert tags["SURFACE_REFLECTANCE"] == "true"
        assert tags["SOURCE_CLASSIFICATION"] == "public_open_data"
        assert "sig=" not in str(tags).lower()


@pytest.mark.asyncio
async def test_import_refetches_item_builds_entity_and_uses_atomic_asset_service(
    tmp_path: Path,
) -> None:
    """导入只信任 Item ID，服务端重新获取来源并复用统一原子入库。"""
    item_dict = _stac_item()
    engine = PublicImageryEngine()
    client = SimpleNamespace(
        COLLECTION="landsat-c2-l2",
        get_item=lambda item_id: item_dict,
        sign_asset_url=lambda href: f"{href}?temporary-signature=masked",
    )
    inspected_tags: dict[str, str] = {}

    def build_subset(item, bbox, signed_urls, output_path):
        assert item.item_id == item_dict["id"]
        assert bbox == (126.5, 45.7, 126.8, 45.9)
        assert all("temporary-signature" in url for url in signed_urls.values())
        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            width=2,
            height=2,
            count=4,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(126.5, 45.9, 0.15, 0.1),
        ) as output:
            output.write(np.ones((4, 2, 2), dtype="float32"))
            output.update_tags(STAC_ITEM_ID=item.item_id)

    engine.build_reflectance_subset = build_subset

    async def upload_asset(
        _db,
        project_code,
        task_code,
        request,
        _filename,
        file_handle,
    ):
        assert project_code == "RS-2026"
        assert task_code == "RS-2026-045"
        assert request.operator_code == "manager-zhao-zhiyuan"
        with rasterio.open(file_handle.name) as dataset:
            inspected_tags.update(dataset.tags())
        return _asset_response()

    asset_service = SimpleNamespace(upload_asset=upload_asset)
    workbench_dao = SimpleNamespace(
        get_project_by_code=AsyncMock(return_value=SimpleNamespace(id=1)),
        get_task_by_code=AsyncMock(return_value=SimpleNamespace(id=2, project_id=1)),
    )
    project_user_service = SimpleNamespace(
        require_capability=AsyncMock(return_value=SimpleNamespace()),
    )
    service = PublicImageryService(
        client=client,
        engine=engine,
        asset_service=asset_service,
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
    )

    response = await service.import_item(
        SimpleNamespace(),
        PublicImageryImportRequest(
            project_code="RS-2026",
            task_code="RS-2026-045",
            item_id=item_dict["id"],
            bbox=(126.5, 45.7, 126.8, 45.9),
            asset_code="LANDSAT_19861209_HRB",
            asset_name="1986 年 Landsat-5 哈尔滨历史影像",
            operator_code="manager-zhao-zhiyuan",
        ),
    )

    assert response.item_id == item_dict["id"]
    assert response.asset.asset_code == "LANDSAT_19861209_HRB"
    assert inspected_tags["STAC_ITEM_ID"] == item_dict["id"]
    project_user_service.require_capability.assert_awaited_once_with(
        ANY,
        1,
        "manager-zhao-zhiyuan",
        "manage_imagery",
    )
