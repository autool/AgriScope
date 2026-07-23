"""真实遥感影像文件入库与元数据提取测试。"""

import asyncio
import json
import warnings
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
import rasterio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile
from rasterio.rpc import RPC
from rasterio.transform import from_origin

from app.api.v1.endpoints import imagery as imagery_endpoint
from app.core.database import get_db
from app.core.exceptions import ValidationException
from app.models.workbench import ImageryAsset
from app.schemas.imagery import (
    ImageryAssetBatchCreateRequest,
    ImageryAssetBatchResponse,
    ImageryAssetCreateRequest,
)
from app.services.imagery_asset_service import (
    ImageryAssetService,
    ImageryBatchUploadFile,
)


def build_geotiff_bytes(
    *,
    include_crs: bool = True,
    tags: dict[str, str] | None = None,
    namespaced_tags: dict[str, dict[str, str]] | None = None,
) -> bytes:
    """构造可由 Rasterio 读取并携带业务标签的三波段 GeoTIFF。"""
    profile = {
        "driver": "GTiff",
        "width": 10,
        "height": 6,
        "count": 3,
        "dtype": "uint16",
        "transform": from_origin(126.0, 46.0, 0.01, 0.01),
    }
    if include_crs:
        profile["crs"] = "EPSG:4326"
    data = np.arange(180, dtype="uint16").reshape(3, 6, 10)
    with MemoryFile() as memory_file:
        with memory_file.open(**profile) as dataset:
            dataset.write(data)
            selected_tags = tags if tags is not None else {
                "SATELLITE": "TEST-SAT",
                "ACQUIRED": "2026-06-18",
                "PROCESSING_LEVEL": "L1A",
                "CLOUD_COVER": "7.25",
            }
            if selected_tags:
                dataset.update_tags(**selected_tags)
            for namespace, namespace_tags in (namespaced_tags or {}).items():
                dataset.update_tags(ns=namespace, **namespace_tags)
        return memory_file.read()


def build_create_request(
    *,
    sensor_type: str | None = None,
    acquired_at: datetime | None = None,
    cloud_cover: float | None = None,
    processing_level: str | None = None,
) -> ImageryAssetCreateRequest:
    """构造合法影像入库业务元数据。"""
    return ImageryAssetCreateRequest(
        asset_code="GF2-TEST-001",
        asset_name="测试卫星影像",
        sensor_type=sensor_type,
        acquired_at=acquired_at,
        cloud_cover=cloud_cover,
        processing_level=processing_level,
        data_status="demo",
        operator_code="interp-li-jing",
    )


def build_rpc_geotiff_bytes() -> bytes:
    """构造无普通 CRS、但带完整 RPC 模型的原始卫星影像。"""
    zeros = [0.0] * 20
    line_numerator = zeros.copy()
    line_numerator[2] = -1.0
    line_denominator = zeros.copy()
    line_denominator[0] = 1.0
    sample_numerator = zeros.copy()
    sample_numerator[1] = 1.0
    sample_denominator = zeros.copy()
    sample_denominator[0] = 1.0
    rpc_model = RPC(
        height_off=100,
        height_scale=500,
        lat_off=45.8,
        lat_scale=0.04,
        line_den_coeff=line_denominator,
        line_num_coeff=line_numerator,
        line_off=2.5,
        line_scale=2.5,
        long_off=126.6,
        long_scale=0.05,
        samp_den_coeff=sample_denominator,
        samp_num_coeff=sample_numerator,
        samp_off=4.5,
        samp_scale=4.5,
        err_bias=0.5,
        err_rand=0.2,
    )
    data = np.arange(180, dtype="uint16").reshape(3, 6, 10)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with MemoryFile() as memory_file:
            with memory_file.open(
                driver="GTiff",
                width=10,
                height=6,
                count=3,
                dtype="uint16",
            ) as dataset:
                dataset.write(data)
                dataset.update_tags(
                    SATELLITE="TEST-RPC-SAT",
                    ACQUIRED="2026-06-18",
                    PROCESSING_LEVEL="L1A",
                )
                dataset.update_tags(ns="RPC", **rpc_model.to_gdal())
            return memory_file.read()


