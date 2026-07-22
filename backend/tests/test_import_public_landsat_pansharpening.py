"""公开 Landsat 同景多光谱与全色实体导入脚本测试。"""

import argparse
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from scripts.import_public_landsat_pansharpening import (
    build_pansharpening_sources,
    parse_bbox,
    parse_mtl,
    parse_scene_id,
)

SCENE_ID = "LC08_L1TP_117028_20200724_20200807_01_T1"


def mtl_content(*, product_id: str = SCENE_ID) -> str:
    """生成包含四波段反射率系数的最小 Landsat MTL 文本。"""
    return f"""
        LANDSAT_PRODUCT_ID = "{product_id}"
        SPACECRAFT_ID = "LANDSAT_8"
        SENSOR_ID = "OLI_TIRS"
        DATE_ACQUIRED = 2020-07-24
        SCENE_CENTER_TIME = "02:14:25.6929380Z"
        CLOUD_COVER = 2.85
        SUN_ELEVATION = 30.0
        REFLECTANCE_MULT_BAND_2 = 0.00002
        REFLECTANCE_ADD_BAND_2 = -0.1
        REFLECTANCE_MULT_BAND_3 = 0.00002
        REFLECTANCE_ADD_BAND_3 = -0.1
        REFLECTANCE_MULT_BAND_4 = 0.00002
        REFLECTANCE_ADD_BAND_4 = -0.1
        REFLECTANCE_MULT_BAND_8 = 0.00002
        REFLECTANCE_ADD_BAND_8 = -0.1
    """


def write_band(
    path: Path,
    value: int,
    *,
    width: int,
    height: int,
    left: float = 126.0,
) -> None:
    """写入一个带固定 WGS84 网格的单波段 DN 测试影像。"""
    data = np.full((height, width), value, dtype="uint16")
    data[0, 0] = 0
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
        nodata=0,
    ) as dataset:
        dataset.write(data, 1)


def write_sources(
    tmp_path: Path,
    *,
    pan_width: int = 200,
    green_left: float = 126.0,
) -> dict[int, str]:
    """写入 B2/B3/B4 及 B8 测试实体并返回地址。"""
    sources: dict[int, str] = {}
    for band, value in ((2, 10_000), (3, 11_000), (4, 12_000)):
        path = tmp_path / f"B{band}.tif"
        write_band(
            path,
            value,
            width=100,
            height=100,
            left=green_left if band == 3 else 126.0,
        )
        sources[band] = str(path)
    pan_path = tmp_path / "B8.tif"
    write_band(
        pan_path,
        13_000,
        width=pan_width,
        height=pan_width,
    )
    sources[8] = str(pan_path)
    return sources


def test_parse_bbox_and_scene_id_reject_uncontrolled_sources() -> None:
    """验证包围盒和产品编号不能构造任意主机或越界范围。"""
    assert parse_bbox("126.58,45.68,126.78,45.88") == (
        126.58,
        45.68,
        126.78,
        45.88,
    )
    scene = parse_scene_id(SCENE_ID)
    assert scene.path == "117"
    assert scene.row == "028"
    assert scene.band_url(8).startswith(
        "https://storage.googleapis.com/gcp-public-data-landsat/LC08/01/117/028/"
    )
    for bbox in ("126,45,127", "127,45,126,46", "-181,45,126,46"):
        with pytest.raises(argparse.ArgumentTypeError):
            parse_bbox(bbox)
    for scene_id in (
        "LC09_L1TP_117028_20260717_20260717_02_T1",
        "../../etc/passwd",
        "LC08_L1TP_117028_20200724_20200807_02_T1",
        "LC08_L1TP_117028_20201340_20200807_01_T1",
    ):
        with pytest.raises(argparse.ArgumentTypeError):
            parse_scene_id(scene_id)


def test_parse_mtl_preserves_identity_time_and_calibration() -> None:
    """验证 MTL 产品身份、采集时间和四波段系数被完整读取。"""
    calibration = parse_mtl(mtl_content(), SCENE_ID)

    assert calibration.product_id == SCENE_ID
    assert calibration.spacecraft_id == "LANDSAT_8"
    assert calibration.sensor_id == "OLI_TIRS"
    assert calibration.acquisition_time == "2020-07-24T02:14:25.6929380Z"
    assert calibration.cloud_cover == 2.85
    assert calibration.sun_elevation == 30
    assert calibration.coefficients[8] == (0.00002, -0.1)


