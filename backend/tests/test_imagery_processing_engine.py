"""平台内置影像预处理执行引擎测试。"""

import asyncio
import warnings
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.errors import NotGeoreferencedWarning
from rasterio.rpc import RPC
from rasterio.transform import from_origin

from app.core.exceptions import ValidationException
from app.core.imagery_files import calculate_sha256
from app.schemas.imagery import (
    ImagerySourceLevelAcceptRequest,
    ImageryStepExecuteRequest,
)
from app.services.imagery_processing_engine import ImageryProcessingEngine
from app.services.imagery_service import ImageryService


def write_four_band_raster(path: Path) -> None:
    """写出具有 WGS84 空间参考的四波段测试影像。"""
    rows, columns = 8, 10
    base = np.arange(rows * columns, dtype="uint16").reshape(rows, columns)
    data = np.stack([base + 100, base + 200, base + 300, base + 500])
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=columns,
        height=rows,
        count=4,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(126.5, 45.9, 0.01, 0.01),
    ) as output:
        output.write(data)


def write_l2a_reflectance_raster(path: Path, *, scale_applied: bool = True) -> None:
    """写出带完整 Sentinel-2 L2A 源级承认证据的浮点反射率。"""
    rows, columns = 8, 10
    base = np.linspace(0.01, 0.8, rows * columns, dtype="float32").reshape(
        rows,
        columns,
    )
    data = np.stack([base, base * 0.9, base * 0.8, base * 1.2])
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=columns,
        height=rows,
        count=4,
        dtype="float32",
        crs="EPSG:32651",
        transform=from_origin(700000, 5080000, 10, 10),
    ) as output:
        output.write(data)
        output.descriptions = ("Blue", "Green", "Red", "NIR")
        output.update_tags(
            PLATFORM="Sentinel-2B",
            INSTRUMENT="MSI",
            PROCESSING_LEVEL="L2A",
            SOURCE_PROVIDER="AWS Open Data / Element 84 Earth Search",
            SOURCE_PRODUCT_URI="S2B_TEST.SAFE",
            SOURCE_PROCESSING_BASELINE="05.12",
            SOURCE_SCALE_APPLIED="true" if scale_applied else "false",
            REFLECTANCE_QUANTITY="BOA_REFLECTANCE",
            SECURITY_CLASSIFICATION="public",
            STAC_ITEM_ID="S2B_TEST_L2A",
            SOURCE_LICENSE_URL="https://example.test/sentinel-license",
        )


def write_rpc_raster(path: Path) -> None:
    """写出无普通 CRS、但带可解算 RPC 模型的单波段影像。"""
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
        line_off=39.5,
        line_scale=39.5,
        long_off=126.6,
        long_scale=0.05,
        samp_den_coeff=sample_denominator,
        samp_num_coeff=sample_numerator,
        samp_off=49.5,
        samp_scale=49.5,
        err_bias=0.5,
        err_rand=0.2,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=100,
            height=80,
            count=1,
            dtype="uint16",
        ) as output:
            output.write(
                np.arange(8_000, dtype="uint16").reshape(1, 80, 100)
            )
            output.update_tags(SATELLITE="TEST-RPC-SAT")
            output.update_tags(ns="RPC", **rpc_model.to_gdal())


def write_dem_raster(path: Path, *, covers_rpc: bool = True) -> None:
    """写出覆盖或不覆盖测试 RPC 范围的实体 DEM。"""
    origin_x = 126.54 if covers_rpc else 120.0
    origin_y = 45.85 if covers_rpc else 40.0
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=120,
        height=100,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(origin_x, origin_y, 0.001, 0.001),
        nodata=-9999,
    ) as output:
        output.write(np.full((1, 100, 120), 100, dtype="float32"))


