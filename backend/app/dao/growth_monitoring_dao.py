"""多时相 NDVI 长势监测数据访问对象。"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.growth_monitoring import (
    GrowthMonitoringEvent,
    GrowthMonitoringRun,
    GrowthMonitoringZone,
)
from app.models.workbench import ImageryAsset, ImageryProcessingStep


@dataclass(frozen=True)
class GrowthSourceRow:
    """一个影像资产及其波段产品步骤。"""

    asset: ImageryAsset
    step: ImageryProcessingStep | None


@dataclass(frozen=True)
class GrowthTaskScope:
    """任务耕地图斑数量、更新时间和合并后的 WGS84 几何。"""

    plot_count: int
    task_updated_at: datetime
    farmland_area_ha: float
    geometry_json: str


@dataclass(frozen=True)
class GrowthCoverageScope:
    """两期影像共同足迹对完整任务耕地的空间覆盖量算。"""

    task_farmland_area_ha: float
    common_footprint_farmland_area_ha: float
    spatial_coverage_ratio: float
    geometry_json: str


class GrowthMonitoringDAO:
    """封装长势监测来源、任务范围、成果和审计操作。"""

    async def list_source_rows(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[GrowthSourceRow]:
        """查询项目影像资产及其波段产品步骤。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[GrowthSourceRow]: 按采集时间倒序的来源列表。
        """
        result = await db.execute(
            select(ImageryAsset, ImageryProcessingStep)
            .outerjoin(
                ImageryProcessingStep,
                (
                    (ImageryProcessingStep.asset_id == ImageryAsset.id)
                    & (ImageryProcessingStep.step_code == "band_products")
                ),
            )
            .where(ImageryAsset.project_id == project_id)
            .order_by(ImageryAsset.acquired_at.desc())
        )
        return [
            GrowthSourceRow(asset=row[0], step=row[1])
            for row in result.all()
        ]

    async def get_source_row(
        self,
        db: AsyncSession,
        project_id: int,
        asset_code: str,
    ) -> GrowthSourceRow | None:
        """按项目和资产编号查询长势监测来源。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            asset_code: 影像资产编号。

        Returns:
            GrowthSourceRow | None: 资产和波段产品步骤。
        """
        result = await db.execute(
            select(ImageryAsset, ImageryProcessingStep)
            .outerjoin(
                ImageryProcessingStep,
                (
                    (ImageryProcessingStep.asset_id == ImageryAsset.id)
                    & (ImageryProcessingStep.step_code == "band_products")
                ),
            )
            .where(
                ImageryAsset.project_id == project_id,
                ImageryAsset.asset_code == asset_code,
            )
        )
        row = result.one_or_none()
        return GrowthSourceRow(asset=row[0], step=row[1]) if row else None

    async def get_task_scope(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> GrowthTaskScope | None:
        """合并当前任务全部有效耕地图斑作为长势计算范围。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            GrowthTaskScope | None: 图斑数量、任务时间和范围几何。
        """
        statement = text(
            """
            SELECT
                COUNT(*)::integer AS plot_count,
                task.updated_at AS task_updated_at,
                ST_Area(
                    ST_UnaryUnion(ST_Collect(plot.geom))::geography
                ) / 10000.0 AS farmland_area_ha,
                ST_AsGeoJSON(
                    ST_Multi(ST_UnaryUnion(ST_Collect(plot.geom)))
                ) AS geometry_json
            FROM monitoring_tasks AS task
            JOIN task_plots AS assignment ON assignment.task_id = task.id
            JOIN farmland_plots AS plot ON plot.plot_code = assignment.plot_code
            WHERE task.id = :task_id
              AND plot.interpretation_status <> 'deleted'
              AND plot.land_class = '耕地'
            GROUP BY task.updated_at
            """
        )
        row = (
            (await db.execute(statement, {"task_id": task_id}))
            .mappings()
            .one_or_none()
        )
        if row is None or not row["geometry_json"]:
            return None
        return GrowthTaskScope(
            plot_count=int(row["plot_count"]),
            task_updated_at=row["task_updated_at"],
            farmland_area_ha=float(row["farmland_area_ha"]),
            geometry_json=str(row["geometry_json"]),
        )

    async def get_coverage_scope(
        self,
        db: AsyncSession,
        task_id: int,
        baseline_asset_id: int,
        current_asset_id: int,
    ) -> GrowthCoverageScope | None:
        """量算两期真实影像足迹共同覆盖的任务耕地范围。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            baseline_asset_id: 基准期影像主键。
            current_asset_id: 监测期影像主键。

        Returns:
            GrowthCoverageScope | None: 完整任务面积、共同覆盖面积和几何。
        """
        statement = text(
            """
            WITH task_scope AS (
                SELECT ST_UnaryUnion(ST_Collect(plot.geom)) AS geom
                FROM task_plots AS assignment
                JOIN farmland_plots AS plot
                  ON plot.plot_code = assignment.plot_code
                WHERE assignment.task_id = :task_id
                  AND plot.interpretation_status <> 'deleted'
                  AND plot.land_class = '耕地'
            ), source_scope AS (
                SELECT ST_CollectionExtract(
                    ST_MakeValid(
                        ST_Intersection(
                            baseline.spatial_extent,
                            current.spatial_extent
                        )
                    ),
                    3
                ) AS geom
                FROM imagery_assets AS baseline
                JOIN imagery_assets AS current
                  ON current.id = :current_asset_id
                WHERE baseline.id = :baseline_asset_id
                  AND baseline.spatial_extent IS NOT NULL
                  AND current.spatial_extent IS NOT NULL
            ), covered AS (
                SELECT
                    task_scope.geom AS task_geom,
                    ST_Multi(
                        ST_CollectionExtract(
                            ST_MakeValid(
                                ST_Intersection(task_scope.geom, source_scope.geom)
                            ),
                            3
                        )
                    ) AS covered_geom
                FROM task_scope
                JOIN source_scope ON TRUE
                WHERE task_scope.geom IS NOT NULL
                  AND source_scope.geom IS NOT NULL
                  AND NOT ST_IsEmpty(source_scope.geom)
            ), measured AS (
                SELECT
                    ST_Area(task_geom::geography) / 10000.0 AS task_area_ha,
                    ST_Area(covered_geom::geography) / 10000.0 AS covered_area_ha,
                    covered_geom
                FROM covered
                WHERE NOT ST_IsEmpty(covered_geom)
            )
            SELECT
                task_area_ha,
                covered_area_ha,
                covered_area_ha / NULLIF(task_area_ha, 0) AS coverage_ratio,
                ST_AsGeoJSON(covered_geom) AS geometry_json
            FROM measured
            WHERE task_area_ha > 0
              AND covered_area_ha > 0
            """
        )
        row = (
            await db.execute(
                statement,
                {
                    "task_id": task_id,
                    "baseline_asset_id": baseline_asset_id,
                    "current_asset_id": current_asset_id,
                },
            )
        ).mappings().one_or_none()
        if row is None or not row["geometry_json"]:
            return None
        return GrowthCoverageScope(
            task_farmland_area_ha=float(row["task_area_ha"]),
            common_footprint_farmland_area_ha=float(row["covered_area_ha"]),
            spatial_coverage_ratio=float(row["coverage_ratio"]),
            geometry_json=str(row["geometry_json"]),
        )

    async def get_source_steps(
        self,
        db: AsyncSession,
        step_ids: Sequence[int],
    ) -> Sequence[ImageryProcessingStep]:
        """查询交付重校验所需的影像处理步骤。

        Args:
            db: 异步数据库会话。
            step_ids: 长势任务快照引用的步骤主键。

        Returns:
            Sequence[ImageryProcessingStep]: 匹配的处理步骤。
        """
        result = await db.execute(
            select(ImageryProcessingStep).where(
                ImageryProcessingStep.id.in_(list(step_ids))
            )
        )
        return result.scalars().all()

    async def get_run(
        self,
        db: AsyncSession,
        project_id: int,
        run_code: str,
    ) -> GrowthMonitoringRun | None:
        """查询项目长势监测任务。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            run_code: 长势监测任务编号。

        Returns:
            GrowthMonitoringRun | None: 长势监测任务。
        """
        result = await db.execute(
            select(GrowthMonitoringRun).where(
                GrowthMonitoringRun.project_id == project_id,
                GrowthMonitoringRun.run_code == run_code,
            )
        )
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[GrowthMonitoringRun]:
        """查询任务长势监测历史。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[GrowthMonitoringRun]: 按生成时间倒序的任务。
        """
        result = await db.execute(
            select(GrowthMonitoringRun)
            .where(GrowthMonitoringRun.task_id == task_id)
            .order_by(GrowthMonitoringRun.created_at.desc())
        )
        return result.scalars().all()

    async def add_run(
        self,
        db: AsyncSession,
        run: GrowthMonitoringRun,
    ) -> GrowthMonitoringRun:
        """写入长势监测任务。

        Args:
            db: 异步数据库会话。
            run: 待保存任务。

        Returns:
            GrowthMonitoringRun: 已刷新任务。
        """
        db.add(run)
        await db.flush()
        await db.refresh(run)
        return run

    async def analyze_clipped_zone(
        self,
        db: AsyncSession,
        task_id: int,
        geometry_json: str,
        minimum_area_ha: float,
    ) -> RowMapping | None:
        """将栅格异常区裁切到任务耕地范围并重算面积。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            geometry_json: 栅格矢量化得到的 WGS84 Polygon。
            minimum_area_ha: 最小异常区面积门槛。

        Returns:
            RowMapping | None: 达到门槛的裁切几何和 PostGIS 面积。
        """
        statement = text(
            """
            WITH candidate AS (
                SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326) AS geom
            ), task_scope AS (
                SELECT ST_UnaryUnion(ST_Collect(plot.geom)) AS geom
                FROM task_plots AS assignment
                JOIN farmland_plots AS plot
                  ON plot.plot_code = assignment.plot_code
                WHERE assignment.task_id = :task_id
                  AND plot.interpretation_status <> 'deleted'
                  AND plot.land_class = '耕地'
            ), clipped AS (
                SELECT ST_Multi(
                    ST_CollectionExtract(
                        ST_MakeValid(ST_Intersection(candidate.geom, task_scope.geom)),
                        3
                    )
                ) AS geom
                FROM candidate
                JOIN task_scope ON TRUE
            ), measured AS (
                SELECT geom, ST_Area(geom::geography) / 10000.0 AS area_ha
                FROM clipped
                WHERE NOT ST_IsEmpty(geom)
                  AND ST_IsValid(geom)
            )
            SELECT
                ST_AsGeoJSON(geom) AS geometry_json,
                area_ha
            FROM measured
            WHERE area_ha >= :minimum_area_ha
            """
        )
        return (
            await db.execute(
                statement,
                {
                    "task_id": task_id,
                    "geometry": geometry_json,
                    "minimum_area_ha": minimum_area_ha,
                },
            )
        ).mappings().one_or_none()

    async def insert_zone(
        self,
        db: AsyncSession,
        run_id: int,
        zone_code: str,
        geometry_json: str,
        area_ha: float,
        baseline_mean: float,
        current_mean: float,
        delta_mean: float,
    ) -> GrowthMonitoringZone:
        """写入已由 PostGIS 裁切和量算的长势异常区。

        Args:
            db: 异步数据库会话。
            run_id: 长势监测任务主键。
            zone_code: 异常区编号。
            geometry_json: 已裁切 WGS84 MultiPolygon。
            area_ha: PostGIS geography 面积。
            baseline_mean: 基准期 NDVI 均值。
            current_mean: 监测期 NDVI 均值。
            delta_mean: NDVI 差值均值。

        Returns:
            GrowthMonitoringZone: 已写入异常区。
        """
        statement = text(
            """
            INSERT INTO growth_monitoring_zones (
                run_id, zone_code, area_ha,
                baseline_ndvi_mean, current_ndvi_mean, ndvi_delta_mean, geom
            ) VALUES (
                :run_id, :zone_code, :area_ha,
                :baseline_mean, :current_mean, :delta_mean,
                ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326))
            )
            RETURNING id
            """
        )
        zone_id = int(
            (
                await db.execute(
                    statement,
                    {
                        "run_id": run_id,
                        "zone_code": zone_code,
                        "area_ha": area_ha,
                        "baseline_mean": baseline_mean,
                        "current_mean": current_mean,
                        "delta_mean": delta_mean,
                        "geometry": geometry_json,
                    },
                )
            ).scalar_one()
        )
        zone = await db.get(GrowthMonitoringZone, zone_id)
        if zone is None:
            raise RuntimeError("长势异常区新增后无法读取")
        return zone

    async def list_zone_rows(
        self,
        db: AsyncSession,
        run_id: int,
    ) -> Sequence[RowMapping]:
        """查询异常区及 GeoJSON 几何。

        Args:
            db: 异步数据库会话。
            run_id: 长势监测任务主键。

        Returns:
            Sequence[RowMapping]: 异常区模型和几何文本。
        """
        result = await db.execute(
            select(
                GrowthMonitoringZone,
                func.ST_AsGeoJSON(GrowthMonitoringZone.geom).label("geometry"),
            )
            .where(GrowthMonitoringZone.run_id == run_id)
            .order_by(GrowthMonitoringZone.area_ha.desc())
        )
        return result.mappings().all()

    async def add_event(
        self,
        db: AsyncSession,
        event: GrowthMonitoringEvent,
    ) -> None:
        """写入长势监测不可变事件。

        Args:
            db: 异步数据库会话。
            event: 审计事件。

        Returns:
            None: 无返回值。
        """
        db.add(event)
        await db.flush()

    async def get_current_state(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> tuple[int, datetime | None]:
        """查询成果包失效判断使用的长势成果数量和最近时间。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            tuple[int, datetime | None]: 任务数量和最近生成时间。
        """
        row = (
            await db.execute(
                select(
                    func.count(GrowthMonitoringRun.id),
                    func.max(GrowthMonitoringRun.created_at),
                ).where(GrowthMonitoringRun.task_id == task_id)
            )
        ).one()
        return int(row[0] or 0), row[1]

    @staticmethod
    def decimal(value: float) -> Decimal:
        """将浮点数转换为无二进制尾差的 Decimal。

        Args:
            value: 浮点值。

        Returns:
            Decimal: 十进制定点值。
        """
        return Decimal(str(value))