def test_parse_mtl_rejects_product_mismatch_and_missing_coefficients() -> None:
    """验证不同景 MTL 或缺少标定系数时不能继续生成实体。"""
    with pytest.raises(RuntimeError, match="产品编号与请求场景不一致"):
        parse_mtl(mtl_content(product_id="OTHER_PRODUCT"), SCENE_ID)
    with pytest.raises(RuntimeError, match="REFLECTANCE_MULT_BAND_8"):
        parse_mtl(
            mtl_content().replace(
                "REFLECTANCE_MULT_BAND_8 = 0.00002",
                "",
            ),
            SCENE_ID,
        )


def test_build_sources_calibrates_real_grids_and_lineage(tmp_path: Path) -> None:
    """验证 30 米 RGB 与 15 米全色输出、TOA 数值及公开来源标签。"""
    scene = parse_scene_id(SCENE_ID)
    calibration = parse_mtl(mtl_content(), SCENE_ID)
    multispectral_output = tmp_path / "multispectral.tif"
    panchromatic_output = tmp_path / "panchromatic.tif"

    build_pansharpening_sources(
        scene,
        calibration,
        (126.2, 45.2, 126.8, 45.8),
        multispectral_output,
        panchromatic_output,
        band_sources=write_sources(tmp_path),
    )

    with rasterio.open(multispectral_output) as multispectral:
        tags = multispectral.tags()
        assert multispectral.count == 3
        assert multispectral.width == 60
        assert multispectral.height == 60
        assert multispectral.descriptions == ("Blue", "Green", "Red")
        assert multispectral.dtypes == ("float32",) * 3
        assert multispectral.read(1)[0, 0] == pytest.approx(0.2)
        assert tags["PLATFORM"] == "LANDSAT-8"
        assert tags["SOURCE_PRODUCT_URI"] == SCENE_ID
        assert tags["RADIOMETRIC_CALIBRATION_APPLIED"] == "true"
        assert tags["REFLECTANCE_QUANTITY"] == "TOA_REFLECTANCE"
        assert tags["SECURITY_CLASSIFICATION"] == "public"
        assert tags["PANSHARPENING_SOURCE_ROLE"] == "multispectral"
        assert '"band":8' in tags["SOURCE_CALIBRATION_JSON"]
        assert "gcp-public-data-landsat" in tags["SOURCE_B08_URL"]

    with rasterio.open(panchromatic_output) as panchromatic:
        tags = panchromatic.tags()
        assert panchromatic.count == 1
        assert panchromatic.width == 120
        assert panchromatic.height == 120
        assert panchromatic.descriptions == ("Panchromatic",)
        assert panchromatic.read(1)[0, 0] == pytest.approx(0.32)
        assert tags["SOURCE_PRODUCT_URI"] == SCENE_ID
        assert tags["PANSHARPENING_SOURCE_ROLE"] == "panchromatic"


def test_build_sources_rejects_different_multispectral_grid(
    tmp_path: Path,
) -> None:
    """验证 B2/B3/B4 网格不一致时拒绝伪对齐输出。"""
    with pytest.raises(RuntimeError, match="不在同一像元网格"):
        build_pansharpening_sources(
            parse_scene_id(SCENE_ID),
            parse_mtl(mtl_content(), SCENE_ID),
            (126.2, 45.2, 126.8, 45.8),
            tmp_path / "multispectral.tif",
            tmp_path / "panchromatic.tif",
            band_sources=write_sources(tmp_path, green_left=126.01),
        )


def test_build_sources_rejects_pan_without_resolution_advantage(
    tmp_path: Path,
) -> None:
    """验证全色分辨率无明显优势时不能用普通重采样冒充融合来源。"""
    with pytest.raises(RuntimeError, match="至少优于多光谱 1.5 倍"):
        build_pansharpening_sources(
            parse_scene_id(SCENE_ID),
            parse_mtl(mtl_content(), SCENE_ID),
            (126.2, 45.2, 126.8, 45.8),
            tmp_path / "multispectral.tif",
            tmp_path / "panchromatic.tif",
            band_sources=write_sources(tmp_path, pan_width=100),
        )
