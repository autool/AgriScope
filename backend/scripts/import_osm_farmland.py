"""导入带来源追踪的 OpenStreetMap 真实地类底块快照。"""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, async_engine

DEFAULT_SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "farmland"
    / "osm_heilongjiang_farmland_20260722.geojson"
)
DEMO_PLOT_CODES = ("HLJ-001", "HLJ-002", "HLJ-003", "HLJ-004", "HLJ-005")
OSM_LAND_CLASS_MAP = {
    "farmland": "耕地",
    "greenhouse_horticulture": "耕地",
    "allotments": "耕地",
    "orchard": "园地",
    "plant_nursery": "园地",
    "vineyard": "园地",
    "forest": "林地",
    "meadow": "草地",
    "grass": "草地",
    "reservoir": "水域",
    "basin": "水域",
    "residential": "建设用地",
    "commercial": "建设用地",
    "industrial": "建设用地",
    "construction": "建设用地",
    "farmyard": "建设用地",
}


def get_source_feature_id(properties: dict[str, Any]) -> str:
    """读取快照中稳定且可追溯的 OSM 来源要素编号。

    Args:
        properties: GeoJSON Feature 属性。

    Returns:
        str: `way/编号` 或 `relation/编号#part/序号`。
    """
    source_feature_id = str(properties.get("source_feature_id") or "").strip()
    if source_feature_id:
        return source_feature_id
    osm_way_id = str(properties.get("osm_way_id") or "").strip()
    return f"way/{osm_way_id}" if osm_way_id else ""


def get_plot_code(source_feature_id: str) -> str:
    """将 OSM 来源要素编号转换为稳定图斑业务编码。

    Args:
        source_feature_id: OSM 来源要素编号。

    Returns:
        str: 平台 `plot_code`。
    """
    if source_feature_id.startswith("way/"):
        return f"OSM-HLJ-{source_feature_id.removeprefix('way/')}"
    if source_feature_id.startswith("relation/"):
        relation_part = source_feature_id.removeprefix("relation/")
        relation_id, _, part_index = relation_part.partition("#part/")
        suffix = f"-P{part_index}" if part_index else ""
        return f"OSM-HLJ-R{relation_id}{suffix}"
    raise ValueError(f"不支持的 OSM 来源要素编号: {source_feature_id or '空值'}")


