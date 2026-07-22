"""OpenStreetMap 农业地块快照与导入规则测试。"""

import asyncio
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock

from scripts.fetch_osm_farmland_snapshot import to_snapshot_feature
from scripts.import_osm_farmland import (
    DEFAULT_SNAPSHOT,
    DEMO_PLOT_CODES,
    get_plot_code,
    get_source_feature_id,
    invalidate_task_quality_evidence,
    load_snapshot,
    map_osm_landuse_to_land_class,
    parse_osm_timestamp,
    refresh_task_summary,
)


def test_snapshot_reload_invalidates_only_derived_quality_evidence() -> None:
    """验证底块重载会清理可重算质检证据并保留其他问题类型。"""
    db = AsyncMock()
    db.execute.side_effect = [
        SimpleNamespace(rowcount=2458),
        SimpleNamespace(rowcount=809),
        SimpleNamespace(rowcount=1),
    ]

    result = asyncio.run(invalidate_task_quality_evidence(db, "RS-2026-045"))

    assert result == (809, 2458)
    assert db.execute.await_count == 3
    statements = [str(call.args[0]) for call in db.execute.await_args_list]
    assert "source = 'auto'" in statements[0]
    assert "issue_type = 'quality_rule'" in statements[0]
    assert "DELETE FROM plot_quality_checks" in statements[1]
    assert "quality_evidence_invalidated" in statements[2]


def test_snapshot_reload_does_not_duplicate_empty_invalidation_audit() -> None:
    """验证重复导入且无旧证据时不会生成空清理审计。"""
    db = AsyncMock()
    db.execute.side_effect = [
        SimpleNamespace(rowcount=0),
        SimpleNamespace(rowcount=0),
    ]

    result = asyncio.run(invalidate_task_quality_evidence(db, "RS-2026-045"))

    assert result == (0, 0)
    assert db.execute.await_count == 2


def test_snapshot_reload_appends_immutable_cycle_audit() -> None:
    """验证每次底块重载追加审计而不是覆盖旧导入记录。"""
    coverage_result = SimpleNamespace(
        one=lambda: SimpleNamespace(
            plot_count=22092,
            city_count=13,
            district_count=122,
        )
    )
    db = AsyncMock()
    db.execute.side_effect = [
        coverage_result,
        SimpleNamespace(rowcount=1),
        SimpleNamespace(rowcount=0),
        SimpleNamespace(rowcount=1),
    ]

    asyncio.run(refresh_task_summary(db, "RS-2026-045"))

    statements = [str(call.args[0]) for call in db.execute.await_args_list]
    assert db.execute.await_count == 4
    assert not any("UPDATE review_records" in statement for statement in statements)
    assert "INSERT INTO review_records" in statements[-1]
    assert "system_osm_import" in statements[-1]


def test_osm_snapshot_contains_traceable_polygon_features() -> None:
    """验证快照数量、边界结构和 OSM 来源链接满足交付约束。"""
    metadata, features = load_snapshot(DEFAULT_SNAPSHOT)

    assert metadata["source_name"] == "OpenStreetMap"
    assert metadata["license"] == "ODbL 1.0"
    assert metadata["city_count"] == 13
    assert metadata["district_count"] == 122
    assert len(features) >= 35000
    assert metadata["feature_count"] == len(features)
    assert metadata["administrative_scope"] == "黑龙江省 13 个地级区域、122 个县级区域"
    source_feature_ids = [
        get_source_feature_id(feature["properties"]) for feature in features
    ]
    assert len(source_feature_ids) == len(set(source_feature_ids))
    for feature in features:
        geometry = feature["geometry"]
        properties = feature["properties"]
        assert geometry["type"] == "Polygon"
        assert len(geometry["coordinates"][0]) >= 5
        assert geometry["coordinates"][0][0] == geometry["coordinates"][0][-1]
        assert 0.05 <= properties["source_area_ha"] <= 500
        source_element_id = get_source_feature_id(properties).split(
            "#part/",
            maxsplit=1,
        )[0]
        assert properties["source_uri"] == (
            f"https://www.openstreetmap.org/{source_element_id}"
        )
        assert properties["osm_version"]
        assert properties["osm_timestamp"]
        assert properties["province_name"] == "黑龙江省"
        assert properties["city_name"]
        assert properties["district_name"]
        assert properties["district_code"]
        assert properties["landuse"] in {
            "farmland",
            "greenhouse_horticulture",
            "orchard",
            "plant_nursery",
            "meadow",
            "allotments",
            "vineyard",
            "forest",
            "grass",
            "reservoir",
            "basin",
            "residential",
            "commercial",
            "industrial",
            "construction",
            "farmyard",
        }


