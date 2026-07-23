"""外业核查实体证据上传、复核、权限和审计测试。"""

import asyncio
import hashlib
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openpyxl import Workbook

from app.core.exceptions import ValidationException
from app.models.workbench import FieldVerificationArtifact
from app.schemas.field_verification import FieldResolutionRequest
from app.services.field_verification_artifact_service import (
    FieldVerificationArtifactService,
)
from app.services.field_verification_service import FieldVerificationService


def build_service(
    tmp_path: Path,
) -> tuple[
    FieldVerificationArtifactService,
    AsyncMock,
    AsyncMock,
    AsyncMock,
    AsyncMock,
]:
    """构造带稳定用户和外业记录上下文的实体证据服务。

    Args:
        tmp_path: 测试受控存储目录。

    Returns:
        tuple: 服务、证据 DAO、外业 DAO、工作台 DAO 和用户服务。
    """
    artifact_dao = AsyncMock()
    artifact_dao.find_duplicate_for_update.return_value = None

    async def add_artifact(
        _: object,
        artifact: FieldVerificationArtifact,
    ) -> FieldVerificationArtifact:
        artifact.id = 17
        return artifact

    artifact_dao.add_artifact.side_effect = add_artifact
    field_dao = AsyncMock()
    field_dao.get_by_code_for_update.return_value = SimpleNamespace(
        id=5,
        task_id=3,
        verification_code="FV-REAL-001",
    )
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_id.return_value = SimpleNamespace(
        id=3,
        project_id=9,
        status="interpreting",
        updated_at=datetime(2026, 7, 23, tzinfo=UTC),
    )
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="张强",
        user_code="field-zhang-qiang",
        role_code="field_inspector",
    )
    service = FieldVerificationArtifactService(
        dao=artifact_dao,
        field_dao=field_dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        storage_root=tmp_path / "field-evidence",
    )
    return service, artifact_dao, field_dao, workbench_dao, user_service


def test_upload_photo_persists_verified_entity_and_audit(tmp_path: Path) -> None:
    """验证现场照片由服务端计算大小与 SHA 并原子登记上传事件。"""
    service, dao, _, workbench_dao, user_service = build_service(tmp_path)
    db = AsyncMock()

    async def refresh(artifact: FieldVerificationArtifact) -> None:
        artifact.created_at = datetime(2026, 7, 23, 8, 30, tzinfo=UTC)

    db.refresh.side_effect = refresh
    content = b"\x89PNG\r\n\x1a\nverified-field-photo"

    response = asyncio.run(
        service.upload_artifact(
            db,
            "FV-REAL-001",
            "photo",
            "field-zhang-qiang",
            "手持终端朝北拍摄，原始照片直传",
            "现场照片.png",
            "image/png",
            BytesIO(content),
        )
    )

    artifact = dao.add_artifact.await_args.args[1]
    stored_path = service.storage_root / artifact.file_uri.removeprefix(
        "storage://field-evidence/"
    )
    assert stored_path.read_bytes() == content
    assert artifact.file_size_bytes == len(content)
    assert artifact.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert artifact.media_type == "image/png"
    assert response.artifact_code == artifact.artifact_code
    assert response.download_url.endswith(
        f"/{artifact.artifact_code}/download"
    )
    event = dao.add_event.await_args.args[1]
    assert event.event_type == "uploaded"
    assert event.actor_code == "field-zhang-qiang"
    assert event.detail["checksum_sha256"] == artifact.checksum_sha256
    user_service.require_capability.assert_awaited_once_with(
        db,
        9,
        "field-zhang-qiang",
        "upload_field_data",
    )
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_import_workbook_is_physically_persisted_and_deduplicated(
    tmp_path: Path,
) -> None:
    """验证原始外业 XLSX 按内容校验值保存且重复导入复用实体。"""
    service, _, _, _, _ = build_service(tmp_path)
    workbook = Workbook()
    workbook.active["A1"] = "外业核查原始工作簿"
    buffer = BytesIO()
    workbook.save(buffer)
    content = buffer.getvalue()

    first = service.store_import_workbook("外业批次.xlsx", content)
    second = service.store_import_workbook("重命名批次.xlsx", content)

    assert first.created_new is True
    assert second.created_new is False
    assert first.path == second.path
    assert first.path.read_bytes() == content
    assert first.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert first.file_uri.startswith("storage://field-evidence/imports/")
    record = SimpleNamespace(
        source_file_uri=first.file_uri,
        source_file_size_bytes=first.file_size_bytes,
        source_checksum_sha256=first.checksum_sha256,
        source_name="省级外业采集 App",
        source_version="2026-07-23",
        import_batch_code="FIELD-BATCH-001",
    )
    structured_record = SimpleNamespace(
        source_file_uri=None,
        source_file_size_bytes=None,
        source_checksum_sha256="b" * 64,
    )

    verified = asyncio.run(
        service.load_verified_import_workbooks(
            [(record, "point"), (record, "point"), (structured_record, "point")]
        )
    )

    assert len(verified) == 1
    assert verified[0].path == first.path


def test_upload_rejects_fake_image_signature_without_residue(tmp_path: Path) -> None:
    """验证伪装成 PNG 的文本不会进入数据库或受控目录。"""
    service, dao, _, _, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="实体签名"):
        asyncio.run(
            service.upload_artifact(
                AsyncMock(),
                "FV-REAL-001",
                "photo",
                "field-zhang-qiang",
                "现场照片",
                "fake.png",
                "image/png",
                BytesIO(b"not-a-real-png"),
            )
        )

    dao.add_artifact.assert_not_awaited()
    assert not list(service.storage_root.rglob("*.part"))
    assert not list(service.storage_root.rglob("FIELD-EV-*"))


