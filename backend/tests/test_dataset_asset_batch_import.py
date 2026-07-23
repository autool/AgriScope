"""多源数据资产 1–20 文件原子批量入库与交付复核测试。"""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.endpoints import production as production_endpoint
from app.core.database import get_db
from app.core.exceptions import ValidationException
from app.models.dataset_asset_import import (
    DatasetAssetImportBatch,
    DatasetAssetImportBatchItem,
)
from app.models.dataset_asset_verification import DatasetAssetVerification
from app.models.workbench import DatasetAsset
from app.schemas.production import (
    DatasetAssetBatchCreateRequest,
    DatasetAssetBatchItemRequest,
    DatasetAssetBatchResponse,
    DatasetAssetResponse,
)
from app.services.dataset_asset_batch_service import (
    DatasetAssetBatchService,
    DatasetAssetBatchUploadFile,
)
from app.services.dataset_asset_service import DatasetAssetService
from app.services.delivery_service import DeliveryService


def build_item(
    sequence: int,
    *,
    filename: str | None = None,
    parent_asset_codes: list[str] | None = None,
) -> DatasetAssetBatchItemRequest:
    """构造一个表格类批次成员。"""
    return DatasetAssetBatchItemRequest(
        filename=filename or f"source-{sequence}.csv",
        asset_code=f"DATASET-BATCH-{sequence:03d}",
        asset_name=f"批量数据资产 {sequence}",
        asset_type="table",
        source_name="黑龙江省公开业务交接目录",
        source_uri=f"https://example.test/datasets/source-{sequence}.csv",
        source_version="2026-07-23",
        crs="EPSG:4326",
        security_classification="public",
        data_status="operational",
        parent_asset_codes=parent_asset_codes or [],
        lineage_relation_type="derived_from",
        metadata={"business_scope": "原子批量入库测试"},
    )


def build_request(
    items: list[DatasetAssetBatchItemRequest] | None = None,
) -> DatasetAssetBatchCreateRequest:
    """构造合法批量入库请求。"""
    return DatasetAssetBatchCreateRequest(
        batch_code="DSBATCH-20260723-001",
        operator_code="manager-zhao-zhiyuan",
        comment="依据公开数据交接清单执行多源实体原子批量入库",
        items=items or [build_item(1), build_item(2)],
    )


def build_files(
    request: DatasetAssetBatchCreateRequest,
    contents: list[bytes] | None = None,
) -> list[DatasetAssetBatchUploadFile]:
    """按清单顺序构造 multipart 文件流。"""
    payloads = contents or [
        f"code,value\n{index},{index * 10}\n".encode()
        for index in range(1, len(request.items) + 1)
    ]
    return [
        DatasetAssetBatchUploadFile(
            filename=item.filename,
            file_handle=BytesIO(content),
            reported_media_type="text/csv",
        )
        for item, content in zip(request.items, payloads, strict=True)
    ]


def asset_row(asset: DatasetAsset) -> dict[object, object]:
    """构造包含空 WGS84 范围的资产查询行。"""
    return {
        DatasetAsset: asset,
        "min_lon": None,
        "min_lat": None,
        "max_lon": None,
        "max_lat": None,
    }


def build_service(
    tmp_path: Path,
) -> tuple[DatasetAssetBatchService, AsyncMock, AsyncMock, dict[str, object]]:
    """构造可观察资产、核验、批次和成员写入的批量服务。"""
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
    dao.get_dataset_import_batch_by_code.return_value = None
    dao.get_assets_by_codes.return_value = []
    dao.get_asset_by_code.return_value = None
    dao.get_asset_by_checksum.return_value = None
    dao.list_parent_asset_codes.return_value = []
    state: dict[str, object] = {
        "assets": {},
        "verifications": [],
        "batch_items": [],
        "lineages": [],
        "audit_events": [],
    }

    async def add_asset(_: object, asset: DatasetAsset) -> DatasetAsset:
        assets = state["assets"]
        assert isinstance(assets, dict)
        asset.id = len(assets) + 1
        assets[asset.asset_code] = asset
        return asset

    async def add_verification(
        _: object,
        verification: DatasetAssetVerification,
    ) -> DatasetAssetVerification:
        verifications = state["verifications"]
        assert isinstance(verifications, list)
        verification.id = len(verifications) + 101
        verifications.append(verification)
        return verification

    async def add_batch(
        _: object,
        batch: DatasetAssetImportBatch,
    ) -> DatasetAssetImportBatch:
        batch.id = 201
        state["batch"] = batch
        return batch

    async def add_batch_items(
        _: object,
        items: list[DatasetAssetImportBatchItem],
    ) -> None:
        state["batch_items"] = items

    async def add_lineages(_: object, items: list[object]) -> None:
        state["lineages"] = items

    async def add_audit_event(_: object, event: object) -> None:
        audit_events = state["audit_events"]
        assert isinstance(audit_events, list)
        audit_events.append(event)

    async def get_asset_row(
        _: object,
        __: int,
        asset_code: str,
    ) -> dict[object, object] | None:
        assets = state["assets"]
        assert isinstance(assets, dict)
        asset = assets.get(asset_code)
        return asset_row(asset) if isinstance(asset, DatasetAsset) else None

    dao.add_asset.side_effect = add_asset
    dao.add_dataset_asset_verification.side_effect = add_verification
    dao.add_dataset_import_batch.side_effect = add_batch
    dao.add_dataset_import_batch_items.side_effect = add_batch_items
    dao.add_lineages.side_effect = add_lineages
    dao.add_audit_event.side_effect = add_audit_event
    dao.get_asset_row_by_code.side_effect = get_asset_row
    asset_service = DatasetAssetService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        storage_root=tmp_path,
    )
    service = DatasetAssetBatchService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        asset_service=asset_service,
    )
    return service, dao, AsyncMock(), state


