"""真实遥感影像文件入库与元数据提取测试。"""

import asyncio
import warnings
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile
from rasterio.rpc import RPC
from rasterio.transform import from_origin

from app.core.exceptions import ValidationException
from app.models.workbench import ImageryAsset
from app.schemas.imagery import ImageryAssetCreateRequest
from app.services.imagery_asset_service import ImageryAssetService


def build_geotiff_bytes(
    *,
    include_crs: bool = True,
    tags: dict[str, str] | None = None,
    namespaced_tags: dict[str, dict[str, str]] | None = None,
) -> bytes:
    """构造可由 Rasterio 读取并携带业务标签的三波段 GeoTIFF。"""
    profile = {
        "driver": "GTiff",
        "width": 10,
        "height": 6,
        "count": 3,
        "dtype": "uint16",
        "transform": from_origin(126.0, 46.0, 0.01, 0.01),
    }
    if include_crs:
        profile["crs"] = "EPSG:4326"
    data = np.arange(180, dtype="uint16").reshape(3, 6, 10)
    with MemoryFile() as memory_file:
        with memory_file.open(**profile) as dataset:
            dataset.write(data)
            selected_tags = tags if tags is not None else {
                "SATELLITE": "TEST-SAT",
                "ACQUIRED": "2026-06-18",
                "PROCESSING_LEVEL": "L1A",
                "CLOUD_COVER": "7.25",
            }
            if selected_tags:
                dataset.update_tags(**selected_tags)
            for namespace, namespace_tags in (namespaced_tags or {}).items():
                dataset.update_tags(ns=namespace, **namespace_tags)
        return memory_file.read()


def build_create_request(
    *,
    sensor_type: str | None = None,
    acquired_at: datetime | None = None,
    cloud_cover: float | None = None,
    processing_level: str | None = None,
) -> ImageryAssetCreateRequest:
    """构造合法影像入库业务元数据。"""
    return ImageryAssetCreateRequest(
        asset_code="GF2-TEST-001",
        asset_name="测试卫星影像",
        sensor_type=sensor_type,
        acquired_at=acquired_at,
        cloud_cover=cloud_cover,
        processing_level=processing_level,
        data_status="demo",
        operator_code="interp-li-jing",
    )


def build_rpc_geotiff_bytes() -> bytes:
    """构造无普通 CRS、但带完整 RPC 模型的原始卫星影像。"""
    zeros = [0.0] * 20
    line_numerator = zeros.copy()
    line_numerator[2] = -1.0
    line_denominator = zeros.copy()
    line_denominator[0] = 1.0
    sample_numerator = zeros.copy()
    sample_numerator[1] = 1.0
    sample_denominator = zeros.copy()
    sample_denominator[0] = 1.0
    rpc_model = RPC(
        height_off=100,
        height_scale=500,
        lat_off=45.8,
        lat_scale=0.04,
        line_den_coeff=line_denominator,
        line_num_coeff=line_numerator,
        line_off=2.5,
        line_scale=2.5,
        long_off=126.6,
        long_scale=0.05,
        samp_den_coeff=sample_denominator,
        samp_num_coeff=sample_numerator,
        samp_off=4.5,
        samp_scale=4.5,
        err_bias=0.5,
        err_rand=0.2,
    )
    data = np.arange(180, dtype="uint16").reshape(3, 6, 10)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with MemoryFile() as memory_file:
            with memory_file.open(
                driver="GTiff",
                width=10,
                height=6,
                count=3,
                dtype="uint16",
            ) as dataset:
                dataset.write(data)
                dataset.update_tags(
                    SATELLITE="TEST-RPC-SAT",
                    ACQUIRED="2026-06-18",
                    PROCESSING_LEVEL="L1A",
                )
                dataset.update_tags(ns="RPC", **rpc_model.to_gdal())
            return memory_file.read()


