"""永久基本农田图斑查询端点。"""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import DatabaseSession
from app.schemas.request import BBoxRequest, PlotViewportRequest, PointQueryRequest
from app.schemas.response import (
    PlotCatalogResponse,
    PlotInfoResponse,
    PlotViewportResponse,
)
from app.services.plot_service import PlotService

router = APIRouter(prefix="/api/v1/plot", tags=["基本农田图斑"])
plot_service = PlotService()


@router.post("/query-point", response_model=PlotInfoResponse, summary="点查所属图斑")
async def query_point(
    request: PointQueryRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> PlotInfoResponse:
    """按 WGS84 坐标查询所属图斑属性。

    Args:
        request: 点查询请求，经纬度坐标系为 EPSG:4326。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        PlotInfoResponse: 命中图斑的编号、面积和权属村。
    """
    return await plot_service.query_by_point(db, request, task_code)


@router.get("/boundary", summary="获取图斑完整边界")
async def get_boundary(
    db: DatabaseSession,
    plot_code: Annotated[
        str,
        Query(min_length=1, max_length=50, pattern=r"^[\w-]+$"),
    ],
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> dict[str, Any]:
    """按图斑编号获取 GeoJSON Feature。

    Args:
        db: FastAPI 注入的异步数据库会话。
        plot_code: 图斑唯一编号。
        task_code: 作业任务编号。

    Returns:
        dict[str, Any]: 图斑 GeoJSON Feature。
    """
    return await plot_service.get_boundary(db, plot_code, task_code)


@router.post("/bbox", summary="查询视野内图斑")
async def query_bbox(
    request: BBoxRequest,
    db: DatabaseSession,
) -> dict[str, Any]:
    """查询与 WGS84 包围盒相交的图斑。

    Args:
        request: 包围盒请求，经纬度坐标系为 EPSG:4326。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        dict[str, Any]: 图斑 GeoJSON FeatureCollection。
    """
    return await plot_service.query_by_bbox(db, request)


@router.get(
    "/catalog",
    response_model=PlotCatalogResponse,
    summary="查询任务轻量地块目录",
)
async def get_plot_catalog(
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> PlotCatalogResponse:
    """查询不携带完整几何的任务地块目录。

    Args:
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        PlotCatalogResponse: 按县区组织的真实地块目录。
    """
    return await plot_service.get_catalog(db, task_code)


@router.post(
    "/viewport",
    response_model=PlotViewportResponse,
    summary="按任务和当前视野加载图斑",
)
async def query_plot_viewport(
    request: PlotViewportRequest,
    db: DatabaseSession,
) -> PlotViewportResponse:
    """按当前地图视野加载完整图斑，范围过大时要求继续放大。

    Args:
        request: 任务、WGS84 包围盒和最大返回数量。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        PlotViewportResponse: 完整视野 GeoJSON 或放大提示。
    """
    return await plot_service.query_viewport(db, request)


@router.get("/click", response_model=PlotInfoResponse, summary="地图点击查询")
async def click_query(
    db: DatabaseSession,
    lon: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> PlotInfoResponse:
    """处理二维或三维地图点击拾取查询。

    Args:
        db: FastAPI 注入的异步数据库会话。
        lon: WGS84 经度。
        lat: WGS84 纬度。
        task_code: 作业任务编号。

    Returns:
        PlotInfoResponse: 命中图斑属性。
    """
    request = PointQueryRequest(lon=lon, lat=lat)
    return await plot_service.query_by_point(db, request, task_code)
