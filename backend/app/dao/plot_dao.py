"""永久基本农田图斑数据访问对象。"""

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plot import FarmlandPlot
from app.models.workbench import MonitoringTask, TaskPlot


class FarmlandPlotDAO:
    """封装图斑参数化空间查询，禁止拼接用户输入。"""

    async def task_exists(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> bool:
        """判断作业任务是否存在。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            bool: 任务存在时为 True。
        """
        result = await db.execute(
            select(MonitoringTask.id).where(
                MonitoringTask.task_code == task_code
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _base_query() -> Select[tuple[Any, ...]]:
        """构造包含 GeoJSON 几何的公共查询列。

        Returns:
            Select: SQLAlchemy 参数化查询对象。
        """
        return select(
            FarmlandPlot.id,
            FarmlandPlot.plot_code,
            FarmlandPlot.owner_village,
            FarmlandPlot.area_ha,
            FarmlandPlot.land_class,
            FarmlandPlot.source_name,
            FarmlandPlot.source_feature_id,
            FarmlandPlot.source_uri,
            FarmlandPlot.source_version,
            FarmlandPlot.source_updated_at,
            FarmlandPlot.province_name,
            FarmlandPlot.city_name,
            FarmlandPlot.district_name,
            FarmlandPlot.district_code,
            func.ST_AsGeoJSON(FarmlandPlot.geom).label("geometry"),
        )

    async def get_by_point(
        self,
        db: AsyncSession,
        lon: float,
        lat: float,
        task_code: str,
    ) -> RowMapping | None:
        """查询包含指定 WGS84 坐标点的图斑。

        Args:
            db: 异步数据库会话。
            lon: WGS84 经度。
            lat: WGS84 纬度。
            task_code: 作业任务编号。

        Returns:
            RowMapping | None: 图斑查询结果；未命中时返回 None。
        """
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
        statement = (
            self._base_query()
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .join(MonitoringTask, MonitoringTask.id == TaskPlot.task_id)
            .where(
                MonitoringTask.task_code == task_code,
                func.ST_Contains(FarmlandPlot.geom, point),
                FarmlandPlot.interpretation_status != "deleted",
            )
        )
        result = await db.execute(statement)
        return result.mappings().first()

    async def get_by_bbox(
        self,
        db: AsyncSession,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> list[RowMapping]:
        """查询与 WGS84 包围盒相交的图斑。

        Args:
            db: 异步数据库会话。
            min_lon: 最小经度。
            min_lat: 最小纬度。
            max_lon: 最大经度。
            max_lat: 最大纬度。

        Returns:
            list[RowMapping]: 相交图斑列表。
        """
        envelope = func.ST_MakeEnvelope(
            min_lon,
            min_lat,
            max_lon,
            max_lat,
            4326,
        )
        statement = self._base_query().where(
            func.ST_Intersects(FarmlandPlot.geom, envelope),
            FarmlandPlot.interpretation_status != "deleted",
        )
        result = await db.execute(statement)
        return list(result.mappings().all())

    async def get_task_catalog(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> list[RowMapping]:
        """查询任务内不携带完整几何的轻量地块目录。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            list[RowMapping]: 县区、地类、来源编号和地块包围盒。
        """
        statement = (
            select(
                FarmlandPlot.plot_code,
                FarmlandPlot.source_feature_id,
                FarmlandPlot.land_class,
                FarmlandPlot.district_code,
                func.ST_XMin(func.Box3D(FarmlandPlot.geom)).label("min_lon"),
                func.ST_YMin(func.Box3D(FarmlandPlot.geom)).label("min_lat"),
                func.ST_XMax(func.Box3D(FarmlandPlot.geom)).label("max_lon"),
                func.ST_YMax(func.Box3D(FarmlandPlot.geom)).label("max_lat"),
            )
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .join(MonitoringTask, MonitoringTask.id == TaskPlot.task_id)
            .where(
                MonitoringTask.task_code == task_code,
                FarmlandPlot.interpretation_status != "deleted",
                FarmlandPlot.district_code.is_not(None),
            )
            .order_by(FarmlandPlot.district_code, FarmlandPlot.plot_code)
        )
        result = await db.execute(statement)
        return list(result.mappings().all())

    async def count_task_by_bbox(
        self,
        db: AsyncSession,
        task_code: str,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> int:
        """统计任务内与当前 WGS84 视野相交的有效图斑。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            min_lon: 最小经度。
            min_lat: 最小纬度。
            max_lon: 最大经度。
            max_lat: 最大纬度。

        Returns:
            int: 当前视野匹配图斑数。
        """
        envelope = func.ST_MakeEnvelope(
            min_lon,
            min_lat,
            max_lon,
            max_lat,
            4326,
        )
        statement = (
            select(func.count(FarmlandPlot.id))
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .join(MonitoringTask, MonitoringTask.id == TaskPlot.task_id)
            .where(
                MonitoringTask.task_code == task_code,
                FarmlandPlot.interpretation_status != "deleted",
                func.ST_Intersects(FarmlandPlot.geom, envelope),
            )
        )
        return int((await db.execute(statement)).scalar_one())

    async def get_task_by_bbox(
        self,
        db: AsyncSession,
        task_code: str,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        max_features: int,
    ) -> list[RowMapping]:
        """查询任务当前视野内不超过上限的完整地块几何。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            min_lon: 最小经度。
            min_lat: 最小纬度。
            max_lon: 最大经度。
            max_lat: 最大纬度。
            max_features: 已校验的最大返回数量。

        Returns:
            list[RowMapping]: 当前视野完整 GeoJSON 查询行。
        """
        envelope = func.ST_MakeEnvelope(
            min_lon,
            min_lat,
            max_lon,
            max_lat,
            4326,
        )
        statement = (
            self._base_query()
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .join(MonitoringTask, MonitoringTask.id == TaskPlot.task_id)
            .where(
                MonitoringTask.task_code == task_code,
                FarmlandPlot.interpretation_status != "deleted",
                func.ST_Intersects(FarmlandPlot.geom, envelope),
            )
            .order_by(FarmlandPlot.id)
            .limit(max_features)
        )
        result = await db.execute(statement)
        return list(result.mappings().all())

    async def get_by_plot_code(
        self,
        db: AsyncSession,
        plot_code: str,
        task_code: str,
    ) -> RowMapping | None:
        """按唯一图斑编号查询图斑。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑唯一编号。
            task_code: 作业任务编号。

        Returns:
            RowMapping | None: 图斑查询结果；不存在时返回 None。
        """
        statement = (
            self._base_query()
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .join(MonitoringTask, MonitoringTask.id == TaskPlot.task_id)
            .where(
                MonitoringTask.task_code == task_code,
                FarmlandPlot.plot_code == plot_code,
                FarmlandPlot.interpretation_status != "deleted",
            )
        )
        result = await db.execute(statement)
        return result.mappings().first()