def build_service(tmp_path: Path) -> tuple[ImageryAssetService, AsyncMock, AsyncMock]:
    """构造使用临时存储目录的影像资产服务。"""
    dao = AsyncMock()
    dao.get_asset_by_code.return_value = None
    dao.get_asset_by_checksum.return_value = None

    async def add_asset(_: object, asset: ImageryAsset) -> ImageryAsset:
        asset.id = 9
        asset.created_at = datetime.now(UTC)
        return asset

    dao.add_asset.side_effect = add_asset
    workbench_dao = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=7)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=7,
    )
    project_user_service = AsyncMock()
    project_user_service.require_capability.return_value = SimpleNamespace(
        user_code="interp-li-jing",
        display_name="李静",
        role_code="interpreter",
    )
    service = ImageryAssetService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
    )
    service.storage_dir = tmp_path
    return service, dao, workbench_dao


def test_imagery_request_requires_timezone() -> None:
    """验证影像采集时间必须带时区。"""
    with pytest.raises(ValidationError, match="必须包含时区"):
        ImageryAssetCreateRequest(
            asset_code="GF2-TEST-001",
            asset_name="测试影像",
            sensor_type="GF2",
            acquired_at=datetime(2026, 6, 18, 10, 42),
            operator_code="interp-li-jing",
        )


def test_upload_geotiff_extracts_real_raster_metadata(tmp_path: Path) -> None:
    """验证 GeoTIFF 入库读取结构和文件业务标签。"""
    service, dao, workbench_dao = build_service(tmp_path)
    db = AsyncMock()

    response = asyncio.run(
        service.upload_asset(
            db,
            "RS-2026",
            "RS-2026-045",
            build_create_request(),
            "gf2_test.tif",
            BytesIO(build_geotiff_bytes()),
        )
    )

    assert response.file_verified is True
    assert response.file_format == "GTiff"
    assert response.crs == "EPSG:4326"
    assert response.band_count == 3
    assert response.raster_width == 10
    assert response.raster_height == 6
    assert response.file_size_bytes and response.file_size_bytes > 0
    assert len(response.checksum_sha256 or "") == 64
    assert response.sensor_type == "TEST-SAT"
    assert response.acquired_at == datetime(2026, 6, 18, tzinfo=UTC)
    assert response.processing_level == "L1A"
    assert response.cloud_cover == 7.25
    business_metadata = response.raster_metadata["business_metadata"]
    assert business_metadata["sensor_type"]["source"] == "raster_tag:SATELLITE"
    assert business_metadata["acquired_at"]["source"] == "raster_tag:ACQUIRED"
    assert business_metadata["acquired_at"]["timezone_assumption"] == "UTC"
    assert business_metadata["processing_level"]["source"] == (
        "raster_tag:PROCESSING_LEVEL"
    )
    assert business_metadata["cloud_cover"]["source"] == (
        "raster_tag:CLOUD_COVER"
    )
    assert response.footprint is not None
    assert response.footprint["type"] == "Polygon"
    stored_path = tmp_path / "assets/GF2-TEST-001/gf2_test.tif"
    assert stored_path.is_file()
    with rasterio.open(stored_path) as dataset:
        assert dataset.count == 3
        assert dataset.tags()["SATELLITE"] == "TEST-SAT"
    dao.add_steps.assert_awaited_once()
    steps = dao.add_steps.await_args.args[1]
    assert [step.step_code for step in steps] == [
        "radiometric",
        "atmospheric",
        "geometric",
        "clip",
        "enhancement",
        "band_products",
    ]
    assert [step.sequence for step in steps] == [1, 2, 3, 4, 5, 6]
    assert [step.is_required for step in steps] == [
        True,
        True,
        True,
        True,
        False,
        True,
    ]
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_upload_accepts_rpc_only_imagery_and_derives_wgs84_footprint(
    tmp_path: Path,
) -> None:
    """验证无普通 CRS 的 RPC 原始影像可入库并保留传感器模型。"""
    service, _, _ = build_service(tmp_path)

    response = asyncio.run(
        service.upload_asset(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            build_create_request(),
            "rpc_source.tif",
            BytesIO(build_rpc_geotiff_bytes()),
        )
    )

    assert response.file_verified is True
    assert response.crs == "RPC:WGS84"
    assert response.raster_metadata["has_rpc"] is True
    assert response.raster_metadata["rpc_summary"]["error_bias"] == 0.5
    assert response.footprint is not None
    coordinates = response.footprint["coordinates"][0]
    assert coordinates[0] == pytest.approx([126.55, 45.76])
    assert coordinates[2] == pytest.approx([126.65, 45.84])
    stored_path = tmp_path / "assets/GF2-TEST-001/rpc_source.tif"
    with rasterio.open(stored_path) as dataset:
        assert dataset.crs is None
        assert dataset.rpcs is not None