def build_service(tmp_path: Path) -> tuple[ImageryAssetService, AsyncMock, AsyncMock]:
    """构造使用临时存储目录的影像资产服务。"""
    dao = AsyncMock()
    dao.get_asset_by_code.return_value = None
    dao.get_asset_by_checksum.return_value = None
    dao.get_import_batch_by_code.return_value = None

    async def add_asset(_: object, asset: ImageryAsset) -> ImageryAsset:
        asset.id = 9
        asset.created_at = datetime.now(UTC)
        return asset

    dao.add_asset.side_effect = add_asset

    async def add_import_batch(_: object, batch: object):
        batch.id = 5
        batch.created_at = datetime.now(UTC)
        return batch

    dao.add_import_batch.side_effect = add_import_batch
    workbench_dao = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=7)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=7,
    )
    project_user_service = AsyncMock()
    project_user_service.require_capability.return_value = SimpleNamespace(
        user_code="interp-li-jing",
        display_name="李静",
        role_code="interpreter",
    )
    service = ImageryAssetService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
    )
    service.storage_dir = tmp_path
    return service, dao, workbench_dao


def test_imagery_request_requires_timezone() -> None:
    """验证影像采集时间必须带时区。"""
    with pytest.raises(ValidationError, match="必须包含时区"):
        ImageryAssetCreateRequest(
            asset_code="GF2-TEST-001",
            asset_name="测试影像",
            sensor_type="GF2",
            acquired_at=datetime(2026, 6, 18, 10, 42),
            operator_code="interp-li-jing",
        )


@pytest.mark.parametrize(
    ("field_name", "first_value", "second_value", "message"),
    [
        ("filename", "same.tif", "SAME.TIF", "重复文件名"),
        ("asset_code", "BATCH-SAME", "BATCH-SAME", "重复资产编号"),
    ],
)
def test_batch_request_rejects_duplicate_manifest_identity(
    field_name: str,
    first_value: str,
    second_value: str,
    message: str,
) -> None:
    """验证批次清单拒绝大小写重复文件名和重复资产编号。"""
    first = {
        "filename": "first.tif",
        "asset_code": "BATCH-FIRST",
        "asset_name": "第一景影像",
    }
    second = {
        "filename": "second.tif",
        "asset_code": "BATCH-SECOND",
        "asset_name": "第二景影像",
    }
    first[field_name] = first_value
    second[field_name] = second_value

    with pytest.raises(ValidationError, match=message):
        ImageryAssetBatchCreateRequest.model_validate({
            "batch_code": "IMB-DUPLICATE-TEST",
            "operator_code": "interp-li-jing",
            "comment": "验证影像批次清单身份字段的唯一性约束",
            "items": [first, second],
        })


