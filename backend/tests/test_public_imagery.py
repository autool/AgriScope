"""公开 Landsat 历史语料检索、反射率裁取和入库服务测试。"""

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.core.exceptions import ValidationException
from app.dao.public_imagery_dao import (
    PublicImageryCoverageAnalysis,
    PublicImageryItemCoverage,
)
from app.schemas.imagery import ImageryAssetBatchResponse, ImageryAssetResponse
from app.schemas.public_imagery import (
    PublicImageryBatchImportRequest,
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
    normalized_bbox = bbox or [126.0, 45.0, 127.0, 46.0]
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
        "bbox": normalized_bbox,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [normalized_bbox[0], normalized_bbox[1]],
                [normalized_bbox[2], normalized_bbox[1]],
                [normalized_bbox[2], normalized_bbox[3]],
                [normalized_bbox[0], normalized_bbox[3]],
                [normalized_bbox[0], normalized_bbox[1]],
            ]],
        },
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


def _coverage_analysis(
    ratios: list[float],
    *,
    union_ratio: float = 1,
    union_covers: bool = True,
) -> PublicImageryCoverageAnalysis:
    """构造与候选顺序一致的 PostGIS 足迹覆盖分析结果。"""
    return PublicImageryCoverageAnalysis(
        items=tuple(
            PublicImageryItemCoverage(
                index=index,
                coverage_ratio=ratio,
                fully_covers_query=ratio == 1,
                geometry_valid=True,
            )
            for index, ratio in enumerate(ratios)
        ),
        union_coverage_ratio=union_ratio,
        union_covers_query=union_covers,
    )


