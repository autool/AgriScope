"""遥感影像预处理流水线数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.imagery_import import ImageryImportBatch, ImageryImportBatchItem
from app.models.workbench import (
    AdministrativeBoundary,
    ImageryAsset,
    ImageryProcessingStep,
)


class ImageryDAO:
    """封装影像资产和处理步骤查询。"""

    async def get_asset_by_code(
        self,
        db: AsyncSession,
        asset_code: str,
    ) -> ImageryAsset | None:
        """按编号查询影像资产。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。

        Returns:
            ImageryAsset | None: 影像资产，不存在时返回 None。
        """
        result = await db.execute(
            select(ImageryAsset).where(ImageryAsset.asset_code == asset_code)
        )
        return result.scalar_one_or_none()

    async def get_asset_by_code_for_update(
        self,
        db: AsyncSession,
        asset_code: str,
    ) -> ImageryAsset | None:
        """锁定并查询待处理影像资产。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。

        Returns:
            ImageryAsset | None: 已锁定资产；不存在时返回 None。
        """
        result = await db.execute(
            select(ImageryAsset)
            .where(ImageryAsset.asset_code == asset_code)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_asset_by_checksum(
        self,
        db: AsyncSession,
        checksum_sha256: str,
    ) -> ImageryAsset | None:
        """按文件 SHA256 查询已入库影像。

        Args:
            db: 异步数据库会话。
            checksum_sha256: 文件 SHA256。

        Returns:
            ImageryAsset | None: 重复文件对应资产，不存在时返回 None。
        """
        result = await db.execute(
            select(ImageryAsset).where(
                ImageryAsset.checksum_sha256 == checksum_sha256
            )
        )
        return result.scalar_one_or_none()

    async def list_assets(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[RowMapping]:
        """查询项目影像资产及 WGS84 GeoJSON 范围。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[RowMapping]: 影像资产字段和范围几何。
        """
        result = await db.execute(
            select(
                ImageryAsset,
                func.ST_AsGeoJSON(ImageryAsset.spatial_extent).label("footprint"),
            )
            .where(ImageryAsset.project_id == project_id)
            .order_by(ImageryAsset.acquired_at.desc())
        )
        return list(result.mappings().all())

    async def add_asset(
        self,
        db: AsyncSession,
        asset: ImageryAsset,
    ) -> ImageryAsset:
        """新增真实影像资产元数据。

        Args:
            db: 异步数据库会话。
            asset: 待入库影像资产。

        Returns:
            ImageryAsset: 已写入会话的影像资产。
        """
        db.add(asset)
        await db.flush()
        await db.refresh(asset)
        return asset

    async def add_steps(
        self,
        db: AsyncSession,
        steps: list[ImageryProcessingStep],
    ) -> None:
        """批量创建影像默认预处理流水线。

        Args:
            db: 异步数据库会话。
            steps: 待创建处理步骤。

        Returns:
            None: 无返回值。
        """
        db.add_all(steps)
        await db.flush()

    async def get_import_batch_by_code(
        self,
        db: AsyncSession,
        batch_code: str,
    ) -> ImageryImportBatch | None:
        """按批次编号查询影像入库批次。

        Args:
            db: 异步数据库会话。
            batch_code: 批次编号。

        Returns:
            ImageryImportBatch | None: 已存在批次或空值。
        """
        result = await db.execute(
            select(ImageryImportBatch).where(
                ImageryImportBatch.batch_code == batch_code
            )
        )
        return result.scalar_one_or_none()

    async def add_import_batch(
        self,
        db: AsyncSession,
        batch: ImageryImportBatch,
    ) -> ImageryImportBatch:
        """新增影像原子入库批次。

        Args:
            db: 异步数据库会话。
            batch: 批次实体。

        Returns:
            ImageryImportBatch: 已刷新批次实体。
        """
        db.add(batch)
        await db.flush()
        await db.refresh(batch)
        return batch

    async def add_import_batch_items(
        self,
        db: AsyncSession,
        items: list[ImageryImportBatchItem],
    ) -> None:
        """批量写入影像入库批次成员。

        Args:
            db: 异步数据库会话。
            items: 批次成员实体。

        Returns:
            None: 无返回值。
        """
        db.add_all(items)
        await db.flush()

    async def get_steps(
        self,
        db: AsyncSession,
        asset_id: int,
    ) -> Sequence[ImageryProcessingStep]:
        """查询影像处理步骤。

        Args:
            db: 异步数据库会话。
            asset_id: 影像资产主键。

        Returns:
            Sequence[ImageryProcessingStep]: 按顺序排列的处理步骤。
        """
        result = await db.execute(
            select(ImageryProcessingStep)
            .where(ImageryProcessingStep.asset_id == asset_id)
            .order_by(ImageryProcessingStep.sequence)
        )
        return result.scalars().all()

    async def get_step(
        self,
        db: AsyncSession,
        asset_id: int,
        step_code: str,
    ) -> ImageryProcessingStep | None:
        """查询指定影像处理步骤。

        Args:
            db: 异步数据库会话。
            asset_id: 影像资产主键。
            step_code: 处理步骤编号。

        Returns:
            ImageryProcessingStep | None: 处理步骤，不存在时返回 None。
        """
        result = await db.execute(
            select(ImageryProcessingStep).where(
                ImageryProcessingStep.asset_id == asset_id,
                ImageryProcessingStep.step_code == step_code,
            )
        )
        return result.scalar_one_or_none()

    async def get_step_for_update(
        self,
        db: AsyncSession,
        asset_id: int,
        step_code: str,
    ) -> ImageryProcessingStep | None:
        """锁定并查询待更新影像处理步骤。

        Args:
            db: 异步数据库会话。
            asset_id: 影像资产主键。
            step_code: 处理步骤编号。

        Returns:
            ImageryProcessingStep | None: 已锁定步骤；不存在时返回 None。
        """
        result = await db.execute(
            select(ImageryProcessingStep)
            .where(
                ImageryProcessingStep.asset_id == asset_id,
                ImageryProcessingStep.step_code == step_code,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_boundary_geometry(
        self,
        db: AsyncSession,
        project_id: int,
        boundary_code: str,
    ) -> str | None:
        """查询项目行政区真实边界 GeoJSON。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            boundary_code: 行政区编码。

        Returns:
            str | None: WGS84 GeoJSON 文本；不存在时返回 None。
        """
        result = await db.execute(
            select(func.ST_AsGeoJSON(AdministrativeBoundary.geom)).where(
                AdministrativeBoundary.project_id == project_id,
                AdministrativeBoundary.boundary_code == boundary_code,
            )
        )
        return result.scalar_one_or_none()