def test_batch_schema_rejects_trimmed_comment_limits_and_duplicates() -> None:
    """验证 1–20、清理后依据和批内文件/资产编号唯一性。"""
    with pytest.raises(ValidationError, match="至少填写 10 个字符"):
        DatasetAssetBatchCreateRequest(
            batch_code="DSBATCH-INVALID-COMMENT",
            operator_code="manager-zhao-zhiyuan",
            comment=" " * 12,
            items=[build_item(1)],
        )
    with pytest.raises(ValidationError):
        build_request([build_item(index) for index in range(1, 22)])
    with pytest.raises(ValidationError, match="重复文件名"):
        build_request([
            build_item(1, filename="SOURCE.csv"),
            build_item(2, filename="source.csv"),
        ])
    duplicate_code = build_item(2)
    duplicate_code.asset_code = "DATASET-BATCH-001"
    with pytest.raises(ValidationError, match="重复资产编号"):
        build_request([build_item(1), duplicate_code])
    with pytest.raises(ValidationError, match="路径片段"):
        build_item(1, filename="../source.csv")


def test_batch_rejects_file_manifest_count_mismatch(tmp_path: Path) -> None:
    """验证物理文件数量与清单不一致时在临时落盘前整批拒绝。"""
    service, _, db, _ = build_service(tmp_path)
    request = build_request()

    with pytest.raises(ValidationException, match="数量.*不一致"):
        asyncio.run(
            service.upload_assets_batch(
                db,
                "RS-2026",
                "RS-2026-045",
                request,
                build_files(request)[:1],
            )
        )

    assert not any(path.is_file() for path in tmp_path.rglob("*"))
    db.commit.assert_not_awaited()


def test_batch_rejects_duplicate_content_and_existing_checksum(
    tmp_path: Path,
) -> None:
    """验证批内相同内容与项目既有 SHA-256 都会整批拒绝并清理。"""
    service, dao, db, _ = build_service(tmp_path)
    request = build_request()
    duplicate_content = b"code,value\n1,10\n"

    with pytest.raises(ValidationException, match="内容重复"):
        asyncio.run(
            service.upload_assets_batch(
                db,
                "RS-2026",
                "RS-2026-045",
                request,
                build_files(request, [duplicate_content, duplicate_content]),
            )
        )
    assert not any(path.is_file() for path in tmp_path.rglob("*"))

    existing = SimpleNamespace(asset_code="EXISTING-ASSET")
    dao.get_asset_by_checksum.return_value = existing
    with pytest.raises(ValidationException, match="已登记为资产"):
        asyncio.run(
            service.upload_assets_batch(
                db,
                "RS-2026",
                "RS-2026-045",
                request,
                build_files(request),
            )
        )
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_batch_validates_internal_lineage_and_rejects_cycle(tmp_path: Path) -> None:
    """验证批内父资产可形成有向无环血缘，但循环必须在上传前拒绝。"""
    first = build_item(1, parent_asset_codes=["DATASET-BATCH-002"])
    second = build_item(2, parent_asset_codes=["DATASET-BATCH-001"])
    cyclic_request = build_request([first, second])
    service, _, db, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="不得形成循环"):
        asyncio.run(
            service.upload_assets_batch(
                db,
                "RS-2026",
                "RS-2026-045",
                cyclic_request,
                build_files(cyclic_request),
            )
        )
    assert not any(path.is_file() for path in tmp_path.rglob("*"))

    derived_request = build_request([
        build_item(1),
        build_item(2, parent_asset_codes=["DATASET-BATCH-001"]),
    ])
    service, _, db, state = build_service(tmp_path)
    result = asyncio.run(
        service.upload_assets_batch(
            db,
            "RS-2026",
            "RS-2026-045",
            derived_request,
            build_files(derived_request),
        )
    )

    assert result.item_count == 2
    lineages = state["lineages"]
    assert isinstance(lineages, list)
    assert len(lineages) == 1
    assert lineages[0].parent_asset_id == 1
    assert lineages[0].derived_asset_id == 2


