"""行政区划与成果交付业务服务单元测试。"""

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zipfile import ZipFile

import pytest

from app.core.exceptions import (
    NotFoundException,
    PermissionDeniedException,
    ValidationException,
)
from app.dao.delivery_dao import DeliveryArchiveState
from app.dao.workbench_dao import QualityGateSummary
from app.models.workbench import DeliveryPackage
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


def build_empty_archive_state() -> DeliveryArchiveState:
    """构造没有附加归档实体的当前状态。"""
    return DeliveryArchiveState(
        thematic_map_count=0,
        thematic_map_latest_at=None,
        supervision_report_count=0,
        supervision_report_latest_at=None,
        dataset_asset_count=0,
        dataset_asset_latest_at=None,
        imagery_step_count=0,
        imagery_step_latest_at=None,
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
        quality_summary={
            "quality_score": 92,
            "plot_count": 809,
            "thematic_map_count": 0,
            "thematic_map_latest_at": None,
            "supervision_report_count": 0,
            "supervision_report_latest_at": None,
            "dataset_asset_count": 0,
            "dataset_asset_latest_at": None,
            "imagery_step_count": 0,
            "imagery_step_latest_at": None,
        },
        created_at=now,
        completed_at=now if status == "completed" else None,
        file_uri=None,
    )


def test_delivery_list_exposes_review_gate_and_download_url() -> None:
    """验证三级审核完成后成果包列表开放生成和下载能力。"""
    dao = AsyncMock()
    dao.get_packages.return_value = [build_delivery_package()]
    dao.get_archive_state.return_value = build_empty_archive_state()
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
    dao.get_archive_state.return_value = build_empty_archive_state()
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=9,
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
    dao.get_archive_state.return_value = build_empty_archive_state()
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


def test_delivery_list_marks_new_thematic_map_as_stale() -> None:
    """验证成果包生成后新增专题图会使旧归档失效。"""
    package = build_delivery_package()
    dao = AsyncMock()
    dao.get_packages.return_value = [package]
    dao.get_archive_state.return_value = DeliveryArchiveState(
        thematic_map_count=1,
        thematic_map_latest_at=datetime(2026, 7, 22, tzinfo=UTC),
        supervision_report_count=0,
        supervision_report_latest_at=None,
        dataset_asset_count=0,
        dataset_asset_latest_at=None,
        imagery_step_count=0,
        imagery_step_latest_at=None,
    )
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
    workbench_dao.get_latest_imagery.return_value = SimpleNamespace(id=3)
    workbench_dao.get_quality_gate_summary.return_value = build_passing_gate()
    service = DeliveryService(dao=dao, workbench_dao=workbench_dao)

    response = asyncio.run(service.list_packages(AsyncMock(), "RS-2026-045"))

    assert response.packages[0].is_current is False
    assert response.packages[0].download_url is None
    assert "专题图" in (response.packages[0].stale_reason or "")


def test_delivery_list_marks_superseded_version_as_history() -> None:
    """验证被新版本替代的成果包永远不会重新成为当前成果。"""
    package = build_delivery_package(status="superseded")
    reason = DeliveryService._get_stale_reason(
        package,
        SimpleNamespace(
            total_plots=809,
            updated_at=datetime(2026, 7, 20, tzinfo=UTC),
        ),
        build_empty_archive_state(),
    )

    assert reason == "成果包已被新版本替代"


def test_delivery_list_blocks_missing_operational_imagery() -> None:
    """验证三级审核完成后仍必须具有可验证业务影像。"""
    dao = AsyncMock()
    dao.get_packages.return_value = []
    dao.get_archive_state.return_value = build_empty_archive_state()
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
    service = DeliveryService(dao=dao, workbench_dao=workbench_dao)

    response = asyncio.run(service.list_packages(AsyncMock(), "RS-2026-045"))

    assert response.can_generate is False
    assert response.generate_blocker == "缺少具备实体校验的业务影像"


def test_delivery_list_blocks_incomplete_quality_coverage() -> None:
    """验证成果列表不能把未覆盖全部图斑的门禁显示为可生成。"""
    workbench_dao = AsyncMock()
    dao = AsyncMock()
    dao.get_archive_state.return_value = build_empty_archive_state()
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
    service = DeliveryService(dao=dao, workbench_dao=workbench_dao)

    response = asyncio.run(service.list_packages(AsyncMock(), "RS-2026-045"))

    assert response.can_generate is False
    assert "800/809" in (response.generate_blocker or "")


