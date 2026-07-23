"""成果交付包和交付数据集访问对象。"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.dataset_asset_import import (
    DatasetAssetImportBatch,
    DatasetAssetImportBatchItem,
)
from app.models.dataset_asset_verification import DatasetAssetVerification
from app.models.disaster_report import DisasterReport
from app.models.growth_monitoring import GrowthMonitoringRun
from app.models.plot import FarmlandPlot
from app.models.statistics_report import StatisticsReport
from app.models.supervision import SupervisionPlan, SupervisionReport
from app.models.thematic_map import ThematicMapAtlas, ThematicMapProduct
from app.models.vector_export import VectorExportPackage
from app.models.workbench import (
    DatasetAsset,
    DeliveryPackage,
    FieldVerification,
    ImageryProcessingStep,
    QualityIssue,
    TaskPlot,
)


@dataclass(frozen=True)
class DeliveryArchiveState:
    """交付归档来源的当前数量和最近更新时间。"""

    thematic_map_count: int
    thematic_map_latest_at: datetime | None
    supervision_report_count: int
    supervision_report_latest_at: datetime | None
    dataset_asset_count: int
    dataset_asset_latest_at: datetime | None
    imagery_step_count: int
    imagery_step_latest_at: datetime | None
    disaster_report_count: int = 0
    disaster_report_latest_at: datetime | None = None
    statistics_report_count: int = 0
    statistics_report_latest_at: datetime | None = None
    vector_export_count: int = 0
    vector_export_latest_at: datetime | None = None
    growth_monitoring_count: int = 0
    growth_monitoring_latest_at: datetime | None = None
    thematic_atlas_count: int = 0
    thematic_atlas_latest_at: datetime | None = None


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
            select(DeliveryPackage).where(DeliveryPackage.package_code == package_code)
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

    async def supersede_completed_packages(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> int:
        """将任务已有已完成成果包标记为被新版本替代。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            int: 被替代的历史成果包数量。
        """
        result = await db.execute(
            update(DeliveryPackage)
            .where(
                DeliveryPackage.task_id == task_id,
                DeliveryPackage.status == "completed",
            )
            .values(status="superseded")
        )
        return int(result.rowcount or 0)

    async def get_thematic_map_products(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[ThematicMapProduct]:
        """查询任务全部有效实体专题图。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            Sequence[ThematicMapProduct]: 按图号排序的已完成专题图。
        """
        result = await db.execute(
            select(ThematicMapProduct)
            .where(
                ThematicMapProduct.task_id == task_id,
                ThematicMapProduct.status == "completed",
            )
            .order_by(
                ThematicMapProduct.map_number,
                ThematicMapProduct.product_code,
            )
        )
        return result.scalars().all()

    async def get_thematic_map_atlases(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[ThematicMapAtlas]:
        """查询任务当前已完成专题图集。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            Sequence[ThematicMapAtlas]: 正常情况下至多一个当前图集。
        """
        result = await db.execute(
            select(ThematicMapAtlas)
            .where(
                ThematicMapAtlas.task_id == task_id,
                ThematicMapAtlas.status == "completed",
            )
            .order_by(ThematicMapAtlas.version.desc())
        )
        return result.scalars().all()

    async def get_supervision_reports(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[SupervisionReport]:
        """查询任务全部独立监理实体报告。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            Sequence[SupervisionReport]: 按生成时间排序的监理报告。
        """
        result = await db.execute(
            select(SupervisionReport)
            .join(
                SupervisionPlan,
                SupervisionPlan.id == SupervisionReport.plan_id,
            )
            .where(SupervisionPlan.task_id == task_id)
            .order_by(SupervisionReport.generated_at, SupervisionReport.report_code)
        )
        return result.scalars().all()

    async def get_disaster_reports(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[DisasterReport]:
        """查询任务当前有效灾害专题报告。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[DisasterReport]: 当前完成报告，正常仅一份。
        """
        result = await db.execute(
            select(DisasterReport)
            .where(
                DisasterReport.task_id == task_id,
                DisasterReport.status == "completed",
            )
            .order_by(DisasterReport.generated_at.desc())
        )
        return result.scalars().all()

    async def get_statistics_reports(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[StatisticsReport]:
        """查询任务当前有效面积统计正式报告。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[StatisticsReport]: 当前完成报告，正常仅一份。
        """
        result = await db.execute(
            select(StatisticsReport)
            .where(
                StatisticsReport.task_id == task_id,
                StatisticsReport.status == "completed",
            )
            .order_by(StatisticsReport.generated_at.desc())
        )
        return result.scalars().all()

    async def get_vector_exports(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[VectorExportPackage]:
        """查询任务当前有效多格式矢量成果包。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[VectorExportPackage]: 当前完成导出包，正常仅一份。
        """
        result = await db.execute(
            select(VectorExportPackage)
            .where(
                VectorExportPackage.task_id == task_id,
                VectorExportPackage.status == "completed",
            )
            .order_by(VectorExportPackage.generated_at.desc())
        )
        return result.scalars().all()

    async def get_growth_monitoring_runs(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[GrowthMonitoringRun]:
        """查询任务全部长势监测物理成果。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[GrowthMonitoringRun]: 按生成时间排序的长势任务。
        """
        result = await db.execute(
            select(GrowthMonitoringRun)
            .where(GrowthMonitoringRun.task_id == task_id)
            .order_by(GrowthMonitoringRun.created_at, GrowthMonitoringRun.run_code)
        )
        return result.scalars().all()

    async def get_dataset_assets(
        self,
        db: AsyncSession,
        project_id: int,
        task_id: int,
    ) -> Sequence[DatasetAsset]:
        """查询项目级及当前任务级多源数据资产目录。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            task_id: 任务主键。

        Returns:
            Sequence[DatasetAsset]: 可追溯数据资产目录。
        """
        result = await db.execute(
            select(DatasetAsset)
            .where(
                DatasetAsset.project_id == project_id,
                or_(
                    DatasetAsset.task_id.is_(None),
                    DatasetAsset.task_id == task_id,
                ),
            )
            .order_by(DatasetAsset.asset_type, DatasetAsset.asset_code)
        )
        return result.scalars().all()

    async def get_dataset_import_batches(
        self,
        db: AsyncSession,
        project_id: int,
        task_id: int,
    ) -> Sequence[DatasetAssetImportBatch]:
        """查询当前任务的数据资产原子入库批次。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            task_id: 任务主键。

        Returns:
            Sequence[DatasetAssetImportBatch]: 按创建时间排序的批次。
        """
        result = await db.execute(
            select(DatasetAssetImportBatch)
            .where(
                DatasetAssetImportBatch.project_id == project_id,
                DatasetAssetImportBatch.task_id == task_id,
            )
            .order_by(DatasetAssetImportBatch.created_at)
        )
        return result.scalars().all()

    async def get_dataset_import_batch_items(
        self,
        db: AsyncSession,
        batch_ids: list[int],
    ) -> list[RowMapping]:
        """查询数据资产批次成员及其资产和核验身份。

        Args:
            db: 异步数据库会话。
            batch_ids: 批次主键列表。

        Returns:
            list[RowMapping]: 批次、成员、资产和核验记录映射行。
        """
        if not batch_ids:
            return []
        result = await db.execute(
            select(
                DatasetAssetImportBatch,
                DatasetAssetImportBatchItem,
                DatasetAsset,
                DatasetAssetVerification,
            )
            .join(
                DatasetAssetImportBatchItem,
                DatasetAssetImportBatchItem.batch_id
                == DatasetAssetImportBatch.id,
            )
            .join(
                DatasetAsset,
                DatasetAsset.id == DatasetAssetImportBatchItem.asset_id,
            )
            .join(
                DatasetAssetVerification,
                DatasetAssetVerification.id
                == DatasetAssetImportBatchItem.verification_id,
            )
            .where(DatasetAssetImportBatch.id.in_(batch_ids))
            .order_by(
                DatasetAssetImportBatch.created_at,
                DatasetAssetImportBatchItem.sequence,
            )
        )
        return list(result.mappings().all())

    async def get_imagery_steps(
        self,
        db: AsyncSession,
        asset_id: int,
    ) -> Sequence[ImageryProcessingStep]:
        """查询当前业务影像全部处理步骤。

        Args:
            db: 异步数据库会话。
            asset_id: 影像资产主键。

        Returns:
            Sequence[ImageryProcessingStep]: 按处理顺序排列的步骤。
        """
        result = await db.execute(
            select(ImageryProcessingStep)
            .where(ImageryProcessingStep.asset_id == asset_id)
            .order_by(ImageryProcessingStep.sequence)
        )
        return result.scalars().all()

    async def get_archive_state(
        self,
        db: AsyncSession,
        project_id: int,
        task_id: int,
        imagery_asset_id: int | None,
    ) -> DeliveryArchiveState:
        """查询判断成果包归档快照是否过期所需的聚合状态。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            task_id: 任务主键。
            imagery_asset_id: 当前业务影像主键；不存在时为空。

        Returns:
            DeliveryArchiveState: 各类归档源数量和最近更新时间。
        """
        thematic_row = (
            await db.execute(
                select(
                    func.count(ThematicMapProduct.id),
                    func.max(ThematicMapProduct.generated_at),
                ).where(
                    ThematicMapProduct.task_id == task_id,
                    ThematicMapProduct.status == "completed",
                )
            )
        ).one()
        thematic_atlas_row = (
            await db.execute(
                select(
                    func.count(ThematicMapAtlas.id),
                    func.max(ThematicMapAtlas.generated_at),
                ).where(
                    ThematicMapAtlas.task_id == task_id,
                    ThematicMapAtlas.status == "completed",
                )
            )
        ).one()
        supervision_row = (
            await db.execute(
                select(
                    func.count(SupervisionReport.id),
                    func.max(SupervisionReport.generated_at),
                )
                .join(
                    SupervisionPlan,
                    SupervisionPlan.id == SupervisionReport.plan_id,
                )
                .where(SupervisionPlan.task_id == task_id)
            )
        ).one()
        disaster_report_row = (
            await db.execute(
                select(
                    func.count(DisasterReport.id),
                    func.max(DisasterReport.generated_at),
                ).where(
                    DisasterReport.task_id == task_id,
                    DisasterReport.status == "completed",
                )
            )
        ).one()
        statistics_report_row = (
            await db.execute(
                select(
                    func.count(StatisticsReport.id),
                    func.max(StatisticsReport.generated_at),
                ).where(
                    StatisticsReport.task_id == task_id,
                    StatisticsReport.status == "completed",
                )
            )
        ).one()
        vector_export_row = (
            await db.execute(
                select(
                    func.count(VectorExportPackage.id),
                    func.max(VectorExportPackage.generated_at),
                ).where(
                    VectorExportPackage.task_id == task_id,
                    VectorExportPackage.status == "completed",
                )
            )
        ).one()
        baseline_growth_step = aliased(ImageryProcessingStep)
        current_growth_step = aliased(ImageryProcessingStep)
        growth_monitoring_row = (
            await db.execute(
                select(
                    func.count(GrowthMonitoringRun.id),
                    func.max(
                        func.greatest(
                            GrowthMonitoringRun.created_at,
                            baseline_growth_step.updated_at,
                            current_growth_step.updated_at,
                        )
                    ),
                )
                .join(
                    baseline_growth_step,
                    baseline_growth_step.id == GrowthMonitoringRun.baseline_step_id,
                )
                .join(
                    current_growth_step,
                    current_growth_step.id == GrowthMonitoringRun.current_step_id,
                )
                .where(GrowthMonitoringRun.task_id == task_id)
            )
        ).one()
        dataset_row = (
            await db.execute(
                select(
                    func.count(DatasetAsset.id),
                    func.max(DatasetAsset.updated_at),
                ).where(
                    DatasetAsset.project_id == project_id,
                    or_(
                        DatasetAsset.task_id.is_(None),
                        DatasetAsset.task_id == task_id,
                    ),
                )
            )
        ).one()
        if imagery_asset_id is None:
            imagery_row = (0, None)
        else:
            imagery_row = (
                await db.execute(
                    select(
                        func.count(ImageryProcessingStep.id),
                        func.max(ImageryProcessingStep.updated_at),
                    ).where(
                        ImageryProcessingStep.asset_id == imagery_asset_id,
                        ImageryProcessingStep.status == "completed",
                        ImageryProcessingStep.output_uri.is_not(None),
                    )
                )
            ).one()
        return DeliveryArchiveState(
            thematic_map_count=int(thematic_row[0] or 0),
            thematic_map_latest_at=thematic_row[1],
            supervision_report_count=int(supervision_row[0] or 0),
            supervision_report_latest_at=supervision_row[1],
            disaster_report_count=int(disaster_report_row[0] or 0),
            disaster_report_latest_at=disaster_report_row[1],
            statistics_report_count=int(statistics_report_row[0] or 0),
            statistics_report_latest_at=statistics_report_row[1],
            vector_export_count=int(vector_export_row[0] or 0),
            vector_export_latest_at=vector_export_row[1],
            growth_monitoring_count=int(growth_monitoring_row[0] or 0),
            growth_monitoring_latest_at=growth_monitoring_row[1],
            dataset_asset_count=int(dataset_row[0] or 0),
            dataset_asset_latest_at=dataset_row[1],
            imagery_step_count=int(imagery_row[0] or 0),
            imagery_step_latest_at=imagery_row[1],
            thematic_atlas_count=int(thematic_atlas_row[0] or 0),
            thematic_atlas_latest_at=thematic_atlas_row[1],
        )

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
                FarmlandPlot.custom_attributes,
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
