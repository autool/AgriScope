"""从 ohsome API 补充黑龙江省可追溯 OpenStreetMap 真实地类底块快照。"""

import argparse
import asyncio
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import httpx

BOUNDARY_SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "administrative_boundaries"
    / "heilongjiang_areas_v3_20260721.geojson"
)
DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "farmland"
    / "osm_heilongjiang_farmland_20260722.geojson"
)
OHSOME_GEOMETRY_URL = "https://api.ohsome.org/v1/elements/geometry"
OHSOME_CENTROID_URL = "https://api.ohsome.org/v1/elements/centroid"
OHSOME_SNAPSHOT_TIME = "2026-06-19"
LAND_PARCEL_LANDUSES = (
    "farmland",
    "orchard",
    "meadow",
    "greenhouse_horticulture",
    "plant_nursery",
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
)
LAND_PARCEL_FILTER = (
    "landuse in (farmland,orchard,meadow,greenhouse_horticulture,"
    "plant_nursery,allotments,vineyard,forest,grass,reservoir,basin,"
    "residential,commercial,industrial,construction,farmyard) "
    "and geometry:polygon"
)
REQUEST_CONCURRENCY = 5
GEOMETRY_IDENTIFIER_BATCH_SIZE = 120
# 以下 OSM 面的 ohsome centroid 位于县界内，但 PostGIS ST_PointOnSurface
# 落在项目县界快照外。为确保快照条数与可确定归属的落库条数一致，显式排除。
EXCLUDED_OSM_ELEMENT_KEYS = {
    "way/1071872882",
    "way/126462917",
    "way/1361165521",
    "way/1485146502",
    "way/1485593214",
    "way/1485605579",
    "way/1485834940",
    "way/150162457",
    "way/674566800",
    "way/909373992",
    "relation/20602112",
}


def get_osm_element_key(properties: dict[str, Any]) -> str:
    """读取快照要素稳定的 OSM 元素键。

    Args:
        properties: OSM 或项目快照属性。

    Returns:
        str: `way/编号` 或 `relation/编号`；无法识别时返回空字符串。
    """
    source_feature_id = str(properties.get("source_feature_id") or "")
    if source_feature_id:
        return source_feature_id.split("#part/", maxsplit=1)[0]
    element_type = str(properties.get("osm_element_type") or "way")
    element_id = str(
        properties.get("osm_element_id")
        or properties.get("osm_way_id")
        or ""
    )
    return f"{element_type}/{element_id}" if element_id else ""


def get_snapshot_feature_key(properties: dict[str, Any]) -> str:
    """读取包含多面分片编号的快照要素唯一键。

    Args:
        properties: 项目快照属性。

    Returns:
        str: 稳定来源要素编号。
    """
    source_feature_id = str(properties.get("source_feature_id") or "")
    if source_feature_id:
        return source_feature_id
    return get_osm_element_key(properties)


def normalize_snapshot_feature(feature: dict[str, Any]) -> dict[str, Any]:
    """补齐旧版 way 快照的统一 OSM 来源字段。

    Args:
        feature: 已存在的 GeoJSON Feature。

    Returns:
        dict[str, Any]: 不改变真实几何的规范化 Feature。
    """
    normalized = dict(feature)
    properties = dict(feature.get("properties") or {})
    element_key = get_osm_element_key(properties)
    element_type, _, element_id = element_key.partition("/")
    properties["osm_element_type"] = element_type
    properties["osm_element_id"] = element_id
    properties["source_feature_id"] = get_snapshot_feature_key(properties)
    normalized["properties"] = properties
    return normalized


def load_geojson(path: Path) -> dict[str, Any]:
    """读取 GeoJSON 文件。

    Args:
        path: GeoJSON 文件路径。

    Returns:
        dict[str, Any]: 已解析的 GeoJSON 对象。
    """
    return json.loads(path.read_text(encoding="utf-8"))