def test_delivery_download_rejects_missing_physical_file() -> None:
    """验证数据库记录存在但实体文件丢失时拒绝下载。"""
    package = build_delivery_package()
    package.file_uri = "/tmp/nonexistent-remote-sensing-delivery.zip"
    dao = AsyncMock()
    dao.get_package_by_code.return_value = package
    dao.get_archive_state.return_value = build_empty_archive_state()
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_id.return_value = SimpleNamespace(
        id=1,
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
    dao.get_archive_state.return_value = build_empty_archive_state()
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_id.return_value = SimpleNamespace(
        id=1,
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


def test_delivery_generation_archives_verified_physical_evidence(
    tmp_path: Path,
) -> None:
    """验证 ZIP 纳入专题图、监理报告、影像血缘和逐文件 SHA-256。"""
    generated_at = datetime(2026, 7, 22, 10, 30, tzinfo=UTC)
    thematic_path = tmp_path / "thematic.png"
    thematic_path.write_bytes(b"\x89PNG\r\n\x1a\nverified-thematic-map")
    supervision_path = tmp_path / "supervision.json"
    supervision_path.write_text('{"report":"verified"}', encoding="utf-8")
    source_path = tmp_path / "source.tif"
    source_path.write_bytes(b"II*\x00source-raster")
    step_path = tmp_path / "step.tif"
    step_path.write_bytes(b"II*\x00processed-raster")
    step_checksum = hashlib.sha256(step_path.read_bytes()).hexdigest()
    archive_state = DeliveryArchiveState(
        thematic_map_count=1,
        thematic_map_latest_at=generated_at,
        supervision_report_count=1,
        supervision_report_latest_at=generated_at,
        dataset_asset_count=1,
        dataset_asset_latest_at=generated_at,
        imagery_step_count=1,
        imagery_step_latest_at=generated_at,
    )
    task = SimpleNamespace(
        id=1,
        project_id=9,
        task_code="RS-2026-045",
        task_name="黑龙江省遥感监测",
        administrative_region="黑龙江省",
        status="completed",
        total_plots=1,
        updated_at=datetime(2026, 7, 20, tzinfo=UTC),
    )
    imagery = SimpleNamespace(
        id=7,
        asset_code="S2B-HRB-20260716-PUBLIC",
        asset_name="Sentinel-2B 哈尔滨公开影像",
        sensor_type="Sentinel-2B MSI",
        acquired_at=generated_at,
        processing_level="L2A",
        data_status="operational",
        file_uri="storage://imagery/source.tif",
        file_size_bytes=source_path.stat().st_size,
        checksum_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        file_format="GeoTIFF",
        crs="EPSG:32651",
        band_count=4,
        raster_metadata={"security_classification": "public"},
        calibration_status="completed",
        correction_status="completed",
    )
    imagery_step = SimpleNamespace(
        step_code="band_products",
        step_name="波段产品",
        sequence=5,
        status="completed",
        progress=100,
        parameters={"artifact_evidence": {"checksum_sha256": step_checksum}},
        output_uri="storage://imagery/processed/step.tif",
        completed_at=generated_at,
        updated_at=generated_at,
    )
    thematic_product = SimpleNamespace(
        product_code="TM-TEST-001",
        output_format="png",
        map_number="HLJ-RS-2026-RGB",
        map_name="黑龙江农业遥感真彩色专题图",
        file_uri="storage://thematic_maps/TM-TEST-001.png",
    )
    supervision_report = SimpleNamespace(
        report_code="SUP-REPORT-001",
        file_uri="storage://supervision/SUP-REPORT-001.json",
    )
    dataset_asset = SimpleNamespace(
        asset_code="DATASET-001",
        asset_name="公开 Sentinel-2 来源目录",
        asset_type="imagery",
        source_name="Element 84 Earth Search",
        source_uri="https://earth-search.aws.element84.com/v1",
        source_version="2026-07-16",
        checksum_sha256="a" * 64,
        crs="EPSG:32651",
        time_start=generated_at,
        time_end=generated_at,
        security_classification="public",
        data_status="operational",
        verification_status="verified",
        metadata_payload={"stac_item_id": "S2B_TEST_L2A"},
        registered_by="赵志远",
        registered_by_code="manager-zhao-zhiyuan",
        registered_by_role="project_manager",
        created_at=generated_at,
        updated_at=generated_at,
    )
    plot_row = SimpleNamespace(
        geometry=(
            '{"type":"Polygon","coordinates":'
            "[[[126.5,45.7],[126.6,45.7],[126.6,45.8],"
            "[126.5,45.7]]]}"
        ),
        plot_code="PLOT-001",
        owner_village="测试村",
        area_ha=1,
        land_class="farmland",
        crop_type="corn",
        planting_mode="single",
        irrigation_condition="irrigated",
        interpretation_status="interpreted",
        version=1,
    )
    statistics = SimpleNamespace(
        by_village=[],
        by_land_class=[],
        by_crop_type=[],
        total_area_ha=1,
        total_area_mu=15,
    )
    disasters = SimpleNamespace(
        total_patches=0,
        affected_area_ha=0,
        feature_collection={"type": "FeatureCollection", "features": []},
    )
    dao = AsyncMock()
    dao.get_next_version.return_value = 1
    dao.get_plot_rows.return_value = [plot_row]
    dao.get_quality_issues.return_value = []
    dao.get_field_rows.return_value = []
    dao.get_thematic_map_products.return_value = [thematic_product]
    dao.get_supervision_reports.return_value = [supervision_report]
    dao.get_dataset_assets.return_value = [dataset_asset]
    dao.get_imagery_steps.return_value = [imagery_step]
    dao.get_archive_state.return_value = archive_state

    async def add_package(
        _: object,
        package: DeliveryPackage,
    ) -> DeliveryPackage:
        package.id = 1
        package.created_at = generated_at
        return package

    dao.add_package.side_effect = add_package
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = task
    workbench_dao.count_open_issues.return_value = 0
    workbench_dao.count_pending_field_verifications.return_value = 0
    workbench_dao.get_latest_imagery.return_value = imagery
    workbench_dao.get_quality_gate_summary.return_value = build_passing_gate(1)
    workbench_dao.get_reviews.return_value = []
    statistics_service = AsyncMock()
    statistics_service.get_area_statistics.return_value = statistics
    disaster_service = AsyncMock()
    disaster_service.get_summary.return_value = disasters
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    imagery_service = MagicMock()
    imagery_service.resolve_verified_asset_source_path.return_value = source_path
    imagery_service.resolve_verified_step_artifact_path.return_value = (
        step_path,
        {"checksum_sha256": step_checksum},
    )
    thematic_service = MagicMock()
    thematic_service.verify_product_file.return_value = thematic_path
    supervision_service = MagicMock()
    supervision_service.verify_report_file.return_value = supervision_path
    service = DeliveryService(
        dao=dao,
        workbench_dao=workbench_dao,
        statistics_service=statistics_service,
        disaster_service=disaster_service,
        project_user_service=user_service,
        imagery_service=imagery_service,
        thematic_map_service=thematic_service,
        supervision_service=supervision_service,
    )
    service.storage_dir = tmp_path / "deliveries"
    db = AsyncMock()

    response = asyncio.run(
        service.generate_package(
            db,
            task.task_code,
            DeliveryGenerateRequest(operator_code="manager-zhao-zhiyuan"),
        )
    )

    package_path = next(service.storage_dir.glob("*.zip"))
    with ZipFile(package_path) as archive:
        names = set(archive.namelist())
        manifest_payload = json.loads(archive.read("manifest.json"))
        assert "thematic_maps/TM-TEST-001.png" in names
        assert "supervision/SUP-REPORT-001.json" in names
        assert "archive/imagery_lineage.json" in names
        assert "archive/dataset_catalog.json" in names
        assert "archive/archive_index.json" in names
        for item in manifest_payload["manifest"]:
            if item["path"] == "manifest.json":
                continue
            content = archive.read(item["path"])
            assert item["file_size_bytes"] == len(content)
            assert item["checksum_sha256"] == hashlib.sha256(content).hexdigest()
    assert response.quality_summary["thematic_map_count"] == 1
    assert response.quality_summary["supervision_report_count"] == 1
    assert response.quality_summary["imagery_step_count"] == 1
    assert response.is_current is True
    dao.supersede_completed_packages.assert_awaited_once_with(db, task.id)


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
        "archive_state": build_empty_archive_state(),
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
    dao.get_archive_state.return_value = build_empty_archive_state()
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_id.return_value = SimpleNamespace(
        id=1,
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
