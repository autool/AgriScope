"""双景影像配准来源、任务和审计数据访问对象。"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.imagery_registration import (
    ImageryRegistrationEvent,
    ImageryRegistrationJob,
)
from app.models.workbench import ImageryAsset, ImageryProcessingStep


@dataclass(frozen=True)
class RegistrationSourceRecord:
    """数据库中的影像资产和一个处理步骤实体。"""

    asset: ImageryAsset
    step: ImageryProcessingStep


class ImageryRegistrationDAO:
    """封装配准来源、任务和事件数据库操作。"""

    async def list_source_records(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[RegistrationSourceRecord]:
        """查询项目内可候选的空间处理步骤。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[RegistrationSourceRecord]: 候选来源记录。
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
        return [
            RegistrationSourceRecord(asset=row[0], step=row[1])
            for row in result
        ]

    async def get_job_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        job_code: str,
    ) -> ImageryRegistrationJob | None:
        """按项目和任务编号查询配准成果。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            job_code: 配准任务编号。

        Returns:
            ImageryRegistrationJob | None: 任务或空值。
        """
        result = await db.execute(
            select(ImageryRegistrationJob).where(
                ImageryRegistrationJob.project_id == project_id,
                ImageryRegistrationJob.job_code == job_code,
            )
        )
        return result.scalar_one_or_none()

    async def get_job_by_id(
        self,
        db: AsyncSession,
        project_id: int,
        job_id: int,
    ) -> ImageryRegistrationJob | None:
        """按项目和主键查询配准成果。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            job_id: 配准任务主键。

        Returns:
            ImageryRegistrationJob | None: 任务或空值。
        """
        result = await db.execute(
            select(ImageryRegistrationJob).where(
                ImageryRegistrationJob.project_id == project_id,
                ImageryRegistrationJob.id == job_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[ImageryRegistrationJob]:
        """查询项目历史配准成果。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[ImageryRegistrationJob]: 按创建时间倒序成果。
        """
        result = await db.execute(
            select(ImageryRegistrationJob)
            .where(ImageryRegistrationJob.project_id == project_id)
            .order_by(ImageryRegistrationJob.created_at.desc())
        )
        return result.scalars().all()

    async def add_job(
        self,
        db: AsyncSession,
        job: ImageryRegistrationJob,
    ) -> ImageryRegistrationJob:
        """新增已通过残差门禁的配准任务。

        Args:
            db: 异步数据库会话。
            job: 配准任务模型。

        Returns:
            ImageryRegistrationJob: 已刷新任务。
        """
        db.add(job)
        await db.flush()
        await db.refresh(job)
        return job

    async def add_event(
        self,
        db: AsyncSession,
        event: ImageryRegistrationEvent,
    ) -> None:
        """写入不可变配准事件。

        Args:
            db: 异步数据库会话。
            event: 配准事件。

        Returns:
            None: 无返回值。
        """
        db.add(event)
        await db.flush()
