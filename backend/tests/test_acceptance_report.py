"""成果验收正式报告生成、版本、实体和权限测试。"""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest

from app.core.exceptions import PermissionDeniedException, ValidationException
from app.models.acceptance_report import AcceptanceReport
from app.schemas.acceptance_report import AcceptanceReportGenerateRequest
from app.services.acceptance_report_renderer import AcceptanceReportRenderer
from app.services.acceptance_report_service import AcceptanceReportService


def build_task() -> SimpleNamespace:
    """构造已完成三级审核的任务。

    Returns:
        SimpleNamespace: 测试任务。
    """
    return SimpleNamespace(
        id=45,
        project_id=1,
        task_code="RS-2026-045",
        task_name="2026 年省级农作物种植监测",
        status="completed",
        total_plots=35_020,
        updated_at=datetime(2026, 7, 23, 8, 0, tzinfo=UTC),
    )


def build_package() -> SimpleNamespace:
    """构造当前有效成果包。

    Returns:
        SimpleNamespace: 测试成果包。
    """
    manifest = [
        {
            "path": f"vector/farmland-{index}.geojson",
            "category": "矢量成果",
            "format": "GeoJSON",
            "record_count": 35_020,
            "description": "最终任务图斑",
            "file_size_bytes": 1_024 + index,
            "checksum_sha256": f"{index + 1:064x}"[-64:],
            "source_entity_code": None,
            "source_uri": None,
            "evidence_status": "included",
        }
        for index in range(28)
    ]
    quality_summary = {
        "plot_count": 35_020,
        "quality_total_count": 35_020,
        "quality_checked_count": 35_020,
        "quality_passing_count": 35_020,
        "quality_score": 96.8,
        "quality_gate_complete": True,
        "open_issue_count": 0,
        "resolved_issue_count": 128,
        "field_verification_count": 20,
        "field_verified_artifact_count": 24,
        "field_import_workbook_count": 1,
        "field_missing_photo_count": 0,
        "pending_field_count": 0,
        "field_evidence_status": "included",
        "disaster_patch_count": 4,
        "affected_area_ha": 18.5,
        "disaster_evidence_status": "provided",
        "imagery_asset_code": "IMG-PUBLIC-S2-001",
        "imagery_processing_complete": True,
        "review_record_count": 8,
        "thematic_map_count": 3,
        "supervision_report_count": 1,
        "disaster_report_count": 1,
        "statistics_report_count": 1,
        "vector_export_count": 1,
        "dataset_asset_count": 9,
        "imagery_step_count": 5,
        "task_status": "completed",
    }
    return SimpleNamespace(
        id=80,
        task_id=45,
        package_code="RS-2026-045-DELIVERY-v2-20260723080000",
        package_name="省级农作物监测最终成果包",
        version=2,
        status="completed",
        file_uri="/tmp/delivery.zip",
        file_size_bytes=8_192,
        checksum_sha256="a" * 64,
        manifest=manifest,
        quality_summary=quality_summary,
        completed_at=datetime(2026, 7, 23, 8, 5, tzinfo=UTC),
    )


def build_operator(role_code: str = "project_manager") -> SimpleNamespace:
    """构造稳定项目用户。

    Args:
        role_code: 用户角色编码。

    Returns:
        SimpleNamespace: 测试项目用户。
    """
    return SimpleNamespace(
        display_name="赵志远" if role_code == "project_manager" else "省厅甲方",
        user_code=(
            "manager-zhao-zhiyuan"
            if role_code == "project_manager"
            else "client-agri-dept"
        ),
        role_code=role_code,
    )