def test_engine_executes_complete_parameterized_raster_chain(
    tmp_path: Path,
) -> None:
    """验证六个步骤均生成可读取且具有真实处理结果的 GeoTIFF。"""
    engine = ImageryProcessingEngine()
    source_path = tmp_path / "source.tif"
    radiometric_path = tmp_path / "radiometric.tif"
    atmospheric_path = tmp_path / "atmospheric.tif"
    geometric_path = tmp_path / "geometric.tif"
    clipped_path = tmp_path / "clipped.tif"
    enhanced_path = tmp_path / "enhanced.tif"
    products_path = tmp_path / "products.tif"
    write_four_band_raster(source_path)

    radiometric = engine.execute(
        "radiometric",
        source_path,
        radiometric_path,
        {"scale_factor": 0.0001, "add_offset": 0},
    )
    atmospheric = engine.execute(
        "atmospheric",
        radiometric_path,
        atmospheric_path,
        {"dark_percentile": 1},
    )
    geometric = engine.execute(
        "geometric",
        atmospheric_path,
        geometric_path,
        {"target_crs": "EPSG:4490"},
    )
    clipped = engine.execute(
        "clip",
        geometric_path,
        clipped_path,
        {"boundary_code": "230000"},
        {
            "type": "Polygon",
            "coordinates": [[
                [126.52, 45.83],
                [126.58, 45.83],
                [126.58, 45.88],
                [126.52, 45.88],
                [126.52, 45.83],
            ]],
        },
    )
    enhanced = engine.execute(
        "enhancement",
        clipped_path,
        enhanced_path,
        {
            "method": "percentile_stretch",
            "lower_percentile": 2,
            "upper_percentile": 98,
        },
    )
    products = engine.execute(
        "band_products",
        enhanced_path,
        products_path,
        {"red_band": 1, "green_band": 2, "blue_band": 3, "nir_band": 4},
    )

    assert radiometric.dtype == "float32"
    assert radiometric.parameters["scale_factor"] == 0.0001
    assert atmospheric.parameters["model"] == "DOS1"
    assert len(atmospheric.parameters["dark_values"]) == 4
    assert geometric.crs == "EPSG:4490"
    assert clipped.width < geometric.width
    assert clipped.height < geometric.height
    assert enhanced.dtype == "float32"
    assert enhanced.parameters["method"] == "percentile_stretch"
    assert len(enhanced.parameters["bands"]) == 4
    assert products.band_count == 7
    with rasterio.open(products_path) as dataset:
        assert dataset.descriptions[-1] == "ndvi"
        ndvi = dataset.read(7, masked=True)
        assert ndvi.count() > 0
        assert float(ndvi.min()) >= -1
        assert float(ndvi.max()) <= 1


def test_engine_executes_histogram_equalization(tmp_path: Path) -> None:
    """验证直方图均衡化输出有限的 0–1 浮点增强栅格。"""
    source_path = tmp_path / "source.tif"
    output_path = tmp_path / "equalized.tif"
    write_four_band_raster(source_path)

    result = ImageryProcessingEngine().execute(
        "enhancement",
        source_path,
        output_path,
        {"method": "histogram_equalization", "histogram_bins": 64},
    )

    assert result.parameters["method"] == "histogram_equalization"
    assert result.parameters["histogram_bins"] == 64
    with rasterio.open(output_path) as output:
        values = output.read(masked=True)
        assert output.dtypes == ("float32",) * 4
        assert output.tags()["ENHANCEMENT_METHOD"] == "histogram_equalization"
        assert float(values.min()) >= 0
        assert float(values.max()) <= 1


def test_engine_rejects_duplicate_band_product_mapping(tmp_path: Path) -> None:
    """验证真彩色、假彩色和 NDVI 不允许复用同一波段冒充不同光谱。"""
    source_path = tmp_path / "source.tif"
    write_four_band_raster(source_path)

    with pytest.raises(ValidationException, match="四个不同波段"):
        ImageryProcessingEngine().execute(
            "band_products",
            source_path,
            tmp_path / "invalid-products.tif",
            {"red_band": 1, "green_band": 1, "blue_band": 3, "nir_band": 4},
        )