def test_upload_uses_audited_user_fallback_when_tags_are_missing(
    tmp_path: Path,
) -> None:
    """验证文件缺少业务标签时允许人工补录并记录来源。"""
    service, _, _ = build_service(tmp_path)
    acquired_at = datetime(2026, 6, 18, 10, 42, tzinfo=UTC)

    response = asyncio.run(
        service.upload_asset(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            build_create_request(
                sensor_type="GF2 PMS1",
                acquired_at=acquired_at,
                cloud_cover=2.3,
                processing_level="L1A",
            ),
            "manual_metadata.tif",
            BytesIO(build_geotiff_bytes(tags={})),
        )
    )

    assert response.sensor_type == "GF2 PMS1"
    assert response.acquired_at == acquired_at
    assert response.cloud_cover == 2.3
    assert response.processing_level == "L1A"
    business_metadata = response.raster_metadata["business_metadata"]
    assert business_metadata["sensor_type"]["source"] == "user_fallback"
    assert business_metadata["acquired_at"]["source"] == "user_fallback"
    assert business_metadata["processing_level"]["source"] == "user_fallback"
    assert business_metadata["cloud_cover"]["source"] == "user_fallback"


def test_upload_extracts_case_insensitive_common_aliases(tmp_path: Path) -> None:
    """验证常见平台、载荷、时间、级别和云量别名大小写无关。"""
    service, _, _ = build_service(tmp_path)

    response = asyncio.run(
        service.upload_asset(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            build_create_request(),
            "sentinel_aliases.tif",
            BytesIO(build_geotiff_bytes(tags={
                "platform": "Sentinel-2A",
                "instrument": "MSI",
                "acquisition_time": "2026-06-18T10:42:00Z",
                "product_level": "L2A",
                "cloudy_pixel_percentage": "3.1%",
            })),
        )
    )

    assert response.sensor_type == "Sentinel-2A MSI"
    assert response.acquired_at == datetime(2026, 6, 18, 10, 42, tzinfo=UTC)
    assert response.processing_level == "L2A"
    assert response.cloud_cover == 3.1
    audit = response.raster_metadata["business_metadata"]
    assert audit["sensor_type"]["raster_tag"] == "platform+instrument"
    assert audit["acquired_at"]["raster_tag"] == "acquisition_time"


def test_upload_requires_sensor_and_time_when_file_tags_are_missing(
    tmp_path: Path,
) -> None:
    """验证文件与人工均未提供必填业务元数据时拒绝入库。"""
    service, dao, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="传感器元数据"):
        asyncio.run(
            service.upload_asset(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                build_create_request(),
                "missing_business_metadata.tif",
                BytesIO(build_geotiff_bytes(tags={})),
            )
        )

    dao.add_asset.assert_not_awaited()


def test_upload_extracts_business_metadata_from_tag_namespace(
    tmp_path: Path,
) -> None:
    """验证 HDF/产品命名空间中的业务标签也可被提取并审计。"""
    service, _, _ = build_service(tmp_path)

    response = asyncio.run(
        service.upload_asset(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            build_create_request(),
            "namespace_metadata.tif",
            BytesIO(build_geotiff_bytes(
                tags={},
                namespaced_tags={
                    "PRODUCT": {
                        "SPACECRAFT_NAME": "LANDSAT_9",
                        "SENSOR_ID": "OLI_TIRS",
                        "DATE_ACQUIRED": "2026-06-18",
                        "CLOUD_COVER": "4.5",
                    },
                },
            )),
        )
    )

    assert response.sensor_type == "LANDSAT_9 OLI_TIRS"
    assert response.cloud_cover == 4.5
    audit = response.raster_metadata["business_metadata"]
    assert audit["sensor_type"]["raster_tag"] == (
        "PRODUCT:SPACECRAFT_NAME+PRODUCT:SENSOR_ID"
    )
    assert response.raster_metadata["tag_namespaces"]["PRODUCT"][
        "DATE_ACQUIRED"
    ] == "2026-06-18"


