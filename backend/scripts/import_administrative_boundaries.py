"""将版本化 GeoJSON 快照导入项目行政区划边界表。"""

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, async_engine

DEFAULT_SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "administrative_boundaries"
    / "heilongjiang_areas_v3_20260721.geojson"
)


def load_snapshot(path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """读取并校验行政区划 GeoJSON 快照。

    Args:
        path: GeoJSON 快照文件路径。

    Returns:
        tuple[dict[str, str], list[dict[str, Any]]]: 元数据和 Feature 列表。
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise ValueError("行政区划快照必须是 GeoJSON FeatureCollection")
    metadata = payload.get("metadata")
    features = payload.get("features")
    if not isinstance(metadata, dict) or not isinstance(features, list):
        raise ValueError("行政区划快照缺少 metadata 或 features")
    if not features:
        raise ValueError("行政区划快照不得为空")
    return metadata, features


async def ensure_boundary_schema(db: AsyncSession) -> None:
    """补齐旧开发数据库所需的行政区划字段。

    Args:
        db: 异步数据库会话。

    Returns:
        None: 无返回值。
    """
    statements = [
        "ALTER TABLE administrative_boundaries "
        "ADD COLUMN IF NOT EXISTS parent_code VARCHAR(50)",
        "ALTER TABLE administrative_boundaries "
        "ADD COLUMN IF NOT EXISTS source_name VARCHAR(120)",
        "ALTER TABLE administrative_boundaries "
        "ADD COLUMN IF NOT EXISTS source_uri VARCHAR(500)",
        "ALTER TABLE administrative_boundaries "
        "ADD COLUMN IF NOT EXISTS source_version VARCHAR(80)",
        "ALTER TABLE administrative_boundaries "
        "ADD COLUMN IF NOT EXISTS source_updated_at DATE",
        "ALTER TABLE administrative_boundaries "
        "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        "UPDATE administrative_boundaries SET source_name = '未标注历史数据' "
        "WHERE source_name IS NULL",
        "ALTER TABLE administrative_boundaries ALTER COLUMN source_name SET NOT NULL",
        "ALTER TABLE administrative_boundaries "
        "ALTER COLUMN geom TYPE GEOMETRY(MULTIPOLYGON, 4326) USING ST_Multi(geom)",
    ]
    for statement in statements:
        await db.execute(text(statement))


async def import_snapshot(
    db: AsyncSession,
    project_code: str,
    metadata: dict[str, str],
    features: list[dict[str, Any]],
) -> int:
    """以事务方式替换指定项目的全部行政区划边界。

    Args:
        db: 异步数据库会话。
        project_code: 监测项目编号。
        metadata: 快照数据来源信息。
        features: 待导入 GeoJSON Feature 列表。

    Returns:
        int: 成功导入的边界数量。
    """
    project_result = await db.execute(
        text("SELECT id FROM monitoring_projects WHERE project_code = :project_code"),
        {"project_code": project_code},
    )
    project_id = project_result.scalar_one_or_none()
    if project_id is None:
        raise ValueError(f"未找到项目 {project_code}")

    await db.execute(
        text("DELETE FROM administrative_boundaries WHERE project_id = :project_id"),
        {"project_id": project_id},
    )
    insert_statement = text(
        """
        INSERT INTO administrative_boundaries (
            project_id, boundary_code, boundary_name, boundary_level,
            parent_code, geom, source_name, source_uri, source_version,
            source_updated_at, updated_at
        ) VALUES (
            :project_id, :boundary_code, :boundary_name, :boundary_level,
            :parent_code,
            ST_Multi(
                ST_CollectionExtract(
                    ST_MakeValid(
                        ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326)
                    ),
                    3
                )
            ),
            :source_name, :source_uri, :source_version,
            :source_updated_at, NOW()
        )
        """
    )
    source_updated_at = date.fromisoformat(metadata["source_updated_at"])
    for feature in features:
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry")
        boundary_code = properties.get("adcode")
        boundary_name = properties.get("name")
        boundary_level = properties.get("level")
        if not boundary_code or not boundary_name or not boundary_level or not geometry:
            raise ValueError("行政区划 Feature 缺少编码、名称、级别或几何")
        parent = properties.get("parent") or {}
        await db.execute(
            insert_statement,
            {
                "project_id": project_id,
                "boundary_code": str(boundary_code),
                "boundary_name": boundary_name,
                "boundary_level": boundary_level,
                "parent_code": str(parent["adcode"]) if parent.get("adcode") else None,
                "geometry": json.dumps(geometry, separators=(",", ":")),
                "source_name": metadata["source_name"],
                "source_uri": metadata["source_uri"],
                "source_version": metadata["source_version"],
                "source_updated_at": source_updated_at,
            },
        )
    await db.commit()
    return len(features)


async def main() -> None:
    """解析命令行参数并执行行政区划快照导入。

    Args:
        无。

    Returns:
        None: 无返回值。
    """
    parser = argparse.ArgumentParser(description="导入行政区划 GeoJSON 快照")
    parser.add_argument("--project-code", default="RS-2026")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args()
    metadata, features = load_snapshot(args.snapshot)
    async with AsyncSessionLocal() as db:
        await ensure_boundary_schema(db)
        count = await import_snapshot(db, args.project_code, metadata, features)
    await async_engine.dispose()
    print(f"已导入 {count} 条真实行政区划边界")


if __name__ == "__main__":
    asyncio.run(main())