def iter_polygon_rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    """提取 Polygon 或 MultiPolygon 的外环。

    Args:
        geometry: GeoJSON 几何。

    Returns:
        list[list[list[float]]]: 多个多边形外环。
    """
    coordinates = geometry.get("coordinates") or []
    if geometry.get("type") == "Polygon":
        return [coordinates[0]] if coordinates else []
    if geometry.get("type") == "MultiPolygon":
        return [polygon[0] for polygon in coordinates if polygon]
    return []


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """使用射线法判断经纬度点是否位于闭合环内。

    Args:
        lon: WGS84 经度。
        lat: WGS84 纬度。
        ring: GeoJSON 线性环。

    Returns:
        bool: 点位于环内时返回 True。
    """
    inside = False
    previous = ring[-1]
    for current in ring:
        current_lon, current_lat = current[:2]
        previous_lon, previous_lat = previous[:2]
        crosses = (current_lat > lat) != (previous_lat > lat)
        if crosses:
            edge_lon = previous_lon + (
                (lat - previous_lat)
                * (current_lon - previous_lon)
                / (current_lat - previous_lat)
            )
            if lon < edge_lon:
                inside = not inside
        previous = current
    return inside


def point_in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    """判断点是否位于行政区 Polygon/MultiPolygon 内。

    Args:
        lon: WGS84 经度。
        lat: WGS84 纬度。
        geometry: 行政区 GeoJSON 几何。

    Returns:
        bool: 点位于任一行政区外环内时返回 True。
    """
    return any(point_in_ring(lon, lat, ring) for ring in iter_polygon_rings(geometry))


def geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    """计算行政区几何包围盒。

    Args:
        geometry: GeoJSON 几何。

    Returns:
        tuple[float, float, float, float]: 最小经纬度和最大经纬度。
    """
    points = [point for ring in iter_polygon_rings(geometry) for point in ring]
    if not points:
        raise ValueError("行政区几何缺少有效坐标")
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def polygon_area_ha(ring: list[list[float]]) -> float:
    """用局部等距近似计算地类底块面积。

    Args:
        ring: WGS84 多边形外环。

    Returns:
        float: 近似面积，单位公顷。
    """
    mean_latitude = math.radians(sum(point[1] for point in ring) / len(ring))
    radius = 6_378_137.0
    projected = [
        (
            radius * math.radians(point[0]) * math.cos(mean_latitude),
            radius * math.radians(point[1]),
        )
        for point in ring
    ]
    signed_area = 0.0
    for index, current in enumerate(projected):
        following = projected[(index + 1) % len(projected)]
        signed_area += current[0] * following[1] - following[0] * current[1]
    return abs(signed_area) / 2 / 10_000


def select_distributed_features(
    features: list[dict[str, Any]],
    limit: int,
    bbox: tuple[float, float, float, float],
) -> list[dict[str, Any]]:
    """使用规则网格轮询选取空间分布更均匀的 OSM 要素。

    Args:
        features: 点几何候选要素。
        limit: 最大选择数量。
        bbox: 行政区包围盒。

    Returns:
        list[dict[str, Any]]: 空间分布后的候选要素。
    """
    if len(features) <= limit:
        return features
    min_lon, min_lat, max_lon, max_lat = bbox
    width = max(max_lon - min_lon, 0.000001)
    height = max(max_lat - min_lat, 0.000001)

    def normalized(feature: dict[str, Any]) -> tuple[float, float]:
        lon, lat = feature["geometry"]["coordinates"][:2]
        return (lon - min_lon) / width, (lat - min_lat) / height

    def feature_identifier(feature: dict[str, Any]) -> str:
        properties = feature["properties"]
        return str(
            properties.get("@osmId")
            or get_snapshot_feature_key(properties)
        )

    grid_size = max(1, math.ceil(math.sqrt(limit)))
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for feature in sorted(features, key=feature_identifier):
        normalized_lon, normalized_lat = normalized(feature)
        column = min(grid_size - 1, max(0, int(normalized_lon * grid_size)))
        row = min(grid_size - 1, max(0, int(normalized_lat * grid_size)))
        buckets.setdefault((row, column), []).append(feature)
    ordered_cells = sorted(buckets)
    selected: list[dict[str, Any]] = []
    depth = 0
    while len(selected) < limit:
        added = False
        for cell in ordered_cells:
            bucket = buckets[cell]
            if depth >= len(bucket):
                continue
            selected.append(bucket[depth])
            added = True
            if len(selected) == limit:
                break
        if not added:
            break
        depth += 1
    return selected


