"""请求模型单元测试。"""

import pytest
from pydantic import ValidationError

from app.schemas.request import BBoxRequest, PointQueryRequest


def test_point_request_accepts_valid_wgs84_coordinate() -> None:
    """验证哈尔滨周边合法 WGS84 坐标可通过校验。"""
    request = PointQueryRequest(lon=126.5, lat=45.8)

    assert request.lon == 126.5
    assert request.lat == 45.8


@pytest.mark.parametrize(
    ("lon", "lat"),
    [(181, 45.8), (-181, 45.8), (126.5, 91), (126.5, -91)],
)
def test_point_request_rejects_out_of_range_coordinate(
    lon: float,
    lat: float,
) -> None:
    """验证超出 WGS84 范围的坐标会被拒绝。"""
    with pytest.raises(ValidationError):
        PointQueryRequest(lon=lon, lat=lat)


def test_bbox_request_rejects_reversed_bounds() -> None:
    """验证包围盒最小坐标不能大于最大坐标。"""
    with pytest.raises(ValidationError):
        BBoxRequest(min_lon=127, min_lat=46, max_lon=126, max_lat=45)
