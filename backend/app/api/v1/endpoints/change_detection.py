"""多时相变化检测任务、候选导入与人工判读端点。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DatabaseSession
from app.schemas.change_detection import (
    ChangeCandidateDiscoveryRequest,
    ChangeCandidateDiscoveryResponse,
    ChangeCandidateGeoJsonImportRequest,
    ChangeCandidateImportResponse,
    ChangeCandidateResponse,
    ChangeCandidateReviewRequest,
    ChangeComparisonMetadataResponse,
    ChangeDetectionOverviewResponse,
    ChangeDetectionRunResponse,
    ChangeRunCreateRequest,
)
from app.services.change_candidate_discovery_service import (
    ChangeCandidateDiscoveryService,
)
from app.services.change_comparison_service import ChangeComparisonService
from app.services.change_detection_service import ChangeDetectionService

router = APIRouter(prefix="/api/v1/change-detection", tags=["多时相变化检测"])
service = ChangeDetectionService()
comparison_service = ChangeComparisonService()
discovery_service = ChangeCandidateDiscoveryService(
    comparison_service=comparison_service,
)


@router.get("/overview", response_model=ChangeDetectionOverviewResponse)
async def get_change_detection_overview(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ChangeDetectionOverviewResponse:
    """查询真实影像资格、检测任务、候选队列和判读历史。

    Args:
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ChangeDetectionOverviewResponse: 变化检测工作台聚合状态。
    """
    return await service.get_overview(db, project_code, task_code)


@router.post(
    "/runs",
    response_model=ChangeDetectionRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_change_detection_run(
    request: ChangeRunCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ChangeDetectionRunResponse:
    """绑定两期已核验影像、规则快照和配准证据创建任务。

    Args:
        request: 时相影像、配准证据和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ChangeDetectionRunResponse: 新建变化检测任务。
    """
    return await service.create_run(db, project_code, task_code, request)


@router.post(
    "/runs/{run_code}/candidates/import-geojson",
    response_model=ChangeCandidateImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_change_candidates(
    run_code: str,
    request: ChangeCandidateGeoJsonImportRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ChangeCandidateImportResponse:
    """原子导入外部模型或生产工具生成的真实候选 GeoJSON。

    Args:
        run_code: 变化检测任务编号。
        request: FeatureCollection、来源、版本和操作审计。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ChangeCandidateImportResponse: 导入批次和候选统计。
    """
    return await service.import_candidates(
        db,
        project_code,
        task_code,
        run_code,
        request,
    )


@router.post(
    "/runs/{run_code}/discover-candidates",
    response_model=ChangeCandidateDiscoveryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def discover_change_candidates(
    run_code: str,
    request: ChangeCandidateDiscoveryRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ChangeCandidateDiscoveryResponse:
    """运行内置 RGB 差分算法并生成待人工分类候选。

    Args:
        run_code: 变化检测任务编号。
        request: 差分阈值、连通域、候选上限和操作说明。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ChangeCandidateDiscoveryResponse: 实体 GeoJSON 和候选统计。
    """
    return await discovery_service.discover_candidates(
        db,
        project_code,
        task_code,
        run_code,
        request,
    )


@router.get(
    "/runs/{run_code}/comparison",
    response_model=ChangeComparisonMetadataResponse,
)
async def get_change_comparison_metadata(
    run_code: str,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ChangeComparisonMetadataResponse:
    """生成或读取双时相公共网格预览及来源清单。

    Args:
        run_code: 变化检测任务编号。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ChangeComparisonMetadataResponse: 两期预览地址和渲染证据。
    """
    return await comparison_service.get_metadata(
        db,
        project_code,
        task_code,
        run_code,
    )


@router.get("/runs/{run_code}/comparison/{side}.png")
async def get_change_comparison_image(
    run_code: str,
    side: Literal["baseline", "target"],
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> Response:
    """读取已校验前或后时相 PNG 预览。

    Args:
        run_code: 变化检测任务编号。
        side: 前时相或后时相。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        Response: 带 SHA-256 ETag 的 PNG 响应。
    """
    content, etag = await comparison_service.get_image(
        db,
        project_code,
        task_code,
        run_code,
        side,
    )
    return Response(
        content=content,
        media_type="image/png",
        headers={
            "ETag": f'"{etag}"',
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch(
    "/runs/{run_code}/candidates/{candidate_code}/review",
    response_model=ChangeCandidateResponse,
)
async def review_change_candidate(
    run_code: str,
    candidate_code: str,
    request: ChangeCandidateReviewRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ChangeCandidateResponse:
    """人工确认、重分类或排除候选并追加不可变判读历史。

    Args:
        run_code: 变化检测任务编号。
        candidate_code: 候选编号。
        request: 判读结论、依据和稳定用户编码。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ChangeCandidateResponse: 更新后的候选及完整历史。
    """
    return await service.review_candidate(
        db,
        project_code,
        task_code,
        run_code,
        candidate_code,
        request,
    )
