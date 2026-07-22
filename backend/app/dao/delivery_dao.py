"""成果交付包和交付数据集访问对象。"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plot import FarmlandPlot
from app.models.workbench import (
    DeliveryPackage,
    FieldVerification,
    QualityIssue,
    TaskPlot,
)


class DeliveryDAO:
    """封装交付包版本和交付源数据查询。"""

    async def get_packages(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[DeliveryPackage]:
        """查询任务全部成果交付包。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[DeliveryPackage]: 按版本倒序排列的交付包。
        """
        result = await db.execute(
            select(DeliveryPackage)
            .where(DeliveryPackage.task_id == task_id)
            .order_by(DeliveryPackage.version.desc())
        )
        return result.scalars().all()

    async def get_package_by_code(
        self,
        db: AsyncSession,
        package_code: str,
    ) -> DeliveryPackage | None:
        """按编号查询成果交付包。

        Args:
            db: 异步数据库会话。
            package_code: 成果包编号。

        Returns:
            DeliveryPackage | None: 成果交付包，不存在时返回 None。
        """
        result = await db.execute(
            select(DeliveryPackage).where(
                DeliveryPackage.package_code == package_code
            )
        )
        return result.scalar_one_or_none()

    async def get_next_version(self, db: AsyncSession, task_id: int) -> int:
        """计算任务下一交付版本号。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            int: 下一版本号。
        """
        result = await db.execute(
            select(func.coalesce(func.max(DeliveryPackage.version), 0)).where(
                DeliveryPackage.task_id == task_id
            )
        )
        return int(result.scalar_one()) + 1

    async def add_package(
        self,
        db: AsyncSession,
        package: DeliveryPackage,
    ) -> DeliveryPackage:
        """新增成果交付包记录。

        Args:
            db: 异步数据库会话。
            package: 待写入成果交付包。

        Returns:
            DeliveryPackage: 已写入成果交付包。
        """
        db.add(package)
        await db.flush()
        return package

    async def get_plot_rows(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[object]:
        """查询任务作用域内的交付图斑和 GeoJSON 几何。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            Sequence[object]: 图斑交付数据行。
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
                FarmlandPlot.interpretation_status,
                FarmlandPlot.version,
                func.ST_AsGeoJSON(FarmlandPlot.geom).label("geometry"),
            )
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .where(
                TaskPlot.task_id == task_id,
                FarmlandPlot.interpretation_status != "deleted",
            )
            .order_by(FarmlandPlot.plot_code)
        )
        return result.all()

    async def get_quality_issues(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[QualityIssue]:
        """查询任务质量问题清单。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[QualityIssue]: 质量问题列表。
        """
        result = await db.execute(
            select(QualityIssue)
            .where(QualityIssue.task_id == task_id)
            .order_by(QualityIssue.created_at)
        )
        return result.scalars().all()

    async def get_field_rows(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[tuple[FieldVerification, str]]:
        """查询外业核查记录及点位 GeoJSON。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[tuple[FieldVerification, str]]: 外业记录和点位几何。
        """
        result = await db.execute(
            select(
                FieldVerification,
                func.ST_AsGeoJSON(FieldVerification.location).label("geometry"),
            )
            .where(FieldVerification.task_id == task_id)
            .order_by(FieldVerification.verification_code)
        )
        return result.tuples().all()