def test_upload_geotiff_extracts_real_raster_metadata(tmp_path: Path) -> None:
    """验证 GeoTIFF 入库读取结构和文件业务标签。"""
    service, dao, workbench_dao = build_service(tmp_path)
    db = AsyncMock()

    response = asyncio.run(
        service.upload_asset(
            db,
            "RS-2026",
            "RS-2026-045",
            build_create_request(),
            "gf2_test.tif",
            BytesIO(build_geotiff_bytes()),
        )
    )

    assert response.file_verified is True
    assert response.file_format == "GTiff"
    assert response.crs == "EPSG:4326"
    assert response.band_count == 3
    assert response.raster_width == 10
    assert response.raster_height == 6
    assert response.file_size_bytes and response.file_size_bytes > 0
    assert len(response.checksum_sha256 or "") == 64
    assert response.sensor_type == "TEST-SAT"
    assert response.acquired_at == datetime(2026, 6, 18, tzinfo=UTC)
    assert response.processing_level == "L1A"
    assert response.cloud_cover == 7.25
    business_metadata = response.raster_metadata["business_metadata"]
    assert business_metadata["sensor_type"]["source"] == "raster_tag:SATELLITE"
    assert business_metadata["acquired_at"]["source"] == "raster_tag:ACQUIRED"
    assert business_metadata["acquired_at"]["timezone_assumption"] == "UTC"
    assert business_metadata["processing_level"]["source"] == (
        "raster_tag:PROCESSING_LEVEL"
    )
    assert business_metadata["cloud_cover"]["source"] == (
        "raster_tag:CLOUD_COVER"
    )
    assert response.footprint is not None
    assert response.footprint["type"] == "Polygon"
    stored_path = tmp_path / "assets/GF2-TEST-001/gf2_test.tif"
    assert stored_path.is_file()
    with rasterio.open(stored_path) as dataset:
        assert dataset.count == 3
        assert dataset.tags()["SATELLITE"] == "TEST-SAT"
    dao.add_steps.assert_awaited_once()
    steps = dao.add_steps.await_args.args[1]
    assert [step.step_code for step in steps] == [
        "radiometric",
        "atmospheric",
        "geometric",
        "clip",
        "enhancement",
        "band_products",
    ]
    assert [step.sequence for step in steps] == [1, 2, 3, 4, 5, 6]
    assert [step.is_required for step in steps] == [
        True,
        True,
        True,
        True,
        False,
        True,
    ]
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_batch_upload_atomically_persists_two_real_rasters(tmp_path: Path) -> None:
    """验证两景影像在一个事务中发布、建流水线并保存批次清单证据。"""
    service, dao, workbench_dao = build_service(tmp_path)
    asset_id = 10

    async def add_asset(_: object, asset: ImageryAsset) -> ImageryAsset:
        nonlocal asset_id
        asset.id = asset_id
        asset_id += 1
        asset.created_at = datetime.now(UTC)
        return asset

    dao.add_asset.side_effect = add_asset
    first_content = build_geotiff_bytes(tags={
        "SATELLITE": "BATCH-SAT-A",
        "ACQUIRED": "2026-06-18",
        "PROCESSING_LEVEL": "L1A",
    })
    second_content = build_geotiff_bytes(tags={
        "SATELLITE": "BATCH-SAT-B",
        "ACQUIRED": "2026-06-19",
        "PROCESSING_LEVEL": "L1A",
    })
    request = ImageryAssetBatchCreateRequest.model_validate({
        "batch_code": "IMB-TEST-001",
        "operator_code": "interp-li-jing",
        "comment": "验证两景真实栅格原子批量入库和审计",
        "items": [
            {
                "filename": "batch_a.tif",
                "asset_code": "BATCH-A",
                "asset_name": "批量影像 A",
                "data_status": "demo",
            },
            {
                "filename": "batch_b.tif",
                "asset_code": "BATCH-B",
                "asset_name": "批量影像 B",
                "data_status": "demo",
            },
        ],
    })
    db = AsyncMock()

    response = asyncio.run(
        service.upload_assets_batch(
            db,
            "RS-2026",
            "RS-2026-045",
            request,
            [
                ImageryBatchUploadFile("batch_a.tif", BytesIO(first_content)),
                ImageryBatchUploadFile("batch_b.tif", BytesIO(second_content)),
            ],
        )
    )

    assert response.batch_code == "IMB-TEST-001"
    assert response.item_count == 2
    assert response.total_size_bytes == len(first_content) + len(second_content)
    assert len(response.manifest_sha256) == 64
    assert [item.asset_code for item in response.items] == ["BATCH-A", "BATCH-B"]
    assert (tmp_path / "assets/BATCH-A/batch_a.tif").is_file()
    assert (tmp_path / "assets/BATCH-B/batch_b.tif").is_file()
    assert dao.add_asset.await_count == 2
    assert dao.add_steps.await_count == 2
    dao.add_import_batch.assert_awaited_once()
    dao.add_import_batch_items.assert_awaited_once()
    batch_items = dao.add_import_batch_items.await_args.args[1]
    assert [item.sequence for item in batch_items] == [1, 2]
    assert [item.asset_id for item in batch_items] == [10, 11]
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_batch_upload_removes_published_files_when_commit_fails(
    tmp_path: Path,
) -> None:
    """验证数据库提交失败时已发布实体仍会全部删除。"""
    service, dao, _ = build_service(tmp_path)
    request = ImageryAssetBatchCreateRequest.model_validate({
        "batch_code": "IMB-TEST-COMMIT-ROLLBACK",
        "operator_code": "interp-li-jing",
        "comment": "验证数据库提交失败时已发布影像实体必须清理",
        "items": [
            {
                "filename": "commit_failure.tif",
                "asset_code": "BATCH-COMMIT-FAILURE",
                "asset_name": "提交失败回滚影像",
                "data_status": "demo",
            },
        ],
    })
    db = AsyncMock()
    db.commit.side_effect = RuntimeError("database commit failed")

    with pytest.raises(RuntimeError, match="database commit failed"):
        asyncio.run(
            service.upload_assets_batch(
                db,
                "RS-2026",
                "RS-2026-045",
                request,
                [
                    ImageryBatchUploadFile(
                        "commit_failure.tif",
                        BytesIO(build_geotiff_bytes()),
                    ),
                ],
            )
        )

    assert not any(path.is_file() for path in tmp_path.glob("assets/**/*"))
    dao.add_asset.assert_awaited_once()
    dao.add_import_batch.assert_awaited_once()
    db.rollback.assert_awaited_once()


