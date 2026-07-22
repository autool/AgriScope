"""图斑业务服务单元测试。"""

import asyncio
from decimal import Decimal
from unittest.mock import ANY, AsyncMock

import pytest

from app.core.exceptions import NotFoundException
from app.schemas.request import PlotViewportRequest, PointQueryRequest
from app.services.plot_service import PlotService


def test_query_by_point_returns_stable_response() -> None:
    """验证 Service 能将 DAO 数据转换为稳定响应。"""
    dao = AsyncMock()
    dao.task_exists.return_value = True
    dao.get_by_point.return_value = {
        "plot_code": "HLJ-001",
        "owner_village": "幸福村",
        "area_ha": Decimal("12.5000"),
    }
    service = PlotService(dao=dao)

    response = asyncio.run(
        service.query_by_point(
            AsyncMock(),
            PointQueryRequest(lon=126.45, lat=45.75),
            "RS-2026-045",
        )
    )

    assert response.plot_code == "HLJ-001"
    assert response.owner_village == "幸福村"
    assert response.area_ha == 12.5


def test_query_by_point_raises_not_found() -> None:
    """验证点位未命中图斑时抛出业务不存在异常。"""
    dao = AsyncMock()
    dao.task_exists.return_value = True
    dao.get_by_point.return_value = None
    service = PlotService(dao=dao)

    with pytest.raises(NotFoundException):
        asyncio.run(
            service.query_by_point(
                AsyncMock(),
                PointQueryRequest(lon=126.0, lat=45.0),
                "RS-2026-045",
            )
        )


def test_get_boundary_hides_plot_outside_current_task() -> None:
    """验证编号搜索不能读取未分配到当前任务的图斑边界。"""
    dao = AsyncMock()
    dao.task_exists.return_value = True
    dao.get_by_plot_code.return_value = None
    service = PlotService(dao=dao)

    with pytest.raises(NotFoundException, match="当前任务未找到图斑"):
        asyncio.run(
            service.get_boundary(
                AsyncMock(),
                "OUTSIDE-001",
                "RS-2026-045",
            )
        )

    dao.get_by_plot_code.assert_awaited_once_with(
        ANY,
        "OUTSIDE-001",
        "RS-2026-045",
    )


def test_plot_catalog_groups_task_plots_without_full_geometry() -> None:
    """验证轻量目录按县区组织并汇总真实地类数量。"""
    dao = AsyncMock()
    dao.task_exists.return_value = True
    dao.get_task_catalog.return_value = [
        {
            "plot_code": "OSM-HLJ-1",
            "source_feature_id": "way/1",
            "land_class": "耕地",
            "district_code": "230109",
            "min_lon": 126.4,
            "min_lat": 45.7,
            "max_lon": 126.5,
            "max_lat": 45.8,
        },
        {
            "plot_code": "OSM-HLJ-2",
            "source_feature_id": "way/2",
            "land_class": "园地",
            "district_code": "230109",
            "min_lon": 126.5,
            "min_lat": 45.7,
            "max_lon": 126.6,
            "max_lat": 45.8,
        },
    ]
    service = PlotService(dao=dao)

    response = asyncio.run(service.get_catalog(AsyncMock(), "RS-2026-045"))

    assert response.total_count == 2
    assert response.land_class_counts == {"耕地": 1, "园地": 1}
    assert response.districts[0].district_code == "230109"
    assert response.districts[0].plot_count == 2
    assert response.districts[0].plots[0].extent == (
        126.4,
        45.7,
        126.5,
        45.8,
    )


def test_viewport_requires_zoom_instead_of_returning_partial_subset() -> None:
    """验证视野超过上限时返回空要素和放大提示。"""
    dao = AsyncMock()
    dao.task_exists.return_value = True
    dao.count_task_by_bbox.return_value = 5001
    service = PlotService(dao=dao)
    request = PlotViewportRequest(
        min_lon=126,
        min_lat=45,
        max_lon=128,
        max_lat=47,
        task_code="RS-2026-045",
        max_features=5000,
    )

    response = asyncio.run(service.query_viewport(AsyncMock(), request))

    assert response.requires_zoom is True
    assert response.matched_count == 5001
    assert response.features == []
    dao.get_task_by_bbox.assert_not_awaited()


def test_viewport_returns_all_features_when_within_limit() -> None:
    """验证视野数量未超限时返回完整 GeoJSON。"""
    dao = AsyncMock()
    dao.task_exists.return_value = True
    dao.count_task_by_bbox.return_value = 1
    dao.get_task_by_bbox.return_value = [
        {
            "id": 1,
            "plot_code": "OSM-HLJ-1",
            "owner_village": None,
            "area_ha": Decimal("1.2"),
            "land_class": "耕地",
            "source_name": "OpenStreetMap",
            "source_feature_id": "way/1",
            "source_uri": "https://www.openstreetmap.org/way/1",
            "source_version": "1",
            "source_updated_at": None,
            "province_name": "黑龙江省",
            "city_name": "哈尔滨市",
            "district_name": "松北区",
            "district_code": "230109",
            "geometry": (
                '{"type":"Polygon","coordinates":'
                '[[[126.4,45.7],[126.5,45.7],[126.5,45.8],[126.4,45.7]]]}'
            ),
        }
    ]
    service = PlotService(dao=dao)
    request = PlotViewportRequest(
        min_lon=126.4,
        min_lat=45.7,
        max_lon=126.6,
        max_lat=45.9,
    )

    response = asyncio.run(service.query_viewport(AsyncMock(), request))

    assert response.requires_zoom is False
    assert response.matched_count == 1
    assert response.features[0]["properties"]["plot_code"] == "OSM-HLJ-1"
