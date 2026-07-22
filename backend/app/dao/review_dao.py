"""成果审核与图斑版本数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workbench import PlotVersion


class ReviewDAO:
    """封装图斑历史版本查询与写入。"""

    async def get_versions(
        self,
        db: AsyncSession,
        plot_code: str,
    ) -> Sequence[PlotVersion]:
        """查询图斑全部历史版本。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑编号。

        Returns:
            Sequence[PlotVersion]: 按版本倒序排列的历史版本。
        """
        result = await db.execute(
            select(PlotVersion)
            .where(PlotVersion.plot_code == plot_code)
            .order_by(PlotVersion.version.desc())
        )
        return result.scalars().all()

    async def get_version(
        self,
        db: AsyncSession,
        plot_code: str,
        version: int,
    ) -> PlotVersion | None:
        """查询指定图斑历史版本。

        Args:
            db: 异步数据库会话。
            plot_code: 图斑编号。
            version: 版本号。

        Returns:
            PlotVersion | None: 历史版本，不存在时返回 None。
        """
        result = await db.execute(
            select(PlotVersion).where(
                PlotVersion.plot_code == plot_code,
                PlotVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def add_version(
        self,
        db: AsyncSession,
        version: PlotVersion,
    ) -> PlotVersion:
        """写入图斑历史版本。

        Args:
            db: 异步数据库会话。
            version: 待写入历史版本。

        Returns:
            PlotVersion: 已写入历史版本。
        """
        db.add(version)
        await db.flush()
        await db.refresh(version)
        return version
