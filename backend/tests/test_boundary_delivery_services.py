"""行政区划与成果交付业务服务单元测试。"""

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import (
    NotFoundException,
    PermissionDeniedException,
    ValidationException,
)
from app.dao.workbench_dao import QualityGateSummary
from app.schemas.delivery import DeliveryGenerateRequest
from app.services.boundary_service import BoundaryService
from app.services.delivery_service import DeliveryService
from app.services.project_user_service import ProjectUserService


def build_passing_gate(total_count: int = 809) -> QualityGateSummary:
    """构造全部图斑已通过的质量门禁。"""
    return QualityGateSummary(
        total_count=total_count,
        checked_count=total_count,
        passing_count=total_count,
        average_score=92.0,
    )


def test_boundary_service_builds_feature_collection() -> None:
    """验证行政区划数据库行可转换为标准 GeoJSON 集合。"""
    dao = AsyncMock()
    dao.get_boundaries.return_value = [
        SimpleNamespace(
            boundary_code="230109",
            boundary_name="松北区",
            boundary_level="district",
            parent_code="230100",
            source_name="geoBoundaries gbOpen / OpenStreetMap",
            source_uri="https://www.geoboundaries.org/",
            source_version="3.0.0",
            source_updated_at=date(2023, 12, 12),
            geometry=(
                '{"type":"Polygon","coordinates":'
                "[[[126.4,45.7],[126.8,45.7],[126.8,45.9],[126.4,45.7]]]}"
            ),
        ),
        SimpleNamespace(
            boundary_code="230109101",
            boundary_name="万宝街道",
            boundary_level="township",
            parent_code="230109",
            source_name="测试数据源",
            source_uri=None,
            source_version="test",
            source_updated_at=None,
            geometry=(
                '{"type":"Polygon","coordinates":'
                "[[[126.5,45.7],[126.6,45.7],[126.6,45.8],[126.5,45.7]]]}"
            ),
        ),
    ]
    service = BoundaryService(dao=dao)

    response = asyncio.run(service.get_boundaries(AsyncMock(), "RS-2026"))

    assert response.type == "FeatureCollection"
    assert len(response.features) == 2
    assert response.features[0]["properties"]["boundary_name"] == "松北区"
    assert response.features[0]["properties"]["source_version"] == "3.0.0"
    assert response.features[1]["geometry"]["type"] == "Polygon"


def test_boundary_service_rejects_project_without_boundaries() -> None:
    """验证未配置边界的项目返回明确业务异常。"""
    dao = AsyncMock()
    dao.get_boundaries.return_value = []
    service = BoundaryService(dao=dao)

    with pytest.raises(NotFoundException, match="行政区划边界"):
        asyncio.run(service.get_boundaries(AsyncMock(), "RS-EMPTY"))


def build_delivery_package(status: str = "completed") -> SimpleNamespace:
    """构造满足成果包响应模型的测试对象。"""
    now = datetime.now(UTC)
    return SimpleNamespace(
        task_id=1,
        package_code="RS-2026-045-DELIVERY-v1-TEST",
        package_name="松北区遥感监测成果包 v1",
        version=1,
        status=status,
        generated_by="项目负责人",
        generated_by_code="manager-zhao-zhiyuan",
        generated_by_role="project_manager",
        file_size_bytes=2048,
        checksum_sha256="a" * 64,
        manifest=[],
        quality_summary={"quality_score": 92, "plot_count": 809},
        created_at=now,
        completed_at=now if status == "completed" else None,
        file_uri=None,
    )


def test_delivery_list_exposes_review_gate_and_download_url() -> None:
    """验证三级审核完成后成果包列表开放生成和下载能力。"""
    dao = AsyncMock()
    dao.get_packages.return_value = [build_delivery_package()]
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=9,
        status="completed",
        total_plots=809,
        updated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    workbench_dao.count_open_issues.return_value = 0
    workbench_dao.count_pending_field_verifications.return_value = 0
    workbench_dao.get_latest_imagery.return_value = SimpleNamespace(
        asset_code="REAL-IMAGERY-001"
    )
    workbench_dao.get_quality_gate_summary.return_value = build_passing_gate()
    service = DeliveryService(dao=dao, workbench_dao=workbench_dao)

    response = asyncio.run(service.list_packages(AsyncMock(), "RS-2026-045"))

    assert response.can_generate is True
    assert response.generate_blocker is None
    assert len(response.packages) == 1
    assert response.packages[0].download_url.endswith("/download")