def test_upload_rejects_sensor_conflict_and_cleans_file(tmp_path: Path) -> None:
    """验证人工传感器与文件标签冲突时整次入库失败。"""
    service, dao, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="传感器.*不一致"):
        asyncio.run(
            service.upload_asset(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                build_create_request(sensor_type="OTHER-SAT"),
                "sensor_conflict.tif",
                BytesIO(build_geotiff_bytes()),
            )
        )

    dao.add_asset.assert_not_awaited()
    assert not list(tmp_path.glob("assets/**/*"))


def test_upload_rejects_acquired_at_conflict(tmp_path: Path) -> None:
    """验证人工采集日期与文件日期不一致时拒绝入库。"""
    service, dao, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="采集时间.*不一致"):
        asyncio.run(
            service.upload_asset(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                build_create_request(
                    acquired_at=datetime(2026, 6, 19, tzinfo=UTC),
                ),
                "time_conflict.tif",
                BytesIO(build_geotiff_bytes()),
            )
        )

    dao.add_asset.assert_not_awaited()


def test_upload_accepts_user_time_refinement_for_date_only_tag(
    tmp_path: Path,
) -> None:
    """验证文件仅提供日期时可由人工补充同日精确时间。"""
    service, _, _ = build_service(tmp_path)
    acquired_at = datetime(2026, 6, 18, 10, 42, tzinfo=UTC)

    response = asyncio.run(
        service.upload_asset(
            AsyncMock(),
            "RS-2026",
            "RS-2026-045",
            build_create_request(acquired_at=acquired_at),
            "time_refinement.tif",
            BytesIO(build_geotiff_bytes()),
        )
    )

    assert response.acquired_at == acquired_at
    acquired_audit = response.raster_metadata["business_metadata"]["acquired_at"]
    assert acquired_audit["source"] == "user_refinement:raster_tag:ACQUIRED"
    assert acquired_audit["precision"] == "date"


def test_upload_rejects_invalid_cloud_tag(tmp_path: Path) -> None:
    """验证文件声明非法云量时不得静默改用人工值。"""
    service, dao, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="CLOUD_COVER.*0 到 100"):
        asyncio.run(
            service.upload_asset(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                build_create_request(cloud_cover=2.0),
                "invalid_cloud.tif",
                BytesIO(build_geotiff_bytes(tags={
                    "SATELLITE": "TEST-SAT",
                    "ACQUIRED": "2026-06-18",
                    "CLOUD_COVER": "125",
                })),
            )
        )

    dao.add_asset.assert_not_awaited()


def test_upload_rejects_raster_without_crs_and_cleans_file(tmp_path: Path) -> None:
    """验证缺少 CRS 的影像被拒绝且不会遗留资产文件。"""
    service, dao, _ = build_service(tmp_path)

    with pytest.raises(ValidationException, match="缺少 CRS"):
        asyncio.run(
            service.upload_asset(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                build_create_request(),
                "missing_crs.tif",
                BytesIO(build_geotiff_bytes(include_crs=False)),
            )
        )

    dao.add_asset.assert_not_awaited()
    assert not list(tmp_path.glob("assets/**/*"))


def test_asset_list_marks_metadata_only_record() -> None:
    """验证没有真实文件的历史元数据记录明确标记为不可用。"""
    asset = ImageryAsset(
        id=1,
        project_id=7,
        asset_code="GF2-METADATA",
        asset_name="历史元数据",
        sensor_type="GF2",
        acquired_at=datetime(2026, 6, 18, tzinfo=UTC),
        calibration_status="pending",
        correction_status="pending",
        data_status="operational",
        raster_metadata={},
        created_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.list_assets.return_value = [{ImageryAsset: asset, "footprint": None}]
    workbench_dao = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=7)
    service = ImageryAssetService(dao=dao, workbench_dao=workbench_dao)

    response = asyncio.run(service.list_assets(AsyncMock(), "RS-2026"))

    assert response.total == 1
    assert response.available == 0
    assert response.metadata_only == 1
    assert response.items[0].file_error == "仅有元数据，未关联实体文件"
