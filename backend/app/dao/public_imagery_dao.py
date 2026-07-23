"""公开影像 STAC 足迹联合覆盖分析数据访问。"""

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PublicImageryItemCoverage:
    """一个 STAC 足迹对查询范围的权威覆盖结果。"""

    index: int
    coverage_ratio: float
    fully_covers_query: bool
    geometry_valid: bool


@dataclass(frozen=True)
class PublicImageryCoverageAnalysis:
    """多景 STAC 足迹对查询范围的联合覆盖结果。"""

    items: tuple[PublicImageryItemCoverage, ...]
    union_coverage_ratio: float
    union_covers_query: bool


class PublicImageryDAO:
    """使用 PostGIS 分析公开 STAC Polygon 足迹的真实联合覆盖。"""

    async def analyze_query_coverage(
        self,
        db: AsyncSession,
        query_bbox: tuple[float, float, float, float],
        geometries: list[dict[str, object]],
    ) -> PublicImageryCoverageAnalysis:
        """计算逐景及多景联合足迹对查询矩形的覆盖比例。

        STAC 足迹可能是倾斜的 Polygon/MultiPolygon，不能用 bbox 并集冒充
        实际覆盖。本查询先验证并修复用于面积运算的多边形，再以 geography
        面积计算比例，同时保留原始几何有效性作为业务门禁证据。

        Args:
            db: 异步数据库会话。
            query_bbox: WGS84 左、下、右、上坐标。
            geometries: 与候选顺序一致的 GeoJSON Polygon/MultiPolygon。

        Returns:
            PublicImageryCoverageAnalysis: 逐景和联合覆盖结果。
        """
        left, bottom, right, top = query_bbox
        result = await db.execute(
            text(
                """
                WITH query_scope AS (
                    SELECT ST_MakeEnvelope(
                        :left,
                        :bottom,
                        :right,
                        :top,
                        4326
                    ) AS geom
                ),
                raw_items AS (
                    SELECT
                        (entry.ordinality - 1)::integer AS item_index,
                        ST_SetSRID(
                            ST_GeomFromGeoJSON(entry.value ->> 'geometry'),
                            4326
                        ) AS source_geom
                    FROM jsonb_array_elements(
                        CAST(:items_json AS jsonb)
                    ) WITH ORDINALITY AS entry(value, ordinality)
                ),
                normalized_items AS (
                    SELECT
                        item_index,
                        ST_IsValid(source_geom) AS geometry_valid,
                        ST_CollectionExtract(
                            ST_MakeValid(source_geom),
                            3
                        ) AS geom
                    FROM raw_items
                ),
                item_metrics AS (
                    SELECT
                        item.item_index,
                        item.geometry_valid,
                        ST_Covers(item.geom, query.geom)
                            AS fully_covers_query,
                        LEAST(
                            1.0,
                            COALESCE(
                                ST_Area(
                                    ST_Intersection(
                                        item.geom,
                                        query.geom
                                    )::geography
                                ) / NULLIF(
                                    ST_Area(query.geom::geography),
                                    0
                                ),
                                0
                            )
                        ) AS coverage_ratio,
                        ST_Intersection(item.geom, query.geom) AS clipped_geom
                    FROM normalized_items AS item
                    CROSS JOIN query_scope AS query
                ),
                union_geometry AS (
                    SELECT ST_UnaryUnion(
                        ST_Collect(clipped_geom)
                    ) AS geom
                    FROM item_metrics
                ),
                union_metrics AS (
                    SELECT
                        COALESCE(
                            ST_Covers(union_geometry.geom, query.geom),
                            FALSE
                        ) AS union_covers_query,
                        LEAST(
                            1.0,
                            COALESCE(
                                ST_Area(
                                    ST_Intersection(
                                        union_geometry.geom,
                                        query.geom
                                    )::geography
                                ) / NULLIF(
                                    ST_Area(query.geom::geography),
                                    0
                                ),
                                0
                            )
                        ) AS union_coverage_ratio
                    FROM union_geometry
                    CROSS JOIN query_scope AS query
                )
                SELECT
                    item.item_index,
                    item.coverage_ratio,
                    item.fully_covers_query,
                    item.geometry_valid,
                    union_metrics.union_coverage_ratio,
                    union_metrics.union_covers_query
                FROM item_metrics AS item
                CROSS JOIN union_metrics
                ORDER BY item.item_index
                """
            ),
            {
                "left": left,
                "bottom": bottom,
                "right": right,
                "top": top,
                "items_json": json.dumps(
                    [{"geometry": geometry} for geometry in geometries],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        )
        rows = list(result.mappings().all())
        if not rows:
            return PublicImageryCoverageAnalysis(
                items=(),
                union_coverage_ratio=0,
                union_covers_query=False,
            )
        return PublicImageryCoverageAnalysis(
            items=tuple(
                PublicImageryItemCoverage(
                    index=int(row["item_index"]),
                    coverage_ratio=float(row["coverage_ratio"] or 0),
                    fully_covers_query=bool(row["fully_covers_query"]),
                    geometry_valid=bool(row["geometry_valid"]),
                )
                for row in rows
            ),
            union_coverage_ratio=float(rows[0]["union_coverage_ratio"] or 0),
            union_covers_query=bool(rows[0]["union_covers_query"]),
        )
