"""多光谱与全色融合任务及审计数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.imagery_fusion import ImageryFusionEvent, ImageryFusionJob
from app.models.workbench import ImageryAsset


class ImageryFusionDAO:
    """封装融合来源、成果和不可变事件数据库操作。"""

    async def list_assets(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[ImageryAsset]:
        """查询项目影像资产。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[ImageryAsset]: 按采集时间倒序的影像资产。
        """
        result = await db.execute(
            select(ImageryAsset)
            .where(ImageryAsset.project_id == project_id)
            .order_by(ImageryAsset.acquired_at.desc())
        )
        return result.scalars().all()

    async def get_asset(
        self,
        db: AsyncSession,
        project_id: int,
        asset_code: str,
    ) -> ImageryAsset | None:
        """按项目和编号查询融合输入资产。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            asset_code: 资产编号。

        Returns:
            ImageryAsset | None: 影像资产或空值。
        """
        result = await db.execute(
            select(ImageryAsset).where(
                ImageryAsset.project_id == project_id,
                ImageryAsset.asset_code == asset_code,
            )
        )
        return result.scalar_one_or_none()

    async def get_job(
        self,
        db: AsyncSession,
        project_id: int,
        job_code: str,
    ) -> ImageryFusionJob | None:
        """查询融合任务。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            job_code: 任务编号。

        Returns:
            ImageryFusionJob | None: 融合任务或空值。
        """
        result = await db.execute(
            select(ImageryFusionJob).where(
                ImageryFusionJob.project_id == project_id,
                ImageryFusionJob.job_code == job_code,
            )
        )
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[ImageryFusionJob]:
        """查询项目融合历史成果。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[ImageryFusionJob]: 按时间倒序任务。
        """
        result = await db.execute(
            select(ImageryFusionJob)
            .where(ImageryFusionJob.project_id == project_id)
            .order_by(ImageryFusionJob.created_at.desc())
        )
        return result.scalars().all()

    async def add_job(
        self,
        db: AsyncSession,
        job: ImageryFusionJob,
    ) -> ImageryFusionJob:
        """写入融合成果。

        Args:
            db: 异步数据库会话。
            job: 融合任务。

        Returns:
            ImageryFusionJob: 已刷新任务。
        """
        db.add(job)
        await db.flush()
        await db.refresh(job)
        return job

    async def add_event(
        self,
        db: AsyncSession,
        event: ImageryFusionEvent,
    ) -> None:
        """写入不可变融合事件。

        Args:
            db: 异步数据库会话。
            event: 审计事件。

        Returns:
            None: 无返回值。
        """
        db.add(event)
        await db.flush()
