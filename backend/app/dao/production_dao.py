"""多源数据目录、生产批次与县区作业包数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import case, func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.plot import FarmlandPlot
from app.models.workbench import (
    AdministrativeBoundary,
    DatasetAsset,
    DatasetLineage,
    ProductionAuditEvent,
    ProductionBatch,
    ProjectUser,
    TaskPlot,
    WorkPackage,
    WorkPackagePlot,
)


class ProductionDAO:
    """封装多源资产、生产批次、作业包和显式图斑分配。"""

    async def get_asset_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        asset_code: str,
    ) -> DatasetAsset | None:
        """按项目和资产编号查询多源数据资产。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            asset_code: 资产编号。

        Returns:
            DatasetAsset | None: 资产不存在时返回 None。
        """
        result = await db.execute(
            select(DatasetAsset).where(
                DatasetAsset.project_id == project_id,
                DatasetAsset.asset_code == asset_code,
            )
        )
        return result.scalar_one_or_none()

    async def get_assets_by_codes(
        self,
        db: AsyncSession,
        project_id: int,
        asset_codes: list[str],
    ) -> Sequence[DatasetAsset]:
        """查询一组同项目父资产。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            asset_codes: 资产编号列表。

        Returns:
            Sequence[DatasetAsset]: 匹配的资产对象。
        """
        if not asset_codes:
            return []
        result = await db.execute(
            select(DatasetAsset).where(
                DatasetAsset.project_id == project_id,
                DatasetAsset.asset_code.in_(asset_codes),
            )
        )
        return result.scalars().all()

    async def get_asset_by_checksum(
        self,
        db: AsyncSession,
        project_id: int,
        checksum_sha256: str,
    ) -> DatasetAsset | None:
        """按项目和内容校验值查询重复数据资产。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            checksum_sha256: 数据内容 SHA256。

        Returns:
            DatasetAsset | None: 已登记相同内容时返回资产。
        """
        result = await db.execute(
            select(DatasetAsset).where(
                DatasetAsset.project_id == project_id,
                DatasetAsset.checksum_sha256 == checksum_sha256,
            )
        )
        return result.scalar_one_or_none()

    async def list_assets(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[RowMapping]:
        """查询项目多源资产和 WGS84 包围盒。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[RowMapping]: 资产 ORM 与包围盒字段。
        """
        box = func.Box2D(DatasetAsset.extent)
        result = await db.execute(
            select(
                DatasetAsset,
                func.ST_XMin(box).label("min_lon"),
                func.ST_YMin(box).label("min_lat"),
                func.ST_XMax(box).label("max_lon"),
                func.ST_YMax(box).label("max_lat"),
            )
            .where(DatasetAsset.project_id == project_id)
            .order_by(DatasetAsset.created_at.desc())
        )
        return list(result.mappings().all())

    async def list_lineages(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[RowMapping]:
        """查询项目资产派生血缘。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[RowMapping]: 父资产与派生资产编号。
        """
        parent = aliased(DatasetAsset)
        derived = aliased(DatasetAsset)
        result = await db.execute(
            select(
                parent.asset_code.label("parent_asset_code"),
                derived.asset_code.label("derived_asset_code"),
            )
            .select_from(DatasetLineage)
            .join(parent, parent.id == DatasetLineage.parent_asset_id)
            .join(derived, derived.id == DatasetLineage.derived_asset_id)
            .where(derived.project_id == project_id)
        )
        return list(result.mappings().all())

    async def add_asset(
        self,
        db: AsyncSession,
        asset: DatasetAsset,
    ) -> DatasetAsset:
        """新增多源数据资产。

        Args:
            db: 异步数据库会话。
            asset: 待登记资产。

        Returns:
            DatasetAsset: 已写入会话的资产。
        """
        db.add(asset)
        await db.flush()
        return asset

    async def add_lineages(
        self,
        db: AsyncSession,
        lineages: list[DatasetLineage],
    ) -> None:
        """批量写入资产派生血缘。

        Args:
            db: 异步数据库会话。
            lineages: 待写入血缘关系。

        Returns:
            None: 无返回值。
        """
        if lineages:
            db.add_all(lineages)
            await db.flush()

    async def add_audit_event(
        self,
        db: AsyncSession,
        event: ProductionAuditEvent,
    ) -> ProductionAuditEvent:
        """写入不可变生产操作审计。

        Args:
            db: 异步数据库会话。
            event: 生产业务操作审计。

        Returns:
            ProductionAuditEvent: 已加入会话的审计事件。
        """
        db.add(event)
        await db.flush()
        return event

    async def list_work_areas(
        self,
        db: AsyncSession,
        project_id: int,
        task_id: int,
    ) -> list[RowMapping]:
        """按真实县区统计当前任务可拆分图斑和面积。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            task_id: 任务主键。

        Returns:
            list[RowMapping]: 县区、所属地级区域、图斑数和面积。
        """
        city = aliased(AdministrativeBoundary)
        district = aliased(AdministrativeBoundary)
        task_scope = (
            select(
                FarmlandPlot.district_code.label("region_code"),
                func.count(FarmlandPlot.plot_code).label("plot_count"),
                func.coalesce(func.sum(FarmlandPlot.area_ha), 0).label("area_ha"),
            )
            .join(
                TaskPlot,
                (TaskPlot.plot_code == FarmlandPlot.plot_code)
                & (TaskPlot.task_id == task_id),
            )
            .where(FarmlandPlot.interpretation_status != "deleted")
            .group_by(FarmlandPlot.district_code)
            .subquery()
        )
        result = await db.execute(
            select(
                city.boundary_code.label("city_code"),
                city.boundary_name.label("city_name"),
                district.boundary_code.label("region_code"),
                district.boundary_name.label("region_name"),
                func.coalesce(task_scope.c.plot_count, 0).label("plot_count"),
                func.coalesce(task_scope.c.area_ha, 0).label("area_ha"),
            )
            .join(city, city.boundary_code == district.parent_code)
            .outerjoin(
                task_scope,
                task_scope.c.region_code == district.boundary_code,
            )
            .where(
                district.project_id == project_id,
                district.boundary_level == "district",
            )
            .order_by(city.boundary_name, district.boundary_name)
        )
        return list(result.mappings().all())

    async def list_region_batch_assignments(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> list[RowMapping]:
        """查询县区已经加入的生产批次。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            list[RowMapping]: 县区编码和生产批次编号。
        """
        result = await db.execute(
            select(WorkPackage.region_code, ProductionBatch.batch_code)
            .join(ProductionBatch, ProductionBatch.id == WorkPackage.batch_id)
            .where(ProductionBatch.task_id == task_id)
            .order_by(ProductionBatch.created_at)
        )
        return list(result.mappings().all())

    async def list_batches(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[ProductionBatch]:
        """查询任务生产批次。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            Sequence[ProductionBatch]: 按创建时间倒序的批次。
        """
        result = await db.execute(
            select(ProductionBatch)
            .where(ProductionBatch.task_id == task_id)
            .order_by(ProductionBatch.created_at.desc())
        )
        return result.scalars().all()

    async def list_package_metrics(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> list[RowMapping]:
        """查询作业包和显式分配图斑的实时进度。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            list[RowMapping]: 作业包、活动图斑和已解译图斑数量。
        """
        result = await db.execute(
            select(
                WorkPackage,
                func.count(WorkPackagePlot.id)
                .filter(FarmlandPlot.interpretation_status != "deleted")
                .label("active_plot_count"),
                func.coalesce(
                    func.sum(
                        case(
                            (FarmlandPlot.interpretation_status == "interpreted", 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("completed_plot_count"),
            )
            .join(ProductionBatch, ProductionBatch.id == WorkPackage.batch_id)
            .outerjoin(
                WorkPackagePlot,
                WorkPackagePlot.work_package_id == WorkPackage.id,
            )
            .outerjoin(
                FarmlandPlot,
                FarmlandPlot.plot_code == WorkPackagePlot.plot_code,
            )
            .where(ProductionBatch.task_id == task_id)
            .group_by(WorkPackage.id)
            .order_by(WorkPackage.deadline, WorkPackage.region_name)
        )
        return list(result.mappings().all())

    async def get_batch_by_code(
        self,
        db: AsyncSession,
        task_id: int,
        batch_code: str,
    ) -> ProductionBatch | None:
        """按任务和编号查询生产批次。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            batch_code: 批次编号。

        Returns:
            ProductionBatch | None: 批次不存在时返回 None。
        """
        result = await db.execute(
            select(ProductionBatch).where(
                ProductionBatch.task_id == task_id,
                ProductionBatch.batch_code == batch_code,
            )
        )
        return result.scalar_one_or_none()

    async def get_batch_by_code_for_update(
        self,
        db: AsyncSession,
        task_id: int,
        batch_code: str,
    ) -> ProductionBatch | None:
        """锁定并查询生产批次。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            batch_code: 批次编号。

        Returns:
            ProductionBatch | None: 已锁定批次。
        """
        result = await db.execute(
            select(ProductionBatch)
            .where(
                ProductionBatch.task_id == task_id,
                ProductionBatch.batch_code == batch_code,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def add_batch(
        self,
        db: AsyncSession,
        batch: ProductionBatch,
    ) -> ProductionBatch:
        """新增生产批次。

        Args:
            db: 异步数据库会话。
            batch: 待新增批次。

        Returns:
            ProductionBatch: 已写入会话的批次。
        """
        db.add(batch)
        await db.flush()
        return batch

    async def get_batch_by_id(
        self,
        db: AsyncSession,
        batch_id: int,
    ) -> ProductionBatch | None:
        """按主键查询生产批次。

        Args:
            db: 异步数据库会话。
            batch_id: 生产批次主键。

        Returns:
            ProductionBatch | None: 批次不存在时返回 None。
        """
        result = await db.execute(
            select(ProductionBatch).where(ProductionBatch.id == batch_id)
        )
        return result.scalar_one_or_none()

    async def get_active_project_user(
        self,
        db: AsyncSession,
        project_id: int,
        user_code: str,
    ) -> ProjectUser | None:
        """查询可作为负责人分配的启用项目成员。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            user_code: 项目成员稳定编码。

        Returns:
            ProjectUser | None: 启用成员不存在时返回 None。
        """
        result = await db.execute(
            select(ProjectUser).where(
                ProjectUser.project_id == project_id,
                ProjectUser.user_code == user_code,
                ProjectUser.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def get_district(
        self,
        db: AsyncSession,
        project_id: int,
        region_code: str,
    ) -> AdministrativeBoundary | None:
        """查询项目真实县区边界目录项。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            region_code: 县区编码。

        Returns:
            AdministrativeBoundary | None: 县区不存在时返回 None。
        """
        result = await db.execute(
            select(AdministrativeBoundary).where(
                AdministrativeBoundary.project_id == project_id,
                AdministrativeBoundary.boundary_code == region_code,
                AdministrativeBoundary.boundary_level == "district",
            )
        )
        return result.scalar_one_or_none()

    async def list_task_region_plots(
        self,
        db: AsyncSession,
        task_id: int,
        region_code: str,
    ) -> list[RowMapping]:
        """查询当前任务在县区内的全部有效图斑。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            region_code: 县区编码。

        Returns:
            list[RowMapping]: 图斑编号和面积。
        """
        result = await db.execute(
            select(FarmlandPlot.plot_code, FarmlandPlot.area_ha)
            .join(
                TaskPlot,
                (TaskPlot.plot_code == FarmlandPlot.plot_code)
                & (TaskPlot.task_id == task_id),
            )
            .where(
                FarmlandPlot.district_code == region_code,
                FarmlandPlot.interpretation_status != "deleted",
            )
            .order_by(FarmlandPlot.plot_code)
        )
        return list(result.mappings().all())

    async def add_package(
        self,
        db: AsyncSession,
        package: WorkPackage,
    ) -> WorkPackage:
        """新增县区作业包。

        Args:
            db: 异步数据库会话。
            package: 作业包主记录。

        Returns:
            WorkPackage: 已写入会话的作业包。
        """
        db.add(package)
        await db.flush()
        return package

    async def add_package_plots(
        self,
        db: AsyncSession,
        assignments: list[WorkPackagePlot],
    ) -> None:
        """批量持久化作业包显式图斑范围。

        Args:
            db: 异步数据库会话。
            assignments: 作业包与图斑关联。

        Returns:
            None: 无返回值。
        """
        db.add_all(assignments)
        await db.flush()

    async def get_package_by_code_for_update(
        self,
        db: AsyncSession,
        task_id: int,
        package_code: str,
    ) -> WorkPackage | None:
        """锁定并查询任务内作业包。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            package_code: 作业包编号。

        Returns:
            WorkPackage | None: 已锁定作业包。
        """
        result = await db.execute(
            select(WorkPackage)
            .join(ProductionBatch, ProductionBatch.id == WorkPackage.batch_id)
            .where(
                ProductionBatch.task_id == task_id,
                WorkPackage.package_code == package_code,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_package_progress(
        self,
        db: AsyncSession,
        package_id: int,
    ) -> tuple[int, int]:
        """查询单个作业包活动图斑和已解译图斑数量。

        Args:
            db: 异步数据库会话。
            package_id: 作业包主键。

        Returns:
            tuple[int, int]: 活动图斑数和已解译图斑数。
        """
        result = await db.execute(
            select(
                func.count(WorkPackagePlot.id).filter(
                    FarmlandPlot.interpretation_status != "deleted"
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (FarmlandPlot.interpretation_status == "interpreted", 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .join(FarmlandPlot, FarmlandPlot.plot_code == WorkPackagePlot.plot_code)
            .where(WorkPackagePlot.work_package_id == package_id)
        )
        row = result.one()
        return int(row[0] or 0), int(row[1] or 0)