def _asset_response(
    asset_code: str = "LANDSAT_19861209_HRB",
    asset_name: str = "1986 年 Landsat-5 哈尔滨历史影像",
) -> ImageryAssetResponse:
    """构造统一影像资产入库响应。"""
    return ImageryAssetResponse(
        asset_code=asset_code,
        asset_name=asset_name,
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
    coverage_dao = SimpleNamespace(
        analyze_query_coverage=AsyncMock(
            return_value=_coverage_analysis([0.25, 1]),
        ),
    )
    service = PublicImageryService(client=client, dao=coverage_dao)

    response = await service.search(
        SimpleNamespace(),
        PublicImagerySearchRequest(
            bbox=(126.5, 45.7, 126.8, 45.9),
            start_date=date(1984, 1, 1),
            end_date=date(1989, 12, 31),
            max_cloud_cover=10,
        ),
    )

    assert response.total == 2
    assert response.items[0].item_id == valid["id"]
    assert response.items[0].fully_covers_query is True
    assert response.items[0].query_coverage_ratio == 1
    assert response.items[1].fully_covers_query is False
    assert response.items[1].query_coverage_ratio == 0.25
    assert response.coverage_basis == "STAC_GEOMETRY_POSTGIS_GEOGRAPHY"
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
        assert tags["SOURCE_SCALE_APPLIED"] == "true"
        assert tags["SURFACE_REFLECTANCE"] == "true"
        assert tags["REFLECTANCE_QUANTITY"] == "SURFACE_REFLECTANCE"
        assert tags["SOURCE_PROCESSING_BASELINE"] == (
            "USGS Landsat Collection 2 Level-2"
        )
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
        dao=SimpleNamespace(
            analyze_query_coverage=AsyncMock(
                return_value=_coverage_analysis([1]),
            ),
        ),
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
    assert response.query_coverage_ratio == 1
    assert inspected_tags["STAC_ITEM_ID"] == item_dict["id"]
    assert inspected_tags["PUBLIC_COVERAGE_BASIS"] == (
        "STAC_GEOMETRY_POSTGIS_GEOGRAPHY"
    )
    project_user_service.require_capability.assert_awaited_once_with(
        ANY,
        1,
        "manager-zhao-zhiyuan",
        "manage_imagery",
    )


def test_public_batch_request_rejects_duplicate_items_and_asset_codes() -> None:
    """公开影像批次必须同时保持 STAC Item 和资产编号唯一。"""
    common = {
        "project_code": "RS-2026",
        "task_code": "RS-2026-045",
        "operator_code": "manager-zhao-zhiyuan",
        "batch_code": "IMB-LANDSAT-HISTORY",
        "comment": "导入两景公开 Landsat 历史地表反射率语料",
        "bbox": (126.5, 45.7, 126.8, 45.9),
    }
    with pytest.raises(ValueError, match="不得重复选择 STAC Item"):
        PublicImageryBatchImportRequest.model_validate({
            **common,
            "items": [
                {
                    "item_id": "LT05_SAME",
                    "asset_code": "LANDSAT_A",
                    "asset_name": "历史影像 A",
                },
                {
                    "item_id": "LT05_SAME",
                    "asset_code": "LANDSAT_B",
                    "asset_name": "历史影像 B",
                },
            ],
        })
    with pytest.raises(ValueError, match="不得包含重复资产编号"):
        PublicImageryBatchImportRequest.model_validate({
            **common,
            "items": [
                {
                    "item_id": "LT05_ITEM_A",
                    "asset_code": "LANDSAT_SAME",
                    "asset_name": "历史影像 A",
                },
                {
                    "item_id": "LT05_ITEM_B",
                    "asset_code": "LANDSAT_SAME",
                    "asset_name": "历史影像 B",
                },
            ],
        })


@pytest.mark.asyncio
async def test_batch_import_prepares_all_items_then_calls_atomic_service_once(
    tmp_path: Path,
) -> None:
    """多景公开影像只调用一次统一批次服务并按请求顺序保存来源。"""
    item_ids = [
        "LT05_L2SP_118028_19881128_02_T1",
        "LT05_L2SP_118028_19890912_02_T1",
    ]
    stac_items = {item_id: _stac_item(item_id=item_id) for item_id in item_ids}
    client = SimpleNamespace(
        COLLECTION="landsat-c2-l2",
        get_item=lambda item_id: stac_items[item_id],
        sign_asset_url=lambda href: f"{href}?temporary-signature=masked",
    )
    engine = PublicImageryEngine()

    def build_subset(item, _bbox, signed_urls, output_path):
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
    prepared_paths = iter([
        tmp_path / "first.tif",
        tmp_path / "second.tif",
    ])
    captured: dict[str, object] = {}

    async def upload_assets_batch(
        _db,
        project_code,
        task_code,
        request,
        files,
    ):
        assert project_code == "RS-2026"
        assert task_code == "RS-2026-045"
        captured["request"] = request
        captured["files"] = [item.filename for item in files]
        for expected_id, upload in zip(item_ids, files, strict=True):
            with rasterio.open(upload.file_handle.name) as dataset:
                assert dataset.tags()["STAC_ITEM_ID"] == expected_id
        return ImageryAssetBatchResponse(
            batch_code=request.batch_code,
            item_count=2,
            total_size_bytes=2048,
            manifest_sha256="b" * 64,
            imported_by="赵志远",
            imported_by_code="manager-zhao-zhiyuan",
            imported_by_role="project_manager",
            comment=request.comment,
            created_at=datetime(2026, 7, 23, tzinfo=UTC),
            items=[
                _asset_response("LANDSAT5_19881128_HRB", "1988 历史影像"),
                _asset_response("LANDSAT5_19890912_HRB", "1989 历史影像"),
            ],
        )

    asset_service = SimpleNamespace(upload_assets_batch=upload_assets_batch)
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
        dao=SimpleNamespace(
            analyze_query_coverage=AsyncMock(
                return_value=_coverage_analysis([1, 1]),
            ),
        ),
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
    )
    service._temporary_output_path = lambda _item_id: next(prepared_paths)

    response = await service.import_batch(
        SimpleNamespace(),
        PublicImageryBatchImportRequest(
            project_code="RS-2026",
            task_code="RS-2026-045",
            operator_code="manager-zhao-zhiyuan",
            batch_code="IMB-LANDSAT-HISTORY-1988-1989-HRB",
            comment="导入两景公开 Landsat 历史地表反射率语料",
            bbox=(126.5, 45.7, 126.8, 45.9),
            items=[
                {
                    "item_id": item_ids[0],
                    "asset_code": "LANDSAT5_19881128_HRB",
                    "asset_name": "1988 历史影像",
                },
                {
                    "item_id": item_ids[1],
                    "asset_code": "LANDSAT5_19890912_HRB",
                    "asset_name": "1989 历史影像",
                },
            ],
        ),
    )

    assert response.batch.item_count == 2
    assert response.union_covers_query is True
    assert response.union_coverage_ratio == 1
    assert response.coverage_mode == "multi_scene_union"
    assert [source.item_id for source in response.sources] == item_ids
    assert captured["files"] == [
        f"{item_ids[0]}_SR_SUBSET.tif",
        f"{item_ids[1]}_SR_SUBSET.tif",
    ]
    assert captured["request"].batch_code == (
        "IMB-LANDSAT-HISTORY-1988-1989-HRB"
    )
    assert not (tmp_path / "first.tif").exists()
    assert not (tmp_path / "second.tif").exists()