def build_reviews() -> list[SimpleNamespace]:
    """构造三级审核与交付审计记录。

    Returns:
        list[SimpleNamespace]: 审核记录。
    """
    return [
        SimpleNamespace(
            review_level=level,
            action="pass",
            reviewer=reviewer,
            reviewer_code=code,
            reviewer_role=role,
            comment="审核通过，证据完整。",
            created_at=datetime(2026, 7, 23, 7, index, tzinfo=UTC),
        )
        for index, (level, reviewer, code, role) in enumerate(
            (
                ("self", "李静", "interp-li-jing", "interpreter"),
                (
                    "quality",
                    "王质检",
                    "quality-wang",
                    "quality_inspector",
                ),
                ("client", "省厅甲方", "client-agri-dept", "client_reviewer"),
            ),
            start=1,
        )
    ]


@pytest.mark.asyncio
async def test_generate_acceptance_report_builds_real_docx_pdf_bundle(
    tmp_path: Path,
) -> None:
    """验证服务端真实生成分页 PDF、DOCX、manifest 和审计版本。"""
    task = build_task()
    package = build_package()
    operator = build_operator()
    dao = AsyncMock()
    dao.get_next_version.return_value = 1
    dao.supersede_completed_reports.return_value = 0
    dao.add_report.side_effect = lambda _db, report: report
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = task
    workbench_dao.get_reviews.return_value = build_reviews()
    delivery_service = AsyncMock()
    delivery_service.get_current_package.return_value = package
    delivery_service.get_package_for_download.return_value = package
    project_user_service = AsyncMock()
    project_user_service.require_capability.return_value = operator
    db = AsyncMock()
    service = AcceptanceReportService(
        dao=dao,
        workbench_dao=workbench_dao,
        delivery_service=delivery_service,
        project_user_service=project_user_service,
        storage_root=tmp_path,
    )

    response = await service.generate_report(
        db,
        task.task_code,
        AcceptanceReportGenerateRequest(
            operator_code=operator.user_code,
            report_title="黑龙江省农业遥感监测成果验收报告",
            comment="依据当前最终成果包、三级审核和质量门禁生成送审材料。",
        ),
    )

    report = dao.add_report.call_args.args[1]
    path = service.verify_report_bundle(report)
    assert response.version == 1
    assert response.is_current is True
    assert response.delivery_package_code == package.package_code
    assert response.task_plot_count == 35_020
    assert response.files[0].format == "DOCX"
    assert response.files[1].format == "PDF"
    assert response.files[1].page_count is not None
    assert response.files[1].page_count >= 3
    assert path.is_file()
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        assert names == {
            report.docx_filename,
            report.pdf_filename,
            "manifest.json",
        }
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["delivery_package"]["package_code"] == package.package_code
        assert manifest["task"]["task_plot_count"] == 35_020
        AcceptanceReportRenderer.validate_docx(
            archive.read(report.docx_filename),
            report.report_code,
        )
        page_count = AcceptanceReportRenderer.validate_pdf(
            archive.read(report.pdf_filename),
            report.report_code,
        )
        assert page_count == response.files[1].page_count

    dao.get_report_by_code.return_value = report
    workbench_dao.get_task_by_id.return_value = task
    project_user_service.require_capability.return_value = build_operator(
        "client_reviewer"
    )
    download = await service.authorize_download(
        db,
        report.report_code,
        "client-agri-dept",
    )
    assert download.path == path
    assert download.filename == f"{report.report_code}.zip"
    assert download.checksum_sha256 == report.bundle_checksum_sha256
    assert workbench_dao.add_review_record.await_count == 2
    assert db.commit.await_count == 2


def test_acceptance_report_becomes_stale_when_delivery_changes() -> None:
    """验证成果包编号、校验值或任务快照变化后旧报告失效。"""
    task = build_task()
    package = build_package()
    report = SimpleNamespace(
        status="completed",
        task_plot_count=task.total_plots,
        task_updated_at_snapshot=task.updated_at,
        delivery_package_id=package.id,
        delivery_package_code=package.package_code,
        delivery_package_checksum_sha256=package.checksum_sha256,
        delivery_package_size_bytes=package.file_size_bytes,
        delivery_package_completed_at_snapshot=package.completed_at,
        delivery_manifest_count=len(package.manifest),
        quality_summary_checksum_sha256=(
            AcceptanceReportService.quality_summary_checksum(
                package.quality_summary
            )
        ),
    )
    assert AcceptanceReportService.get_stale_reason(report, task, package) is None

    package.checksum_sha256 = "b" * 64
    assert (
        AcceptanceReportService.get_stale_reason(report, task, package)
        == "成果包 SHA-256 在报告生成后发生变化"
    )