async def request_geojson(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str],
) -> dict[str, Any]:
    """带有限重试地请求 ohsome GeoJSON。

    Args:
        client: 复用连接池的异步 HTTP 客户端。
        url: ohsome API 地址。
        params: 查询参数。

    Returns:
        dict[str, Any]: GeoJSON 响应。
    """
    for attempt in range(1, 4):
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, json.JSONDecodeError):
            if attempt == 3:
                raise
            await asyncio.sleep(attempt * 2)
    raise RuntimeError("ohsome API 请求未返回结果")


def to_snapshot_feature(
    feature: dict[str, Any],
    district: dict[str, Any],
    city_names: dict[str, str],
) -> list[dict[str, Any]]:
    """将 ohsome 要素转换为项目版本化 Polygon 快照。

    Args:
        feature: ohsome Polygon 或 MultiPolygon Feature。
        district: 县级行政区 Feature。
        city_names: 地级行政编码到名称的索引。

    Returns:
        list[dict[str, Any]]: 合格地类面；MultiPolygon 按真实组成面拆分。
    """
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    landuse = str(properties.get("landuse") or "").strip()
    osm_identifier = str(properties.get("@osmId") or "")
    try:
        element_type, element_id = osm_identifier.split("/", maxsplit=1)
    except ValueError:
        return []
    if (
        element_type not in {"way", "relation"}
        or not element_id.isdigit()
        or geometry.get("type") not in {"Polygon", "MultiPolygon"}
        or landuse not in LAND_PARCEL_LANDUSES
    ):
        return []
    polygons = (
        [geometry.get("coordinates") or []]
        if geometry.get("type") == "Polygon"
        else geometry.get("coordinates") or []
    )
    district_properties = district["properties"]
    city_code = str(district_properties["parent"]["adcode"])
    converted: list[dict[str, Any]] = []
    for part_index, polygon_coordinates in enumerate(polygons, start=1):
        if not polygon_coordinates or len(polygon_coordinates[0]) < 5:
            continue
        ring = polygon_coordinates[0]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        area_ha = polygon_area_ha(ring)
        if not 0.05 <= area_ha <= 500:
            continue
        source_feature_id = f"{element_type}/{element_id}"
        if len(polygons) > 1:
            source_feature_id = f"{source_feature_id}#part/{part_index}"
        converted.append({
            "type": "Feature",
            "id": (
                f"osm-{element_type}-{element_id}"
                if len(polygons) == 1
                else f"osm-{element_type}-{element_id}-part-{part_index}"
            ),
            "properties": {
                "osm_element_type": element_type,
                "osm_element_id": element_id,
                "osm_part_index": part_index if len(polygons) > 1 else None,
                "osm_way_id": element_id if element_type == "way" else None,
                "osm_version": str(properties.get("@version") or ""),
                "osm_timestamp": properties.get("@lastEdit"),
                "osm_changeset": str(properties.get("@changesetId") or ""),
                "osm_user": properties.get("@user"),
                "landuse": landuse,
                "name": properties.get("name"),
                "province_name": "黑龙江省",
                "province_code": "230000",
                "city_name": city_names[city_code],
                "city_code": city_code,
                "district_name": district_properties["name"],
                "district_code": str(district_properties["adcode"]),
                "source_area_ha": round(area_ha, 4),
                "source_node_count": len(ring),
                "source_name": "OpenStreetMap",
                "source_feature_id": source_feature_id,
                "source_uri": (
                    f"https://www.openstreetmap.org/{element_type}/{element_id}"
                ),
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": polygon_coordinates,
            },
        })
    return converted