def test_osm_timestamp_is_bound_as_timezone_aware_datetime() -> None:
    """验证 OSM 时间可安全绑定到 PostgreSQL TIMESTAMPTZ。"""
    parsed = parse_osm_timestamp("2023-07-08T14:53:58Z")

    assert parsed.tzinfo == UTC
    assert parsed.isoformat() == "2023-07-08T14:53:58+00:00"


def test_obsolete_rectangle_codes_are_explicitly_scoped() -> None:
    """验证清理范围只包含用户要求移除的五条演示数据。"""
    assert DEMO_PLOT_CODES == (
        "HLJ-001",
        "HLJ-002",
        "HLJ-003",
        "HLJ-004",
        "HLJ-005",
    )


def test_osm_agricultural_landuses_map_to_real_land_classes() -> None:
    """验证农业用地标签不会在导入时全部冒充耕地。"""
    assert map_osm_landuse_to_land_class("farmland") == "耕地"
    assert map_osm_landuse_to_land_class("greenhouse_horticulture") == "耕地"
    assert map_osm_landuse_to_land_class("allotments") == "耕地"
    assert map_osm_landuse_to_land_class("orchard") == "园地"
    assert map_osm_landuse_to_land_class("plant_nursery") == "园地"
    assert map_osm_landuse_to_land_class("vineyard") == "园地"
    assert map_osm_landuse_to_land_class("forest") == "林地"
    assert map_osm_landuse_to_land_class("meadow") == "草地"
    assert map_osm_landuse_to_land_class("grass") == "草地"
    assert map_osm_landuse_to_land_class("reservoir") == "水域"
    assert map_osm_landuse_to_land_class("basin") == "水域"
    assert map_osm_landuse_to_land_class("residential") == "建设用地"
    assert map_osm_landuse_to_land_class("commercial") == "建设用地"
    assert map_osm_landuse_to_land_class("industrial") == "建设用地"
    assert map_osm_landuse_to_land_class("construction") == "建设用地"
    assert map_osm_landuse_to_land_class("farmyard") == "建设用地"


def test_osm_source_ids_generate_stable_plot_codes() -> None:
    """验证 way 与 relation 多面分片生成稳定且不冲突的图斑编码。"""
    assert get_plot_code("way/123") == "OSM-HLJ-123"
    assert get_plot_code("relation/456") == "OSM-HLJ-R456"
    assert get_plot_code("relation/456#part/3") == "OSM-HLJ-R456-P3"


def test_relation_multipolygon_is_split_into_traceable_polygon_parts() -> None:
    """验证 OSM relation 多面按真实组成面拆分且保留同一来源链。"""
    district = {
        "properties": {
            "name": "测试县",
            "adcode": 230101,
            "parent": {"adcode": 230100},
        }
    }
    feature = {
        "properties": {
            "@osmId": "relation/456",
            "@version": 2,
            "@lastEdit": "2025-01-02T03:04:05Z",
            "@changesetId": 789,
            "@user": "tester",
            "landuse": "farmland",
        },
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [
                        [126.0, 45.0],
                        [126.002, 45.0],
                        [126.002, 45.002],
                        [126.0, 45.002],
                        [126.0, 45.0],
                    ]
                ],
                [
                    [
                        [126.01, 45.01],
                        [126.012, 45.01],
                        [126.012, 45.012],
                        [126.01, 45.012],
                        [126.01, 45.01],
                    ]
                ],
            ],
        },
    }

    converted = to_snapshot_feature(feature, district, {"230100": "测试市"})

    assert len(converted) == 2
    assert {item["geometry"]["type"] for item in converted} == {"Polygon"}
    assert {item["properties"]["source_feature_id"] for item in converted} == {
        "relation/456#part/1",
        "relation/456#part/2",
    }
    assert {item["properties"]["source_uri"] for item in converted} == {
        "https://www.openstreetmap.org/relation/456"
    }
