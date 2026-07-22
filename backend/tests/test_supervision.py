"""独立监理抽样、权限、整改复检门禁和报告门禁测试。"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.schemas.supervision import (
    SupervisionFindingCreateRequest,
    SupervisionInspectionCreateRequest,
    SupervisionPlanCreateRequest,
    SupervisionRectificationRequest,
    SupervisionReportGenerateRequest,
)
from app.services.supervision_service import SupervisionService


def test_plan_schema_rejects_duplicate_regions_and_reversed_dates() -> None:
    """验证抽样县区唯一且计划日期必须正向。"""
    with pytest.raises(ValidationError):
        SupervisionPlanCreateRequest(
            plan_code="SV-001",
            plan_name="首轮独立监理",
            sampling_method="systematic",
            sample_ratio=5,
            minimum_per_region=3,
            region_codes=["230102", "230102"],
            planned_start_date=date(2026, 8, 2),
            planned_end_date=date(2026, 8, 1),
            operator_code="supervisor-independent",
            comment="按县区执行首轮抽样",
        )


def test_inspection_schema_requires_timezone() -> None:
    """验证过程检查时间必须包含可审计时区。"""
    with pytest.raises(ValidationError, match="必须包含时区"):
        SupervisionInspectionCreateRequest(
            inspection_code="INSP-001",
            inspection_stage="plot_interpretation",
            inspected_at=datetime(2026, 8, 1, 9, 0),
            conclusion="conditional",
            evidence_uri="archive://supervision/inspection-001",
            summary="抽样检查发现边界证据不完整",
            operator_code="supervisor-independent",
        )


def test_finding_schema_rejects_blank_required_evidence() -> None:
    """验证监理问题必填事实不能被空白字符串绕过。"""
    with pytest.raises(ValidationError, match="监理问题字段不得为空"):
        SupervisionFindingCreateRequest(
            finding_code="F-001",
            plot_code=None,
            region_code="230102",
            issue_type="边界偏差",
            severity="major",
            description="存在边界套合偏差",
            evidence_uri="   ",
            rework_deadline=date(2026, 8, 10),
            operator_code="supervisor-independent",
        )


def test_systematic_sampling_is_even_and_reproducible() -> None:
    """验证系统抽样均匀覆盖排序后的县区图斑。"""
    candidates = [{"plot_code": f"PLOT-{index:02d}"} for index in range(10)]
    selected = SupervisionService._select_region_candidates(
        candidates,
        "SV-001",
        "systematic",
        4,
    )

    assert [row["plot_code"] for row in selected] == [
        "PLOT-01",
        "PLOT-03",
        "PLOT-06",
        "PLOT-08",
    ]


def test_stratified_random_sampling_uses_stable_plan_salt() -> None:
    """验证分层随机抽样在相同计划编号下结果稳定。"""
    candidates = [{"plot_code": f"PLOT-{index:02d}"} for index in range(20)]
    first = SupervisionService._select_region_candidates(
        candidates,
        "SV-STABLE",
        "stratified_random",
        5,
    )
    second = SupervisionService._select_region_candidates(
        list(reversed(candidates)),
        "SV-STABLE",
        "stratified_random",
        5,
    )

    assert [row["plot_code"] for row in first] == [
        row["plot_code"] for row in second
    ]


def test_create_plan_persists_explicit_real_samples() -> None:
    """验证计划按县区比例写入真实任务图斑和版本快照。"""
    dao = SimpleNamespace(
        get_plan_by_code=AsyncMock(return_value=None),
        list_work_areas=AsyncMock(
            return_value=[
                {
                    "city_code": "230100",
                    "city_name": "哈尔滨市",
                    "region_code": "230102",
                    "region_name": "道里区",
                    "plot_count": 4,
                    "area_ha": 10,
                }
            ]
        ),
        list_candidate_plots=AsyncMock(
            return_value=[
                {
                    "plot_code": f"PLOT-{index}",
                    "region_code": "230102",
                    "region_name": "道里区",
                    "plot_version": index,
                }
                for index in range(1, 5)
            ]
        ),
        count_task_plots=AsyncMock(return_value=35020),
        add_plan=AsyncMock(side_effect=lambda _db, plan: setattr(plan, "id", 10)),
        add_samples=AsyncMock(),
        add_event=AsyncMock(),
    )
    task_updated_at = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
    workbench_dao = SimpleNamespace(
        get_project_by_code=AsyncMock(return_value=SimpleNamespace(id=1)),
        get_task_by_code=AsyncMock(
            return_value=SimpleNamespace(
                id=2,
                project_id=1,
                updated_at=task_updated_at,
            )
        ),
    )
    user_service = SimpleNamespace(
        require_capability=AsyncMock(
            return_value=SimpleNamespace(
                display_name="独立监理单位代表",
                user_code="supervisor-independent",
                role_code="independent_supervisor",
            )
        )
    )
    service = SupervisionService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
    )
    response = SimpleNamespace(sample_count=2)
    service._build_plan_response = AsyncMock(return_value=response)
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    request = SupervisionPlanCreateRequest(
        plan_code="SV-001",
        plan_name="首轮独立监理",
        sampling_method="systematic",
        sample_ratio=50,
        minimum_per_region=1,
        region_codes=["230102"],
        planned_start_date=date(2026, 7, 22),
        planned_end_date=date(2026, 8, 22),
        operator_code="supervisor-independent",
        comment="按真实任务图斑抽样",
    )

    result = asyncio.run(service.create_plan(db, "RS-2026", "RS-2026-045", request))

    assert result is response
    samples = dao.add_samples.await_args.args[1]
    assert len(samples) == 2
    assert {sample.plot_code for sample in samples}.issubset(
        {"PLOT-1", "PLOT-2", "PLOT-3", "PLOT-4"}
    )
    assert all(sample.plot_version_snapshot > 0 for sample in samples)
    user_service.require_capability.assert_awaited_once_with(
        db,
        1,
        "supervisor-independent",
        "supervise_project",
    )


def test_rectification_requires_production_team_capability() -> None:
    """验证整改提交走独立能力校验而非客户端角色字符串。"""
    dao = SimpleNamespace(
        get_plan_by_code=AsyncMock(
            return_value=SimpleNamespace(id=10, status="active")
        ),
        get_finding_by_code_for_update=AsyncMock(
            return_value=SimpleNamespace(
                finding_code="F-001",
                status="open",
                rectification_comment=None,
                rectification_evidence_uri=None,
                rectified_by=None,
                rectified_by_code=None,
                rectified_by_role=None,
                rectified_at=None,
                updated_at=None,
            )
        ),
        add_event=AsyncMock(),
    )
    workbench_dao = SimpleNamespace(
        get_project_by_code=AsyncMock(return_value=SimpleNamespace(id=1)),
        get_task_by_code=AsyncMock(
            return_value=SimpleNamespace(id=2, project_id=1)
        ),
    )
    user_service = SimpleNamespace(
        require_capability=AsyncMock(
            return_value=SimpleNamespace(
                display_name="项目负责人",
                user_code="manager-001",
                role_code="project_manager",
            )
        )
    )
    db = SimpleNamespace(commit=AsyncMock())
    service = SupervisionService(dao, workbench_dao, user_service)
    service._build_plan_response = AsyncMock(return_value=SimpleNamespace())
    request = SupervisionRectificationRequest(
        rectification_comment="已重新提交边界判读证据",
        rectification_evidence_uri="archive://rectification/F-001",
        operator_code="manager-001",
    )

    asyncio.run(
        service.submit_rectification(
            db,
            "RS-2026",
            "RS-2026-045",
            "SV-001",
            "F-001",
            request,
        )
    )

    user_service.require_capability.assert_awaited_once_with(
        db,
        1,
        "manager-001",
        "rectify_supervision_finding",
    )


def test_report_generation_rejects_open_findings() -> None:
    """验证未闭环监理问题阻止生成不可变报告。"""
    task_updated_at = datetime.now(UTC)
    plan = SimpleNamespace(
        id=10,
        plan_code="SV-001",
        status="active",
        task_plot_count_snapshot=35020,
        task_updated_at_snapshot=task_updated_at,
    )
    dao = SimpleNamespace(
        get_plan_by_code=AsyncMock(return_value=plan),
        get_report=AsyncMock(return_value=None),
        count_task_plots=AsyncMock(return_value=35020),
    )
    workbench_dao = SimpleNamespace(
        get_project_by_code=AsyncMock(return_value=SimpleNamespace(id=1)),
        get_task_by_code=AsyncMock(
            return_value=SimpleNamespace(
                id=2,
                project_id=1,
                updated_at=task_updated_at,
            )
        ),
    )
    user_service = SimpleNamespace(
        require_capability=AsyncMock(
            return_value=SimpleNamespace(
                display_name="独立监理单位代表",
                user_code="supervisor-independent",
                role_code="independent_supervisor",
            )
        )
    )
    service = SupervisionService(dao, workbench_dao, user_service)
    service._build_plan_response = AsyncMock(
        return_value=SimpleNamespace(
            inspection_count=1,
            open_finding_count=2,
        )
    )
    request = SupervisionReportGenerateRequest(
        operator_code="supervisor-independent",
        comment="生成首轮独立监理报告",
    )

    with pytest.raises(ValidationException, match="仍有 2 个监理问题未闭环"):
        asyncio.run(
            service.generate_report(
                None,
                "RS-2026",
                "RS-2026-045",
                "SV-001",
                request,
            )
        )


def test_report_generation_rejects_stale_task_snapshot() -> None:
    """验证任务范围变化后旧监理计划不能继续生成报告。"""
    snapshot_time = datetime.now(UTC) - timedelta(days=1)
    task_time = datetime.now(UTC)
    plan = SimpleNamespace(
        id=10,
        plan_code="SV-001",
        status="active",
        task_plot_count_snapshot=35020,
        task_updated_at_snapshot=snapshot_time,
    )
    dao = SimpleNamespace(
        get_plan_by_code=AsyncMock(return_value=plan),
        get_report=AsyncMock(return_value=None),
        count_task_plots=AsyncMock(return_value=35020),
    )
    workbench_dao = SimpleNamespace(
        get_project_by_code=AsyncMock(return_value=SimpleNamespace(id=1)),
        get_task_by_code=AsyncMock(
            return_value=SimpleNamespace(id=2, project_id=1, updated_at=task_time)
        ),
    )
    user_service = SimpleNamespace(
        require_capability=AsyncMock(
            return_value=SimpleNamespace(
                display_name="独立监理单位代表",
                user_code="supervisor-independent",
                role_code="independent_supervisor",
            )
        )
    )
    service = SupervisionService(dao, workbench_dao, user_service)
    request = SupervisionReportGenerateRequest(
        operator_code="supervisor-independent",
        comment="生成首轮独立监理报告",
    )

    with pytest.raises(ValidationException, match="任务图斑范围或数据版本已变化"):
        asyncio.run(
            service.generate_report(
                None,
                "RS-2026",
                "RS-2026-045",
                "SV-001",
                request,
            )
        )
