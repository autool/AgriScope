"""源栅格离线介质封存数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.offline_archive import (
    OfflineArchive,
    OfflineArchiveEvent,
    OfflineArchiveSource,
    OfflineArchiveVolume,
)
from app.models.workbench import DatasetAsset, ImageryAsset, ImageryProcessingStep


class OfflineArchiveDAO:
    """封装离线封存版本、来源、分卷和事件查询。"""

    async def list_archives(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[OfflineArchive]:
        """查询任务全部离线封存版本。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[OfflineArchive]: 按版本倒序排列的封存版本。
        """
        result = await db.execute(
            select(OfflineArchive)
            .where(OfflineArchive.task_id == task_id)
            .order_by(OfflineArchive.version.desc())
        )
        return result.scalars().all()

    async def get_archive_by_code(
        self,
        db: AsyncSession,
        archive_code: str,
    ) -> OfflineArchive | None:
        """按业务编号查询离线封存版本。

        Args:
            db: 异步数据库会话。
            archive_code: 离线封存编号。

        Returns:
            OfflineArchive | None: 匹配的封存版本。
        """
        result = await db.execute(
            select(OfflineArchive).where(
                OfflineArchive.archive_code == archive_code
            )
        )
        return result.scalar_one_or_none()

    async def get_next_version(self, db: AsyncSession, task_id: int) -> int:
        """计算任务下一离线封存版本号。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            int: 下一版本号。
        """
        result = await db.execute(
            select(func.coalesce(func.max(OfflineArchive.version), 0)).where(
                OfflineArchive.task_id == task_id
            )
        )
        return int(result.scalar_one()) + 1

    async def list_current_archives_for_update(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[OfflineArchive]:
        """锁定任务当前完成的离线封存版本。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[OfflineArchive]: 待被新版本替代的封存版本。
        """
        result = await db.execute(
            select(OfflineArchive)
            .where(
                OfflineArchive.task_id == task_id,
                OfflineArchive.status == "completed",
            )
            .with_for_update()
        )
        return result.scalars().all()

    async def add_archive(
        self,
        db: AsyncSession,
        archive: OfflineArchive,
    ) -> OfflineArchive:
        """新增并刷新离线封存主记录。

        Args:
            db: 异步数据库会话。
            archive: 待持久化的封存记录。

        Returns:
            OfflineArchive: 已分配主键的封存记录。
        """
        db.add(archive)
        await db.flush()
        return archive

    async def add_volumes(
        self,
        db: AsyncSession,
        volumes: Sequence[OfflineArchiveVolume],
    ) -> None:
        """批量新增分卷记录。

        Args:
            db: 异步数据库会话。
            volumes: 分卷记录序列。

        Returns:
            None: 写入会话后无返回值。
        """
        db.add_all(list(volumes))
        await db.flush()

    async def add_sources(
        self,
        db: AsyncSession,
        sources: Sequence[OfflineArchiveSource],
    ) -> None:
        """批量新增来源快照记录。

        Args:
            db: 异步数据库会话。
            sources: 来源快照序列。

        Returns:
            None: 写入会话后无返回值。
        """
        db.add_all(list(sources))
        await db.flush()

    async def add_event(
        self,
        db: AsyncSession,
        event: OfflineArchiveEvent,
    ) -> None:
        """新增一条不可变封存事件。

        Args:
            db: 异步数据库会话。
            event: 待持久化事件。

        Returns:
            None: 写入会话后无返回值。
        """
        db.add(event)
        await db.flush()

    async def list_volumes(
        self,
        db: AsyncSession,
        archive_id: int,
    ) -> Sequence[OfflineArchiveVolume]:
        """查询封存版本全部分卷。

        Args:
            db: 异步数据库会话。
            archive_id: 离线封存主键。

        Returns:
            Sequence[OfflineArchiveVolume]: 按卷序排列的分卷。
        """
        result = await db.execute(
            select(OfflineArchiveVolume)
            .where(OfflineArchiveVolume.archive_id == archive_id)
            .order_by(OfflineArchiveVolume.sequence)
        )
        return result.scalars().all()

    async def get_volume(
        self,
        db: AsyncSession,
        archive_id: int,
        sequence: int,
    ) -> OfflineArchiveVolume | None:
        """查询指定卷序的离线封存分卷。

        Args:
            db: 异步数据库会话。
            archive_id: 离线封存主键。
            sequence: 分卷序号。

        Returns:
            OfflineArchiveVolume | None: 匹配的分卷记录。
        """
        result = await db.execute(
            select(OfflineArchiveVolume).where(
                OfflineArchiveVolume.archive_id == archive_id,
                OfflineArchiveVolume.sequence == sequence,
            )
        )
        return result.scalar_one_or_none()

    async def list_sources(
        self,
        db: AsyncSession,
        archive_id: int,
    ) -> Sequence[OfflineArchiveSource]:
        """查询封存版本全部来源快照。

        Args:
            db: 异步数据库会话。
            archive_id: 离线封存主键。

        Returns:
            Sequence[OfflineArchiveSource]: 按来源序号排列的快照。
        """
        result = await db.execute(
            select(OfflineArchiveSource)
            .where(OfflineArchiveSource.archive_id == archive_id)
            .order_by(OfflineArchiveSource.sequence)
        )
        return result.scalars().all()

    async def list_operational_imagery_assets(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[ImageryAsset]:
        """查询项目全部业务可用影像源实体。

        Args:
            db: 异步数据库会话。
            project_id: 监测项目主键。

        Returns:
            Sequence[ImageryAsset]: 按采集时间和编号排列的业务影像。
        """
        result = await db.execute(
            select(ImageryAsset)
            .where(
                ImageryAsset.project_id == project_id,
                ImageryAsset.data_status == "operational",
            )
            .order_by(ImageryAsset.acquired_at, ImageryAsset.asset_code)
        )
        return result.scalars().all()

    async def list_completed_imagery_steps(
        self,
        db: AsyncSession,
        asset_ids: list[int],
    ) -> Sequence[ImageryProcessingStep]:
        """查询业务影像全部已完成处理产物。

        Args:
            db: 异步数据库会话。
            asset_ids: 业务影像主键列表。

        Returns:
            Sequence[ImageryProcessingStep]: 按资产和步骤顺序排列的产物。
        """
        if not asset_ids:
            return []
        result = await db.execute(
            select(ImageryProcessingStep)
            .where(
                ImageryProcessingStep.asset_id.in_(asset_ids),
                ImageryProcessingStep.status == "completed",
            )
            .order_by(
                ImageryProcessingStep.asset_id,
                ImageryProcessingStep.sequence,
            )
        )
        return result.scalars().all()

    async def list_verified_dataset_assets(
        self,
        db: AsyncSession,
        project_id: int,
        task_id: int,
    ) -> Sequence[DatasetAsset]:
        """查询项目级及任务级已验证多源数据实体。

        Args:
            db: 异步数据库会话。
            project_id: 监测项目主键。
            task_id: 作业任务主键。

        Returns:
            Sequence[DatasetAsset]: 可被离线封存的实体数据资产。
        """
        result = await db.execute(
            select(DatasetAsset)
            .where(
                DatasetAsset.project_id == project_id,
                DatasetAsset.verification_status == "verified",
                or_(
                    DatasetAsset.task_id.is_(None),
                    DatasetAsset.task_id == task_id,
                ),
            )
            .order_by(DatasetAsset.asset_type, DatasetAsset.asset_code)
        )
        return result.scalars().all()