def test_upload_duplicate_checksum_returns_existing_without_publishing_file(
    tmp_path: Path,
) -> None:
    """验证移动网络重试同一实体时幂等返回已有证据。"""
    service, dao, _, _, _ = build_service(tmp_path)
    dao.find_duplicate_for_update.return_value = SimpleNamespace(
        artifact_code="FIELD-EV-EXISTING",
        artifact_type="photo",
        original_filename="现场照片.jpg",
        media_type="image/jpeg",
        file_size_bytes=16,
        checksum_sha256="a" * 64,
        description="首次上传现场照片",
        uploaded_by="张强",
        uploaded_by_code="field-zhang-qiang",
        uploaded_by_role="field_inspector",
        created_at=datetime(2026, 7, 23, tzinfo=UTC),
    )
    db = AsyncMock()

    response = asyncio.run(
        service.upload_artifact(
            db,
            "FV-REAL-001",
            "photo",
            "field-zhang-qiang",
            "重复照片",
            "duplicate.jpg",
            "image/jpeg",
            BytesIO(b"\xff\xd8\xffverified-jpeg"),
        )
    )

    assert response.artifact_code == "FIELD-EV-EXISTING"
    dao.add_artifact.assert_not_awaited()
    db.rollback.assert_not_awaited()
    assert not list(service.storage_root.rglob("FIELD-EV-*"))


def test_download_revalidates_entity_and_records_stable_user_event(
    tmp_path: Path,
) -> None:
    """验证下载前复核实体并记录下载人稳定编码与角色。"""
    service, dao, _, workbench_dao, user_service = build_service(tmp_path)
    content = b"%PDF-1.7\nverified-field-form"
    path = service.storage_root / "FV-REAL-001" / "FIELD-EV-FORM.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    artifact = SimpleNamespace(
        id=21,
        field_verification_id=5,
        artifact_code="FIELD-EV-FORM",
        artifact_type="form",
        original_filename="调查表.pdf",
        media_type="application/pdf",
        file_uri="storage://field-evidence/FV-REAL-001/FIELD-EV-FORM.pdf",
        file_size_bytes=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )
    record = SimpleNamespace(id=5, task_id=3)
    dao.get_artifact_record.return_value = (artifact, record)
    workbench_dao.get_task_by_id.return_value = SimpleNamespace(
        id=3,
        project_id=9,
    )
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="王海峰",
        user_code="quality-wang-haifeng",
        role_code="quality_inspector",
    )
    db = AsyncMock()

    download = asyncio.run(
        service.get_artifact_for_download(
            db,
            "FV-REAL-001",
            "FIELD-EV-FORM",
            "quality-wang-haifeng",
        )
    )

    assert download.path == path
    assert download.checksum_sha256 == artifact.checksum_sha256
    event = dao.add_event.await_args.args[1]
    assert event.event_type == "downloaded"
    assert event.actor_code == "quality-wang-haifeng"
    user_service.require_capability.assert_awaited_once_with(
        db,
        9,
        "quality-wang-haifeng",
        "view_field_evidence",
    )
    db.commit.assert_awaited_once()


def test_download_rejects_tampered_entity_before_audit(tmp_path: Path) -> None:
    """验证实体内容被改写后下载失败且不写成功事件。"""
    service, dao, _, workbench_dao, _ = build_service(tmp_path)
    path = service.storage_root / "FV-REAL-001" / "FIELD-EV-PHOTO.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\ntampered")
    artifact = SimpleNamespace(
        id=22,
        field_verification_id=5,
        artifact_code="FIELD-EV-PHOTO",
        artifact_type="photo",
        original_filename="现场照片.png",
        media_type="image/png",
        file_uri="storage://field-evidence/FV-REAL-001/FIELD-EV-PHOTO.png",
        file_size_bytes=path.stat().st_size,
        checksum_sha256="0" * 64,
    )
    dao.get_artifact_record.return_value = (
        artifact,
        SimpleNamespace(id=5, task_id=3),
    )
    workbench_dao.get_task_by_id.return_value = SimpleNamespace(
        id=3,
        project_id=9,
    )

    with pytest.raises(ValidationException, match="SHA-256"):
        asyncio.run(
            service.get_artifact_for_download(
                AsyncMock(),
                "FV-REAL-001",
                "FIELD-EV-PHOTO",
                "quality-wang-haifeng",
            )
        )

    dao.add_event.assert_not_awaited()


def test_field_issue_resolution_requires_verified_photo() -> None:
    """验证历史照片 URL 不能绕过外业疑点实体证据门禁。"""
    field_dao = AsyncMock()
    field_dao.get_by_code_for_update.return_value = SimpleNamespace(
        id=5,
        task_id=3,
        verification_code="FV-REAL-001",
        match_status="offset",
        resolution_status="pending",
    )
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_id_for_update.return_value = SimpleNamespace(
        id=3,
        project_id=9,
    )
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="王海峰",
        user_code="quality-wang-haifeng",
        role_code="quality_inspector",
    )
    artifact_dao = AsyncMock()
    artifact_dao.count_by_record_type.return_value = 0
    service = FieldVerificationService(
        dao=field_dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
        artifact_dao=artifact_dao,
    )

    with pytest.raises(ValidationException, match="至少一张"):
        asyncio.run(
            service.resolve_record(
                AsyncMock(),
                "FV-REAL-001",
                FieldResolutionRequest(
                    decision="keep_internal",
                    reviewer_code="quality-wang-haifeng",
                    comment="复核影像后保留内业结论",
                ),
            )
        )

    workbench_dao.get_plot_by_code.assert_not_awaited()
