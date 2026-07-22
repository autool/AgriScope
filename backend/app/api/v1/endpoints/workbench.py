"""遥感监测工作台业务端点。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DatabaseSession
from app.schemas.workbench import (
    BatchPlotAttributeUpdateRequest,
    BatchPlotAttributeUpdateResponse,
    PlotAttributeMutationRequest,
    PlotAttributesResponse,
    PlotCreateRequest,
    PlotDeleteRequest,
    PlotGeometryUpdateRequest,
    PlotHistoryActionRequest,
    PlotHistoryActionResponse,
    PlotMergeRequest,
    PlotMergeResponse,
    PlotOperationHistoryStateResponse,
    PlotQualityCheckRequest,
    PlotSplitRequest,
    PlotSplitResponse,
    QualityCheckResponse,
    QualityIssueListResponse,
    QualityIssueResolveRequest,
    QualityIssueResolveResponse,
    TaskQualityCheckRequest,
    TaskQualityCheckResponse,
    TaskSubmitRequest,
    TaskSummary,
    WorkbenchOverviewResponse,
)
from app.services.workbench_service import WorkbenchService

router = APIRouter(prefix="/api/v1/workbench", tags=["遥感监测工作台"])
workbench_service = WorkbenchService()


@router.get("/overview", response_model=WorkbenchOverviewResponse)
async def get_workbench_overview(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> WorkbenchOverviewResponse:
    """获取工作台项目、任务、影像和审核聚合数据。

    Args:
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        WorkbenchOverviewResponse: 工作台初始化数据。
    """
    return await workbench_service.get_overview(db, project_code, task_code)


@router.get("/plots/{plot_code}", response_model=PlotAttributesResponse)
async def get_plot_attributes(
    plot_code: str,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> PlotAttributesResponse:
    """获取解译图斑业务属性。

    Args:
        plot_code: 图斑编号。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        PlotAttributesResponse: 图斑业务属性。
    """
    return await workbench_service.get_plot_attributes(db, task_code, plot_code)


@router.post("/plots", response_model=PlotAttributesResponse)
async def create_plot(
    request: PlotCreateRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> PlotAttributesResponse:
    """创建人工解译图斑并生成初始版本。

    Args:
        request: 新建图斑几何、属性和操作信息。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        PlotAttributesResponse: 新建图斑属性。
    """
    return await workbench_service.create_plot(db, task_code, request)


@router.patch("/plots/{plot_code}", response_model=PlotAttributesResponse)
async def update_plot_attributes(
    plot_code: str,
    request: PlotAttributeMutationRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> PlotAttributesResponse:
    """更新解译图斑属性并生成新版本。

    Args:
        plot_code: 图斑编号。
        request: 图斑属性更新请求。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        PlotAttributesResponse: 更新后的图斑属性。
    """
    return await workbench_service.update_plot_attributes(
        db,
        task_code,
        plot_code,
        request,
    )


@router.post(
    "/tasks/{task_code}/plots/batch-attributes",
    response_model=BatchPlotAttributeUpdateResponse,
)
async def batch_update_plot_attributes(
    task_code: str,
    request: BatchPlotAttributeUpdateRequest,
    db: DatabaseSession,
) -> BatchPlotAttributeUpdateResponse:
    """对显式选择的任务图斑批量赋值并生成新版本。

    Args:
        task_code: 作业任务编号。
        request: 图斑编号、目标属性、操作人和说明。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        BatchPlotAttributeUpdateResponse: 更新数量和任务进度。
    """
    return await workbench_service.batch_update_plot_attributes(
        db,
        task_code,
        request,
    )


@router.patch(
    "/plots/{plot_code}/geometry",
    response_model=PlotAttributesResponse,
)
async def update_plot_geometry(
    plot_code: str,
    request: PlotGeometryUpdateRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> PlotAttributesResponse:
    """保存节点编辑后的图斑边界并生成新版本。

    Args:
        plot_code: 图斑编号。
        request: 新边界、操作人和说明。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        PlotAttributesResponse: 更新后的图斑属性。
    """
    return await workbench_service.update_plot_geometry(
        db,
        task_code,
        plot_code,
        request,
    )


@router.delete("/plots/{plot_code}", response_model=PlotAttributesResponse)
async def delete_plot(
    plot_code: str,
    request: PlotDeleteRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> PlotAttributesResponse:
    """软删除图斑并保留版本和审计记录。

    Args:
        plot_code: 图斑编号。
        request: 操作人和删除原因。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        PlotAttributesResponse: 删除状态图斑属性。
    """
    return await workbench_service.delete_plot(
        db,
        task_code,
        plot_code,
        request,
    )


@router.post(
    "/tasks/{task_code}/plots/{plot_code}/split",
    response_model=PlotSplitResponse,
)
async def split_plot(
    task_code: str,
    plot_code: str,
    request: PlotSplitRequest,
    db: DatabaseSession,
) -> PlotSplitResponse:
    """使用人工绘制分割线拆分任务内图斑。

    Args:
        task_code: 作业任务编号。
        plot_code: 待分割图斑编号。
        request: 分割线、操作人编码和判读依据。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        PlotSplitResponse: 两个子图斑、面积守恒和审计结果。
    """
    return await workbench_service.split_plot(
        db,
        task_code,
        plot_code,
        request,
    )


@router.post(
    "/tasks/{task_code}/plots/merge",
    response_model=PlotMergeResponse,
)
async def merge_plots(
    task_code: str,
    request: PlotMergeRequest,
    db: DatabaseSession,
) -> PlotMergeResponse:
    """合并显式选择的相邻任务图斑并保存属性冲突结论。

    Args:
        task_code: 作业任务编号。
        request: 源图斑编号、确认属性、操作人和合并依据。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        PlotMergeResponse: 合并结果、面积和操作审计。
    """
    return await workbench_service.merge_plots(db, task_code, request)


@router.get(
    "/tasks/{task_code}/plot-operations/history-state",
    response_model=PlotOperationHistoryStateResponse,
)
async def get_plot_operation_history_state(
    task_code: str,
    db: DatabaseSession,
) -> PlotOperationHistoryStateResponse:
    """查询任务当前可撤销和可重做操作。

    Args:
        task_code: 作业任务编号。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        PlotOperationHistoryStateResponse: 撤销和重做候选摘要。
    """
    return await workbench_service.get_plot_operation_history_state(
        db,
        task_code,
    )


@router.post(
    "/tasks/{task_code}/plot-operations/undo",
    response_model=PlotHistoryActionResponse,
)
async def undo_plot_operation(
    task_code: str,
    request: PlotHistoryActionRequest,
    db: DatabaseSession,
) -> PlotHistoryActionResponse:
    """撤销最近一个仍生效的分割或合并操作。

    Args:
        task_code: 作业任务编号。
        request: 操作人编码和撤销依据。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        PlotHistoryActionResponse: 撤销后的活动图斑和任务进度。
    """
    return await workbench_service.undo_plot_operation(db, task_code, request)


@router.post(
    "/tasks/{task_code}/plot-operations/redo",
    response_model=PlotHistoryActionResponse,
)
async def redo_plot_operation(
    task_code: str,
    request: PlotHistoryActionRequest,
    db: DatabaseSession,
) -> PlotHistoryActionResponse:
    """重做最近一个已撤销且尚未失效的操作。

    Args:
        task_code: 作业任务编号。
        request: 操作人编码和重做依据。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        PlotHistoryActionResponse: 重做后的活动图斑和任务进度。
    """
    return await workbench_service.redo_plot_operation(db, task_code, request)


@router.post(
    "/plots/{plot_code}/quality-check",
    response_model=QualityCheckResponse,
)
async def check_plot_quality(
    plot_code: str,
    request: PlotQualityCheckRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> QualityCheckResponse:
    """执行图斑质量规则检查并持久化问题。

    Args:
        plot_code: 图斑编号。
        request: 质检操作人编码。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        QualityCheckResponse: 质量得分和规则结果。
    """
    return await workbench_service.check_plot_quality(
        db,
        task_code,
        plot_code,
        request,
    )


@router.post(
    "/tasks/{task_code}/quality-checks/run",
    response_model=TaskQualityCheckResponse,
)
async def run_task_quality_checks(
    task_code: str,
    request: TaskQualityCheckRequest,
    db: DatabaseSession,
) -> TaskQualityCheckResponse:
    """执行任务作用域内全部图斑质量检查。

    Args:
        task_code: 作业任务编号。
        request: 操作人和执行说明。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        TaskQualityCheckResponse: 任务质量覆盖率、通过率和规则汇总。
    """
    return await workbench_service.run_task_quality_checks(
        db,
        task_code,
        request,
    )


@router.get(
    "/tasks/{task_code}/quality-issues",
    response_model=QualityIssueListResponse,
)
async def get_task_quality_issues(
    task_code: str,
    db: DatabaseSession,
    status: Annotated[Literal["open", "resolved", "all"], Query()] = "open",
    rule_code: Annotated[str | None, Query(max_length=60)] = None,
    severity: Annotated[
        Literal["high", "medium", "low"] | None,
        Query(),
    ] = None,
    issue_type: Annotated[str | None, Query(max_length=30)] = None,
    keyword: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=10, le=100)] = 20,
) -> QualityIssueListResponse:
    """分页查询任务质量问题队列。

    Args:
        task_code: 作业任务编号。
        db: FastAPI 注入的异步数据库会话。
        status: 问题状态或全部。
        rule_code: 可选质量规则编码。
        severity: 可选严重度。
        issue_type: 可选问题类型。
        keyword: 图斑编号或行政区关键词。
        page: 页码。
        page_size: 每页条数。

    Returns:
        QualityIssueListResponse: 问题分页、规则数量和严重度汇总。
    """
    return await workbench_service.get_task_quality_issues(
        db,
        task_code,
        status=status,
        rule_code=rule_code,
        severity=severity,
        issue_type=issue_type,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/tasks/{task_code}/quality-issues/{issue_id}/resolve",
    response_model=QualityIssueResolveResponse,
)
async def resolve_review_issue(
    task_code: str,
    issue_id: int,
    request: QualityIssueResolveRequest,
    db: DatabaseSession,
) -> QualityIssueResolveResponse:
    """确认关闭审核人员提出的人工问题。

    Args:
        task_code: 作业任务编号。
        issue_id: 问题主键。
        request: 操作人编码和关闭依据。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        QualityIssueResolveResponse: 问题关闭审计结果。
    """
    return await workbench_service.resolve_review_issue(
        db,
        task_code,
        issue_id,
        request,
    )


@router.post("/tasks/{task_code}/submit", response_model=TaskSummary)
async def submit_task_for_self_check(
    task_code: str,
    request: TaskSubmitRequest,
    db: DatabaseSession,
) -> TaskSummary:
    """提交任务至内业自检节点。

    Args:
        task_code: 作业任务编号。
        request: 提交人和备注。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        TaskSummary: 更新后的任务摘要。
    """
    return await workbench_service.submit_task_for_self_check(db, task_code, request)