async def fetch_district_features(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    district: dict[str, Any],
    city_names: dict[str, str],
    needed_count: int,
    existing_ids: set[str],
) -> list[dict[str, Any]]:
    """获取一个县级行政区内的真实地类底块样本。

    Args:
        client: ohsome 异步 HTTP 客户端。
        semaphore: 并发请求限制器。
        district: 县级行政区 Feature。
        city_names: 地级行政编码到名称的索引。
        needed_count: 当前县区仍需补充的图斑数量。
        existing_ids: 快照中已经存在的 OSM way ID。

    Returns:
        list[dict[str, Any]]: 经过几何和来源校验的真实地类底块。
    """
    geometry = district["geometry"]
    bbox = geometry_bbox(geometry)
    bbox_text = ",".join(f"{value:.7f}" for value in bbox)
    common_params = {
        "bboxes": bbox_text,
        "filter": LAND_PARCEL_FILTER,
        "time": OHSOME_SNAPSHOT_TIME,
        "properties": "tags,metadata",
    }
    async with semaphore:
        centroid_payload = await request_geojson(
            client,
            OHSOME_CENTROID_URL,
            common_params,
        )
    candidates = []
    for feature in centroid_payload.get("features") or []:
        osm_identifier = str((feature.get("properties") or {}).get("@osmId") or "")
        point = (feature.get("geometry") or {}).get("coordinates") or []
        if (
            osm_identifier.split("/", maxsplit=1)[0] in {"way", "relation"}
            and osm_identifier not in existing_ids
            and len(point) >= 2
            and point_in_geometry(point[0], point[1], geometry)
        ):
            candidates.append(feature)
    candidates = select_distributed_features(
        candidates,
        needed_count * 8,
        bbox,
    )
    if not candidates:
        return []
    identifiers = [feature["properties"]["@osmId"] for feature in candidates]
    geometry_features: list[dict[str, Any]] = []
    for start_index in range(0, len(identifiers), GEOMETRY_IDENTIFIER_BATCH_SIZE):
        identifier_batch = identifiers[
            start_index : start_index + GEOMETRY_IDENTIFIER_BATCH_SIZE
        ]
        geometry_params = {
            "bboxes": bbox_text,
            "filter": f"id:({','.join(identifier_batch)})",
            "time": OHSOME_SNAPSHOT_TIME,
            "properties": "tags,metadata",
            "clipGeometry": "false",
        }
        async with semaphore:
            geometry_payload = await request_geojson(
                client,
                OHSOME_GEOMETRY_URL,
                geometry_params,
            )
        geometry_features.extend(geometry_payload.get("features") or [])
    converted = [
        converted_feature
        for feature in geometry_features
        for converted_feature in to_snapshot_feature(
            feature,
            district,
            city_names,
        )
    ]
    return select_distributed_features(
        [
            {
                **feature,
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        sum(point[0] for point in feature["geometry"]["coordinates"][0])
                        / len(feature["geometry"]["coordinates"][0]),
                        sum(point[1] for point in feature["geometry"]["coordinates"][0])
                        / len(feature["geometry"]["coordinates"][0]),
                    ],
                },
                "_polygon_geometry": feature["geometry"],
            }
            for feature in converted
        ],
        needed_count,
        bbox,
    )


def restore_polygon_geometry(feature: dict[str, Any]) -> dict[str, Any]:
    """移除分布采样临时字段并恢复 Polygon 几何。

    Args:
        feature: 包含临时点几何的快照 Feature。

    Returns:
        dict[str, Any]: 可写入快照的标准 Polygon Feature。
    """
    restored = dict(feature)
    restored["geometry"] = restored.pop("_polygon_geometry")
    return restored


