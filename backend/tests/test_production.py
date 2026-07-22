"""多源数据目录和生产调度业务测试。"""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.models.workbench import WorkPackage
from app.schemas.production import (
    DatasetAssetCreateRequest,
    ProductionBatchCreateRequest,
    WorkPackageCreateRequest,
    WorkPackageResponse,
    WorkPackageUpdateRequest,
)
from app.services.production_service import ProductionService


def test_dataset_asset_rejects_invalid_wgs84_extent() -> None:
    """验证多源资产范围必须是合法 WGS84 包围盒。"""
    with pytest.raises(ValidationError, match="经度不合法"):
        DatasetAssetCreateRequest(
            asset_code="HLJ-DEM-001",
            asset_name="黑龙江省公开 DEM",
            asset_type="dem",
            source_name="公开数据源",
            source_uri="https://example.test/dem.tif",
            source_version="2026-07",
            checksum_sha256="a" * 64,
            crs="EPSG:4326",
            extent_bbox=(130, 45, 120, 50),
            security_classification="public",
            operator_code="manager-zhao-zhiyuan",
        )


def test_production_batch_rejects_same_temporal_asset() -> None:
    """验证生产批次前后时相不能绑定同一数据资产。"""
    with pytest.raises(ValidationError, match="前后时相资产不能相同"):
        ProductionBatchCreateRequest(
            batch_code="HLJ-2026-A",
            batch_name="七月变化监测批次",
            source_asset_code="IMG-001",
            target_asset_code="IMG-001",
            planned_start_date=date(2026, 7, 1),
            planned_end_date=date(2026, 7, 31),
            operator_code="manager-zhao-zhiyuan",
        )


class StubOverviewProductionService(ProductionService):
    """为写操作测试提供固定的提交后聚合结果。"""

    def __init__(self, overview: object, **kwargs: object) -> None:
        """初始化固定聚合结果服务。"""
        super().__init__(**kwargs)
        self.overview = overview

    async def get_overview(
        self,
        db: object,
        project_code: str,
        task_code: str,
    ) -> object:
        """返回测试预置的提交后聚合结果。"""
        return self.overview


def build_package_response() -> WorkPackageResponse:
    """构造已由数据库聚合的县区作业包响应。"""
    return WorkPackageResponse(
        package_code="HLJ-2026-A-230102",
        package_name="道里区生产作业包",
        region_code="230102",
        region_name="道里区",
        region_level="district",
        planned_area_ha=12.5,
        planned_plot_count=2,
        active_plot_count=2,
        completed_plot_count=0,
        progress=0,
        assignee_code="interp-li-jing",
        assignee_name="李静",
        deadline=date(2026, 7, 20),
        overdue=False,
        status="pending",
        reconciliation_status="pending",
        delivery_status="pending",
        updated_at=datetime.now(UTC),
    )


def test_create_work_package_persists_explicit_plot_assignments() -> None:
    """验证县区拆包会逐条写入当前任务图斑，而非仅保存县区名称。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    project = SimpleNamespace(id=1)
    task = SimpleNamespace(id=2, project_id=1)
    batch = SimpleNamespace(
        id=3,
        batch_code="HLJ-2026-A",
        status="planned",
        planned_start_date=date(2026, 7, 1),
        planned_end_date=date(2026, 7, 31),
    )
    workbench_dao.get_project_by_code.return_value = project
    workbench_dao.get_task_by_code.return_value = task
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    dao.get_active_project_user.return_value = SimpleNamespace(
        user_code="interp-li-jing",
        display_name="李静",
    )
    dao.get_batch_by_code_for_update.return_value = batch
    dao.list_package_metrics.return_value = []
    dao.get_district.return_value = SimpleNamespace(boundary_name="道里区")
    dao.list_task_region_plots.return_value = [
        {"plot_code": "OSM-HLJ-1", "area_ha": Decimal("5.0000")},
        {"plot_code": "OSM-HLJ-2", "area_ha": Decimal("7.5000")},
    ]

    async def add_package(_: object, package: WorkPackage) -> WorkPackage:
        package.id = 10
        return package

    dao.add_package.side_effect = add_package
    response_package = build_package_response()
    service = StubOverviewProductionService(
        SimpleNamespace(
            batches=[
                SimpleNamespace(
                    batch_code="HLJ-2026-A",
                    packages=[response_package],
                )
            ]
        ),
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        rule_service=AsyncMock(),
    )

    result = asyncio.run(
        service.create_work_packages(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            "HLJ-2026-A",
            WorkPackageCreateRequest(
                region_codes=["230102"],
                assignee_code="interp-li-jing",
                deadline=date(2026, 7, 20),
                operator_code="manager-zhao-zhiyuan",
            ),
        )
    )

    assert result.created_count == 1
    assert result.assigned_plot_count == 2
    assignments = dao.add_package_plots.await_args.args[1]
    assert [item.plot_code for item in assignments] == [
        "OSM-HLJ-1",
        "OSM-HLJ-2",
    ]
    package = dao.add_package.await_args.args[1]
    assert package.planned_plot_count == 2
    assert package.planned_area_ha == Decimal("12.5000")


def test_work_package_cannot_complete_before_all_plots_and_reconciliation() -> None:
    """验证作业包完成状态受图斑进度和合并校核门禁约束。"""
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=1)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(id=2, project_id=1)
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    dao.get_package_by_code_for_update.return_value = SimpleNamespace(
        id=10,
        batch_id=3,
        package_code="HLJ-2026-A-230102",
        assignee_code="interp-li-jing",
        assignee_name="李静",
        deadline=date(2026, 7, 20),
        status="in_progress",
        reconciliation_status="checking",
        delivery_status="pending",
    )
    dao.get_batch_by_id.return_value = SimpleNamespace(
        status="in_progress",
        planned_start_date=date(2026, 7, 1),
        planned_end_date=date(2026, 7, 31),
    )
    dao.get_package_progress.return_value = (20, 18)
    service = ProductionService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        rule_service=AsyncMock(),
    )

    with pytest.raises(ValidationException, match="尚未全部解译"):
        asyncio.run(
            service.update_work_package(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                "HLJ-2026-A-230102",
                WorkPackageUpdateRequest(
                    status="completed",
                    reconciliation_status="passed",
                    operator_code="manager-zhao-zhiyuan",
                ),
            )
        )