def test_batch_upload_cleans_files_even_when_database_rollback_fails(
    tmp_path: Path,
) -> None:
    """验证回滚连接异常也不会跳过已发布实体清理。"""
    service, _, _ = build_service(tmp_path)
    request = ImageryAssetBatchCreateRequest.model_validate({
        "batch_code": "IMB-TEST-ROLLBACK-ERROR",
        "operator_code": "interp-li-jing",
        "comment": "验证数据库回滚异常时仍然删除批次已发布实体",
        "items": [
            {
                "filename": "rollback_error.tif",
                "asset_code": "BATCH-ROLLBACK-ERROR",
                "asset_name": "回滚异常清理影像",
                "data_status": "demo",
            },
        ],
    })
    db = AsyncMock()
    db.commit.side_effect = RuntimeError("database commit failed")
    db.rollback.side_effect = RuntimeError("database rollback failed")

    with pytest.raises(RuntimeError, match="database rollback failed"):
        asyncio.run(
            service.upload_assets_batch(
                db,
                "RS-2026",
                "RS-2026-045",
                request,
                [
                    ImageryBatchUploadFile(
                        "rollback_error.tif",
                        BytesIO(build_geotiff_bytes()),
                    ),
                ],
            )
        )

    assert not any(path.is_file() for path in tmp_path.glob("assets/**/*"))


