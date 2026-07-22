"""永久基本农田图斑业务服务。"""

import json
import logging
from typing import Any

from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.dao.plot_dao import FarmlandPlotDAO
from app.schemas.request import BBoxRequest, PlotViewportRequest, PointQueryRequest
from app.schemas.response import (
    PlotCatalogDistrict,
    PlotCatalogItem,
    PlotCatalogResponse,
    PlotInfoResponse,
    PlotViewportResponse,
)

logger = logging.getLogger(__name__)


class PlotService:
    """协调图斑查询、异常转换及 GeoJSON 响应组装。"""

    def __init__(self, dao: FarmlandPlotDAO | None = None) -> None:
        """初始化图斑业务服务。

        Args:
            dao: 可选的数据访问对象，便于测试替换。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or FarmlandPlotDAO()

    @staticmethod
    def _to_plot_info(row: RowMapping) -> PlotInfoResponse:
        """将数据库行转换为稳定的图斑属性响应。

        Args:
            row: DAO 返回的数据库映射行。

        Returns:
            PlotInfoResponse: 图斑属性响应。
        """
        return PlotInfoResponse(
            plot_code=row["plot_code"],
            owner_village=row["owner_village"],
            area_ha=float(row["area_ha"]) if row["area_ha"] is not None else None,
            land_class=row.get("land_class"),
            source_name=row.get("source_name"),
            source_feature_id=row.get("source_feature_id"),
            source_uri=row.get("source_uri"),
            source_version=row.get("source_version"),
            source_updated_at=row.get("source_updated_at"),
            province_name=row.get("province_name"),
            city_name=row.get("city_name"),
            district_name=row.get("district_name"),
            district_code=row.get("district_code"),
        )

    @staticmethod
    def _to_feature(row: RowMapping) -> dict[str, Any]:
        """将数据库行组装为 GeoJSON Feature。

        Args:
            row: 包含 GeoJSON 字符串的数据库映射行。

        Returns:
            dict[str, Any]: 标准 GeoJSON Feature。
        """
        return {
            "type": "Feature",
            "id": row["id"],
            "geometry": json.loads(row["geometry"]),
            "properties": {
                "plot_code": row["plot_code"],
                "owner_village": row["owner_village"],
                "area_ha": (
                    float(row["area_ha"]) if row["area_ha"] is not None else None
                ),
                "land_class": row.get("land_class"),
                "source_name": row.get("source_name"),
                "source_feature_id": row.get("source_feature_id"),
                "source_uri": row.get("source_uri"),
                "source_version": row.get("source_version"),
                "province_name": row.get("province_name"),
                "city_name": row.get("city_name"),
                "district_name": row.get("district_name"),
                "district_code": row.get("district_code"),
                "source_updated_at": (
                    row.get("source_updated_at").isoformat()
                    if row.get("source_updated_at") is not None
                    else None
                ),
            },
        }

    async def query_by_point(
        self,
        db: AsyncSession,
        request: PointQueryRequest,
        task_code: str,
    ) -> PlotInfoResponse:
        """按 WGS84 坐标点查询所属图斑。

        Args:
            db: 异步数据库会话。
            request: 已校验的点查询请求。
            task_code: 作业任务编号。

        Returns:
            PlotInfoResponse: 命中图斑属性。
        """
        logger.info("执行点查图斑: lon=%s, lat=%s", request.lon, request.lat)
        try:
            if not await self.dao.task_exists(db, task_code):
                raise NotFoundException(f"未找到任务 {task_code}")
            row = await self.dao.get_by_point(
                db,
                request.lon,
                request.lat,
                task_code,
            )
            if row is None:
                raise NotFoundException("该坐标不在当前任务图斑范围内")
            return self._to_plot_info(row)
        except NotFoundException:
            raise
        except Exception:
            logger.exception("点查图斑失败")
            raise

    async def get_boundary(
        self,
        db: AsyncSession,
        plot_code: str,
        task_code: str,
    ) -> dict[str, Any]:
        """获取指定编号图斑的完整 GeoJSON 边界。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑唯一编号。
            task_code: 作业任务编号。

        Returns:
            dict[str, Any]: 标准 GeoJSON Feature。
        """
        logger.info("查询图斑边界: plot_code=%s", plot_code)
        try:
            if not await self.dao.task_exists(db, task_code):
                raise NotFoundException(f"未找到任务 {task_code}")
            row = await self.dao.get_by_plot_code(db, plot_code, task_code)
            if row is None:
                raise NotFoundException(f"当前任务未找到图斑 {plot_code}")
            return self._to_feature(row)
        except NotFoundException:
            raise
        except Exception:
            logger.exception("查询图斑边界失败")
            raise

    async def query_by_bbox(
        self,
        db: AsyncSession,
        request: BBoxRequest,
    ) -> dict[str, Any]:
        """查询与 WGS84 视野包围盒相交的图斑。

        Args:
            db: 异步数据库会话。
            request: 已校验的包围盒请求。

        Returns:
            dict[str, Any]: 标准 GeoJSON FeatureCollection。
        """
        logger.info("执行视野查询: bbox=%s", request.model_dump())
        try:
            rows = await self.dao.get_by_bbox(db, **request.model_dump())
            return {
                "type": "FeatureCollection",
                "features": [self._to_feature(row) for row in rows],
            }
        except Exception:
            logger.exception("视野查询失败")
            raise

    async def get_catalog(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> PlotCatalogResponse:
        """查询任务作用域内不携带完整几何的分级地块目录。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            PlotCatalogResponse: 按县区组织的轻量地块目录。
        """
        if not await self.dao.task_exists(db, task_code):
            raise NotFoundException(f"未找到任务 {task_code}")
        rows = await self.dao.get_task_catalog(db, task_code)
        district_plots: dict[str, list[PlotCatalogItem]] = {}
        land_class_counts: dict[str, int] = {}
        for row in rows:
            district_code = str(row["district_code"])
            land_class = row["land_class"]
            district_plots.setdefault(district_code, []).append(
                PlotCatalogItem(
                    plot_code=row["plot_code"],
                    source_feature_id=row["source_feature_id"],
                    land_class=land_class,
                    extent=(
                        float(row["min_lon"]),
                        float(row["min_lat"]),
                        float(row["max_lon"]),
                        float(row["max_lat"]),
                    ),
                )
            )
            label = land_class or "待分类"
            land_class_counts[label] = land_class_counts.get(label, 0) + 1
        return PlotCatalogResponse(
            task_code=task_code,
            total_count=len(rows),
            land_class_counts=land_class_counts,
            districts=[
                PlotCatalogDistrict(
                    district_code=district_code,
                    plot_count=len(plots),
                    plots=plots,
                )
                for district_code, plots in district_plots.items()
            ],
        )

    async def query_viewport(
        self,
        db: AsyncSession,
        request: PlotViewportRequest,
    ) -> PlotViewportResponse:
        """按任务和当前视野受控加载完整地块几何。

        当前范围超过上限时不返回任意子集，避免局部数据被误认为全量。

        Args:
            db: 异步数据库会话。
            request: 任务、WGS84 包围盒和最大图斑数量。

        Returns:
            PlotViewportResponse: 完整视野要素或继续放大提示。
        """
        if not await self.dao.task_exists(db, request.task_code):
            raise NotFoundException(f"未找到任务 {request.task_code}")
        bounds = request.model_dump(
            exclude={"task_code", "max_features"},
        )
        matched_count = await self.dao.count_task_by_bbox(
            db,
            request.task_code,
            **bounds,
        )
        if matched_count > request.max_features:
            return PlotViewportResponse(
                features=[],
                matched_count=matched_count,
                max_features=request.max_features,
                requires_zoom=True,
            )
        rows = await self.dao.get_task_by_bbox(
            db,
            request.task_code,
            max_features=request.max_features,
            **bounds,
        )
        return PlotViewportResponse(
            features=[self._to_feature(row) for row in rows],
            matched_count=matched_count,
            max_features=request.max_features,
            requires_zoom=False,
        )
