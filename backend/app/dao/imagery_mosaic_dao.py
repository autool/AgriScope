"""多景影像镶嵌任务、输入血缘和审计数据访问对象。"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.imagery_mosaic import (
    ImageryMosaicEvent,
    ImageryMosaicInput,
    ImageryMosaicJob,
)
from app.models.workbench import (
    AdministrativeBoundary,
    ImageryAsset,
    ImageryProcessingStep,
)


@dataclass(frozen=True)
class MosaicSourceRecord:
    """数据库中一个已登记影像步骤来源。"""

    asset: ImageryAsset
    step: ImageryProcessingStep


class ImageryMosaicDAO:
    """封装镶嵌来源、任务、输入和事件数据库操作。"""

    async def list_source_records(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[MosaicSourceRecord]:
        """查询项目可候选的空间处理步骤。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[MosaicSourceRecord]: 候选来源记录。
        """
        result = await db.execute(
            select(ImageryAsset, ImageryProcessingStep)
            .join(
                ImageryProcessingStep,
                ImageryProcessingStep.asset_id == ImageryAsset.id,
            )
            .where(
                ImageryAsset.project_id == project_id,
                ImageryProcessingStep.step_code.in_((
                    "geometric",
                    "clip",
                    "enhancement",
                    "band_products",
                )),
            )
            .order_by(
                ImageryAsset.acquired_at.desc(),
                ImageryAsset.asset_code,
                ImageryProcessingStep.sequence.desc(),
            )
        )
        return [MosaicSourceRecord(asset=row[0], step=row[1]) for row in result]

    async def get_boundary_geojson(
        self,
        db: AsyncSession,
        project_id: int,
        boundary_code: str,
    ) -> tuple[str, str] | None:
        """查询真实行政区名称和 WGS84 几何。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            boundary_code: 行政区编码。

        Returns:
            tuple[str, str] | None: 名称与 GeoJSON，未找到返回空。
        """
        result = await db.execute(
            select(
                AdministrativeBoundary.boundary_name,
                func.ST_AsGeoJSON(AdministrativeBoundary.geom),
            ).where(
                AdministrativeBoundary.project_id == project_id,
                AdministrativeBoundary.boundary_code == boundary_code,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        return str(row[0]), str(row[1])

    async def get_job_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        job_code: str,
    ) -> ImageryMosaicJob | None:
        """按项目和业务编号查询镶嵌任务。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            job_code: 镶嵌任务编号。

        Returns:
            ImageryMosaicJob | None: 任务或空值。
        """
        result = await db.execute(
            select(ImageryMosaicJob).where(
                ImageryMosaicJob.project_id == project_id,
                ImageryMosaicJob.job_code == job_code,
            )
        )
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[ImageryMosaicJob]:
        """查询项目镶嵌成果。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[ImageryMosaicJob]: 按时间倒序任务。
        """
        result = await db.execute(
            select(ImageryMosaicJob)
            .where(ImageryMosaicJob.project_id == project_id)
            .order_by(ImageryMosaicJob.created_at.desc())
        )
        return result.scalars().all()

    async def list_inputs(
        self,
        db: AsyncSession,
        job_id: int,
    ) -> Sequence[ImageryMosaicInput]:
        """查询任务显式输入血缘。

        Args:
            db: 异步数据库会话。
            job_id: 镶嵌任务主键。

        Returns:
            Sequence[ImageryMosaicInput]: 按输入顺序排列的记录。
        """
        result = await db.execute(
            select(ImageryMosaicInput)
            .where(ImageryMosaicInput.job_id == job_id)
            .order_by(ImageryMosaicInput.source_order)
        )
        return result.scalars().all()

    async def add_job(
        self,
        db: AsyncSession,
        job: ImageryMosaicJob,
    ) -> ImageryMosaicJob:
        """新增已完成镶嵌任务。

        Args:
            db: 异步数据库会话。
            job: 任务模型。

        Returns:
            ImageryMosaicJob: 已刷新任务。
        """
        db.add(job)
        await db.flush()
        await db.refresh(job)
        return job

    async def add_inputs(
        self,
        db: AsyncSession,
        inputs: list[ImageryMosaicInput],
    ) -> None:
        """批量写入显式输入。

        Args:
            db: 异步数据库会话。
            inputs: 输入模型。

        Returns:
            None: 无返回值。
        """
        db.add_all(inputs)
        await db.flush()

    async def add_event(
        self,
        db: AsyncSession,
        event: ImageryMosaicEvent,
    ) -> None:
        """写入不可变镶嵌事件。

        Args:
            db: 异步数据库会话。
            event: 审计事件。

        Returns:
            None: 无返回值。
        """
        db.add(event)
        await db.flush()
