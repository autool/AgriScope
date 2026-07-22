"""Earth Search 公共 Sentinel-2 实体影像导入脚本测试。"""

import argparse
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from scripts.import_public_sentinel_imagery import (
    BAND_ASSETS,
    build_multiband_geotiff,
    parse_bbox,
    select_item,
)


def build_item(
    asset_paths: dict[str, Path],
    *,
    item_id: str = "S2A_TEST_L2A",
    acquired_at: str = "2026-07-16T02:44:55Z",
    cloud_cover: float = 1.3,
) -> dict:
    """构造指向本地单波段 GeoTIFF 的 STAC Feature。"""
    return {
        "id": item_id,
        "properties": {
            "datetime": acquired_at,
            "eo:cloud_cover": cloud_cover,
            "platform": "sentinel-2a",
            "instruments": ["msi"],
            "s2:product_uri": "S2A_MSIL2A_TEST.SAFE",
            "s2:processing_baseline": "05.11",
        },
        "assets": {
            asset_name: {
                "href": str(asset_paths[asset_name]),
                "raster:bands": [{
                    "nodata": 0,
                    "scale": 0.01,
                    "offset": -1,
                }],
            }
            for asset_name, _ in BAND_ASSETS
        },
    }


def write_single_band(
    path: Path,
    value: int,
    *,
    left: float = 126.0,
) -> None:
    """写入固定 WGS84 网格的单波段测试影像。"""
    width = 100
    height = 100
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_bounds(left, 45.0, left + 1.0, 46.0, width, height),
    ) as dataset:
        dataset.write(np.full((height, width), value, dtype="uint16"), 1)


def write_band_set(tmp_path: Path) -> dict[str, Path]:
    """写入蓝、绿、红、近红外同网格测试波段。"""
    paths: dict[str, Path] = {}
    for index, (asset_name, _) in enumerate(BAND_ASSETS, start=1):
        path = tmp_path / f"{asset_name}.tif"
        write_single_band(path, index * 100)
        paths[asset_name] = path
    return paths


def test_parse_bbox_validates_wgs84_order_and_range() -> None:
    """验证 bbox 解析接受合法范围并拒绝数量、顺序和范围错误。"""
    assert parse_bbox("126.58, 45.76, 126.68, 45.84") == (
        126.58,
        45.76,
        126.68,
        45.84,
    )
    for value in ("126,45,127", "127,45,126,46", "-181,45,126,46"):
        with pytest.raises(argparse.ArgumentTypeError):
            parse_bbox(value)


def test_select_item_uses_latest_complete_candidate_and_lowest_cloud_tie() -> None:
    """验证候选必须四波段齐全，并按最新时间、同时间最低云量选择。"""
    hrefs = {asset_name: Path(f"/{asset_name}.tif") for asset_name, _ in BAND_ASSETS}
    older = build_item(
        hrefs,
        item_id="OLDER",
        acquired_at="2026-07-15T02:44:55Z",
        cloud_cover=0,
    )
    latest_cloudy = build_item(hrefs, item_id="LATEST-CLOUDY", cloud_cover=5)
    latest_clear = build_item(hrefs, item_id="LATEST-CLEAR", cloud_cover=0)
    incomplete = build_item(hrefs, item_id="INCOMPLETE", cloud_cover=0)
    incomplete["assets"].pop("nir")

    selected = select_item([incomplete, older, latest_cloudy, latest_clear])

    assert selected["id"] == "LATEST-CLEAR"


def test_build_multiband_geotiff_preserves_grid_bands_and_lineage(
    tmp_path: Path,
) -> None:
    """验证四波段输出的网格、描述、平台与公开来源标签。"""
    item = build_item(write_band_set(tmp_path))
    output_path = tmp_path / "sentinel_subset.tif"

    build_multiband_geotiff(
        item,
        (126.2, 45.2, 126.8, 45.8),
        output_path,
    )

    with rasterio.open(output_path) as dataset:
        tags = dataset.tags()
        assert dataset.crs.to_string() == "EPSG:4326"
        assert dataset.count == 4
        assert dataset.width == 60
        assert dataset.height == 60
        assert dataset.dtypes == ("float32",) * 4
        assert dataset.descriptions == ("Blue", "Green", "Red", "NIR")
        assert dataset.read(1)[0, 0] == pytest.approx(0)
        assert dataset.read(4)[0, 0] == pytest.approx(3)
        assert tags["PLATFORM"] == "Sentinel-2A"
        assert tags["INSTRUMENT"] == "MSI"
        assert tags["PROCESSING_LEVEL"] == "L2A"
        assert tags["STAC_ITEM_ID"] == "S2A_TEST_L2A"
        assert tags["SOURCE_PRODUCT_URI"] == "S2A_MSIL2A_TEST.SAFE"
        assert tags["SOURCE_PROCESSING_BASELINE"] == "05.11"
        assert tags["SOURCE_SCALE_APPLIED"] == "true"
        assert tags["REFLECTANCE_QUANTITY"] == "BOA_REFLECTANCE"
        assert '"scale":0.01' in tags["SOURCE_RASTER_BANDS_JSON"]
        assert '"offset":-1.0' in tags["SOURCE_RASTER_BANDS_JSON"]
        assert tags["SECURITY_CLASSIFICATION"] == "public"
        assert "Copernicus Sentinel Data Legal Notice" == tags["SOURCE_LICENSE"]


def test_build_multiband_geotiff_rejects_different_source_grid(
    tmp_path: Path,
) -> None:
    """验证任一波段网格不一致时拒绝生成伪对齐多波段影像。"""
    paths = write_band_set(tmp_path)
    write_single_band(paths["nir"], 400, left=126.01)

    with pytest.raises(RuntimeError, match="不在同一像元网格"):
        build_multiband_geotiff(
            build_item(paths),
            (126.2, 45.2, 126.8, 45.8),
            tmp_path / "invalid.tif",
        )


def test_build_multiband_geotiff_rejects_missing_stac_scale(
    tmp_path: Path,
) -> None:
    """验证缺少 STAC 反射率比例时不把原始 DN 冒充 L2A 反射率。"""
    item = build_item(write_band_set(tmp_path))
    item["assets"]["red"]["raster:bands"] = [{"offset": -0.1}]

    with pytest.raises(RuntimeError, match="red 缺少数值 scale"):
        build_multiband_geotiff(
            item,
            (126.2, 45.2, 126.8, 45.8),
            tmp_path / "missing-scale.tif",
        )