@pytest.mark.asyncio
async def test_list_reports_requires_current_delivery_package(tmp_path: Path) -> None:
    """验证没有当前有效成果包时返回真实生成阻断。"""
    task = build_task()
    dao = AsyncMock()
    dao.get_reports.return_value = []
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = task
    delivery_service = AsyncMock()
    delivery_service.get_current_package.return_value = None
    service = AcceptanceReportService(
        dao=dao,
        workbench_dao=workbench_dao,
        delivery_service=delivery_service,
        storage_root=tmp_path,
    )

    response = await service.list_reports(AsyncMock(), task.task_code)

    assert response.can_generate is False
    assert response.current_delivery_package_code is None
    assert response.generate_blocker == "请先生成与当前任务一致的成果交付包"


@pytest.mark.asyncio
async def test_generate_acceptance_report_rejects_unauthorized_user(
    tmp_path: Path,
) -> None:
    """验证甲方或内业不能越权生成验收报告。"""
    task = build_task()
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = task
    project_user_service = AsyncMock()
    project_user_service.require_capability.side_effect = PermissionDeniedException(
        "当前身份无权生成成果验收报告"
    )
    service = AcceptanceReportService(
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
        storage_root=tmp_path,
    )

    with pytest.raises(PermissionDeniedException):
        await service.generate_report(
            AsyncMock(),
            task.task_code,
            AcceptanceReportGenerateRequest(
                operator_code="client-agri-dept",
                report_title="越权验收报告",
                comment="验证无权限用户不能生成验收报告。",
            ),
        )


def test_verify_report_bundle_rejects_modified_pdf(tmp_path: Path) -> None:
    """验证 ZIP 内 PDF 被修改后不能通过实体复核。"""
    service = AcceptanceReportService(storage_root=tmp_path)
    report = AcceptanceReport(
        task_id=45,
        delivery_package_id=80,
        report_code="ACCRPT-TEST-CORRUPTED",
        report_title="损坏报告",
        version=1,
        status="completed",
        bundle_uri=(
            "storage://acceptance-reports/RS-2026-045/"
            "ACCRPT-TEST-CORRUPTED.zip"
        ),
        bundle_size_bytes=10,
        bundle_checksum_sha256="a" * 64,
        docx_filename="ACCRPT-TEST-CORRUPTED.docx",
        docx_size_bytes=10,
        docx_checksum_sha256="b" * 64,
        pdf_filename="ACCRPT-TEST-CORRUPTED.pdf",
        pdf_size_bytes=10,
        pdf_checksum_sha256="c" * 64,
        task_plot_count=1,
        task_updated_at_snapshot=datetime.now(UTC),
        delivery_package_code="DELIVERY-1",
        delivery_package_completed_at_snapshot=datetime.now(UTC),
        delivery_package_size_bytes=10,
        delivery_package_checksum_sha256="d" * 64,
        delivery_manifest_count=1,
        quality_summary_checksum_sha256="e" * 64,
        report_manifest={},
        generation_comment="实体损坏验证",
        generated_by="赵志远",
        generated_by_code="manager-zhao-zhiyuan",
        generated_by_role="project_manager",
        generated_at=datetime.now(UTC),
    )
    path = tmp_path / "RS-2026-045" / "ACCRPT-TEST-CORRUPTED.zip"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"PK\x03\x04corrupted")
    report.bundle_size_bytes = path.stat().st_size
    report.bundle_checksum_sha256 = service.quality_summary_checksum(
        {"content": "not-the-bundle"}
    )

    with pytest.raises(ValidationException, match="ZIP SHA-256"):
        service.verify_report_bundle(report)
