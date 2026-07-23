"""多源数据资产实体上传、核验、下载和生产门禁测试。"""

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
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
from rasterio.transform import from_origin
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.endpoints import production as production_endpoint
from app.core.database import get_db
from app.core.dataset_files import inspect_dataset_file
from app.core.exceptions import NotFoundException, ValidationException
from app.models.workbench import DatasetAsset
from app.schemas.production import (
    DatasetAssetResponse,
    DatasetAssetUploadRequest,
    DatasetAssetVerifyRequest,
    ProductionBatchCreateRequest,
)
from app.services.dataset_asset_service import DatasetAssetService
from app.services.production_service import ProductionService


def build_asset(
    *,
    checksum: str,
    verification_status: str = "pending",
) -> DatasetAsset:
    """构造测试数据资产模型。"""
    return DatasetAsset(
        id=10,
        project_id=1,
        task_id=2,
        asset_code="DATASET-001",
        asset_name="测试数据资产",
        asset_type="table",
        source_name="公开测试来源",
        source_uri="https://example.test/source.csv",
        source_version="2026-07",
        checksum_sha256=checksum,
        crs="EPSG:4326",
        extent=None,
        time_start=None,
        time_end=None,
        security_classification="public",
        data_status="operational",
        verification_status=verification_status,
        metadata_payload={},
        registered_by="赵志远",
        registered_by_code="manager-zhao-zhiyuan",
        registered_by_role="project_manager",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def asset_row(asset: DatasetAsset) -> dict[object, object]:
    """构造包含空空间范围的 DAO 映射行。"""
    return {
        DatasetAsset: asset,
        "min_lon": None,
        "min_lat": None,
        "max_lon": None,
        "max_lat": None,
    }


def build_service(
    tmp_path: Path,
) -> tuple[DatasetAssetService, AsyncMock, AsyncMock, AsyncMock]:
    """构造带固定项目身份的实体服务。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=1)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=2,
        project_id=1,
    )
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )
    service = DatasetAssetService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        storage_root=tmp_path,
    )
    return service, dao, workbench_dao, user_service


def build_upload_request() -> DatasetAssetUploadRequest:
    """构造直接上传登记请求。"""
    return DatasetAssetUploadRequest(
        asset_code="DATASET-001",
        asset_name="测试数据资产",
        asset_type="table",
        source_name="公开测试来源",
        source_uri="https://example.test/source.csv",
        source_version="2026-07",
        crs="EPSG:4326",
        security_classification="public",
        operator_code="manager-zhao-zhiyuan",
        verification_comment="依据公开交接清单上传并核验实体文件",
    )


def test_verification_comment_rejects_whitespace_only_basis() -> None:
    """验证核验依据按清理后的实际字符数执行门禁。"""
    payload = build_upload_request().model_dump()
    payload["verification_comment"] = " " * 10

    with pytest.raises(ValidationError, match="至少填写 10 个字符"):
        DatasetAssetUploadRequest(**payload)


def test_raster_inspection_uses_original_suffix_for_part_file(tmp_path: Path) -> None:
    """验证临时 `.part` 文件仍按原始 GeoTIFF 扩展名检查签名。"""
    path = tmp_path / "upload.part"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=4,
        height=3,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(126, 46, 0.01, 0.01),
    ) as dataset:
        dataset.write(np.arange(12, dtype="uint8").reshape(3, 4), 1)

    inspection = inspect_dataset_file(
        path,
        "imagery",
        "source.tif",
        "image/tiff",
        1024 * 1024,
    )

    assert inspection.suffix == ".tif"
    assert inspection.metadata["driver"] == "GTiff"


def test_upload_registration_publishes_verified_entity(tmp_path: Path) -> None:
    """验证直接上传由服务端计算校验值并原子登记为已核验。"""
    service, dao, _, _ = build_service(tmp_path)
    asset_holder: dict[str, DatasetAsset] = {}

    async def add_asset(_: object, asset: DatasetAsset) -> DatasetAsset:
        asset.id = 10
        asset_holder["asset"] = asset
        return asset

    async def add_verification(
        _: object,
        verification: object,
    ) -> object:
        return verification

    dao.get_asset_by_code.return_value = None
    dao.get_assets_by_codes.return_value = []
    dao.get_asset_by_checksum.return_value = None
    dao.add_asset.side_effect = add_asset
    dao.add_dataset_asset_verification.side_effect = add_verification
    dao.get_asset_row_by_code.side_effect = lambda *_: asset_row(asset_holder["asset"])
    dao.list_parent_asset_codes.return_value = []
    db = AsyncMock()
    content = b"district_code,temperature\n230102,-18.5\n"

    response = asyncio.run(
        service.register_uploaded_asset(
            db,
            "RS-2026",
            "RS-2026-045",
            build_upload_request(),
            "weather.csv",
            "text/csv",
            BytesIO(content),
        )
    )

    asset = asset_holder["asset"]
    assert response.verification_status == "verified"
    assert asset.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert asset.physical_checksum_sha256 == asset.checksum_sha256
    assert asset.physical_file_uri.startswith("storage://datasets/DATASET-001/")
    published = tmp_path / asset.physical_file_uri.removeprefix(
        "storage://datasets/"
    )
    assert published.read_bytes() == content
    db.commit.assert_awaited_once()


def test_checksum_mismatch_persists_rejection_without_file(tmp_path: Path) -> None:
    """验证补传校验值不一致时保存拒绝记录且不发布实体。"""
    service, dao, _, _ = build_service(tmp_path)
    asset = build_asset(checksum="a" * 64)
    dao.get_asset_by_code.return_value = asset
    dao.get_asset_by_code_for_update.return_value = asset
    dao.get_asset_row_by_code.return_value = asset_row(asset)
    dao.list_parent_asset_codes.return_value = []

    async def add_verification(
        _: object,
        verification: object,
    ) -> object:
        return verification

    dao.add_dataset_asset_verification.side_effect = add_verification
    db = AsyncMock()

    result = asyncio.run(
        service.verify_existing_asset(
            db,
            "RS-2026",
            "RS-2026-045",
            asset.asset_code,
            DatasetAssetVerifyRequest(
                operator_code="manager-zhao-zhiyuan",
                verification_comment="核对公开交接文件与目录登记校验值",
            ),
            "source.csv",
            "text/csv",
            BytesIO(b"code,value\n1,2\n"),
        )
    )

    assert result.verification_status == "rejected"
    assert result.checksum_match is False
    assert asset.verification_status == "rejected"
    verification = dao.add_dataset_asset_verification.await_args.args[1]
    assert verification.file_uri is None
    assert verification.verification_error is not None
    assert not any(path.is_file() for path in tmp_path.rglob("*"))
    db.commit.assert_awaited_once()


def test_commit_failure_removes_published_dataset_file(tmp_path: Path) -> None:
    """验证数据库提交失败会删除已发布实体和临时文件。"""
    service, dao, _, _ = build_service(tmp_path)

    async def add_asset(_: object, asset: DatasetAsset) -> DatasetAsset:
        asset.id = 10
        return asset

    dao.get_asset_by_code.return_value = None
    dao.get_assets_by_codes.return_value = []
    dao.get_asset_by_checksum.return_value = None
    dao.add_asset.side_effect = add_asset
    dao.add_dataset_asset_verification.side_effect = (
        lambda _, verification: verification
    )
    db = AsyncMock()
    db.commit.side_effect = SQLAlchemyError("commit failed")

    with pytest.raises(ValidationException, match="登记失败"):
        asyncio.run(
            service.register_uploaded_asset(
                db,
                "RS-2026",
                "RS-2026-045",
                build_upload_request(),
                "source.csv",
                "text/csv",
                BytesIO(b"code,value\n1,2\n"),
            )
        )

    assert not any(path.is_file() for path in tmp_path.rglob("*"))
    db.rollback.assert_awaited_once()


def test_download_revalidation_detects_tampered_content(tmp_path: Path) -> None:
    """验证下载前重新计算 SHA-256 并拒绝被篡改实体。"""
    service, _, _, _ = build_service(tmp_path)
    original = b"code,value\n1,2\n"
    tampered = b"code,value\n1,9\n"
    path = tmp_path / "DATASET-001" / "verified.csv"
    path.parent.mkdir(parents=True)
    path.write_bytes(original)
    asset = build_asset(
        checksum=hashlib.sha256(original).hexdigest(),
        verification_status="verified",
    )
    asset.physical_file_uri = "storage://datasets/DATASET-001/verified.csv"
    asset.physical_original_filename = "source.csv"
    asset.physical_file_size_bytes = len(original)
    asset.physical_checksum_sha256 = asset.checksum_sha256
    asset.physical_media_type = "text/csv"
    asset.verified_at = datetime.now(UTC)
    asset.verified_by = "赵志远"
    asset.verified_by_code = "manager-zhao-zhiyuan"
    asset.verified_by_role = "project_manager"
    asset.verification_comment = "依据公开交接清单完成实体核验"
    path.write_bytes(tampered)

    with pytest.raises(ValidationException, match="SHA-256"):
        service.resolve_verified_file(asset)


def test_production_batch_rejects_unverified_imagery_asset() -> None:
    """验证生产批次不能绑定仅登记但未核验的影像目录项。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=1)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(id=2, project_id=1)
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )
    imagery = build_asset(checksum="a" * 64)
    imagery.asset_type = "imagery"
    dao.get_batch_by_code.return_value = None
    dao.get_asset_by_code.return_value = imagery
    service = ProductionService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        rule_service=AsyncMock(),
    )

    with pytest.raises(ValidationException, match="尚未通过实体核验"):
        asyncio.run(
            service.create_batch(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                ProductionBatchCreateRequest(
                    batch_code="BATCH-001",
                    batch_name="实体门禁测试批次",
                    source_asset_code=imagery.asset_code,
                    target_asset_code=None,
                    planned_start_date=date(2026, 7, 1),
                    planned_end_date=date(2026, 7, 31),
                    operator_code="manager-zhao-zhiyuan",
                ),
            )
        )


