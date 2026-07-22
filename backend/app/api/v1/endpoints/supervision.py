"""独立监理抽样、过程检查、整改复检、县区评价和报告端点。"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DatabaseSession
from app.schemas.supervision import (
    SupervisionCountyEvaluationRequest,
    SupervisionFindingCreateRequest,
    SupervisionInspectionCreateRequest,
    SupervisionOverviewResponse,
    SupervisionPlanCreateRequest,
    SupervisionPlanResponse,
    SupervisionRectificationRequest,
    SupervisionReinspectionRequest,
    SupervisionReportGenerateRequest,
    SupervisionReportResponse,
    SupervisionSamplePageResponse,
)
from app.services.supervision_service import SupervisionService

router = APIRouter(prefix="/api/v1/supervision", tags=["独立项目监理"])
service = SupervisionService()


@router.get("/overview", response_model=SupervisionOverviewResponse)
async def get_supervision_overview(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> SupervisionOverviewResponse:
    """查询独立监理真实工作区、计划和闭环证据。

    Args:
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        SupervisionOverviewResponse: 独立监理工作台聚合状态。
    """
    return await service.get_overview(db, project_code, task_code)


@router.post(
    "/plans",
    response_model=SupervisionPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_supervision_plan(
    request: SupervisionPlanCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> SupervisionPlanResponse:
    """从任务真实图斑创建可复现县区抽样计划。

    Args:
        request: 抽样方法、比例、县区和操作审计。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        SupervisionPlanResponse: 新建监理计划。
    """
    return await service.create_plan(db, project_code, task_code, request)


@router.get(
    "/plans/{plan_code}/samples",
    response_model=SupervisionSamplePageResponse,
)
async def list_supervision_samples(
    plan_code: str,
    db: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    region_code: Annotated[str | None, Query(max_length=50)] = None,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> SupervisionSamplePageResponse:
    """分页查询计划显式监理样本。

    Args:
        plan_code: 监理计划编号。
        db: FastAPI 注入的异步数据库会话。
        page: 页码。
        page_size: 每页样本数。
        region_code: 可选县区筛选。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        SupervisionSamplePageResponse: 样本总数和当前页。
    """
    return await service.list_samples(
        db,
        project_code,
        task_code,
        plan_code,
        page,
        page_size,
        region_code,
    )


@router.post(
    "/plans/{plan_code}/inspections",
    response_model=SupervisionPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_supervision_inspection(
    plan_code: str,
    request: SupervisionInspectionCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> SupervisionPlanResponse:
    """登记独立监理过程检查及实体证据。

    Args:
        plan_code: 监理计划编号。
        request: 检查环节、结论、时间和证据。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        SupervisionPlanResponse: 更新后的监理计划。
    """
    return await service.create_inspection(
        db,
        project_code,
        task_code,
        plan_code,
        request,
    )


@router.post(
    "/plans/{plan_code}/inspections/{inspection_code}/findings",
    response_model=SupervisionPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_supervision_finding(
    plan_code: str,
    inspection_code: str,
    request: SupervisionFindingCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> SupervisionPlanResponse:
    """为过程检查登记监理问题、证据和整改期限。

    Args:
        plan_code: 监理计划编号。
        inspection_code: 过程检查编号。
        request: 问题内容、严重度和证据。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        SupervisionPlanResponse: 更新后的监理计划。
    """
    return await service.create_finding(
        db,
        project_code,
        task_code,
        plan_code,
        inspection_code,
        request,
    )


@router.post(
    "/plans/{plan_code}/findings/{finding_code}/rectification",
    response_model=SupervisionPlanResponse,
)
async def submit_supervision_rectification(
    plan_code: str,
    finding_code: str,
    request: SupervisionRectificationRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> SupervisionPlanResponse:
    """生产团队提交监理问题整改证据。

    Args:
        plan_code: 监理计划编号。
        finding_code: 问题编号。
        request: 整改说明、证据和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        SupervisionPlanResponse: 更新后的监理计划。
    """
    return await service.submit_rectification(
        db,
        project_code,
        task_code,
        plan_code,
        finding_code,
        request,
    )


@router.post(
    "/plans/{plan_code}/findings/{finding_code}/reinspect",
    response_model=SupervisionPlanResponse,
)
async def reinspect_supervision_finding(
    plan_code: str,
    finding_code: str,
    request: SupervisionReinspectionRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> SupervisionPlanResponse:
    """独立监理执行问题逐轮复检。

    Args:
        plan_code: 监理计划编号。
        finding_code: 问题编号。
        request: 复检结果、证据和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        SupervisionPlanResponse: 更新后的监理计划。
    """
    return await service.reinspect_finding(
        db,
        project_code,
        task_code,
        plan_code,
        finding_code,
        request,
    )


@router.patch(
    "/plans/{plan_code}/county-evaluations/{region_code}",
    response_model=SupervisionPlanResponse,
)
async def evaluate_supervision_county(
    plan_code: str,
    region_code: str,
    request: SupervisionCountyEvaluationRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> SupervisionPlanResponse:
    """新增或更新县区独立监理量化评价。

    Args:
        plan_code: 监理计划编号。
        region_code: 县区编码。
        request: 三项评分、评价说明和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        SupervisionPlanResponse: 更新后的监理计划。
    """
    return await service.evaluate_county(
        db,
        project_code,
        task_code,
        plan_code,
        region_code,
        request,
    )


@router.post(
    "/plans/{plan_code}/report",
    response_model=SupervisionReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_supervision_report(
    plan_code: str,
    request: SupervisionReportGenerateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> SupervisionReportResponse:
    """通过闭环门禁后生成不可变监理实体报告。

    Args:
        plan_code: 监理计划编号。
        request: 生成操作人和说明。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        SupervisionReportResponse: 报告实体和校验值。
    """
    return await service.generate_report(
        db,
        project_code,
        task_code,
        plan_code,
        request,
    )


@router.get("/reports/{report_code}/download")
async def download_supervision_report(
    report_code: str,
    db: DatabaseSession,
    user_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> Response:
    """鉴权并重新校验 SHA-256 后下载监理报告。

    Args:
        report_code: 报告编号。
        db: FastAPI 注入的异步数据库会话。
        user_code: 下载用户稳定编码。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        Response: 监理 JSON 报告文件。
    """
    content, filename, checksum = await service.get_report_file(
        db,
        project_code,
        task_code,
        report_code,
        user_code,
    )
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + quote(filename)
            ),
            "ETag": f'"{checksum}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