def test_batch_success_persists_manifest_assets_verifications_and_audit(
    tmp_path: Path,
) -> None:
    """验证成功批次在一次提交内保存全部实体证据、成员顺序和审计。"""
    service, _, db, state = build_service(tmp_path)
    request = build_request()
    result = asyncio.run(
        service.upload_assets_batch(
            db,
            "RS-2026",
            "RS-2026-045",
            request,
            build_files(request),
        )
    )

    batch = state["batch"]
    assert isinstance(batch, DatasetAssetImportBatch)
    canonical = json.dumps(
        batch.manifest_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert batch.manifest_sha256 == hashlib.sha256(canonical).hexdigest()
    assert result.manifest_sha256 == batch.manifest_sha256
    assert result.item_count == 2
    assert result.total_size_bytes == sum(
        item.physical_file_size_bytes or 0 for item in result.items
    )
    batch_items = state["batch_items"]
    assert isinstance(batch_items, list)
    assert [item.sequence for item in batch_items] == [1, 2]
    verifications = state["verifications"]
    assert isinstance(verifications, list)
    assert all(item.verification_status == "verified" for item in verifications)
    audit_events = state["audit_events"]
    assert isinstance(audit_events, list)
    assert [event.action for event in audit_events].count(
        "batch_uploaded_and_verified"
    ) == 2
    assert audit_events[-1].action == "atomic_batch_imported"
    assert len(list(tmp_path.rglob("*.csv"))) == 2
    assert not list(tmp_path.rglob("*.part"))
    db.commit.assert_awaited_once()


def test_second_file_validation_failure_leaves_no_file_or_database_write(
    tmp_path: Path,
) -> None:
    """验证第二个成员格式失败时清除首个临时文件且不发布、不入库。"""
    request = build_request([
        build_item(1),
        build_item(2, filename="invalid.exe"),
    ])
    service, dao, db, _ = build_service(tmp_path)

    with pytest.raises(ValidationException):
        asyncio.run(
            service.upload_assets_batch(
                db,
                "RS-2026",
                "RS-2026-045",
                request,
                build_files(request),
            )
        )

    assert not any(path.is_file() for path in tmp_path.rglob("*"))
    dao.add_asset.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_commit_and_rollback_failures_still_remove_all_published_files(
    tmp_path: Path,
) -> None:
    """验证提交失败及回滚异常都不会遗留已发布实体。"""
    service, _, db, _ = build_service(tmp_path)
    request = build_request()
    db.commit.side_effect = SQLAlchemyError("commit failed")

    with pytest.raises(ValidationException, match="事务提交失败"):
        asyncio.run(
            service.upload_assets_batch(
                db,
                "RS-2026",
                "RS-2026-045",
                request,
                build_files(request),
            )
        )
    assert not any(path.is_file() for path in tmp_path.rglob("*"))

    service, _, db, _ = build_service(tmp_path)
    db.commit.side_effect = SQLAlchemyError("commit failed")
    db.rollback.side_effect = SQLAlchemyError("rollback failed")
    with pytest.raises(ValidationException, match="数据库回滚失败"):
        asyncio.run(
            service.upload_assets_batch(
                db,
                "RS-2026",
                "RS-2026-045",
                request,
                build_files(request),
            )
        )
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_exclusive_publish_never_overwrites_concurrent_target(tmp_path: Path) -> None:
    """验证排他发布遇到同名目标时保留并发文件且明确拒绝。"""
    service = DatasetAssetService(storage_root=tmp_path)
    prepared = service.prepare_upload(
        BytesIO(b"code,value\n1,2\n"),
        "source.csv",
        "table",
        "text/csv",
    )
    target = tmp_path / "DATASET-001" / "VERIFY-001.csv"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"concurrent-content")

    with pytest.raises(ValidationException, match="目标文件已存在"):
        service.publish_upload(prepared, "DATASET-001", "VERIFY-001")

    assert target.read_bytes() == b"concurrent-content"
    assert prepared.temporary_path.exists()


