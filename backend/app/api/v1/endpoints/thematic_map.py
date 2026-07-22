"""专题图模板、批量生成、总览和实体下载端点。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DatabaseSession
from app.schemas.thematic_map import (
    ThematicMapBatchGenerateRequest,
    ThematicMapBatchGenerateResponse,
    ThematicMapOverviewResponse,
    ThematicMapTemplateCreateRequest,
    ThematicMapTemplateResponse,
)
from app.services.thematic_map_service import ThematicMapService

router = APIRouter(prefix="/api/v1/thematic-maps", tags=["专题制图"])
service = ThematicMapService()


@router.get("/overview", response_model=ThematicMapOverviewResponse)
async def get_thematic_map_overview(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ThematicMapOverviewResponse:
    """查询模板、真实影像产品来源和实体专题图。

    Args:
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ThematicMapOverviewResponse: 专题制图总览。
    """
    return await service.get_overview(db, project_code, task_code)


@router.post(
    "/templates",
    response_model=ThematicMapTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_thematic_map_template(
    request: ThematicMapTemplateCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ThematicMapTemplateResponse:
    """创建持久化专题图版式模板。

    Args:
        request: 图名模式、图幅、图例和制图单位等参数。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 审计所属任务编号。

    Returns:
        ThematicMapTemplateResponse: 已创建模板。
    """
    return await service.create_template(db, project_code, task_code, request)


@router.post(
    "/products/generate",
    response_model=ThematicMapBatchGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_thematic_map_products(
    request: ThematicMapBatchGenerateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ThematicMapBatchGenerateResponse:
    """从同一已校验波段产品实体原子批量生成专题图。

    Args:
        request: 模板、影像、成图定义和稳定操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ThematicMapBatchGenerateResponse: 全部实体成果。
    """
    return await service.generate_batch(db, project_code, task_code, request)


@router.get("/products/{product_code}/download")
async def download_thematic_map_product(
    product_code: str,
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    disposition: Annotated[
        Literal["inline", "attachment"],
        Query(),
    ] = "attachment",
) -> Response:
    """鉴权并重新校验大小、签名和 SHA256 后返回专题图。

    Args:
        product_code: 专题图成果编号。
        db: FastAPI 注入的异步数据库会话。
        operator_code: 预览或下载人稳定编码。
        disposition: 浏览器内预览或附件下载。

    Returns:
        Response: PNG 或 PDF 实体文件。
    """
    download = await service.get_download(
        db,
        product_code,
        operator_code,
        disposition,
    )
    return Response(
        content=download.content,
        media_type=download.media_type,
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{download.filename}"'
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