@pytest.mark.asyncio
async def test_dataset_upload_api_maps_multipart_to_entity_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证实体上传端点把文件与 JSON 清单一次交给业务服务。"""
    captured: dict[str, object] = {}
    now = datetime.now(UTC)
    response_asset = DatasetAssetResponse(
        asset_code="DATASET-API-001",
        asset_name="接口数据资产",
        asset_type="table",
        source_name="公开测试来源",
        source_uri="https://example.test/source.csv",
        source_version="2026-07",
        checksum_sha256="b" * 64,
        crs="EPSG:4326",
        extent_bbox=None,
        time_start=None,
        time_end=None,
        security_classification="public",
        data_status="operational",
        verification_status="verified",
        physical_file_uri="storage://datasets/DATASET-API-001/file.csv",
        physical_original_filename="api.csv",
        physical_file_size_bytes=8,
        physical_checksum_sha256="b" * 64,
        physical_media_type="text/csv",
        verified_at=now,
        verified_by="赵志远",
        verified_by_code="manager-zhao-zhiyuan",
        verified_by_role="project_manager",
        verification_comment="验证 multipart 实体上传接口映射",
        parent_asset_codes=[],
        metadata={},
        registered_by="赵志远",
        registered_by_code="manager-zhao-zhiyuan",
        registered_by_role="project_manager",
        created_at=now,
    )

    async def register_uploaded_asset(
        db: object,
        project_code: str,
        task_code: str,
        request: DatasetAssetUploadRequest,
        original_filename: str,
        reported_media_type: str | None,
        file_handle: object,
    ) -> DatasetAssetResponse:
        captured.update({
            "db": db,
            "project_code": project_code,
            "task_code": task_code,
            "request": request,
            "filename": original_filename,
            "media_type": reported_media_type,
            "content": file_handle.read(),
        })
        return response_asset

    monkeypatch.setattr(
        production_endpoint,
        "dataset_asset_service",
        SimpleNamespace(register_uploaded_asset=register_uploaded_asset),
    )
    app = FastAPI()
    app.include_router(production_endpoint.router)
    db = AsyncMock()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    payload = build_upload_request().model_dump(mode="json")
    payload["asset_code"] = "DATASET-API-001"
    payload["asset_name"] = "接口数据资产"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/production/dataset-assets/upload",
            params={"project_code": "RS-2026", "task_code": "RS-2026-045"},
            files=[
                ("file", ("api.csv", b"a,b\n1,2\n", "text/csv")),
                ("metadata_json", (None, json.dumps(payload))),
            ],
        )

    assert response.status_code == 201
    assert response.json()["asset_code"] == "DATASET-API-001"
    assert captured["filename"] == "api.csv"
    assert captured["content"] == b"a,b\n1,2\n"
    assert isinstance(captured["request"], DatasetAssetUploadRequest)


def test_verified_asset_missing_file_is_not_downloadable(tmp_path: Path) -> None:
    """验证数据库已核验状态不能替代真实受控实体。"""
    service, _, _, _ = build_service(tmp_path)
    asset = build_asset(checksum="a" * 64, verification_status="verified")
    asset.physical_file_uri = "storage://datasets/DATASET-001/missing.csv"
    asset.physical_original_filename = "missing.csv"
    asset.physical_file_size_bytes = 10
    asset.physical_checksum_sha256 = asset.checksum_sha256
    asset.physical_media_type = "text/csv"
    asset.verified_at = datetime.now(UTC)
    asset.verified_by = "赵志远"
    asset.verified_by_code = "manager-zhao-zhiyuan"
    asset.verified_by_role = "project_manager"
    asset.verification_comment = "依据公开交接清单完成实体核验"

    with pytest.raises(NotFoundException, match="实体不存在"):
        service.resolve_verified_file(asset)