@pytest.mark.asyncio
async def test_batch_upload_api_maps_multipart_files_to_one_service_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证批量端点一次接收全部文件和清单，而非拆成单文件请求。"""
    captured: dict[str, object] = {}

    async def upload_assets_batch(
        db: object,
        project_code: str,
        task_code: str,
        request: ImageryAssetBatchCreateRequest,
        files: list[ImageryBatchUploadFile],
    ) -> ImageryAssetBatchResponse:
        captured.update({
            "db": db,
            "project_code": project_code,
            "task_code": task_code,
            "request": request,
            "filenames": [item.filename for item in files],
            "contents": [item.file_handle.read() for item in files],
        })
        return ImageryAssetBatchResponse(
            batch_code=request.batch_code,
            item_count=len(files),
            total_size_bytes=sum(len(content) for content in captured["contents"]),
            manifest_sha256="a" * 64,
            imported_by="李静",
            imported_by_code=request.operator_code,
            imported_by_role="interpreter",
            comment=request.comment,
            created_at=datetime.now(UTC),
            items=[],
        )

    service = SimpleNamespace(upload_assets_batch=upload_assets_batch)
    monkeypatch.setattr(imagery_endpoint, "asset_service", service)
    app = FastAPI()
    app.include_router(imagery_endpoint.router)
    db = AsyncMock()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    manifest = {
        "batch_code": "IMB-API-TEST",
        "operator_code": "interp-li-jing",
        "comment": "验证 multipart 批量端点只调用一次业务服务",
        "items": [
            {
                "filename": "api_a.tif",
                "asset_code": "API-A",
                "asset_name": "接口影像 A",
            },
            {
                "filename": "api_b.img",
                "asset_code": "API-B",
                "asset_name": "接口影像 B",
            },
        ],
    }
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/imagery-assets/batch",
            params={"project_code": "RS-2026", "task_code": "RS-2026-045"},
            files=[
                ("files", ("api_a.tif", b"first-content", "image/tiff")),
                (
                    "files",
                    ("api_b.img", b"second-content", "application/octet-stream"),
                ),
                ("manifest_json", (None, json.dumps(manifest))),
            ],
        )

    assert response.status_code == 201
    assert response.json()["batch_code"] == "IMB-API-TEST"
    assert captured["project_code"] == "RS-2026"
    assert captured["task_code"] == "RS-2026-045"
    assert captured["filenames"] == ["api_a.tif", "api_b.img"]
    assert captured["contents"] == [b"first-content", b"second-content"]
    assert isinstance(captured["request"], ImageryAssetBatchCreateRequest)


def test_batch_upload_rolls_back_all_files_when_one_raster_is_invalid(
    tmp_path: Path,
) -> None:
    """验证批次中任一文件损坏时不发布前序文件且不写任何资产。"""
    service, dao, _ = build_service(tmp_path)
    request = ImageryAssetBatchCreateRequest.model_validate({
        "batch_code": "IMB-TEST-ROLLBACK",
        "operator_code": "interp-li-jing",
        "comment": "验证第二个文件失败时整批实体和数据库回滚",
        "items": [
            {
                "filename": "valid.tif",
                "asset_code": "BATCH-VALID",
                "asset_name": "有效影像",
                "data_status": "demo",
            },
            {
                "filename": "broken.tif",
                "asset_code": "BATCH-BROKEN",
                "asset_name": "损坏影像",
                "sensor_type": "BROKEN",
                "acquired_at": "2026-06-19T00:00:00Z",
                "data_status": "demo",
            },
        ],
    })
    db = AsyncMock()

    with pytest.raises(
        ValidationException,
        match="格式扩展名不一致|无法识别|文件已损坏",
    ):
        asyncio.run(
            service.upload_assets_batch(
                db,
                "RS-2026",
                "RS-2026-045",
                request,
                [
                    ImageryBatchUploadFile(
                        "valid.tif",
                        BytesIO(build_geotiff_bytes()),
                    ),
                    ImageryBatchUploadFile("broken.tif", BytesIO(b"broken")),
                ],
            )
        )

    assert not list(tmp_path.glob("assets/**/*"))
    dao.add_asset.assert_not_awaited()
    dao.add_import_batch.assert_not_awaited()
    db.rollback.assert_awaited_once()


def test_batch_upload_rejects_duplicate_file_content(tmp_path: Path) -> None:
    """验证不同文件名和资产编号也不能绕过批内 SHA256 去重。"""
    service, dao, _ = build_service(tmp_path)
    request = ImageryAssetBatchCreateRequest.model_validate({
        "batch_code": "IMB-TEST-DUPLICATE-SHA",
        "operator_code": "interp-li-jing",
        "comment": "验证批次内相同实体内容必须整批拒绝并回滚",
        "items": [
            {
                "filename": "duplicate_a.tif",
                "asset_code": "BATCH-DUPLICATE-A",
                "asset_name": "重复实体 A",
                "data_status": "demo",
            },
            {
                "filename": "duplicate_b.tif",
                "asset_code": "BATCH-DUPLICATE-B",
                "asset_name": "重复实体 B",
                "data_status": "demo",
            },
        ],
    })
    content = build_geotiff_bytes()
    db = AsyncMock()

    with pytest.raises(ValidationException, match="同批其他文件内容重复"):
        asyncio.run(
            service.upload_assets_batch(
                db,
                "RS-2026",
                "RS-2026-045",
                request,
                [
                    ImageryBatchUploadFile("duplicate_a.tif", BytesIO(content)),
                    ImageryBatchUploadFile("duplicate_b.tif", BytesIO(content)),
                ],
            )
        )

    assert not list(tmp_path.glob("assets/**/*"))
    dao.add_asset.assert_not_awaited()
    dao.add_import_batch.assert_not_awaited()
    db.rollback.assert_awaited_once()


def test_batch_publish_never_overwrites_existing_target(tmp_path: Path) -> None:
    """验证并发目标冲突时原子发布不会覆盖另一批次的实体。"""
    temporary_path = tmp_path / ".uploads" / "pending.tif.part"
    final_path = tmp_path / "assets" / "BATCH-RACE" / "source.tif"
    temporary_path.parent.mkdir(parents=True)
    final_path.parent.mkdir(parents=True)
    temporary_path.write_bytes(b"new-batch-content")
    final_path.write_bytes(b"committed-batch-content")
    item = SimpleNamespace(
        temporary_path=temporary_path,
        final_path=final_path,
        request=SimpleNamespace(asset_code="BATCH-RACE"),
    )

    with pytest.raises(ValidationException, match="目标文件已存在"):
        ImageryAssetService._publish_prepared_file(item)

    assert final_path.read_bytes() == b"committed-batch-content"
    assert temporary_path.read_bytes() == b"new-batch-content"


def test_upload_accepts_rpc_only_imagery_and_derives_wgs84_footprint(
    tmp_path: Path,
) -> None:
    """验证无普通 CRS 的 RPC 原始影像可入库并保留传感器模型。"""
    service, _, _ = build_service(tmp_path)

    response = asyncio.run(
        service.upload_asset(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            build_create_request(),
            "rpc_source.tif",
            BytesIO(build_rpc_geotiff_bytes()),
        )
    )

    assert response.file_verified is True
    assert response.crs == "RPC:WGS84"
    assert response.raster_metadata["has_rpc"] is True
    assert response.raster_metadata["rpc_summary"]["error_bias"] == 0.5
    assert response.footprint is not None
    coordinates = response.footprint["coordinates"][0]
    assert coordinates[0] == pytest.approx([126.55, 45.76])
    assert coordinates[2] == pytest.approx([126.65, 45.84])
    stored_path = tmp_path / "assets/GF2-TEST-001/rpc_source.tif"
    with rasterio.open(stored_path) as dataset:
        assert dataset.crs is None
        assert dataset.rpcs is not None


def test_upload_uses_audited_user_fallback_when_tags_are_missing(
    tmp_path: Path,
) -> None:
    """验证文件缺少业务标签时允许人工补录并记录来源。"""
    service, _, _ = build_service(tmp_path)
    acquired_at = datetime(2026, 6, 18, 10, 42, tzinfo=UTC)

    response = asyncio.run(
        service.upload_asset(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            build_create_request(
                sensor_type="GF2 PMS1",
                acquired_at=acquired_at,
                cloud_cover=2.3,
                processing_level="L1A",
            ),
            "manual_metadata.tif",
            BytesIO(build_geotiff_bytes(tags={})),
        )
    )

    assert response.sensor_type == "GF2 PMS1"
    assert response.acquired_at == acquired_at
    assert response.cloud_cover == 2.3
    assert response.processing_level == "L1A"
    business_metadata = response.raster_metadata["business_metadata"]
    assert business_metadata["sensor_type"]["source"] == "user_fallback"
    assert business_metadata["acquired_at"]["source"] == "user_fallback"
    assert business_metadata["processing_level"]["source"] == "user_fallback"
    assert business_metadata["cloud_cover"]["source"] == "user_fallback"


def test_upload_extracts_case_insensitive_common_aliases(tmp_path: Path) -> None:
    """验证常见平台、载荷、时间、级别和云量别名大小写无关。"""
    service, _, _ = build_service(tmp_path)

    response = asyncio.run(
        service.upload_asset(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            build_create_request(),
            "sentinel_aliases.tif",
            BytesIO(build_geotiff_bytes(tags={
                "platform": "Sentinel-2A",
                "instrument": "MSI",
                "acquisition_time": "2026-06-18T10:42:00Z",
                "product_level": "L2A",
                "cloudy_pixel_percentage": "3.1%",
            })),
        )
    )

    assert response.sensor_type == "Sentinel-2A MSI"
    assert response.acquired_at == datetime(2026, 6, 18, 10, 42, tzinfo=UTC)
    assert response.processing_level == "L2A"
    assert response.cloud_cover == 3.1
    audit = response.raster_metadata["business_metadata"]
    assert audit["sensor_type"]["raster_tag"] == "platform+instrument"
    assert audit["acquired_at"]["raster_tag"] == "acquisition_time"


def test_upload_requires_sensor_and_time_when_file_tags_are_missing(
    tmp_path: Path,
) -> None:
    """验证文件与人工均未提供必填业务元数据时拒绝入库。"""
    service, dao, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="传感器元数据"):
        asyncio.run(
            service.upload_asset(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                build_create_request(),
                "missing_business_metadata.tif",
                BytesIO(build_geotiff_bytes(tags={})),
            )
        )

    dao.add_asset.assert_not_awaited()


def test_upload_extracts_business_metadata_from_tag_namespace(
    tmp_path: Path,
) -> None:
    """验证 HDF/产品命名空间中的业务标签也可被提取并审计。"""
    service, _, _ = build_service(tmp_path)

    response = asyncio.run(
        service.upload_asset(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            build_create_request(),
            "namespace_metadata.tif",
            BytesIO(build_geotiff_bytes(
                tags={},
                namespaced_tags={
                    "PRODUCT": {
                        "SPACECRAFT_NAME": "LANDSAT_9",
                        "SENSOR_ID": "OLI_TIRS",
                        "DATE_ACQUIRED": "2026-06-18",
                        "CLOUD_COVER": "4.5",
                    },
                },
            )),
        )
    )

    assert response.sensor_type == "LANDSAT_9 OLI_TIRS"
    assert response.cloud_cover == 4.5
    audit = response.raster_metadata["business_metadata"]
    assert audit["sensor_type"]["raster_tag"] == (
        "PRODUCT:SPACECRAFT_NAME+PRODUCT:SENSOR_ID"
    )
    assert response.raster_metadata["tag_namespaces"]["PRODUCT"][
        "DATE_ACQUIRED"
    ] == "2026-06-18"


def test_upload_rejects_sensor_conflict_and_cleans_file(tmp_path: Path) -> None:
    """验证人工传感器与文件标签冲突时整次入库失败。"""
    service, dao, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="传感器.*不一致"):
        asyncio.run(
            service.upload_asset(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                build_create_request(sensor_type="OTHER-SAT"),
                "sensor_conflict.tif",
                BytesIO(build_geotiff_bytes()),
            )
        )

    dao.add_asset.assert_not_awaited()
    assert not list(tmp_path.glob("assets/**/*"))


def test_upload_rejects_acquired_at_conflict(tmp_path: Path) -> None:
    """验证人工采集日期与文件日期不一致时拒绝入库。"""
    service, dao, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="采集时间.*不一致"):
        asyncio.run(
            service.upload_asset(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                build_create_request(
                    acquired_at=datetime(2026, 6, 19, tzinfo=UTC),
                ),
                "time_conflict.tif",
                BytesIO(build_geotiff_bytes()),
            )
        )

    dao.add_asset.assert_not_awaited()


def test_upload_accepts_user_time_refinement_for_date_only_tag(
    tmp_path: Path,
) -> None:
    """验证文件仅提供日期时可由人工补充同日精确时间。"""
    service, _, _ = build_service(tmp_path)
    acquired_at = datetime(2026, 6, 18, 10, 42, tzinfo=UTC)

    response = asyncio.run(
        service.upload_asset(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            build_create_request(acquired_at=acquired_at),
            "time_refinement.tif",
            BytesIO(build_geotiff_bytes()),
        )
    )

    assert response.acquired_at == acquired_at
    acquired_audit = response.raster_metadata["business_metadata"]["acquired_at"]
    assert acquired_audit["source"] == "user_refinement:raster_tag:ACQUIRED"
    assert acquired_audit["precision"] == "date"


def test_upload_rejects_invalid_cloud_tag(tmp_path: Path) -> None:
    """验证文件声明非法云量时不得静默改用人工值。"""
    service, dao, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="CLOUD_COVER.*0 到 100"):
        asyncio.run(
            service.upload_asset(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                build_create_request(cloud_cover=2.0),
                "invalid_cloud.tif",
                BytesIO(build_geotiff_bytes(tags={
                    "SATELLITE": "TEST-SAT",
                    "ACQUIRED": "2026-06-18",
                    "CLOUD_COVER": "125",
                })),
            )
        )

    dao.add_asset.assert_not_awaited()


def test_upload_rejects_raster_without_crs_and_cleans_file(tmp_path: Path) -> None:
    """验证缺少 CRS 的影像被拒绝且不会遗留资产文件。"""
    service, dao, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="缺少 CRS"):
        asyncio.run(
            service.upload_asset(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                build_create_request(),
                "missing_crs.tif",
                BytesIO(build_geotiff_bytes(include_crs=False)),
            )
        )

    dao.add_asset.assert_not_awaited()
    assert not list(tmp_path.glob("assets/**/*"))


def test_asset_list_marks_metadata_only_record() -> None:
    """验证没有真实文件的历史元数据记录明确标记为不可用。"""
    asset = ImageryAsset(
        id=1,
        project_id=7,
        asset_code="GF2-METADATA",
        asset_name="历史元数据",
        sensor_type="GF2",
        acquired_at=datetime(2026, 6, 18, tzinfo=UTC),
        calibration_status="pending",
        correction_status="pending",
        data_status="operational",
        raster_metadata={},
        created_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.list_assets.return_value = [{ImageryAsset: asset, "footprint": None}]
    workbench_dao = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=7)
    service = ImageryAssetService(dao=dao, workbench_dao=workbench_dao)

    response = asyncio.run(service.list_assets(AsyncMock(), "RS-2026"))

    assert response.total == 1
    assert response.available == 0
    assert response.metadata_only == 1
    assert response.items[0].file_error == "仅有元数据，未关联实体文件"