def test_engine_executes_gcp_affine_correction_with_pixel_rmse(
    tmp_path: Path,
) -> None:
    """验证 GCP 精校正生成实体网格并保存逐点像素残差。"""
    source_path = tmp_path / "source.tif"
    output_path = tmp_path / "gcp-corrected.tif"
    write_four_band_raster(source_path)
    control_points = [
        {
            "point_id": "GCP-TL",
            "pixel_column": 0,
            "pixel_row": 0,
            "x": 126.5,
            "y": 45.9,
            "source": "省级实测控制点成果",
        },
        {
            "point_id": "GCP-TR",
            "pixel_column": 9,
            "pixel_row": 0,
            "x": 126.59,
            "y": 45.9,
            "source": "省级实测控制点成果",
        },
        {
            "point_id": "GCP-BR",
            "pixel_column": 9,
            "pixel_row": 7,
            "x": 126.59,
            "y": 45.83,
            "source": "省级实测控制点成果",
        },
        {
            "point_id": "GCP-BL",
            "pixel_column": 0,
            "pixel_row": 7,
            "x": 126.5,
            "y": 45.83,
            "source": "省级实测控制点成果",
        },
    ]

    result = ImageryProcessingEngine().execute(
        "geometric",
        source_path,
        output_path,
        {
            "method": "gcp",
            "gcp_crs": "EPSG:4326",
            "target_crs": "EPSG:4490",
            "target_resolution": 0.01,
            "resampling": "cubic",
            "max_rmse_pixels": 0.1,
            "control_points": control_points,
        },
    )

    assert result.parameters["method"] == "gcp_affine"
    assert result.parameters["gcp_count"] == 4
    assert result.parameters["rmse_pixels"] < 0.000001
    assert len(result.parameters["control_points"]) == 4
    assert all(
        point["source"] == "省级实测控制点成果"
        for point in result.parameters["control_points"]
    )
    with rasterio.open(output_path) as corrected:
        tags = corrected.tags()
        assert corrected.crs.to_string() == "EPSG:4490"
        assert tags["GEOMETRIC_METHOD"] == "gcp_affine"
        assert tags["GCP_COUNT"] == "4"
        assert tags["RESAMPLING"] == "cubic"


def test_engine_rejects_collinear_or_high_residual_gcps(tmp_path: Path) -> None:
    """验证共线控制点及超过 RMSE 门槛的控制网不能产生成果。"""
    source_path = tmp_path / "source.tif"
    write_four_band_raster(source_path)
    collinear = [
        {
            "point_id": f"GCP-{index}",
            "pixel_column": index,
            "pixel_row": index,
            "x": 126.5 + index * 0.01,
            "y": 45.8 + index * 0.01,
            "source": "实测控制点",
        }
        for index in range(3)
    ]
    with pytest.raises(ValidationException, match="不能全部共线"):
        ImageryProcessingEngine().execute(
            "geometric",
            source_path,
            tmp_path / "collinear.tif",
            {"method": "gcp", "control_points": collinear},
        )

    inconsistent = [
        {
            "point_id": "GCP-TL",
            "pixel_column": 0,
            "pixel_row": 0,
            "x": 126.5,
            "y": 45.9,
            "source": "实测控制点",
        },
        {
            "point_id": "GCP-TR",
            "pixel_column": 9,
            "pixel_row": 0,
            "x": 126.59,
            "y": 45.9,
            "source": "实测控制点",
        },
        {
            "point_id": "GCP-BR",
            "pixel_column": 9,
            "pixel_row": 7,
            "x": 126.7,
            "y": 45.75,
            "source": "错误匹配点",
        },
        {
            "point_id": "GCP-BL",
            "pixel_column": 0,
            "pixel_row": 7,
            "x": 126.5,
            "y": 45.83,
            "source": "实测控制点",
        },
    ]
    with pytest.raises(ValidationException, match="超过门槛"):
        ImageryProcessingEngine().execute(
            "geometric",
            source_path,
            tmp_path / "high-rmse.tif",
            {
                "method": "gcp",
                "control_points": inconsistent,
                "max_rmse_pixels": 0.01,
            },
        )


