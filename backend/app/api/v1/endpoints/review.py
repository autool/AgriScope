"""三级成果审核与版本管理端点。"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DatabaseSession
from app.schemas.review import (
    PlotRollbackRequest,
    PlotVersionListResponse,
    ReviewActionRequest,
    ReviewActionResponse,
)
from app.schemas.workbench import PlotAttributesResponse
from app.services.review_service import ReviewService

router = APIRouter(prefix="/api/v1/reviews", tags=["成果审核与版本管理"])
service = ReviewService()


@router.post("/tasks/{task_code}/actions", response_model=ReviewActionResponse)
async def execute_review_action(
    task_code: str,
    request: ReviewActionRequest,
    db: DatabaseSession,
) -> ReviewActionResponse:
    """执行任务通过、退回或驳回动作。

    Args:
        task_code: 作业任务编号。
        request: 审核动作和意见。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        ReviewActionResponse: 审核状态流转结果。
    """
    return await service.execute_task_action(db, task_code, request)


@router.get("/plots/{plot_code}/versions", response_model=PlotVersionListResponse)
async def list_plot_versions(
    plot_code: str,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> PlotVersionListResponse:
    """查询图斑历史版本。

    Args:
        plot_code: 图斑编号。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        PlotVersionListResponse: 当前版本和历史版本列表。
    """
    return await service.list_plot_versions(db, task_code, plot_code)


@router.post(
    "/plots/{plot_code}/rollback",
    response_model=PlotAttributesResponse,
)
async def rollback_plot_version(
    plot_code: str,
    request: PlotRollbackRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> PlotAttributesResponse:
    """回退图斑历史版本并生成新版本。

    Args:
        plot_code: 图斑编号。
        request: 目标版本和操作说明。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        PlotAttributesResponse: 回退后的图斑属性。
    """
    return await service.rollback_plot(db, task_code, plot_code, request)
