"""项目级地块自定义属性字段端点。"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DatabaseSession
from app.schemas.plot_attribute_field import (
    PlotAttributeFieldCreateRequest,
    PlotAttributeFieldListResponse,
    PlotAttributeFieldResponse,
    PlotAttributeFieldUpdateRequest,
)
from app.services.plot_attribute_field_service import PlotAttributeFieldService

router = APIRouter(
    prefix="/api/v1/plot-attribute-fields",
    tags=["项目地块自定义属性"],
)
service = PlotAttributeFieldService()


@router.get("", response_model=PlotAttributeFieldListResponse)
async def list_plot_attribute_fields(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    include_inactive: bool = True,
) -> PlotAttributeFieldListResponse:
    """查询项目自定义字段和当前活动模式摘要。

    Args:
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目业务编号。
        include_inactive: 是否包含停用字段。

    Returns:
        PlotAttributeFieldListResponse: 字段列表和模式 SHA-256。
    """
    return await service.list_fields(
        db,
        project_code,
        include_inactive=include_inactive,
    )


@router.post("", response_model=PlotAttributeFieldResponse)
async def create_plot_attribute_field(
    request: PlotAttributeFieldCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> PlotAttributeFieldResponse:
    """创建项目级自定义地块属性字段。

    Args:
        request: 字段语义和稳定操作人编码。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目业务编号。

    Returns:
        PlotAttributeFieldResponse: 新建字段定义。
    """
    return await service.create_field(db, project_code, request)


@router.patch("/{field_code}", response_model=PlotAttributeFieldResponse)
async def update_plot_attribute_field(
    field_code: str,
    request: PlotAttributeFieldUpdateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> PlotAttributeFieldResponse:
    """更新字段语义、排序或启停状态。

    Args:
        field_code: 不可变字段编码。
        request: 新字段语义和稳定操作人编码。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目业务编号。

    Returns:
        PlotAttributeFieldResponse: 更新后的字段定义。
    """
    return await service.update_field(db, project_code, field_code, request)