def load_snapshot(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """读取并校验真实地类底块 GeoJSON 快照。

    Args:
        path: GeoJSON 快照文件路径。

    Returns:
        tuple[dict[str, Any], list[dict[str, Any]]]: 元数据和 Feature 列表。
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise ValueError("真实地类底块快照必须是 GeoJSON FeatureCollection")
    metadata = payload.get("metadata")
    features = payload.get("features")
    if not isinstance(metadata, dict) or not isinstance(features, list):
        raise ValueError("真实地类底块快照缺少 metadata 或 features")
    if len(features) < 35000:
        raise ValueError("省级真实地类底块快照不得少于 35000 条")
    if int(metadata.get("city_count", 0)) < 13:
        raise ValueError("省级真实地类底块快照必须覆盖 13 个地级区域")
    if int(metadata.get("district_count", 0)) < 122:
        raise ValueError("省级真实地类底块快照必须覆盖 122 个县级区域")
    return metadata, features


def parse_osm_timestamp(value: object) -> datetime:
    """将 OSM UTC 时间文本转换为带时区的 datetime。

    Args:
        value: OSM Feature 中的时间值。

    Returns:
        datetime: 可直接绑定到 PostgreSQL TIMESTAMPTZ 的时间。
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("OSM Feature 缺少更新时间")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def map_osm_landuse_to_land_class(value: object) -> str:
    """将 OSM landuse 标签映射为平台一级地类。

    Args:
        value: OSM `landuse` 标签值。

    Returns:
        str: 平台使用的耕地、园地或草地。
    """
    landuse = str(value or "").strip()
    try:
        return OSM_LAND_CLASS_MAP[landuse]
    except KeyError as exc:
        raise ValueError(f"不支持的 OSM 地类类型: {landuse or '空值'}") from exc


async def ensure_plot_source_schema(db: AsyncSession) -> None:
    """补齐旧开发数据库的图斑来源追踪字段。

    Args:
        db: 异步数据库会话。

    Returns:
        None: 无返回值。
    """
    statements = [
        "ALTER TABLE farmland_plots "
        "ADD COLUMN IF NOT EXISTS source_name VARCHAR(120)",
        "ALTER TABLE farmland_plots "
        "ADD COLUMN IF NOT EXISTS source_feature_id VARCHAR(80)",
        "ALTER TABLE farmland_plots "
        "ADD COLUMN IF NOT EXISTS source_uri VARCHAR(500)",
        "ALTER TABLE farmland_plots "
        "ADD COLUMN IF NOT EXISTS source_version VARCHAR(80)",
        "ALTER TABLE farmland_plots "
        "ADD COLUMN IF NOT EXISTS source_updated_at TIMESTAMPTZ",
        "ALTER TABLE farmland_plots "
        "ADD COLUMN IF NOT EXISTS province_name VARCHAR(100)",
        "ALTER TABLE farmland_plots " "ADD COLUMN IF NOT EXISTS city_name VARCHAR(100)",
        "ALTER TABLE farmland_plots "
        "ADD COLUMN IF NOT EXISTS district_name VARCHAR(100)",
        "ALTER TABLE farmland_plots "
        "ADD COLUMN IF NOT EXISTS district_code VARCHAR(50)",
        "ALTER TABLE plot_versions "
        "ADD COLUMN IF NOT EXISTS created_by_code VARCHAR(50)",
        "ALTER TABLE plot_versions "
        "ADD COLUMN IF NOT EXISTS created_by_role VARCHAR(40)",
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "idx_farmland_plots_source_feature "
        "ON farmland_plots (source_name, source_feature_id) "
        "WHERE source_name IS NOT NULL AND source_feature_id IS NOT NULL",
    ]
    for statement in statements:
        await db.execute(text(statement))
    await db.execute(
        text(
            """
            UPDATE plot_versions
            SET created_by_code = CASE created_by
                    WHEN 'OpenStreetMap 数据导入程序' THEN 'system_osm_import'
                    WHEN '系统初始化' THEN 'system_init'
                    ELSE created_by_code
                END,
                created_by_role = 'system'
            WHERE created_by_code IS NULL
              AND created_by IN (
                  'OpenStreetMap 数据导入程序',
                  '系统初始化'
              )
            """
        )
    )


async def ensure_task_plot_schema(db: AsyncSession) -> None:
    """补齐任务图斑关联表，确保导入数据具有明确作业作用域。

    Args:
        db: 异步数据库会话。

    Returns:
        None: 无返回值。
    """
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS task_plots (
                id SERIAL PRIMARY KEY,
                task_id INTEGER NOT NULL
                    REFERENCES monitoring_tasks(id) ON DELETE CASCADE,
                plot_code VARCHAR(50) NOT NULL
                    REFERENCES farmland_plots(plot_code) ON DELETE CASCADE,
                assigned_by VARCHAR(100) NOT NULL,
                assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_task_plot UNIQUE (task_id, plot_code)
            )
            """
        )
    )
    await db.execute(
        text("CREATE INDEX IF NOT EXISTS idx_task_plots_task ON task_plots (task_id)")
    )
    await db.execute(
        text("CREATE INDEX IF NOT EXISTS idx_task_plots_plot ON task_plots (plot_code)")
    )
    await db.execute(
        text(
            "ALTER TABLE task_plots "
            "ADD COLUMN IF NOT EXISTS assigned_by_code VARCHAR(50)"
        )
    )
    await db.execute(
        text(
            "ALTER TABLE task_plots "
            "ADD COLUMN IF NOT EXISTS assigned_by_role VARCHAR(40)"
        )
    )
    await db.execute(
        text(
            """
            UPDATE task_plots
            SET assigned_by_code = CASE assigned_by
                    WHEN 'OpenStreetMap 数据导入程序' THEN 'system_osm_import'
                    WHEN '任务图斑作用域迁移' THEN 'system_task_scope_migration'
                    ELSE assigned_by_code
                END,
                assigned_by_role = 'system'
            WHERE assigned_by_code IS NULL
              AND assigned_by IN (
                  'OpenStreetMap 数据导入程序',
                  '任务图斑作用域迁移'
              )
            """
        )
    )


async def assign_active_plots_to_task(db: AsyncSession, task_code: str) -> int:
    """将当前有效地块纳入指定导入任务作用域。

    Args:
        db: 异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        int: 新增任务图斑关联数量。
    """
    result = await db.execute(
        text(
            """
            INSERT INTO task_plots (
                task_id, plot_code, assigned_by,
                assigned_by_code, assigned_by_role
            )
            SELECT task.id, plot.plot_code, 'OpenStreetMap 数据导入程序',
                   'system_osm_import', 'system'
            FROM monitoring_tasks AS task
            JOIN farmland_plots AS plot
              ON plot.interpretation_status != 'deleted'
            WHERE task.task_code = :task_code
            ON CONFLICT (task_id, plot_code) DO NOTHING
            """
        ),
        {"task_code": task_code},
    )
    return int(result.rowcount or 0)


async def remove_demo_plots(db: AsyncSession) -> int:
    """删除旧版五条规则矩形演示图斑及其引用。

    Args:
        db: 异步数据库会话。

    Returns:
        int: 实际删除的演示图斑数量。
    """
    deleted = 0
    for plot_code in DEMO_PLOT_CODES:
        await db.execute(
            text(
                """
                UPDATE field_verifications
                SET matched_plot_code = NULL,
                    offset_distance_m = NULL,
                    match_status = 'pending',
                    updated_at = NOW()
                WHERE matched_plot_code = :plot_code
                """
            ),
            {"plot_code": plot_code},
        )
        result = await db.execute(
            text("DELETE FROM farmland_plots WHERE plot_code = :plot_code"),
            {"plot_code": plot_code},
        )
        deleted += int(result.rowcount or 0)
    return deleted


async def remove_legacy_osm_plots(db: AsyncSession) -> int:
    """清理本轮开发产生的旧哈尔滨前缀 OSM 图斑。

    Args:
        db: 异步数据库会话。

    Returns:
        int: 清理的旧前缀图斑数量。
    """
    await db.execute(
        text(
            """
            UPDATE field_verifications
            SET matched_plot_code = NULL,
                offset_distance_m = NULL,
                match_status = 'pending',
                updated_at = NOW()
            WHERE matched_plot_code LIKE 'OSM-HRB-%'
            """
        )
    )
    result = await db.execute(
        text(
            """
            DELETE FROM farmland_plots
            WHERE plot_code LIKE 'OSM-HRB-%'
              AND source_name = 'OpenStreetMap'
            """
        )
    )
    return int(result.rowcount or 0)


async def import_features(
    db: AsyncSession,
    metadata: dict[str, Any],
    features: list[dict[str, Any]],
) -> int:
    """同步 OSM 农业面并为新图斑创建不可变初始版本。

    Args:
        db: 异步数据库会话。
        metadata: 快照来源元数据。
        features: GeoJSON 真实地类底块 Feature 列表。

    Returns:
        int: 本次同步图斑数量。
    """
    insert_statement = text(
        """
        WITH candidate AS (
            SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326) AS geom
        ), district_match AS (
            SELECT boundary_code, boundary_name, parent_code
            FROM administrative_boundaries AS boundary, candidate
            WHERE boundary.boundary_level = 'district'
              AND ST_Covers(
                  boundary.geom,
                  ST_PointOnSurface(candidate.geom)
              )
            ORDER BY ST_Area(boundary.geom::geography)
            LIMIT 1
        ), city_match AS (
            SELECT boundary_name
            FROM administrative_boundaries
            WHERE boundary_code = (SELECT parent_code FROM district_match)
        )
        INSERT INTO farmland_plots (
            plot_code, owner_village, area_ha, geom, land_class, crop_type,
            planting_mode, irrigation_condition, interpretation_status,
            version, updated_at, source_name, source_feature_id, source_uri,
            source_version, source_updated_at, province_name, city_name,
            district_name, district_code
        )
        SELECT
            :plot_code,
            COALESCE(
                NULLIF(:feature_name, ''),
                district_match.boundary_name || '（OSM未标注村名）'
            ),
            ROUND((ST_Area(candidate.geom::geography) / 10000.0)::numeric, 4),
            candidate.geom,
            :land_class, NULL, NULL, NULL, 'interpreting', 1, NOW(),
            :source_name, :source_feature_id, :source_uri, :source_version,
            CAST(:source_updated_at AS TIMESTAMPTZ), '黑龙江省',
            city_match.boundary_name, district_match.boundary_name,
            district_match.boundary_code
        FROM candidate
        JOIN district_match ON TRUE
        JOIN city_match ON TRUE
        WHERE ST_IsValid(candidate.geom)
          AND ST_Area(candidate.geom::geography) > 0
        ON CONFLICT (plot_code) DO UPDATE SET
            owner_village = EXCLUDED.owner_village,
            source_name = EXCLUDED.source_name,
            source_feature_id = EXCLUDED.source_feature_id,
            source_uri = EXCLUDED.source_uri,
            source_version = EXCLUDED.source_version,
            source_updated_at = EXCLUDED.source_updated_at,
            province_name = EXCLUDED.province_name,
            city_name = EXCLUDED.city_name,
            district_name = EXCLUDED.district_name,
            district_code = EXCLUDED.district_code,
            land_class = EXCLUDED.land_class,
            updated_at = NOW()
        RETURNING plot_code
        """
    )
    version_statement = text(
        """
        INSERT INTO plot_versions (
            plot_code, version, land_class, crop_type, planting_mode,
            irrigation_condition, interpretation_status, geom,
            change_summary, created_by, created_by_code, created_by_role
        )
        SELECT
            plot_code, version, land_class, crop_type, planting_mode,
            irrigation_condition, interpretation_status, geom,
            '导入 OpenStreetMap 真实地类底块边界',
            'OpenStreetMap 数据导入程序', 'system_osm_import', 'system'
        FROM farmland_plots
        WHERE plot_code = :plot_code
        ON CONFLICT (plot_code, version) DO NOTHING
        """
    )
    synchronized = 0
    for feature in features:
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry")
        source_feature_id = get_source_feature_id(properties)
        source_uri = str(properties.get("source_uri") or "").strip()
        if not source_feature_id or not geometry or geometry.get("type") != "Polygon":
            raise ValueError("真实地类底块 Feature 缺少 OSM 来源编号或 Polygon 几何")
        source_element_id = source_feature_id.split("#part/", maxsplit=1)[0]
        expected_source_uri = f"https://www.openstreetmap.org/{source_element_id}"
        if source_uri != expected_source_uri:
            raise ValueError(f"OSM 要素 {source_feature_id} 缺少可追溯来源链接")
        plot_code = get_plot_code(source_feature_id)
        result = await db.execute(
            insert_statement,
            {
                "plot_code": plot_code,
                "feature_name": str(properties.get("name") or ""),
                "geometry": json.dumps(geometry, separators=(",", ":")),
                "land_class": map_osm_landuse_to_land_class(properties.get("landuse")),
                "source_name": metadata["source_name"],
                "source_feature_id": source_feature_id,
                "source_uri": source_uri,
                "source_version": str(properties.get("osm_version") or ""),
                "source_updated_at": parse_osm_timestamp(
                    properties.get("osm_timestamp")
                ),
            },
        )
        if result.scalar_one_or_none() is None:
            continue
        synchronized += 1
        await db.execute(version_statement, {"plot_code": plot_code})
    return synchronized


async def refresh_task_summary(db: AsyncSession, task_code: str) -> None:
    """按当前有效图斑重算工作任务概要并记录来源导入审计。

    Args:
        db: 异步数据库会话。
        task_code: 需要更新的作业任务编号。

    Returns:
        None: 无返回值。
    """
    coverage_result = await db.execute(
        text(
            """
            SELECT
                COUNT(*) AS plot_count,
                COUNT(DISTINCT city_name) AS city_count,
                COUNT(DISTINCT district_code) AS district_count
            FROM task_plots AS scope
            JOIN monitoring_tasks AS task ON task.id = scope.task_id
            JOIN farmland_plots AS plot ON plot.plot_code = scope.plot_code
            WHERE task.task_code = :task_code
              AND plot.interpretation_status != 'deleted'
            """
        ),
        {"task_code": task_code},
    )
    coverage = coverage_result.one()
    coverage_text = (
        f"13 个地级区域、122 个县区全量行政层级；"
        f"OSM 底块覆盖 {coverage.city_count} 个地级区域 "
        f"{coverage.district_count} 个县区"
    )
    import_comment = (
        f"同步 {coverage.plot_count} 条可追溯 OpenStreetMap 真实地类底块边界，"
        f"覆盖 {coverage.city_count} 个地级区域 "
        f"{coverage.district_count} 个县区"
    )
    await db.execute(
        text(
            """
            UPDATE monitoring_tasks
            SET task_name = '黑龙江省全域分级农业用地解译作业单元',
                administrative_region = :coverage_text,
                status = 'interpreting',
                total_plots = (
                    SELECT COUNT(*)
                    FROM task_plots AS scope
                    JOIN farmland_plots AS plot
                      ON plot.plot_code = scope.plot_code
                    WHERE scope.task_id = monitoring_tasks.id
                      AND plot.interpretation_status != 'deleted'
                ),
                completed_plots = (
                    SELECT COUNT(*)
                    FROM task_plots AS scope
                    JOIN farmland_plots AS plot
                      ON plot.plot_code = scope.plot_code
                    WHERE scope.task_id = monitoring_tasks.id
                      AND plot.interpretation_status = 'interpreted'
                ),
                quality_score = NULL,
                updated_at = NOW()
            WHERE task_code = :task_code
            """
        ),
        {"task_code": task_code, "coverage_text": coverage_text},
    )
    await db.execute(
        text(
            """
            DELETE FROM review_records
            WHERE task_id = (
                SELECT id FROM monitoring_tasks WHERE task_code = :task_code
            )
              AND action = 'attribute_updated'
              AND comment = '完成首批地块属性批量赋值'
            """
        ),
        {"task_code": task_code},
    )
    await db.execute(
        text(
            """
            INSERT INTO review_records (
                task_id, review_level, action, reviewer,
                reviewer_code, reviewer_role, comment
            )
            SELECT
                id, 'interpretation', 'plot_source_imported',
                'OpenStreetMap 数据导入程序',
                'system_osm_import', 'system',
                :import_comment
            FROM monitoring_tasks
            WHERE task_code = :task_code
            """
        ),
        {"task_code": task_code, "import_comment": import_comment},
    )


async def invalidate_task_quality_evidence(
    db: AsyncSession,
    task_code: str,
) -> tuple[int, int]:
    """底块快照重载后失效旧自动质检问题和派生检查结果。

    人工审核问题和外业核查问题属于独立业务证据，必须保留；这里只关闭
    `source=auto` 且 `issue_type=quality_rule` 的开放问题，并删除可重算的
    `plot_quality_checks` 当前态记录。完整执行历史仍保存在审核日志中。

    Args:
        db: 异步数据库会话。
        task_code: 已重载底块快照的任务编号。

    Returns:
        tuple[int, int]: 删除的检查结果数量和关闭的自动问题数量。
    """
    resolved_result = await db.execute(
        text(
            """
            UPDATE quality_issues
            SET status = 'resolved',
                resolved_at = NOW(),
                resolved_by = 'OpenStreetMap 数据导入程序',
                resolved_by_code = 'system_osm_import',
                resolved_by_role = 'system',
                resolution_comment = '底块快照已重载，旧自动质检证据失效'
            WHERE task_id = (
                SELECT id FROM monitoring_tasks WHERE task_code = :task_code
            )
              AND source = 'auto'
              AND issue_type = 'quality_rule'
              AND status = 'open'
            """
        ),
        {"task_code": task_code},
    )
    removed_result = await db.execute(
        text(
            """
            DELETE FROM plot_quality_checks
            WHERE task_id = (
                SELECT id FROM monitoring_tasks WHERE task_code = :task_code
            )
            """
        ),
        {"task_code": task_code},
    )
    removed_checks = int(removed_result.rowcount or 0)
    resolved_issues = int(resolved_result.rowcount or 0)
    if removed_checks or resolved_issues:
        await db.execute(
            text(
                """
                INSERT INTO review_records (
                    task_id, review_level, action, reviewer,
                    reviewer_code, reviewer_role, comment
                )
                SELECT
                    id, 'quality', 'quality_evidence_invalidated',
                    'OpenStreetMap 数据导入程序',
                    'system_osm_import', 'system', :comment
                FROM monitoring_tasks
                WHERE task_code = :task_code
                """
            ),
            {
                "task_code": task_code,
                "comment": (
                    f"底块快照重载后删除 {removed_checks} 条旧检查结果，"
                    f"关闭 {resolved_issues} 条旧自动质量问题；"
                    "人工审核和外业问题保持不变"
                ),
            },
        )
    return removed_checks, resolved_issues


async def main() -> None:
    """解析参数并以单个事务导入真实地类底块快照。

    Args:
        无。

    Returns:
        None: 无返回值。
    """
    parser = argparse.ArgumentParser(description="导入 OSM 真实地类底块 GeoJSON 快照")
    parser.add_argument("--task-code", default="RS-2026-045")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args()
    metadata, features = load_snapshot(args.snapshot)
    async with AsyncSessionLocal() as db:
        await ensure_plot_source_schema(db)
        await ensure_task_plot_schema(db)
        removed = await remove_demo_plots(db)
        removed_legacy = await remove_legacy_osm_plots(db)
        synchronized = await import_features(db, metadata, features)
        assigned = await assign_active_plots_to_task(db, args.task_code)
        await refresh_task_summary(db, args.task_code)
        removed_checks, resolved_issues = await invalidate_task_quality_evidence(
            db,
            args.task_code,
        )
        await db.commit()
    await async_engine.dispose()
    print(
        f"已删除 {removed} 条规则矩形演示图斑，"
        f"清理 {removed_legacy} 条旧前缀图斑，"
        f"同步 {synchronized} 条 OpenStreetMap 真实地类底块，"
        f"新增 {assigned} 条任务图斑关联，"
        f"删除 {removed_checks} 条旧质量检查结果，"
        f"关闭 {resolved_issues} 条旧自动质量问题"
    )


if __name__ == "__main__":
    asyncio.run(main())
