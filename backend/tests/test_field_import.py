"""外业核查 CSV 批量导入业务测试。"""

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openpyxl import Workbook
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.schemas.field_verification import (
    FieldVerificationBatchImportRequest,
    FieldVerificationFileImportMetadata,
)
from app.services.field_verification_service import FieldVerificationService
from app.services.field_workbook_parser import (
    ALL_HEADERS,
    FieldVerificationWorkbookParser,
)


def build_xlsx_bytes(
    *,
    captured_at: object = "2026-07-22T09:30:00+08:00",
    verification_code: object = "FV-XLSX-001",
) -> bytes:
    """构造一条标准外业核查 XLSX 文件。

    Args:
        captured_at: 采集时间单元格值。
        verification_code: 核查编号单元格值。

    Returns:
        bytes: XLSX 实体文件。
    """
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "外业核查导入"
    worksheet.append(list(ALL_HEADERS))
    worksheet.append(
        [
            verification_code,
            "mobile-xlsx-001",
            126.45,
            45.75,
            "耕地",
            "玉米",
            captured_at,
            "https://files.example/field/xlsx-001.jpg",
            "",
            "Excel 导入测试",
        ]
    )
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def build_import_request() -> FieldVerificationBatchImportRequest:
    """构造两条带照片证据的外业批量导入请求。

    Returns:
        FieldVerificationBatchImportRequest: 标准外业导入批次。
    """
    return FieldVerificationBatchImportRequest.model_validate(
        {
            "source_name": "省级外业采集 App",
            "source_uri": "field-app://exports/20260722/batch-01",
            "source_version": "mobile-export-20260722",
            "uploader_code": "field-zhang-qiang",
            "comment": "松北区外业调查批次导入",
            "records": [
                {
                    "verification_code": "FV-IMPORT-001",
                    "source_record_id": "mobile-001",
                    "lon": 126.45,
                    "lat": 45.75,
                    "observed_land_class": "耕地",
                    "observed_crop_type": "玉米",
                    "photo_urls": ["https://files.example/field/001.jpg"],
                    "voice_url": None,
                    "remark": "现场边界清晰",
                    "captured_at": "2026-07-22T09:30:00+08:00",
                },
                {
                    "verification_code": "FV-IMPORT-002",
                    "source_record_id": "mobile-002",
                    "lon": 126.46,
                    "lat": 45.76,
                    "observed_land_class": "建设用地",
                    "observed_crop_type": None,
                    "photo_urls": ["https://files.example/field/002.jpg"],
                    "voice_url": "https://files.example/field/002.m4a",
                    "remark": "现场为临时堆场",
                    "captured_at": "2026-07-22T10:00:00+08:00",
                },
            ],
        }
    )


def build_service() -> tuple[FieldVerificationService, AsyncMock, AsyncMock]:
    """构造具有外业上传权限和项目规则的服务替身。

    Returns:
        tuple: 服务、外业 DAO 和工作台 DAO。
    """
    dao = AsyncMock()
    dao.get_import_conflicts_for_update.return_value = []
    dao.is_point_within_project.return_value = True

    async def create_record(_db, record, _lon, _lat):
        record.id = len(dao.create.await_args_list) + 1
        return record

    dao.create.side_effect = create_record
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = SimpleNamespace(
        id=7,
        project_id=3,
        status="self_check",
        quality_score=92,
        updated_at=datetime.now(UTC),
    )
    workbench_dao.get_latest_imagery.return_value = None
    rule_service = AsyncMock()
    rule_service.ensure_for_project.return_value = SimpleNamespace()
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="field-zhang-qiang",
        display_name="张强",
        role_code="field_inspector",
    )
    artifact_service = MagicMock()

    def store_workbook(filename: str, content: bytes) -> SimpleNamespace:
        return SimpleNamespace(
            path=Path("/tmp") / filename,
            file_uri=f"storage://field-evidence/imports/{sha256(content).hexdigest()}.xlsx",
            file_size_bytes=len(content),
            checksum_sha256=sha256(content).hexdigest(),
            created_new=False,
        )

    artifact_service.store_import_workbook.side_effect = store_workbook
    service = FieldVerificationService(
        dao=dao,
        workbench_dao=workbench_dao,
        rule_config_service=rule_service,
        project_user_service=user_service,
        artifact_service=artifact_service,
    )

    async def match_record(_db, _task, record, _config, _imagery):
        record.match_status = (
            "consistent"
            if record.verification_code == "FV-IMPORT-001"
            else "unmatched"
        )
        record.resolution_status = (
            "not_required" if record.match_status == "consistent" else "pending"
        )
        return record.match_status != "consistent"

    service._match_record = AsyncMock(side_effect=match_record)
    return service, dao, workbench_dao


