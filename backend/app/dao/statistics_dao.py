"""种植面积统计分析数据访问对象。"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plot import FarmlandPlot
from app.models.workbench import (
    AreaStatisticsImportBatch,
    AreaStatisticsSnapshot,
    MonitoringProject,
    TaskPlot,
)


class StatisticsDAO:
    """封装任务图斑面积聚合和年度快照查询。"""

    @staticmethod
    def _scope_statement(
        statement: Select[tuple[Any, ...]],
        task_id: int,
    ) -> Select[tuple[Any, ...]]:
        """为聚合查询附加任务图斑作用域和有效状态条件。

        Args:
            statement: 以 FarmlandPlot 为主表的 SQLAlchemy 查询。
            task_id: 作业任务主键。

        Returns:
            Select: 已限定 `task_plots` 的查询。
        """
        return (
            statement.join(
                TaskPlot,
                TaskPlot.plot_code == FarmlandPlot.plot_code,
            )
            .where(
                TaskPlot.task_id == task_id,
                FarmlandPlot.interpretation_status != "deleted",
            )
        )

    async def get_totals(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> tuple[int, object]:
        """统计任务图斑总数和总面积。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            tuple[int, object]: 图斑数量和公顷面积。
        """
        statement = self._scope_statement(
            select(
                func.count(FarmlandPlot.id),
                func.coalesce(func.sum(FarmlandPlot.area_ha), 0),
            ),
            task_id,
        )
        result = await db.execute(statement)
        return result.one()

    async def get_land_class_groups(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[object]:
        """按一级地类汇总任务图斑数量和面积。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[object]: 地类聚合行。
        """
        statement = self._scope_statement(
            select(
                func.coalesce(FarmlandPlot.land_class, "未分类").label("label"),
                func.count(FarmlandPlot.id).label("plot_count"),
                func.coalesce(func.sum(FarmlandPlot.area_ha), 0).label("area_ha"),
            ),
            task_id,
        )
        result = await db.execute(
            statement
            .group_by(FarmlandPlot.land_class)
            .order_by(func.sum(FarmlandPlot.area_ha).desc())
        )
        return result.all()

    async def get_crop_type_groups(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[object]:
        """按作物类型汇总任务图斑数量和面积。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[object]: 作物聚合行。
        """
        statement = self._scope_statement(
            select(
                func.coalesce(FarmlandPlot.crop_type, "作物未录入").label("label"),
                func.count(FarmlandPlot.id).label("plot_count"),
                func.coalesce(func.sum(FarmlandPlot.area_ha), 0).label("area_ha"),
            ),
            task_id,
        )
        result = await db.execute(
            statement
            .group_by(FarmlandPlot.crop_type)
            .order_by(func.sum(FarmlandPlot.area_ha).desc())
        )
        return result.all()

    async def get_crop_assignment_counts(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> tuple[int, int]:
        """统计任务耕地图斑数和已录入作物的耕地图斑数。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            tuple[int, int]: 耕地图斑数、已录入作物图斑数。
        """
        statement = self._scope_statement(
            select(
                func.count(FarmlandPlot.id).filter(
                    FarmlandPlot.land_class == "耕地"
                ),
                func.count(FarmlandPlot.id).filter(
                    FarmlandPlot.land_class == "耕地",
                    FarmlandPlot.crop_type.is_not(None),
                ),
            ),
            task_id,
        )
        result = await db.execute(statement)
        farmland_count, assigned_count = result.one()
        return int(farmland_count), int(assigned_count)

    async def get_planting_mode_groups(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[object]:
        """按种植模式汇总任务图斑数量和面积。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[object]: 种植模式聚合行。
        """
        statement = self._scope_statement(
            select(
                func.coalesce(
                    FarmlandPlot.planting_mode,
                    "种植模式未录入",
                ).label("label"),
                func.count(FarmlandPlot.id).label("plot_count"),
                func.coalesce(func.sum(FarmlandPlot.area_ha), 0).label("area_ha"),
            ),
            task_id,
        )
        result = await db.execute(
            statement
            .group_by(FarmlandPlot.planting_mode)
            .order_by(func.sum(FarmlandPlot.area_ha).desc())
        )
        return result.all()

    async def get_city_groups(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[object]:
        """按地级区域汇总任务图斑数量和面积。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[object]: 地级区域聚合行。
        """
        statement = self._scope_statement(
            select(
                func.coalesce(FarmlandPlot.city_name, "地级区域未归属").label(
                    "label"
                ),
                func.count(FarmlandPlot.id).label("plot_count"),
                func.coalesce(func.sum(FarmlandPlot.area_ha), 0).label("area_ha"),
            ),
            task_id,
        )
        result = await db.execute(
            statement
            .group_by(FarmlandPlot.city_name)
            .order_by(func.sum(FarmlandPlot.area_ha).desc())
        )
        return result.all()

    async def get_district_groups(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[object]:
        """按县区汇总任务图斑数量和面积并保留地级父级。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[object]: 县区聚合行。
        """
        statement = self._scope_statement(
            select(
                FarmlandPlot.district_code.label("code"),
                func.coalesce(FarmlandPlot.district_name, "县区未归属").label(
                    "label"
                ),
                func.coalesce(FarmlandPlot.city_name, "地级区域未归属").label(
                    "parent_label"
                ),
                func.count(FarmlandPlot.id).label("plot_count"),
                func.coalesce(func.sum(FarmlandPlot.area_ha), 0).label("area_ha"),
            ),
            task_id,
        )
        result = await db.execute(
            statement
            .group_by(
                FarmlandPlot.district_code,
                FarmlandPlot.district_name,
                FarmlandPlot.city_name,
            )
            .order_by(func.sum(FarmlandPlot.area_ha).desc())
        )
        return result.all()

    async def get_village_groups(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[object]:
        """按权属村汇总任务图斑数量和面积。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[object]: 村级聚合行。
        """
        statement = self._scope_statement(
            select(
                func.coalesce(FarmlandPlot.owner_village, "权属未录入").label("label"),
                func.count(FarmlandPlot.id).label("plot_count"),
                func.coalesce(func.sum(FarmlandPlot.area_ha), 0).label("area_ha"),
            ),
            task_id,
        )
        result = await db.execute(
            statement
            .group_by(FarmlandPlot.owner_village)
            .order_by(func.sum(FarmlandPlot.area_ha).desc())
        )
        return result.all()

    async def get_project_monitor_year(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> int:
        """查询项目监测年度。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            int: 项目监测年度。
        """
        result = await db.execute(
            select(MonitoringProject.monitor_year).where(
                MonitoringProject.id == project_id
            )
        )
        return int(result.scalar_one())

    async def get_annual_trend(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[object]:
        """查询项目已持久化的历史面积统计快照。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[object]: 按年份升序排列并包含来源审计的快照。
        """
        result = await db.execute(
            select(
                AreaStatisticsSnapshot.monitor_year,
                AreaStatisticsSnapshot.total_area_ha,
                AreaStatisticsSnapshot.generated_at,
                AreaStatisticsImportBatch.source_name,
                AreaStatisticsImportBatch.source_version,
            )
            .outerjoin(
                AreaStatisticsImportBatch,
                AreaStatisticsImportBatch.id
                == AreaStatisticsSnapshot.import_batch_id,
            )
            .where(AreaStatisticsSnapshot.project_id == project_id)
            .order_by(AreaStatisticsSnapshot.monitor_year)
        )
        return result.all()

    async def get_snapshots_for_update(
        self,
        db: AsyncSession,
        project_id: int,
        years: list[int],
    ) -> dict[int, AreaStatisticsSnapshot]:
        """锁定项目指定年度的现有统计快照。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            years: 待导入监测年度。

        Returns:
            dict[int, AreaStatisticsSnapshot]: 按年度索引的现有快照。
        """
        result = await db.execute(
            select(AreaStatisticsSnapshot)
            .where(
                AreaStatisticsSnapshot.project_id == project_id,
                AreaStatisticsSnapshot.monitor_year.in_(years),
            )
            .with_for_update()
        )
        return {
            snapshot.monitor_year: snapshot
            for snapshot in result.scalars().all()
        }

    async def create_import_batch(
        self,
        db: AsyncSession,
        batch: AreaStatisticsImportBatch,
    ) -> AreaStatisticsImportBatch:
        """创建不可变历史统计导入批次。

        Args:
            db: 异步数据库会话。
            batch: 来源、文件校验和操作人审计。

        Returns:
            AreaStatisticsImportBatch: 已写入批次。
        """
        db.add(batch)
        await db.flush()
        await db.refresh(batch)
        return batch

    async def save_snapshot(
        self,
        db: AsyncSession,
        snapshot: AreaStatisticsSnapshot | None,
        *,
        project_id: int,
        monitor_year: int,
        total_area_ha: object,
        farmland_area_ha: object,
        crop_area_ha: object,
        import_batch_id: int,
    ) -> AreaStatisticsSnapshot:
        """新增或替换一个项目历史年度快照。

        Args:
            db: 异步数据库会话。
            snapshot: 已锁定的现有快照；新增时为空。
            project_id: 项目主键。
            monitor_year: 历史监测年度。
            total_area_ha: 总面积公顷数。
            farmland_area_ha: 耕地面积公顷数。
            crop_area_ha: 作物面积公顷数。
            import_batch_id: 当前导入批次主键。

        Returns:
            AreaStatisticsSnapshot: 当前有效快照。
        """
        target = snapshot or AreaStatisticsSnapshot(
            project_id=project_id,
            monitor_year=monitor_year,
            total_area_ha=total_area_ha,
            farmland_area_ha=farmland_area_ha,
            crop_area_ha=crop_area_ha,
            import_batch_id=import_batch_id,
        )
        target.total_area_ha = total_area_ha
        target.farmland_area_ha = farmland_area_ha
        target.crop_area_ha = crop_area_ha
        target.import_batch_id = import_batch_id
        target.generated_at = datetime.now(UTC)
        target.updated_at = target.generated_at
        if snapshot is None:
            db.add(target)
        await db.flush()
        return target