def test_delivery_list_blocks_task_before_final_review() -> None:
    """验证未完成三级审核的任务不能生成成果包。"""
    dao = AsyncMock()
    dao.get_packages.return_value = []
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        status="quality_review",
        total_plots=809,
        updated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    workbench_dao.count_open_issues.return_value = 0
    workbench_dao.count_pending_field_verifications.return_value = 0
    service = DeliveryService(dao=dao, workbench_dao=workbench_dao)

    response = asyncio.run(service.list_packages(AsyncMock(), "RS-2026-045"))

    assert response.can_generate is False
    assert response.generate_blocker == "任务需完成三级审核后才能生成成果包"


def test_delivery_list_marks_outdated_plot_scope_as_stale() -> None:
    """验证旧地块范围成果包不会继续显示为当前可下载成果。"""
    package = build_delivery_package()
    package.quality_summary = {"quality_score": 92, "plot_count": 5}
    dao = AsyncMock()
    dao.get_packages.return_value = [package]
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=9,
        status="completed",
        total_plots=809,
        updated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    workbench_dao.count_open_issues.return_value = 0
    workbench_dao.count_pending_field_verifications.return_value = 0
    workbench_dao.get_latest_imagery.return_value = SimpleNamespace(
        asset_code="REAL-IMAGERY-001"
    )
    workbench_dao.get_quality_gate_summary.return_value = build_passing_gate()
    service = DeliveryService(dao=dao, workbench_dao=workbench_dao)

    response = asyncio.run(service.list_packages(AsyncMock(), "RS-2026-045"))

    assert response.packages[0].is_current is False
    assert response.packages[0].download_url is None
    assert "图斑数量" in (response.packages[0].stale_reason or "")


def test_delivery_list_blocks_missing_operational_imagery() -> None:
    """验证三级审核完成后仍必须具有可验证业务影像。"""
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=9,
        status="completed",
        total_plots=809,
        updated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    workbench_dao.count_open_issues.return_value = 0
    workbench_dao.count_pending_field_verifications.return_value = 0
    workbench_dao.get_latest_imagery.return_value = None
    service = DeliveryService(dao=AsyncMock(), workbench_dao=workbench_dao)

    response = asyncio.run(service.list_packages(AsyncMock(), "RS-2026-045"))

    assert response.can_generate is False
    assert response.generate_blocker == "缺少具备实体校验的业务影像"


def test_delivery_list_blocks_incomplete_quality_coverage() -> None:
    """验证成果列表不能把未覆盖全部图斑的门禁显示为可生成。"""
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=9,
        status="completed",
        total_plots=809,
        updated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    workbench_dao.count_open_issues.return_value = 0
    workbench_dao.count_pending_field_verifications.return_value = 0
    workbench_dao.get_latest_imagery.return_value = SimpleNamespace(
        asset_code="REAL-IMAGERY-001"
    )
    workbench_dao.get_quality_gate_summary.return_value = QualityGateSummary(
        total_count=809,
        checked_count=800,
        passing_count=800,
        average_score=92.0,
    )
    service = DeliveryService(dao=AsyncMock(), workbench_dao=workbench_dao)

    response = asyncio.run(service.list_packages(AsyncMock(), "RS-2026-045"))

    assert response.can_generate is False
    assert "800/809" in (response.generate_blocker or "")


def test_delivery_download_rejects_missing_physical_file() -> None:
    """验证数据库记录存在但实体文件丢失时拒绝下载。"""
    package = build_delivery_package()
    package.file_uri = "/tmp/nonexistent-remote-sensing-delivery.zip"
    dao = AsyncMock()
    dao.get_package_by_code.return_value = package
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_id.return_value = SimpleNamespace(
        project_id=9,
        total_plots=809,
        updated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace()
    service = DeliveryService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )

    with pytest.raises(NotFoundException, match="成果包文件不存在"):
        asyncio.run(
            service.get_package_for_download(
                AsyncMock(),
                package.package_code,
                "manager-zhao-zhiyuan",
            )
        )


def test_delivery_download_rejects_generating_package() -> None:
    """验证尚未生成完成的成果包不能下载。"""
    package = build_delivery_package("generating")
    dao = AsyncMock()
    dao.get_package_by_code.return_value = package
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_id.return_value = SimpleNamespace(
        project_id=9,
        total_plots=809,
        updated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace()
    service = DeliveryService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )

    with pytest.raises(ValidationException, match="尚未生成完成"):
        asyncio.run(
            service.get_package_for_download(
                AsyncMock(),
                package.package_code,
                "manager-zhao-zhiyuan",
            )
        )