@pytest.mark.filterwarnings(
    "ignore::rasterio.errors.NotGeoreferencedWarning"
)
def test_engine_executes_rpc_dem_orthorectification_and_preserves_rpc_chain(
    tmp_path: Path,
) -> None:
    """验证 RPC 模型跨定标/大气步骤保留，并由受控 DEM 生成正射成果。"""
    source_path = tmp_path / "rpc-source.tif"
    radiometric_path = tmp_path / "rpc-radiometric.tif"
    atmospheric_path = tmp_path / "rpc-atmospheric.tif"
    dem_path = tmp_path / "dem.tif"
    orthorectified_path = tmp_path / "rpc-ortho.tif"
    write_rpc_raster(source_path)
    write_dem_raster(dem_path)
    engine = ImageryProcessingEngine()

    engine.execute(
        "radiometric",
        source_path,
        radiometric_path,
        {"scale_factor": 0.0001, "add_offset": 0},
    )
    engine.execute(
        "atmospheric",
        radiometric_path,
        atmospheric_path,
        {"dark_percentile": 1},
    )
    with rasterio.open(atmospheric_path) as atmospheric:
        assert atmospheric.rpcs is not None
        assert atmospheric.tags()["SATELLITE"] == "TEST-RPC-SAT"

    dem_evidence = {
        "relative_path": "dem.tif",
        "file_size_bytes": dem_path.stat().st_size,
        "checksum_sha256": calculate_sha256(dem_path),
        "crs": "EPSG:4326",
    }
    result = engine.execute(
        "geometric",
        atmospheric_path,
        orthorectified_path,
        {
            "method": "rpc_dem",
            "target_crs": "EPSG:4490",
            "target_resolution": 0.001,
            "resampling": "bilinear",
            "rpc_height_offset_m": 0,
        },
        rpc_dem_path=dem_path,
        dem_evidence=dem_evidence,
    )

    assert result.parameters["method"] == "rpc_dem_orthorectification"
    assert result.parameters["rpc_checksum_sha256"]
    assert result.parameters["dem_evidence"]["checksum_sha256"] == (
        calculate_sha256(dem_path)
    )
    with rasterio.open(orthorectified_path) as orthorectified:
        tags = orthorectified.tags()
        assert orthorectified.crs.to_string() == "EPSG:4490"
        assert orthorectified.rpcs is None
        assert tags["ORTHORECTIFIED"] == "true"
        assert tags["RPC_DEM_SHA256"] == calculate_sha256(dem_path)
        assert orthorectified.read(1).max() > 0


def test_service_validates_rpc_dem_coverage_and_checksum(tmp_path: Path) -> None:
    """验证业务层只接受完整覆盖 RPC 范围的受控 DEM。"""
    source_path = tmp_path / "rpc-source.tif"
    valid_dem_path = tmp_path / "valid-dem.tif"
    invalid_dem_path = tmp_path / "invalid-dem.tif"
    write_rpc_raster(source_path)
    write_dem_raster(valid_dem_path)
    write_dem_raster(invalid_dem_path, covers_rpc=False)
    service = ImageryService()
    service.storage_dir = tmp_path

    resolved_path, evidence = service._inspect_rpc_dem(
        source_path,
        "valid-dem.tif",
    )

    assert resolved_path == valid_dem_path
    assert evidence["checksum_sha256"] == calculate_sha256(valid_dem_path)
    assert evidence["rpc_required_bounds_wgs84"] == pytest.approx(
        [126.55, 45.76, 126.65, 45.84]
    )
    with pytest.raises(ValidationException, match="未完整覆盖"):
        service._inspect_rpc_dem(source_path, "invalid-dem.tif")