def build_api_asset(code: str, filename: str) -> DatasetAssetResponse:
    """构造批量端点返回的已核验资产。"""
    now = datetime.now(UTC)
    return DatasetAssetResponse(
        asset_code=code,
        asset_name=code,
        asset_type="table",
        source_name="公开测试来源",
        source_uri=f"https://example.test/{filename}",
        source_version="2026-07-23",
        checksum_sha256="a" * 64,
        crs="EPSG:4326",
        extent_bbox=None,
        time_start=None,
        time_end=None,
        security_classification="public",
        data_status="operational",
        verification_status="verified",
        physical_file_uri=f"storage://datasets/{code}/{filename}",
        physical_original_filename=filename,
        physical_file_size_bytes=8,
        physical_checksum_sha256="a" * 64,
        physical_media_type="text/csv",
        verified_at=now,
        verified_by="赵志远",
        verified_by_code="manager-zhao-zhiyuan",
        verified_by_role="project_manager",
        verification_comment="验证多文件原子上传端点只调用一次业务服务",
        parent_asset_codes=[],
        metadata={},
        registered_by="赵志远",
        registered_by_code="manager-zhao-zhiyuan",
        registered_by_role="project_manager",
        created_at=now,
    )


@pytest.mark.asyncio
async def test_batch_api_passes_all_files_to_service_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 multipart 端点一次性把全部文件和清单交给批量服务。"""
    calls: list[dict[str, object]] = []
    now = datetime.now(UTC)

    async def upload_assets_batch(
        db: object,
        project_code: str,
        task_code: str,
        request: DatasetAssetBatchCreateRequest,
        files: list[DatasetAssetBatchUploadFile],
    ) -> DatasetAssetBatchResponse:
        calls.append({
            "db": db,
            "project_code": project_code,
            "task_code": task_code,
            "request": request,
            "filenames": [item.filename for item in files],
            "contents": [item.file_handle.read() for item in files],
        })
        return DatasetAssetBatchResponse(
            batch_code=request.batch_code,
            item_count=2,
            total_size_bytes=16,
            manifest_sha256="b" * 64,
            imported_by="赵志远",
            imported_by_code=request.operator_code,
            imported_by_role="project_manager",
            comment=request.comment,
            created_at=now,
            items=[
                build_api_asset("DATASET-BATCH-001", "source-1.csv"),
                build_api_asset("DATASET-BATCH-002", "source-2.csv"),
            ],
        )

    monkeypatch.setattr(
        production_endpoint,
        "dataset_asset_batch_service",
        SimpleNamespace(upload_assets_batch=upload_assets_batch),
    )
    app = FastAPI()
    app.include_router(production_endpoint.router)
    db = AsyncMock()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    request = build_request()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/production/dataset-assets/batch",
            params={"project_code": "RS-2026", "task_code": "RS-2026-045"},
            files=[
                ("files", ("source-1.csv", b"a,b\n1,2\n", "text/csv")),
                ("files", ("source-2.csv", b"a,b\n3,4\n", "text/csv")),
                (
                    "manifest_json",
                    (None, json.dumps(request.model_dump(mode="json"))),
                ),
            ],
        )

    assert response.status_code == 201
    assert len(calls) == 1
    assert calls[0]["filenames"] == ["source-1.csv", "source-2.csv"]
    assert calls[0]["contents"] == [b"a,b\n1,2\n", b"a,b\n3,4\n"]


def build_delivery_source() -> tuple[dict[str, object], dict[str, object]]:
    """构造可通过交付复核的数据资产批次证据。"""
    now = datetime.now(UTC)
    metadata = build_item(1).model_dump(mode="json")
    payload = {
        "schema_version": "dataset-asset-batch-v1",
        "batch_code": "DSBATCH-DELIVERY-001",
        "operator_code": "manager-zhao-zhiyuan",
        "comment": "依据公开数据交接清单完成实体原子批量入库",
        "items": [{
            "sequence": 1,
            "metadata": metadata,
            "file_size_bytes": 18,
            "checksum_sha256": "c" * 64,
            "media_type": "text/csv",
            "inspection": {"suffix": ".csv"},
        }],
    }
    manifest_sha = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    batch = DatasetAssetImportBatch(
        id=1,
        project_id=1,
        task_id=2,
        batch_code="DSBATCH-DELIVERY-001",
        item_count=1,
        total_size_bytes=18,
        manifest_sha256=manifest_sha,
        manifest_payload=payload,
        imported_by="赵志远",
        imported_by_code="manager-zhao-zhiyuan",
        imported_by_role="project_manager",
        import_comment="依据公开数据交接清单完成实体原子批量入库",
        created_at=now,
    )
    asset = DatasetAsset(
        id=10,
        project_id=1,
        task_id=2,
        asset_code="DATASET-BATCH-001",
        asset_name="批量数据资产 1",
        asset_type="table",
        source_name="黑龙江省公开业务交接目录",
        source_uri="https://example.test/datasets/source-1.csv",
        source_version="2026-07-23",
        checksum_sha256="c" * 64,
        crs="EPSG:4326",
        extent=None,
        time_start=None,
        time_end=None,
        security_classification="public",
        data_status="operational",
        verification_status="verified",
        physical_file_uri="storage://datasets/DATASET-BATCH-001/source.csv",
        physical_original_filename="source-1.csv",
        physical_file_size_bytes=18,
        physical_checksum_sha256="c" * 64,
        physical_media_type="text/csv",
        verified_at=now,
        verified_by="赵志远",
        verified_by_code="manager-zhao-zhiyuan",
        verified_by_role="project_manager",
        verification_comment="依据公开数据交接清单完成实体原子批量入库",
        metadata_payload={
            "import_batch_code": batch.batch_code,
            "import_batch_sequence": 1,
            "import_manifest_sha256": manifest_sha,
        },
        registered_by="赵志远",
        registered_by_code="manager-zhao-zhiyuan",
        registered_by_role="project_manager",
        created_at=now,
        updated_at=now,
    )
    verification = DatasetAssetVerification(
        id=20,
        asset_id=asset.id,
        verification_code="DSVERIFY-DELIVERY-001",
        verification_status="verified",
        original_filename="source-1.csv",
        file_uri=asset.physical_file_uri,
        file_size_bytes=18,
        expected_checksum_sha256="c" * 64,
        computed_checksum_sha256="c" * 64,
        media_type="text/csv",
        inspection_metadata={"suffix": ".csv"},
        verification_error=None,
        operator="赵志远",
        operator_code="manager-zhao-zhiyuan",
        operator_role="project_manager",
        verification_comment="依据公开数据交接清单完成实体原子批量入库",
        created_at=now,
    )
    item = DatasetAssetImportBatchItem(
        id=30,
        batch_id=batch.id,
        asset_id=asset.id,
        verification_id=verification.id,
        sequence=1,
        original_filename="source-1.csv",
        file_size_bytes=18,
        checksum_sha256="c" * 64,
        created_at=now,
    )
    source = {
        "dataset_import_batches": [batch],
        "dataset_import_batch_items": [{
            DatasetAssetImportBatch: batch,
            DatasetAssetImportBatchItem: item,
            DatasetAsset: asset,
            DatasetAssetVerification: verification,
        }],
        "verified_dataset_files": [
            SimpleNamespace(asset_code=asset.asset_code)
        ],
    }
    return source, {
        "batch": batch,
        "item": item,
        "asset": asset,
        "verification": verification,
    }


@pytest.mark.parametrize(
    "tamper_kind",
    ["manifest", "member", "verification", "entity"],
)
def test_delivery_rejects_tampered_batch_evidence(tamper_kind: str) -> None:
    """验证清单、成员、核验或实体任一被篡改都会阻断交付。"""
    source, evidence = build_delivery_source()
    if tamper_kind == "manifest":
        batch = evidence["batch"]
        assert isinstance(batch, DatasetAssetImportBatch)
        batch.manifest_payload["comment"] = "被篡改的批次依据"
    elif tamper_kind == "member":
        item = evidence["item"]
        assert isinstance(item, DatasetAssetImportBatchItem)
        item.file_size_bytes = 19
    elif tamper_kind == "verification":
        verification = evidence["verification"]
        assert isinstance(verification, DatasetAssetVerification)
        verification.verification_status = "rejected"
    else:
        source["verified_dataset_files"] = []

    with pytest.raises(ValidationException):
        DeliveryService._build_dataset_import_batch_catalog(source)


def test_delivery_builds_ordered_batch_catalog_from_verified_evidence() -> None:
    """验证交付目录保留规范化清单、成员顺序和稳定核验身份。"""
    source, _ = build_delivery_source()

    catalog = DeliveryService._build_dataset_import_batch_catalog(source)

    assert len(catalog) == 1
    assert catalog[0]["batch_code"] == "DSBATCH-DELIVERY-001"
    assert catalog[0]["members"][0]["sequence"] == 1
    assert (
        catalog[0]["members"][0]["verification_code"]
        == "DSVERIFY-DELIVERY-001"
    )