async def build_snapshot(output: Path, target_per_district: int) -> None:
    """补充并写出全省多层级真实地类底块快照。

    Args:
        output: 输出 GeoJSON 文件。
        target_per_district: 每个有 OSM 数据县区的目标样本量。

    Returns:
        None: 无返回值。
    """
    boundary_payload = load_geojson(BOUNDARY_SNAPSHOT)
    cities = {
        str(feature["properties"]["adcode"]): feature["properties"]["name"]
        for feature in boundary_payload["features"]
        if feature["properties"]["level"] == "city"
    }
    districts = [
        feature
        for feature in boundary_payload["features"]
        if feature["properties"]["level"] == "district"
    ]
    existing_payload = load_geojson(output) if output.exists() else {"features": []}
    existing_features = [
        normalize_snapshot_feature(feature)
        for feature in existing_payload.get("features") or []
        if get_osm_element_key(feature["properties"])
        not in EXCLUDED_OSM_ELEMENT_KEYS
    ]
    existing_ids = {
        get_osm_element_key(feature["properties"])
        for feature in existing_features
    }
    existing_counts = Counter(
        str(feature["properties"]["district_code"])
        for feature in existing_features
    )
    pending_districts = [
        district
        for district in districts
        if existing_counts[str(district["properties"]["adcode"])]
        < target_per_district
    ]
    semaphore = asyncio.Semaphore(REQUEST_CONCURRENCY)
    timeout = httpx.Timeout(90, connect=20)
    headers = {"User-Agent": "remote-sensing-gis-platform/1.0"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        results = await asyncio.gather(
            *[
                fetch_district_features(
                    client,
                    semaphore,
                    district,
                    cities,
                    target_per_district
                    - existing_counts[str(district["properties"]["adcode"])],
                    existing_ids,
                )
                for district in pending_districts
            ],
            return_exceptions=True,
        )
    additions: list[dict[str, Any]] = []
    addition_keys: set[str] = set()
    failures: list[str] = []
    for district, result in zip(pending_districts, results, strict=True):
        district_name = district["properties"]["name"]
        if isinstance(result, BaseException):
            failures.append(f"{district_name}: {result}")
            continue
        for feature in result:
            element_key = get_osm_element_key(feature["properties"])
            feature_key = get_snapshot_feature_key(feature["properties"])
            if (
                feature_key in addition_keys
                or element_key in EXCLUDED_OSM_ELEMENT_KEYS
            ):
                continue
            additions.append(restore_polygon_geometry(feature))
            addition_keys.add(feature_key)
            existing_ids.add(element_key)

    features = existing_features + additions
    features.sort(
        key=lambda feature: (
            feature["properties"]["city_code"],
            feature["properties"]["district_code"],
            get_snapshot_feature_key(feature["properties"]),
        )
    )
    city_count = len({feature["properties"]["city_code"] for feature in features})
    district_count = len(
        {feature["properties"]["district_code"] for feature in features}
    )
    payload = {
        "type": "FeatureCollection",
        "metadata": {
            "name": "黑龙江省多区域 OpenStreetMap 真实地类底块快照",
            "source_name": "OpenStreetMap",
            "source_uri": "https://www.openstreetmap.org",
            "acquisition_api": "https://api.ohsome.org/v1/elements/geometry",
            "license": "ODbL 1.0",
            "retrieved_at": date.today().isoformat(),
            "source_snapshot_time": OHSOME_SNAPSHOT_TIME,
            "selection_rule": (
                f"{LAND_PARCEL_FILTER}; valid Polygon; 0.05-500 ha; "
                "at least 5 closed-ring coordinates; "
                "spatially distributed samples per district"
            ),
            "administrative_scope": "黑龙江省 13 个地级区域、122 个县级区域",
            "city_count": city_count,
            "district_count": district_count,
            "feature_count": len(features),
        },
        "features": features,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_suffix(f"{output.suffix}.tmp")
    temporary_output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary_output.replace(output)
    print(
        f"保留 {len(existing_features)} 条，新增 {len(additions)} 条，"
        f"合计 {len(features)} 条；覆盖 {city_count} 市 {district_count} 县区"
    )
    if failures:
        print(f"{len(failures)} 个县区请求失败：")
        print("\n".join(failures))


async def main() -> None:
    """解析参数并生成版本化真实地类底块快照。

    Returns:
        None: 无返回值。
    """
    parser = argparse.ArgumentParser(description="补充 OSM 真实地类底块边界快照")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-per-district", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.target_per_district <= 1000:
        raise ValueError("每县目标图斑数量必须在 1 到 1000 之间")
    await build_snapshot(args.output, args.target_per_district)


if __name__ == "__main__":
    asyncio.run(main())