def test_delivery_generation_rejects_non_manager_role() -> None:
    """验证已完成任务也只能由项目负责人生成成果包。"""
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = SimpleNamespace(
        id=1,
        project_id=9,
        status="completed",
    )
    user_dao = AsyncMock()
    user_dao.get_active_user.return_value = SimpleNamespace(
        user_code="quality-wang-haifeng",
        display_name="王海峰",
        role_code="quality_inspector",
        role_name="质检员",
    )
    service = DeliveryService(
        dao=AsyncMock(),
        workbench_dao=workbench_dao,
        project_user_service=ProjectUserService(dao=user_dao),
    )

    with pytest.raises(PermissionDeniedException, match="无权执行当前业务节点"):
        asyncio.run(
            service.generate_package(
                AsyncMock(),
                "RS-2026-045",
                DeliveryGenerateRequest(
                    operator_code="quality-wang-haifeng",
                ),
            )
        )


def test_delivery_generation_blocks_unresolved_issues() -> None:
    """验证项目负责人也不能绕过未关闭问题生成成果包。"""
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = SimpleNamespace(
        id=1,
        project_id=9,
        status="completed",
    )
    workbench_dao.count_open_issues.return_value = 2
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    service = DeliveryService(
        dao=AsyncMock(),
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )

    with pytest.raises(ValidationException, match="仍有 2 条问题未关闭"):
        asyncio.run(
            service.generate_package(
                AsyncMock(),
                "RS-2026-045",
                DeliveryGenerateRequest(
                    operator_code="manager-zhao-zhiyuan",
                ),
            )
        )


def test_delivery_generation_blocks_missing_quality_coverage() -> None:
    """验证生成接口会独立复核质量覆盖而不只信任任务状态。"""
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = SimpleNamespace(
        id=1,
        project_id=9,
        status="completed",
    )
    workbench_dao.count_open_issues.return_value = 0
    workbench_dao.count_pending_field_verifications.return_value = 0
    workbench_dao.get_latest_imagery.return_value = SimpleNamespace(
        asset_code="REAL-IMAGERY-001"
    )
    workbench_dao.get_quality_gate_summary.return_value = QualityGateSummary(
        total_count=809,
        checked_count=800,
        passing_count=800,
        average_score=92.0,
    )
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    service = DeliveryService(
        dao=AsyncMock(),
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )

    with pytest.raises(ValidationException, match="800/809"):
        asyncio.run(
            service.generate_package(
                AsyncMock(),
                "RS-2026-045",
                DeliveryGenerateRequest(
                    operator_code="manager-zhao-zhiyuan",
                ),
            )
        )


def test_delivery_reports_do_not_claim_missing_optional_evidence() -> None:
    """验证空外业和空灾害文件不会在报告中被描述为已完成成果。"""
    task = SimpleNamespace(
        task_code="RS-2026-045",
        task_name="黑龙江省遥感监测",
        administrative_region="黑龙江省",
        status="completed",
        quality_score=92,
    )
    source_data = {
        "plot_rows": [SimpleNamespace()],
        "quality_issues": [],
        "field_rows": [],
        "disasters": SimpleNamespace(total_patches=0, affected_area_ha=0),
        "reviews": [SimpleNamespace()],
        "quality_gate": build_passing_gate(total_count=1),
        "imagery": SimpleNamespace(
            asset_code="REAL-IMAGERY-001",
            acquired_at=datetime(2026, 7, 20, tzinfo=UTC),
            calibration_status="completed",
            correction_status="completed",
        ),
        "statistics": SimpleNamespace(total_area_ha=10, total_area_mu=150),
    }

    summary = DeliveryService._build_quality_summary(task, source_data)
    quality_report = DeliveryService._build_quality_report(task, summary)
    acceptance_report = DeliveryService._build_acceptance_report(
        task,
        source_data,
        summary,
    )

    assert summary["field_evidence_status"] == "not_provided"
    assert summary["disaster_evidence_status"] == "not_provided"
    assert "不作外业一致性结论" in quality_report
    assert "外业一致性检查" not in quality_report
    assert "未提供外业核查记录" in acceptance_report
    assert "未导入灾害模型成果" in acceptance_report
    assert "空集合冒充已完成成果" in acceptance_report


def test_delivery_download_rejects_interpreter_role() -> None:
    """验证成果包下载仅对项目负责人和甲方开放。"""
    package = build_delivery_package()
    dao = AsyncMock()
    dao.get_package_by_code.return_value = package
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_id.return_value = SimpleNamespace(
        project_id=9,
        total_plots=809,
        updated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    user_dao = AsyncMock()
    user_dao.get_active_user.return_value = SimpleNamespace(
        user_code="interp-li-jing",
        display_name="李静",
        role_code="interpreter",
        role_name="内业解译员",
    )
    service = DeliveryService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=ProjectUserService(dao=user_dao),
    )

    with pytest.raises(PermissionDeniedException, match="无权执行当前业务节点"):
        asyncio.run(
            service.get_package_for_download(
                AsyncMock(),
                package.package_code,
                "interp-li-jing",
            )
        )
