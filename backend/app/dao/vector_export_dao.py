"""任务作用域矢量成果导出数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.plot import FarmlandPlot
from app.models.vector_export import VectorExportPackage
from app.models.workbench import TaskPlot


class VectorExportDAO:
    """封装导出范围查询、版本和报告状态。"""

    @staticmethod
    def _scope_statement(
        task_id: int,
        district_codes: list[str],
        land_classes: list[str],
    ) -> list[ColumnElement[bool]]:
        """构建任务作用域与可选业务筛选条件。

        Args:
            task_id: 作业任务主键。
            district_codes: 县区编码筛选。
            land_classes: 一级地类筛选。

        Returns:
            list[ColumnElement[bool]]: TaskPlot 连接后的 WHERE 条件。
        """
        conditions = [
            TaskPlot.task_id == task_id,
            FarmlandPlot.interpretation_status != "deleted",
        ]
        if district_codes:
            conditions.append(FarmlandPlot.district_code.in_(district_codes))
        if land_classes:
            conditions.append(FarmlandPlot.land_class.in_(land_classes))
        return conditions

    async def count_features(
        self,
        db: AsyncSession,
        task_id: int,
        district_codes: list[str] | None = None,
        land_classes: list[str] | None = None,
    ) -> int:
        """统计任务内满足筛选条件的有效图斑数。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            district_codes: 可选县区编码筛选。
            land_classes: 可选一级地类筛选。

        Returns:
            int: 精确图斑数量。
        """
        result = await db.execute(
            select(func.count(FarmlandPlot.id))
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .where(
                *self._scope_statement(
                    task_id,
                    district_codes or [],
                    land_classes or [],
                )
            )
        )
        return int(result.scalar_one())

    async def get_export_rows(
        self,
        db: AsyncSession,
        task_id: int,
        district_codes: list[str],
        land_classes: list[str],
    ) -> Sequence[object]:
        """查询任务内待导出的完整属性和 WGS84 Polygon。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            district_codes: 县区编码筛选。
            land_classes: 一级地类筛选。

        Returns:
            Sequence[object]: 按图斑编号排序的导出行。
        """
        result = await db.execute(
            select(
                FarmlandPlot.plot_code,
                FarmlandPlot.owner_village,
                FarmlandPlot.area_ha,
                FarmlandPlot.land_class,
                FarmlandPlot.crop_type,
                FarmlandPlot.planting_mode,
                FarmlandPlot.irrigation_condition,
                FarmlandPlot.custom_attributes,
                FarmlandPlot.interpretation_status,
                FarmlandPlot.version,
                FarmlandPlot.province_name,
                FarmlandPlot.city_name,
                FarmlandPlot.district_name,
                FarmlandPlot.district_code,
                FarmlandPlot.source_name,
                FarmlandPlot.source_feature_id,
                FarmlandPlot.source_uri,
                FarmlandPlot.source_version,
                FarmlandPlot.source_updated_at,
                func.ST_AsGeoJSON(FarmlandPlot.geom).label("geometry"),
            )
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .where(
                *self._scope_statement(
                    task_id,
                    district_codes,
                    land_classes,
                )
            )
            .order_by(FarmlandPlot.plot_code)
        )
        return result.all()

    async def get_district_options(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[object]:
        """查询任务内可导出的县区及精确图斑数量。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[object]: 县区编码、名称、地级区域和数量。
        """
        result = await db.execute(
            select(
                FarmlandPlot.district_code.label("code"),
                func.coalesce(
                    FarmlandPlot.district_name,
                    "县区未归属",
                ).label("label"),
                func.coalesce(
                    FarmlandPlot.city_name,
                    "地级区域未归属",
                ).label("parent_label"),
                func.count(FarmlandPlot.id).label("feature_count"),
            )
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .where(
                TaskPlot.task_id == task_id,
                FarmlandPlot.interpretation_status != "deleted",
            )
            .group_by(
                FarmlandPlot.district_code,
                FarmlandPlot.district_name,
                FarmlandPlot.city_name,
            )
            .order_by(FarmlandPlot.city_name, FarmlandPlot.district_name)
        )
        return result.all()

    async def get_land_class_options(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[object]:
        """查询任务内可导出的地类及精确图斑数量。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[object]: 地类名称和数量。
        """
        result = await db.execute(
            select(
                func.coalesce(
                    FarmlandPlot.land_class,
                    "未分类",
                ).label("label"),
                func.count(FarmlandPlot.id).label("feature_count"),
            )
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .where(
                TaskPlot.task_id == task_id,
                FarmlandPlot.interpretation_status != "deleted",
            )
            .group_by(FarmlandPlot.land_class)
            .order_by(func.count(FarmlandPlot.id).desc())
        )
        return result.all()

    async def list_packages(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[VectorExportPackage]:
        """查询任务全部导出版本。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[VectorExportPackage]: 按版本倒序排列的导出包。
        """
        result = await db.execute(
            select(VectorExportPackage)
            .where(VectorExportPackage.task_id == task_id)
            .order_by(VectorExportPackage.version.desc())
        )
        return result.scalars().all()

    async def get_package_by_code(
        self,
        db: AsyncSession,
        export_code: str,
    ) -> VectorExportPackage | None:
        """按业务编号查询导出包。

        Args:
            db: 异步数据库会话。
            export_code: 导出包业务编号。

        Returns:
            VectorExportPackage | None: 导出包，不存在时为空。
        """
        result = await db.execute(
            select(VectorExportPackage).where(
                VectorExportPackage.export_code == export_code
            )
        )
        return result.scalar_one_or_none()

    async def get_next_version(self, db: AsyncSession, task_id: int) -> int:
        """计算下一导出版本号。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            int: 从 1 开始递增的版本号。
        """
        result = await db.execute(
            select(func.coalesce(func.max(VectorExportPackage.version), 0)).where(
                VectorExportPackage.task_id == task_id
            )
        )
        return int(result.scalar_one()) + 1

    async def supersede_completed_packages(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> int:
        """将已有当前导出包转为历史版本。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            int: 被替代数量。
        """
        result = await db.execute(
            update(VectorExportPackage)
            .where(
                VectorExportPackage.task_id == task_id,
                VectorExportPackage.status == "completed",
            )
            .values(status="superseded")
        )
        return int(result.rowcount or 0)

    async def add_package(
        self,
        db: AsyncSession,
        package: VectorExportPackage,
    ) -> VectorExportPackage:
        """新增导出包实体。

        Args:
            db: 异步数据库会话。
            package: 待写入导出包。

        Returns:
            VectorExportPackage: 已刷新主键的实体。
        """
        db.add(package)
        await db.flush()
        await db.refresh(package)
        return package