def test_service_executes_step_and_persists_checksum_evidence(
    tmp_path: Path,
) -> None:
    """验证业务服务使用稳定用户编码执行并保存完整产物证据。"""
    asset_dir = tmp_path / "assets" / "DEMO-RASTER"
    asset_dir.mkdir(parents=True)
    source_path = asset_dir / "source.tif"
    write_four_band_raster(source_path)
    asset = SimpleNamespace(
        id=3,
        project_id=7,
        asset_code="DEMO-RASTER",
        asset_name="测试四波段影像",
        sensor_type="TEST-MSI",
        acquired_at=datetime(2026, 6, 18, tzinfo=UTC),
        cloud_cover=0,
        resolution_m=1000,
        processing_level="L1A",
        calibration_status="pending",
        correction_status="pending",
        file_uri="storage://imagery/assets/DEMO-RASTER/source.tif",
        file_size_bytes=source_path.stat().st_size,
        checksum_sha256=calculate_sha256(source_path),
    )
    step = SimpleNamespace(
        step_code="radiometric",
        step_name="辐射定标",
        sequence=1,
        status="pending",
        progress=0,
        parameters={
            "output": "TOA reflectance",
            "artifact_evidence": {
                "relative_path": "processed/DEMO-RASTER/old-radiometric.tif",
                "file_size_bytes": 123,
                "checksum_sha256": "old-radiometric-checksum",
            },
        },
        output_uri=None,
        started_at=None,
        completed_at=None,
        updated_at=None,
    )
    downstream_step = SimpleNamespace(
        step_code="atmospheric",
        step_name="大气校正",
        sequence=2,
        status="completed",
        progress=100,
        parameters={
            "model": "DOS1",
            "artifact_evidence": {
                "relative_path": "processed/DEMO-RASTER/old-atmospheric.tif",
                "checksum_sha256": "old-checksum",
            },
        },
        output_uri="storage://imagery/processed/DEMO-RASTER/old-atmospheric.tif",
        started_at=datetime(2026, 7, 21, tzinfo=UTC),
        completed_at=datetime(2026, 7, 21, tzinfo=UTC),
        updated_at=datetime(2026, 7, 21, tzinfo=UTC),
    )
    dao = AsyncMock()
    dao.get_asset_by_code_for_update.return_value = asset
    dao.get_asset_by_code.return_value = asset
    dao.get_step_for_update.return_value = step
    dao.get_steps.return_value = [step, downstream_step]
    workbench_dao = AsyncMock()
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
    service = ImageryService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
    )
    service.storage_dir = tmp_path
    db = AsyncMock()

    response = asyncio.run(
        service.execute_step(
            db,
            "DEMO-RASTER",
            "radiometric",
            "RS-2026-045",
            ImageryStepExecuteRequest(
                operator_code="interp-li-jing",
                parameters={"scale_factor": 0.0001, "add_offset": 0},
                comment="使用公开定标比例系数执行",
            ),
        )
    )

    evidence = step.parameters["artifact_evidence"]
    output_path = tmp_path / evidence["relative_path"]
    assert output_path.is_file()
    assert evidence["execution_mode"] == "built_in"
    assert evidence["execution_parameters"]["scale_factor"] == 0.0001
    assert evidence["output_band_count"] == 4
    assert evidence["checksum_sha256"] == calculate_sha256(output_path)
    assert step.parameters["artifact_history"][0][
        "checksum_sha256"
    ] == "old-radiometric-checksum"
    assert step.parameters["artifact_history"][0][
        "superseded_by_operator_code"
    ] == "interp-li-jing"
    assert response.steps[0].output_verified is True
    assert response.completion_rate == 50
    assert asset.calibration_status == "completed"
    assert asset.correction_status == "pending"
    assert downstream_step.status == "pending"
    assert downstream_step.output_uri is None
    assert "artifact_evidence" not in downstream_step.parameters
    assert downstream_step.parameters["artifact_history"][0][
        "superseded_by_step"
    ] == "radiometric"
    project_user_service.require_capability.assert_awaited_once_with(
        db,
        7,
        "interp-li-jing",
        "process_imagery",
    )
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_optional_enhancement_does_not_reduce_required_completion(
    tmp_path: Path,
) -> None:
    """验证未执行可选增强不会把已完成必选流水线标记为不完整。"""
    artifact_path = tmp_path / "required.tif"
    write_four_band_raster(artifact_path)
    required_step = SimpleNamespace(
        step_code="clip",
        step_name="行政区裁剪",
        sequence=4,
        is_required=True,
        status="completed",
        progress=100,
        parameters={
            "artifact_evidence": {
                "relative_path": "required.tif",
                "file_size_bytes": artifact_path.stat().st_size,
                "checksum_sha256": calculate_sha256(artifact_path),
            }
        },
        output_uri="storage://imagery/required.tif",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    optional_step = SimpleNamespace(
        step_code="enhancement",
        step_name="影像增强",
        sequence=5,
        is_required=False,
        status="pending",
        progress=0,
        parameters={"method": "optional"},
        output_uri=None,
        started_at=None,
        completed_at=None,
        updated_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.get_asset_by_code.return_value = SimpleNamespace(
        id=3,
        asset_code="OPTIONAL-ENHANCEMENT",
        asset_name="可选增强测试影像",
        sensor_type="TEST",
        acquired_at=datetime.now(UTC),
        cloud_cover=0,
        resolution_m=10,
        processing_level="L2A",
    )
    dao.get_steps.return_value = [required_step, optional_step]
    service = ImageryService(dao=dao)
    service.storage_dir = tmp_path

    response = asyncio.run(
        service.get_processing(AsyncMock(), "OPTIONAL-ENHANCEMENT")
    )

    assert response.completion_rate == 100
    assert response.completed_steps == 1
    assert response.total_steps == 1
    assert response.steps[1].is_required is False
    assert response.steps[1].output_verified is False


def test_source_level_acceptance_requires_explicit_no_algorithm_confirmation() -> None:
    """验证源级承认必须明确确认不会执行或伪造重复算法。"""
    with pytest.raises(ValidationError, match="不执行重复算法"):
        ImagerySourceLevelAcceptRequest(
            operator_code="manager-zhao-zhiyuan",
            expected_processing_level="L2A",
            confirm_no_algorithm_execution=False,
            justification="已核对 Sentinel-2 L2A 官方产品级别",
        )


def test_service_accepts_verified_l2a_source_without_copying_or_processing(
    tmp_path: Path,
) -> None:
    """验证 L2A 源级承认复用同一实体、保存依据且不调用处理引擎。"""
    asset_dir = tmp_path / "assets" / "S2B-L2A"
    asset_dir.mkdir(parents=True)
    source_path = asset_dir / "source.tif"
    write_l2a_reflectance_raster(source_path)
    asset = SimpleNamespace(
        id=8,
        project_id=7,
        asset_code="S2B-L2A",
        asset_name="Sentinel-2B L2A 公开影像",
        sensor_type="Sentinel-2B MSI",
        acquired_at=datetime(2026, 7, 16, tzinfo=UTC),
        cloud_cover=4.04,
        resolution_m=10,
        processing_level="L2A",
        calibration_status="pending",
        correction_status="pending",
        file_uri="storage://imagery/assets/S2B-L2A/source.tif",
        file_size_bytes=source_path.stat().st_size,
        checksum_sha256=calculate_sha256(source_path),
    )
    radiometric_step = SimpleNamespace(
        step_code="radiometric",
        step_name="辐射定标",
        sequence=1,
        status="pending",
        progress=0,
        parameters={},
        output_uri=None,
        started_at=None,
        completed_at=None,
        updated_at=None,
    )
    atmospheric_step = SimpleNamespace(
        step_code="atmospheric",
        step_name="大气校正",
        sequence=2,
        status="pending",
        progress=0,
        parameters={},
        output_uri=None,
        started_at=None,
        completed_at=None,
        updated_at=None,
    )
    dao = AsyncMock()
    dao.get_asset_by_code_for_update.return_value = asset
    dao.get_asset_by_code.return_value = asset
    dao.get_step_for_update.return_value = radiometric_step
    dao.get_steps.return_value = [radiometric_step, atmospheric_step]
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=7,
    )
    project_user_service = AsyncMock()
    project_user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    processing_engine = MagicMock()
    service = ImageryService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
        processing_engine=processing_engine,
    )
    service.storage_dir = tmp_path
    db = AsyncMock()

    response = asyncio.run(
        service.accept_source_level_step(
            db,
            "S2B-L2A",
            "radiometric",
            "RS-2026-045",
            ImagerySourceLevelAcceptRequest(
                operator_code="manager-zhao-zhiyuan",
                expected_processing_level="L2A",
                confirm_no_algorithm_execution=True,
                justification="STAC 标度已在导入时应用，源文件为 L2A 地表反射率",
            ),
        )
    )

    evidence = radiometric_step.parameters["artifact_evidence"]
    assert evidence["execution_mode"] == "source_level_acceptance"
    assert evidence["algorithm_executed"] is False
    assert evidence["source_evidence"]["processing_level"] == "L2A"
    assert evidence["source_evidence"]["reflectance_quantity"] == (
        "BOA_REFLECTANCE"
    )
    assert evidence["relative_path"] == "assets/S2B-L2A/source.tif"
    assert evidence["checksum_sha256"] == calculate_sha256(source_path)
    assert response.completion_rate == 50
    assert asset.calibration_status == "completed"
    assert list(tmp_path.rglob("*.tif")) == [source_path]
    processing_engine.execute.assert_not_called()
    review_record = workbench_dao.add_review_record.await_args.args[1]
    assert review_record.action == "source_level_accepted"
    assert review_record.reviewer_code == "manager-zhao-zhiyuan"
    db.commit.assert_awaited_once()


