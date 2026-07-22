"""任务作用域面积统计与导出测试。"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import PermissionDeniedException, ValidationException
from app.dao.statistics_dao import StatisticsDAO
from app.schemas.statistics import (
    AreaGroupItem,
    AreaStatisticsResponse,
    AreaStatisticsSnapshotImportMetadata,
    AreaTrendItem,
)
from app.services.statistics_service import StatisticsService
from app.services.statistics_snapshot_parser import StatisticsSnapshotCsvParser


def build_summary() -> AreaStatisticsResponse:
    """构造可导出的任务统计响应。

    Returns:
        AreaStatisticsResponse: 包含行政区和作物维度的统计响应。
    """
    district = AreaGroupItem(
        code="230109",
        label="松北区",
        parent_label="哈尔滨市",
        plot_count=2,
        area_ha=20,
        area_mu=300,
        percentage=100,
    )
    city = AreaGroupItem(
        label="哈尔滨市",
        plot_count=2,
        area_ha=20,
        area_mu=300,
        percentage=100,
    )
    return AreaStatisticsResponse(
        task_code="RS-TEST",
        monitor_year=2026,
        generated_at=datetime(2026, 7, 22, tzinfo=UTC),
        total_plot_count=2,
        total_area_ha=20,
        total_area_mu=300,
        average_plot_area_ha=10,
        farmland_area_ha=20,
        crop_assigned_plot_count=2,
        crop_assignment_rate=100,
        by_land_class=[city.model_copy(update={"label": "耕地"})],
        by_crop_type=[city.model_copy(update={"label": "玉米"})],
        by_planting_mode=[city.model_copy(update={"label": "单季种植"})],
        by_city=[city],
        by_district=[district],
        by_village=[city.model_copy(update={"label": "幸福村"})],
        annual_trend=[
            AreaTrendItem(
                year=2026,
                area_ha=20,
                year_over_year=None,
                source_name="当前任务实时汇总",
                source_version=None,
                recorded_at=datetime(2026, 7, 22, tzinfo=UTC),
                is_current=True,
            )
        ],
    )


def test_statistics_dao_totals_join_explicit_task_scope() -> None:
    """验证总量查询必须连接 task_plots 并绑定任务主键。"""
    dao = StatisticsDAO()
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(
        one=lambda: (2, Decimal("20.0000")),
    )

    result = asyncio.run(dao.get_totals(db, 91))

    statement = db.execute.await_args.args[0]
    compiled = statement.compile()
    assert result == (2, Decimal("20.0000"))
    assert "task_plots" in str(compiled)
    assert 91 in compiled.params.values()


def test_statistics_trend_uses_current_task_value_for_monitor_year() -> None:
    """验证当前年度固定使用任务实时面积而不是旧快照值。"""
    result = StatisticsService._build_trend(
        [
            SimpleNamespace(
                monitor_year=2025,
                total_area_ha=Decimal("18"),
                source_name="年度验收成果",
                source_version="v2025",
                generated_at=datetime(2025, 12, 31, tzinfo=UTC),
            ),
            SimpleNamespace(
                monitor_year=2026,
                total_area_ha=Decimal("999"),
                source_name="错误当前年快照",
                source_version="invalid",
                generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ],
        2026,
        Decimal("20"),
        datetime(2026, 7, 22, tzinfo=UTC),
    )

    assert [item.year for item in result] == [2025, 2026]
    assert result[-1].area_ha == 20
    assert result[-1].year_over_year == 11.11
    assert result[-1].is_current is True
    assert result[0].source_version == "v2025"


def test_statistics_csv_export_contains_scope_and_dimensions() -> None:
    """验证项目负责人可导出包含行政区和业务维度的 UTF-8 CSV。"""
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=7,
        project_id=3,
    )
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )
    service = StatisticsService(
        dao=AsyncMock(),
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )
    service.get_area_statistics = AsyncMock(return_value=build_summary())

    filename, content = asyncio.run(
        service.export_area_statistics_csv(
            AsyncMock(),
            "RS-TEST",
            "manager-zhao-zhiyuan",
        )
    )

    decoded = content.decode("utf-8-sig")
    assert filename == "RS-TEST_area_statistics_2026.csv"
    assert "任务图斑数,2" in decoded
    assert "地级区域" in decoded
    assert "县区" in decoded
    assert "种植模式" in decoded
    assert "230109,松北区,哈尔滨市" in decoded


def test_statistics_csv_export_rejects_interpreter() -> None:
    """验证内业解译员不能绕过后端能力门禁导出统计成果。"""
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=7,
        project_id=3,
    )
    user_service = AsyncMock()
    user_service.require_capability.side_effect = PermissionDeniedException(
        "内业解译员无权执行当前业务节点"
    )
    service = StatisticsService(
        dao=AsyncMock(),
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )

    with pytest.raises(PermissionDeniedException):
        asyncio.run(
            service.export_area_statistics_csv(
                AsyncMock(),
                "RS-TEST",
                "interp-li-jing",
            )
        )


def test_statistics_history_parser_rejects_invalid_area_relationship() -> None:
    """验证作物面积超过耕地面积时整批拒绝。"""
    parser = StatisticsSnapshotCsvParser()
    content = (
        b"monitor_year,total_area_ha,farmland_area_ha,crop_area_ha\n"
        b"2025,100,80,90\n"
    )

    with pytest.raises(ValidationException, match="作物面积不得大于耕地面积"):
        parser.parse("history.csv", content)


def test_statistics_history_import_persists_file_audit() -> None:
    """验证历史快照导入保存文件校验、批次和项目负责人审计。"""
    dao = AsyncMock()
    dao.get_project_monitor_year.return_value = 2026
    dao.get_snapshots_for_update.return_value = {}

    async def create_batch(_db, batch):
        batch.id = 99
        return batch

    dao.create_import_batch.side_effect = create_batch
    workbench_dao = AsyncMock()
    task = SimpleNamespace(
        id=7,
        project_id=3,
        updated_at=datetime(2026, 7, 22, tzinfo=UTC),
    )
    workbench_dao.get_task_by_code_for_update.return_value = task
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )
    service = StatisticsService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )
    metadata = AreaStatisticsSnapshotImportMetadata(
        source_name="2025 年农业农村统计年报",
        source_uri="archive://statistics/2025/final.csv",
        source_version="final-v1",
        operator_code="manager-zhao-zhiyuan",
        comment="经甲方盖章成果表核对后导入",
        conflict_strategy="reject",
    )
    content = (
        b"monitor_year,total_area_ha,farmland_area_ha,crop_area_ha\n"
        b"2024,100.5,80.2,70.1\n"
        b"2025,102.5,82.2,72.1\n"
    )
    db = AsyncMock()

    response = asyncio.run(
        service.import_history_csv(
            db,
            "RS-TEST",
            metadata,
            "history.csv",
            content,
        )
    )

    assert response.imported_count == 2
    assert response.replaced_count == 0
    assert response.years == [2024, 2025]
    assert response.source_checksum_sha256 == sha256(content).hexdigest()
    assert dao.save_snapshot.await_count == 2
    batch = dao.create_import_batch.await_args.args[1]
    assert batch.source_uri == "archive://statistics/2025/final.csv"
    assert batch.imported_by_code == "manager-zhao-zhiyuan"
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_statistics_history_import_rejects_current_year() -> None:
    """验证历史导入不得覆盖当前监测年度实时值。"""
    dao = AsyncMock()
    dao.get_project_monitor_year.return_value = 2026
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = SimpleNamespace(
        id=7,
        project_id=3,
    )
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace()
    service = StatisticsService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )
    metadata = AreaStatisticsSnapshotImportMetadata(
        source_name="统计年报",
        source_uri="archive://statistics/current.csv",
        source_version="v1",
        operator_code="manager-zhao-zhiyuan",
        comment="当前年度拒绝测试",
    )

    with pytest.raises(ValidationException, match="必须早于当前监测年度"):
        asyncio.run(
            service.import_history_csv(
                AsyncMock(),
                "RS-TEST",
                metadata,
                "history.csv",
                (
                    b"monitor_year,total_area_ha,farmland_area_ha,crop_area_ha\n"
                    b"2026,100,80,70\n"
                ),
            )
        )

    dao.create_import_batch.assert_not_awaited()
