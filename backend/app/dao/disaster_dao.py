"""灾害斑块监测数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import func, or_, select, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workbench import DisasterPatch


class DisasterDAO:
    """封装灾害斑块空间查询与更新。"""

    async def get_patches(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[tuple[DisasterPatch, str]]:
        """查询任务灾害斑块及 GeoJSON 几何。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[tuple[DisasterPatch, str]]: 灾害对象和 GeoJSON 字符串。
        """
        result = await db.execute(
            select(
                DisasterPatch,
                func.ST_AsGeoJSON(DisasterPatch.geom).label("geometry"),
            )
            .where(DisasterPatch.task_id == task_id)
            .order_by(DisasterPatch.detected_at.desc(), DisasterPatch.patch_code)
        )
        return result.tuples().all()

    async def get_patch_by_code(
        self,
        db: AsyncSession,
        patch_code: str,
    ) -> DisasterPatch | None:
        """按编号查询灾害斑块。

        Args:
            db: 异步数据库会话。
            patch_code: 灾害斑块编号。

        Returns:
            DisasterPatch | None: 灾害斑块，不存在时返回 None。
        """
        result = await db.execute(
            select(DisasterPatch).where(DisasterPatch.patch_code == patch_code)
        )
        return result.scalar_one_or_none()

    async def get_patch_by_code_for_update(
        self,
        db: AsyncSession,
        patch_code: str,
    ) -> DisasterPatch | None:
        """锁定并查询待人工复核的灾害斑块。

        Args:
            db: 异步数据库会话。
            patch_code: 灾害斑块编号。

        Returns:
            DisasterPatch | None: 已锁定斑块；不存在时返回 None。
        """
        result = await db.execute(
            select(DisasterPatch)
            .where(DisasterPatch.patch_code == patch_code)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_patch_geometry(
        self,
        db: AsyncSession,
        patch_code: str,
    ) -> str:
        """读取灾害斑块 GeoJSON 几何。

        Args:
            db: 异步数据库会话。
            patch_code: 灾害斑块编号。

        Returns:
            str: GeoJSON 几何字符串。
        """
        result = await db.execute(
            select(func.ST_AsGeoJSON(DisasterPatch.geom)).where(
                DisasterPatch.patch_code == patch_code
            )
        )
        return str(result.scalar_one())

    async def get_conflicting_patches_for_update(
        self,
        db: AsyncSession,
        task_id: int,
        patch_codes: list[str],
        source_name: str,
        source_feature_ids: list[str],
    ) -> Sequence[DisasterPatch]:
        """锁定编号或来源要素与导入批次冲突的灾害斑块。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            patch_codes: 待导入斑块编号。
            source_name: 模型来源名称。
            source_feature_ids: 模型来源要素编号。

        Returns:
            Sequence[DisasterPatch]: 已锁定的冲突斑块。
        """
        result = await db.execute(
            select(DisasterPatch)
            .where(
                DisasterPatch.task_id == task_id,
                or_(
                    DisasterPatch.patch_code.in_(patch_codes),
                    (
                        (DisasterPatch.source == source_name)
                        & DisasterPatch.source_feature_id.in_(source_feature_ids)
                    ),
                ),
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
        """校验灾害 Polygon 并计算椭球面积及省域包含关系。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            geometry_json: WGS84 GeoJSON Polygon 字符串。

        Returns:
            RowMapping | None: 几何有效性、省域包含状态和公顷面积。
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

    async def insert_imported_patch(
        self,
        db: AsyncSession,
        values: dict[str, object],
    ) -> DisasterPatch:
        """新增一条已校验的灾害模型斑块。

        Args:
            db: 异步数据库会话。
            values: 参数化插入字段和 GeoJSON 几何。

        Returns:
            DisasterPatch: 新增灾害斑块。
        """
        statement = text(
            """
            INSERT INTO disaster_patches (
                task_id, patch_code, disaster_type, severity,
                affected_area_ha, crop_type, detected_at, ndvi_change,
                status, source, source_uri, source_version,
                source_feature_id, source_checksum_sha256,
                import_batch_code, imported_by, imported_by_code,
                imported_by_role, geom, updated_at
            ) VALUES (
                :task_id, :patch_code, :disaster_type, :severity,
                :affected_area_ha, :crop_type, :detected_at, :ndvi_change,
                'pending', :source, :source_uri, :source_version,
                :source_feature_id, :source_checksum_sha256,
                :import_batch_code, :imported_by, :imported_by_code,
                :imported_by_role,
                ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326), NOW()
            )
            RETURNING id
            """
        )
        result = await db.execute(statement, values)
        patch_id = int(result.scalar_one())
        patch = await db.get(DisasterPatch, patch_id)
        if patch is None:
            raise RuntimeError("灾害斑块新增后无法读取")
        return patch

    async def replace_imported_patch(
        self,
        db: AsyncSession,
        patch_id: int,
        values: dict[str, object],
    ) -> DisasterPatch:
        """以新模型证据替换同编号灾害斑块并重置人工复核。

        Args:
            db: 异步数据库会话。
            patch_id: 待替换斑块主键。
            values: 参数化更新字段和 GeoJSON 几何。

        Returns:
            DisasterPatch: 替换后的灾害斑块。
        """
        statement = text(
            """
            UPDATE disaster_patches
            SET disaster_type = :disaster_type,
                severity = :severity,
                affected_area_ha = :affected_area_ha,
                crop_type = :crop_type,
                detected_at = :detected_at,
                ndvi_change = :ndvi_change,
                status = 'pending',
                source = :source,
                source_uri = :source_uri,
                source_version = :source_version,
                source_feature_id = :source_feature_id,
                source_checksum_sha256 = :source_checksum_sha256,
                import_batch_code = :import_batch_code,
                imported_by = :imported_by,
                imported_by_code = :imported_by_code,
                imported_by_role = :imported_by_role,
                reviewed_by = NULL,
                reviewed_by_code = NULL,
                reviewed_by_role = NULL,
                review_comment = NULL,
                reviewed_at = NULL,
                geom = ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326),
                updated_at = NOW()
            WHERE id = :patch_id
            RETURNING id
            """
        )
        result = await db.execute(statement, {**values, "patch_id": patch_id})
        updated_id = int(result.scalar_one())
        db.expire_all()
        patch = await db.get(DisasterPatch, updated_id)
        if patch is None:
            raise RuntimeError("灾害斑块替换后无法读取")
        return patch