@pytest.mark.asyncio
async def test_batch_import_accepts_authoritative_multi_scene_union_coverage(
    tmp_path: Path,
) -> None:
    """两景各自仅部分覆盖时按真实足迹联合通过并分别裁取交集矩形。"""
    item_ids = ["LT05_PARTIAL_WEST", "LT05_PARTIAL_EAST"]
    stac_items = {
        item_ids[0]: _stac_item(
            item_id=item_ids[0],
            bbox=[126.0, 45.0, 126.6, 46.0],
        ),
        item_ids[1]: _stac_item(
            item_id=item_ids[1],
            bbox=[126.4, 45.0, 127.0, 46.0],
        ),
    }
    client = SimpleNamespace(
        COLLECTION="landsat-c2-l2",
        get_item=lambda item_id: stac_items[item_id],
        sign_asset_url=lambda href: f"{href}?temporary-signature=masked",
    )
    engine = PublicImageryEngine()
    captured_bboxes: list[tuple[float, float, float, float]] = []

    def build_subset(_item, bbox, _signed_urls, output_path):
        captured_bboxes.append(bbox)
        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            width=2,
            height=2,
            count=4,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(bbox[0], bbox[3], 0.1, 0.1),
        ) as output:
            output.write(np.ones((4, 2, 2), dtype="float32"))

    engine.build_reflectance_subset = build_subset
    prepared_paths = iter([
        tmp_path / "west.tif",
        tmp_path / "east.tif",
    ])

    async def upload_assets_batch(_db, _project, _task, request, files):
        for upload in files:
            with rasterio.open(upload.file_handle.name) as dataset:
                assert dataset.tags()["PUBLIC_UNION_SCENE_COUNT"] == "2"
                assert dataset.tags()["PUBLIC_COVERAGE_BASIS"] == (
                    "STAC_GEOMETRY_POSTGIS_GEOGRAPHY"
                )
        return ImageryAssetBatchResponse(
            batch_code=request.batch_code,
            item_count=2,
            total_size_bytes=2048,
            manifest_sha256="c" * 64,
            imported_by="赵志远",
            imported_by_code="manager-zhao-zhiyuan",
            imported_by_role="project_manager",
            comment=request.comment,
            created_at=datetime(2026, 7, 23, tzinfo=UTC),
            items=[
                _asset_response("LANDSAT_WEST", "西侧历史影像"),
                _asset_response("LANDSAT_EAST", "东侧历史影像"),
            ],
        )

    service = PublicImageryService(
        client=client,
        engine=engine,
        asset_service=SimpleNamespace(upload_assets_batch=upload_assets_batch),
        dao=SimpleNamespace(
            analyze_query_coverage=AsyncMock(
                return_value=_coverage_analysis(
                    [2 / 3, 2 / 3],
                    union_ratio=1,
                    union_covers=True,
                ),
            ),
        ),
        workbench_dao=SimpleNamespace(
            get_project_by_code=AsyncMock(return_value=SimpleNamespace(id=1)),
            get_task_by_code=AsyncMock(
                return_value=SimpleNamespace(id=2, project_id=1),
            ),
        ),
        project_user_service=SimpleNamespace(
            require_capability=AsyncMock(return_value=SimpleNamespace()),
        ),
    )
    service._temporary_output_path = lambda _item_id: next(prepared_paths)

    response = await service.import_batch(
        SimpleNamespace(),
        PublicImageryBatchImportRequest(
            project_code="RS-2026",
            task_code="RS-2026-045",
            operator_code="manager-zhao-zhiyuan",
            batch_code="IMB-LANDSAT-CROSS-TRACK",
            comment="两景跨轨 Landsat 共同覆盖目标区域并原子入库",
            bbox=(126.2, 45.2, 126.8, 45.8),
            items=[
                {
                    "item_id": item_ids[0],
                    "asset_code": "LANDSAT_WEST",
                    "asset_name": "西侧历史影像",
                },
                {
                    "item_id": item_ids[1],
                    "asset_code": "LANDSAT_EAST",
                    "asset_name": "东侧历史影像",
                },
            ],
        ),
    )

    assert response.coverage_mode == "multi_scene_union"
    assert response.union_covers_query is True
    assert response.union_coverage_ratio == 1
    assert captured_bboxes == [
        (126.2, 45.2, 126.6, 45.8),
        (126.4, 45.2, 126.8, 45.8),
    ]
    assert [source.query_coverage_ratio for source in response.sources] == [
        pytest.approx(2 / 3),
        pytest.approx(2 / 3),
    ]


