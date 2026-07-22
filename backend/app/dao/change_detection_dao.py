"""多时相变化检测任务、候选图斑和审计事件数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import func, or_, select, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change_detection import (
    ChangeCandidate,
    ChangeDetectionEvent,
    ChangeDetectionRun,
)
from app.models.workbench import ImageryAsset, TaskPlot


class ChangeDetectionDAO:
    """封装变化检测任务、空间候选和不可变事件持久化。"""

    async def list_imagery_assets(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[RowMapping]:
        """查询项目影像资产及其 WGS84 范围。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[RowMapping]: 影像资产与 GeoJSON 范围。
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

    async def get_imagery_asset(
        self,
        db: AsyncSession,
        project_id: int,
        asset_code: str,
    ) -> ImageryAsset | None:
        """按项目和编号查询影像资产。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            asset_code: 影像资产编号。

        Returns:
            ImageryAsset | None: 不存在时返回 None。
        """
        result = await db.execute(
            select(ImageryAsset).where(
                ImageryAsset.project_id == project_id,
                ImageryAsset.asset_code == asset_code,
            )
        )
        return result.scalar_one_or_none()

    async def get_imagery_assets_by_ids(
        self,
        db: AsyncSession,
        project_id: int,
        asset_ids: list[int],
    ) -> Sequence[ImageryAsset]:
        """按项目查询检测任务绑定的影像资产。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            asset_ids: 影像资产主键列表。

        Returns:
            Sequence[ImageryAsset]: 匹配的项目影像。
        """
        if not asset_ids:
            return []
        result = await db.execute(
            select(ImageryAsset).where(
                ImageryAsset.project_id == project_id,
                ImageryAsset.id.in_(asset_ids),
            )
        )
        return result.scalars().all()

    async def analyze_asset_pair(
        self,
        db: AsyncSession,
        baseline_asset_id: int,
        target_asset_id: int,
    ) -> RowMapping | None:
        """计算两期影像范围交集及相对较小范围的覆盖比。

        Args:
            db: 异步数据库会话。
            baseline_asset_id: 前时相影像主键。
            target_asset_id: 后时相影像主键。

        Returns:
            RowMapping | None: 是否具备范围、是否相交和覆盖比。
        """
        statement = text(
            """
            WITH baseline AS (
                SELECT spatial_extent AS geom
                FROM imagery_assets
                WHERE id = :baseline_asset_id
            ), target AS (
                SELECT spatial_extent AS geom
                FROM imagery_assets
                WHERE id = :target_asset_id
            )
            SELECT
                baseline.geom IS NOT NULL AND target.geom IS NOT NULL
                    AS has_extents,
                CASE
                    WHEN baseline.geom IS NULL OR target.geom IS NULL THEN FALSE
                    ELSE ST_Intersects(baseline.geom, target.geom)
                END AS intersects,
                CASE
                    WHEN baseline.geom IS NULL OR target.geom IS NULL THEN 0
                    ELSE COALESCE(
                        ST_Area(
                            ST_Intersection(baseline.geom, target.geom)::geography
                        ) / NULLIF(
                            LEAST(
                                ST_Area(baseline.geom::geography),
                                ST_Area(target.geom::geography)
                            ),
                            0
                        ),
                        0
                    )
                END AS overlap_ratio
            FROM baseline
            CROSS JOIN target
            """
        )
        result = await db.execute(
            statement,
            {
                "baseline_asset_id": baseline_asset_id,
                "target_asset_id": target_asset_id,
            },
        )
        return result.mappings().one_or_none()

    async def count_task_plots(self, db: AsyncSession, task_id: int) -> int:
        """统计当前任务显式图斑范围。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            int: 任务图斑数量。
        """
        result = await db.execute(
            select(func.count(TaskPlot.id)).where(TaskPlot.task_id == task_id)
        )
        return int(result.scalar_one())

    async def list_runs(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[ChangeDetectionRun]:
        """查询任务变化检测任务。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            Sequence[ChangeDetectionRun]: 按创建时间倒序的任务。
        """
        result = await db.execute(
            select(ChangeDetectionRun)
            .where(ChangeDetectionRun.task_id == task_id)
            .order_by(ChangeDetectionRun.created_at.desc())
        )
        return result.scalars().all()

    async def get_run_by_code(
        self,
        db: AsyncSession,
        task_id: int,
        run_code: str,
    ) -> ChangeDetectionRun | None:
        """按任务和编号查询变化检测任务。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            run_code: 检测任务编号。

        Returns:
            ChangeDetectionRun | None: 不存在时返回 None。
        """
        result = await db.execute(
            select(ChangeDetectionRun).where(
                ChangeDetectionRun.task_id == task_id,
                ChangeDetectionRun.run_code == run_code,
            )
        )
        return result.scalar_one_or_none()

    async def get_run_by_code_for_update(
        self,
        db: AsyncSession,
        task_id: int,
        run_code: str,
    ) -> ChangeDetectionRun | None:
        """锁定并查询变化检测任务。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            run_code: 检测任务编号。

        Returns:
            ChangeDetectionRun | None: 已锁定任务。
        """
        result = await db.execute(
            select(ChangeDetectionRun)
            .where(
                ChangeDetectionRun.task_id == task_id,
                ChangeDetectionRun.run_code == run_code,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def add_run(
        self,
        db: AsyncSession,
        run: ChangeDetectionRun,
    ) -> ChangeDetectionRun:
        """新增变化检测任务。

        Args:
            db: 异步数据库会话。
            run: 待新增任务。

        Returns:
            ChangeDetectionRun: 已写入会话的任务。
        """
        db.add(run)
        await db.flush()
        return run

    async def list_candidate_rows(
        self,
        db: AsyncSession,
        run_ids: list[int],
    ) -> list[RowMapping]:
        """查询检测任务候选及其 GeoJSON 几何。

        Args:
            db: 异步数据库会话。
            run_ids: 检测任务主键列表。

        Returns:
            list[RowMapping]: 候选 ORM 与 GeoJSON 文本。
        """
        if not run_ids:
            return []
        result = await db.execute(
            select(
                ChangeCandidate,
                func.ST_AsGeoJSON(ChangeCandidate.geom).label("geometry"),
            )
            .where(ChangeCandidate.run_id.in_(run_ids))
            .order_by(ChangeCandidate.created_at, ChangeCandidate.candidate_code)
        )
        return list(result.mappings().all())

    async def list_events(
        self,
        db: AsyncSession,
        run_ids: list[int],
    ) -> Sequence[ChangeDetectionEvent]:
        """查询检测任务全部不可变事件。

        Args:
            db: 异步数据库会话。
            run_ids: 检测任务主键列表。

        Returns:
            Sequence[ChangeDetectionEvent]: 按时间排序的事件。
        """
        if not run_ids:
            return []
        result = await db.execute(
            select(ChangeDetectionEvent)
            .where(ChangeDetectionEvent.run_id.in_(run_ids))
            .order_by(ChangeDetectionEvent.created_at, ChangeDetectionEvent.id)
        )
        return result.scalars().all()

    async def get_conflicting_candidates_for_update(
        self,
        db: AsyncSession,
        run_id: int,
        candidate_codes: list[str],
        source_name: str,
        source_feature_ids: list[str],
    ) -> Sequence[ChangeCandidate]:
        """锁定候选编号或同来源要素冲突记录。

        Args:
            db: 异步数据库会话。
            run_id: 检测任务主键。
            candidate_codes: 待导入候选编号。
            source_name: 来源名称。
            source_feature_ids: 来源要素编号。

        Returns:
            Sequence[ChangeCandidate]: 冲突候选。
        """
        result = await db.execute(
            select(ChangeCandidate)
            .where(
                ChangeCandidate.run_id == run_id,
                or_(
                    ChangeCandidate.candidate_code.in_(candidate_codes),
                    (
                        (ChangeCandidate.source_name == source_name)
                        & ChangeCandidate.source_feature_id.in_(source_feature_ids)
                    ),
                )
            )
            .with_for_update()
        )
        return result.scalars().all()

    async def analyze_import_geometry(
        self,
        db: AsyncSession,
        project_id: int,
        geometry_json: str,
    ) -> RowMapping | None:
        """验证候选几何有效性、省域包含关系并计算公顷面积。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            geometry_json: 标准 GeoJSON Polygon 文本。

        Returns:
            RowMapping | None: 几何校验和面积结果。
        """
        statement = text(
            """
            WITH candidate AS (
                SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326) AS geom
            ), province AS (
                SELECT geom
                FROM administrative_boundaries
                WHERE project_id = :project_id
                  AND boundary_level = 'province'
                LIMIT 1
            )
            SELECT
                ST_IsValid(candidate.geom) AS geometry_valid,
                ST_CoveredBy(candidate.geom, province.geom) AS within_project,
                ST_Area(candidate.geom::geography) / 10000.0 AS area_ha
            FROM candidate
            JOIN province ON TRUE
            """
        )
        result = await db.execute(
            statement,
            {"project_id": project_id, "geometry": geometry_json},
        )
        return result.mappings().one_or_none()

    async def insert_candidate(
        self,
        db: AsyncSession,
        values: dict[str, object],
    ) -> ChangeCandidate:
        """参数化新增一条已校验变化候选。

        Args:
            db: 异步数据库会话。
            values: 候选字段和 GeoJSON 几何。

        Returns:
            ChangeCandidate: 新增候选。
        """
        statement = text(
            """
            INSERT INTO change_candidates (
                run_id, candidate_code, source_name, source_uri,
                source_version, source_feature_id, source_checksum_sha256,
                import_batch_code, change_class, confidence, area_ha,
                evidence_uri, geom, status, imported_by, imported_by_code,
                imported_by_role, updated_at
            ) VALUES (
                :run_id, :candidate_code, :source_name, :source_uri,
                :source_version, :source_feature_id, :source_checksum_sha256,
                :import_batch_code, :change_class, :confidence, :area_ha,
                :evidence_uri,
                ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326),
                'pending', :imported_by, :imported_by_code,
                :imported_by_role, NOW()
            )
            RETURNING id
            """
        )
        result = await db.execute(statement, values)
        candidate_id = int(result.scalar_one())
        candidate = await db.get(ChangeCandidate, candidate_id)
        if candidate is None:
            raise RuntimeError("变化候选新增后无法读取")
        return candidate

    async def get_candidate_for_update(
        self,
        db: AsyncSession,
        run_id: int,
        candidate_code: str,
    ) -> ChangeCandidate | None:
        """锁定并查询检测任务内候选。

        Args:
            db: 异步数据库会话。
            run_id: 检测任务主键。
            candidate_code: 候选编号。

        Returns:
            ChangeCandidate | None: 已锁定候选。
        """
        result = await db.execute(
            select(ChangeCandidate)
            .where(
                ChangeCandidate.run_id == run_id,
                ChangeCandidate.candidate_code == candidate_code,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def count_candidate_statuses(
        self,
        db: AsyncSession,
        run_id: int,
    ) -> dict[str, int]:
        """按状态统计检测任务候选数量。

        Args:
            db: 异步数据库会话。
            run_id: 检测任务主键。

        Returns:
            dict[str, int]: 状态到数量的映射。
        """
        result = await db.execute(
            select(ChangeCandidate.status, func.count(ChangeCandidate.id))
            .where(ChangeCandidate.run_id == run_id)
            .group_by(ChangeCandidate.status)
        )
        return {str(status): int(count) for status, count in result.all()}

    async def add_event(
        self,
        db: AsyncSession,
        event: ChangeDetectionEvent,
    ) -> ChangeDetectionEvent:
        """写入不可变变化检测事件。

        Args:
            db: 异步数据库会话。
            event: 待写入事件。

        Returns:
            ChangeDetectionEvent: 已加入会话的事件。
        """
        db.add(event)
        await db.flush()
        return event
