"""历史影像覆盖矩阵与处理证据时间线数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import select, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workbench import (
    AdministrativeBoundary,
    ImageryAsset,
    ImageryProcessingStep,
)


class ImageryHistoryDAO:
    """批量读取影像时相、真实行政区覆盖和处理步骤。"""

    async def list_assets(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[ImageryAsset]:
        """查询项目全部影像时相。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[ImageryAsset]: 按采集时间倒序排列的影像资产。
        """
        result = await db.execute(
            select(ImageryAsset)
            .where(ImageryAsset.project_id == project_id)
            .order_by(ImageryAsset.acquired_at.desc(), ImageryAsset.asset_code)
        )
        return result.scalars().all()

    async def list_steps(
        self,
        db: AsyncSession,
        asset_ids: list[int],
    ) -> Sequence[ImageryProcessingStep]:
        """一次查询全部影像处理步骤，避免逐景 N+1 查询。

        Args:
            db: 异步数据库会话。
            asset_ids: 影像资产主键列表。

        Returns:
            Sequence[ImageryProcessingStep]: 按资产和步骤顺序排列的处理步骤。
        """
        if not asset_ids:
            return ()
        result = await db.execute(
            select(ImageryProcessingStep)
            .where(ImageryProcessingStep.asset_id.in_(asset_ids))
            .order_by(
                ImageryProcessingStep.asset_id,
                ImageryProcessingStep.sequence,
            )
        )
        return result.scalars().all()

    async def list_boundaries(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[RowMapping]:
        """查询覆盖矩阵使用的全部地级和县级真实行政区。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[RowMapping]: 行政区目录和来源信息。
        """
        result = await db.execute(
            select(
                AdministrativeBoundary.boundary_code,
                AdministrativeBoundary.boundary_name,
                AdministrativeBoundary.boundary_level,
                AdministrativeBoundary.parent_code,
                AdministrativeBoundary.source_name,
                AdministrativeBoundary.source_version,
                AdministrativeBoundary.source_updated_at,
            )
            .where(
                AdministrativeBoundary.project_id == project_id,
                AdministrativeBoundary.boundary_level.in_(("city", "district")),
            )
            .order_by(
                AdministrativeBoundary.boundary_level,
                AdministrativeBoundary.boundary_code,
            )
        )
        return list(result.mappings().all())

    async def list_county_coverage(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[RowMapping]:
        """批量计算每景影像与每个县区的真实面积覆盖率。

        业务含义：以数据库中的完整县级行政区 geography 面积为分母，影像
        WGS84 足迹与县界交集面积为分子。没有足迹或没有交集时明确返回 0，
        不省略空县区，也不使用包围盒面积冒充真实覆盖率。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[RowMapping]: 影像、地级区域、县区面积与覆盖面积。
        """
        query = text(
            """
            SELECT
                asset.id AS asset_id,
                asset.asset_code AS asset_code,
                prefecture.boundary_code AS prefecture_code,
                prefecture.boundary_name AS prefecture_name,
                county.boundary_code AS county_code,
                county.boundary_name AS county_name,
                ST_Area(county.geom::geography) / 10000.0 AS county_area_ha,
                CASE
                    WHEN asset.spatial_extent IS NULL
                      OR NOT ST_Intersects(asset.spatial_extent, county.geom)
                    THEN 0.0
                    ELSE ST_Area(
                        ST_Intersection(asset.spatial_extent, county.geom)::geography
                    ) / 10000.0
                END AS covered_area_ha
            FROM imagery_assets AS asset
            CROSS JOIN administrative_boundaries AS county
            JOIN administrative_boundaries AS prefecture
              ON prefecture.project_id = county.project_id
             AND prefecture.boundary_code = county.parent_code
             AND prefecture.boundary_level = 'city'
            WHERE asset.project_id = :project_id
              AND county.project_id = :project_id
              AND county.boundary_level = 'district'
            ORDER BY asset.acquired_at DESC, asset.asset_code, county.boundary_code
            """
        )
        result = await db.execute(query, {"project_id": project_id})
        return list(result.mappings().all())