@pytest.mark.asyncio
async def test_batch_import_rejects_incomplete_union_before_signing() -> None:
    """多景真实足迹联合覆盖不足时不得申请 SAS、裁取或进入入库事务。"""
    item_ids = ["LT05_GAPPED_WEST", "LT05_GAPPED_EAST"]
    client = SimpleNamespace(
        COLLECTION="landsat-c2-l2",
        get_item=lambda item_id: _stac_item(item_id=item_id),
        sign_asset_url=lambda _href: (_ for _ in ()).throw(
            AssertionError("覆盖不足时不得申请 SAS")
        ),
    )
    asset_service = SimpleNamespace(upload_assets_batch=AsyncMock())
    service = PublicImageryService(
        client=client,
        asset_service=asset_service,
        dao=SimpleNamespace(
            analyze_query_coverage=AsyncMock(
                return_value=_coverage_analysis(
                    [0.4, 0.4],
                    union_ratio=0.8,
                    union_covers=False,
                ),
            ),
        ),
        workbench_dao=SimpleNamespace(
            get_project_by_code=AsyncMock(return_value=SimpleNamespace(id=1)),
            get_task_by_code=AsyncMock(
                return_value=SimpleNamespace(id=2, project_id=1),
            ),
        ),
        project_user_service=SimpleNamespace(
            require_capability=AsyncMock(return_value=SimpleNamespace()),
        ),
    )

    with pytest.raises(ValidationException, match="真实覆盖率 80.00%"):
        await service.import_batch(
            SimpleNamespace(),
            PublicImageryBatchImportRequest(
                project_code="RS-2026",
                task_code="RS-2026-045",
                operator_code="manager-zhao-zhiyuan",
                batch_code="IMB-LANDSAT-INCOMPLETE-UNION",
                comment="验证跨轨候选存在覆盖缺口时整批拒绝",
                bbox=(126.2, 45.2, 126.8, 45.8),
                items=[
                    {
                        "item_id": item_ids[0],
                        "asset_code": "LANDSAT_GAPPED_WEST",
                        "asset_name": "西侧缺口影像",
                    },
                    {
                        "item_id": item_ids[1],
                        "asset_code": "LANDSAT_GAPPED_EAST",
                        "asset_name": "东侧缺口影像",
                    },
                ],
            ),
        )

    asset_service.upload_assets_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_import_cleans_all_subsets_when_later_item_fails(
    tmp_path: Path,
) -> None:
    """任一景裁取失败时清除全部公开临时实体且不进入影像入库事务。"""
    item_ids = ["LT05_ITEM_OK", "LT05_ITEM_FAILED"]
    stac_items = {item_id: _stac_item(item_id=item_id) for item_id in item_ids}
    client = SimpleNamespace(
        COLLECTION="landsat-c2-l2",
        get_item=lambda item_id: stac_items[item_id],
        sign_asset_url=lambda href: f"{href}?temporary-signature=masked",
    )
    engine = PublicImageryEngine()

    def build_subset(item, _bbox, _signed_urls, output_path):
        if item.item_id == item_ids[1]:
            output_path.write_bytes(b"partial")
            raise RuntimeError("第二景裁取失败")
        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            width=2,
            height=2,
            count=4,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(126.5, 45.9, 0.1, 0.1),
        ) as output:
            output.write(np.ones((4, 2, 2), dtype="float32"))

    engine.build_reflectance_subset = build_subset
    prepared_paths = iter([
        tmp_path / "first.tif",
        tmp_path / "failed.tif",
    ])
    asset_service = SimpleNamespace(upload_assets_batch=AsyncMock())
    service = PublicImageryService(
        client=client,
        engine=engine,
        asset_service=asset_service,
        dao=SimpleNamespace(
            analyze_query_coverage=AsyncMock(
                return_value=_coverage_analysis([1, 1]),
            ),
        ),
        workbench_dao=SimpleNamespace(
            get_project_by_code=AsyncMock(return_value=SimpleNamespace(id=1)),
            get_task_by_code=AsyncMock(
                return_value=SimpleNamespace(id=2, project_id=1)
            ),
        ),
        project_user_service=SimpleNamespace(
            require_capability=AsyncMock(return_value=SimpleNamespace()),
        ),
    )
    service._temporary_output_path = lambda _item_id: next(prepared_paths)
    request = PublicImageryBatchImportRequest(
        project_code="RS-2026",
        task_code="RS-2026-045",
        operator_code="manager-zhao-zhiyuan",
        batch_code="IMB-LANDSAT-ROLLBACK",
        comment="验证任一公开影像失败时整批清理临时实体",
        bbox=(126.5, 45.7, 126.8, 45.9),
        items=[
            {
                "item_id": item_ids[0],
                "asset_code": "LANDSAT_OK",
                "asset_name": "成功候选",
            },
            {
                "item_id": item_ids[1],
                "asset_code": "LANDSAT_FAILED",
                "asset_name": "失败候选",
            },
        ],
    )

    with pytest.raises(RuntimeError, match="第二景裁取失败"):
        await service.import_batch(SimpleNamespace(), request)

    asset_service.upload_assets_batch.assert_not_awaited()
    assert not (tmp_path / "first.tif").exists()
    assert not (tmp_path / "failed.tif").exists()