def test_service_rejects_l2a_source_without_applied_stac_scale(
    tmp_path: Path,
) -> None:
    """验证仍为量化 DN 的 L2A 文件不能绕过辐射定标。"""
    source_path = tmp_path / "source.tif"
    write_l2a_reflectance_raster(source_path, scale_applied=False)
    asset = SimpleNamespace(
        id=8,
        project_id=7,
        asset_code="S2B-L2A",
        processing_level="L2A",
        file_uri="storage://imagery/source.tif",
        file_size_bytes=source_path.stat().st_size,
        checksum_sha256=calculate_sha256(source_path),
    )
    step = SimpleNamespace(
        step_code="radiometric",
        step_name="辐射定标",
        sequence=1,
        status="pending",
        progress=0,
        parameters={},
        output_uri=None,
        started_at=None,
        completed_at=None,
        updated_at=None,
    )
    dao = AsyncMock()
    dao.get_asset_by_code_for_update.return_value = asset
    dao.get_step_for_update.return_value = step
    dao.get_steps.return_value = [step]
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(
        id=1,
        project_id=7,
    )
    project_user_service = AsyncMock()
    project_user_service.require_capability.return_value = SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code="project_manager",
    )
    service = ImageryService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=project_user_service,
    )
    service.storage_dir = tmp_path

    with pytest.raises(ValidationException, match="尚未应用 STAC 反射率标度"):
        asyncio.run(
            service.accept_source_level_step(
                AsyncMock(),
                "S2B-L2A",
                "radiometric",
                "RS-2026-045",
                ImagerySourceLevelAcceptRequest(
                    operator_code="manager-zhao-zhiyuan",
                    expected_processing_level="L2A",
                    confirm_no_algorithm_execution=True,
                    justification="准备核对源产品级别并承认定标要求已经满足",
                ),
            )
        )