def test_field_batch_rejects_naive_capture_time() -> None:
    """验证 CSV 外业采集时间必须携带时区。"""
    payload = build_import_request().model_dump(mode="json")
    payload["records"][0]["captured_at"] = "2026-07-22T09:30:00"

    with pytest.raises(ValidationError, match="必须包含时区"):
        FieldVerificationBatchImportRequest.model_validate(payload)


def test_field_batch_rejects_missing_photo_evidence() -> None:
    """验证批量导入记录必须至少包含一张现场照片。"""
    payload = build_import_request().model_dump(mode="json")
    payload["records"][0]["photo_urls"] = []

    with pytest.raises(ValidationError, match="至少需要一张现场照片"):
        FieldVerificationBatchImportRequest.model_validate(payload)


def test_field_batch_import_is_atomic_and_reopens_issue_task() -> None:
    """验证批次一次提交、自动匹配并在存在疑点时重开解译状态。"""
    service, dao, workbench_dao = build_service()
    db = AsyncMock()

    response = asyncio.run(
        service.import_batch(db, "RS-2026-045", build_import_request())
    )

    task = workbench_dao.get_task_by_code_for_update.return_value
    assert response.imported_count == 2
    assert response.consistent_count == 1
    assert response.unmatched_count == 1
    assert response.issue_count == 1
    assert task.status == "interpreting"
    assert task.quality_score is None
    assert dao.create.await_count == 2
    assert dao.create.await_args_list[0].args[1].source_record_id == "mobile-001"
    assert dao.create.await_args_list[0].args[1].imported_by_code == (
        "field-zhang-qiang"
    )
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_field_batch_rejects_existing_record_before_writes() -> None:
    """验证已有核查编号或来源记录时整批拒绝。"""
    service, dao, _ = build_service()
    dao.get_import_conflicts_for_update.return_value = [
        SimpleNamespace(verification_code="FV-IMPORT-001")
    ]
    db = AsyncMock()

    with pytest.raises(ValidationException, match="已存在"):
        asyncio.run(
            service.import_batch(db, "RS-2026-045", build_import_request())
        )

    dao.create.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_field_batch_rolls_back_when_any_point_is_outside_project() -> None:
    """验证批次中任一点越出项目边界时已暂存记录也会回滚。"""
    service, dao, _ = build_service()
    dao.is_point_within_project.side_effect = [True, False]
    db = AsyncMock()

    with pytest.raises(ValidationException, match="超出项目行政区范围"):
        asyncio.run(
            service.import_batch(db, "RS-2026-045", build_import_request())
        )

    assert dao.create.await_count == 1
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


def test_field_xlsx_parser_rejects_formula_cells() -> None:
    """验证 Excel 公式必须粘贴为值后才能导入。"""
    parser = FieldVerificationWorkbookParser()

    with pytest.raises(ValidationException, match="包含公式"):
        parser.parse(
            "field.xlsx",
            build_xlsx_bytes(verification_code='="FV-"&"XLSX-001"'),
        )


def test_field_xlsx_parser_rejects_naive_excel_datetime() -> None:
    """验证 Excel 日期单元格缺少时区时整批拒绝。"""
    parser = FieldVerificationWorkbookParser()

    with pytest.raises(ValidationException, match="必须包含时区"):
        parser.parse(
            "field.xlsx",
            build_xlsx_bytes(captured_at=datetime(2026, 7, 22, 9, 30)),
        )


def test_field_xlsx_import_uses_physical_file_checksum() -> None:
    """验证 XLSX 导入复用原子匹配事务并审计原始文件 SHA256。"""
    service, dao, _ = build_service()
    db = AsyncMock()
    content = build_xlsx_bytes()
    metadata = FieldVerificationFileImportMetadata(
        source_name="省级外业采集 App",
        source_uri="field-app://exports/20260722/xlsx-01",
        source_version="xlsx-export-20260722",
        uploader_code="field-zhang-qiang",
        comment="Excel 实体文件导入测试",
    )

    response = asyncio.run(
        service.import_xlsx(
            db,
            "RS-2026-045",
            metadata,
            "field-verification.xlsx",
            content,
        )
    )

    assert response.imported_count == 1
    assert response.source_checksum_sha256 == sha256(content).hexdigest()
    record = dao.create.await_args.args[1]
    assert record.source_record_id == "mobile-xlsx-001"
    assert record.source_file_size_bytes == len(content)
    assert record.source_file_uri.startswith(
        "storage://field-evidence/imports/"
    )
    service.artifact_service.store_import_workbook.assert_called_once_with(
        "field-verification.xlsx",
        content,
    )
    db.commit.assert_awaited_once()


def test_field_xlsx_template_is_parseable() -> None:
    """验证服务端下载模板可直接回读为标准外业记录。"""
    parser = FieldVerificationWorkbookParser()

    records = parser.parse("template.xlsx", parser.build_template())

    assert len(records) == 1
    assert records[0].verification_code == "FV-2026-0001"
