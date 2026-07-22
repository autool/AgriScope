"""多光谱与全色实体融合引擎测试。"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.core.exceptions import ValidationException
from app.core.imagery_files import calculate_sha256
from app.schemas.imagery_fusion import ImageryFusionCreateRequest
from app.services.imagery_fusion_engine import FusionSource, ImageryFusionEngine
from app.services.imagery_fusion_service import ImageryFusionService


def write_multispectral(path: Path) -> None:
    """写出三个具有真实空间渐变的 30 米多光谱波段。"""
    rows, columns = np.mgrid[0:60, 0:60].astype("float32")
    red = 0.12 + columns / 600 + rows / 1200
    green = 0.10 + columns / 800 + rows / 700
    blue = 0.08 + columns / 1000 + rows / 900
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=60,
        height=60,
        count=3,
        dtype="float32",
        crs="EPSG:32652",
        transform=from_origin(500000, 5200000, 30, 30),
        nodata=np.nan,
    ) as dataset:
        dataset.write(np.stack([red, green, blue]))
        dataset.descriptions = ("Red", "Green", "Blue")
        dataset.update_tags(
            RADIOMETRIC_CALIBRATION_APPLIED="true",
            REFLECTANCE_QUANTITY="TOA_REFLECTANCE",
            SOURCE_PRODUCT_URI="LANDSAT-SAME-SCENE",
        )


def write_panchromatic(path: Path) -> None:
    """写出同范围、含高频空间细节的 15 米全色波段。"""
    rows, columns = np.mgrid[0:120, 0:120].astype("float32")
    low_frequency = 0.11 + columns / 1400 + rows / 1700
    checker = ((rows.astype("int32") // 4 + columns.astype("int32") // 4) % 2)
    pan = low_frequency + checker.astype("float32") * 0.035
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=120,
        height=120,
        count=1,
        dtype="float32",
        crs="EPSG:32652",
        transform=from_origin(500000, 5200000, 15, 15),
        nodata=np.nan,
    ) as dataset:
        dataset.write(pan, 1)
        dataset.descriptions = ("Panchromatic",)
        dataset.update_tags(
            RADIOMETRIC_CALIBRATION_APPLIED="true",
            REFLECTANCE_QUANTITY="TOA_REFLECTANCE",
            SOURCE_PRODUCT_URI="LANDSAT-SAME-SCENE",
        )


def source(path: Path, code: str) -> FusionSource:
    """构造测试实体来源。"""
    return FusionSource(
        path=path,
        asset_code=code,
        source_uri=f"storage://imagery/{path.name}",
        source_size_bytes=path.stat().st_size,
        source_sha256=code.lower().ljust(64, "0")[:64],
    )


def imagery_asset(
    path: Path,
    code: str,
    acquired_at: datetime,
    *,
    data_status: str = "operational",
) -> SimpleNamespace:
    """构造带真实文件大小和 SHA-256 的影像资产。

    Args:
        path: 影像实体路径。
        code: 资产编号。
        acquired_at: 采集时间。
        data_status: 数据状态。

    Returns:
        SimpleNamespace: 服务测试使用的资产对象。
    """
    with rasterio.open(path) as dataset:
        return SimpleNamespace(
            id=10 if dataset.count > 1 else 11,
            asset_code=code,
            asset_name=code,
            sensor_type="Landsat-9 OLI",
            acquired_at=acquired_at,
            data_status=data_status,
            file_uri=f"storage://imagery/assets/{code}/source.tif",
            file_size_bytes=path.stat().st_size,
            checksum_sha256=calculate_sha256(path),
            crs=dataset.crs.to_string(),
            raster_width=dataset.width,
            raster_height=dataset.height,
            band_count=dataset.count,
            _test_path=path,
        )


def fusion_request(job_code: str) -> ImageryFusionCreateRequest:
    """构造完整的融合服务请求。

    Args:
        job_code: 融合任务编号。

    Returns:
        ImageryFusionCreateRequest: 通过 Schema 校验的请求。
    """
    return ImageryFusionCreateRequest(
        job_code=job_code,
        job_name="Landsat 同景全色融合",
        multispectral_asset_code="LANDSAT-MS",
        panchromatic_asset_code="LANDSAT-PAN",
        multispectral_band_indexes=[1, 2, 3],
        panchromatic_band_index=1,
        resampling_method="cubic",
        minimum_overlap_ratio=0.95,
        minimum_spectral_correlation=0.75,
        minimum_spatial_detail_gain=1.05,
        gain_limit=4,
        operator_code="manager-zhao-zhiyuan",
        comment="使用同景已定标 Landsat 多光谱与全色实体执行融合验收",
    )


def fusion_service(
    tmp_path: Path,
    multispectral_asset: SimpleNamespace,
    panchromatic_asset: SimpleNamespace,
) -> tuple[ImageryFusionService, AsyncMock]:
    """构造带项目、用户和实体路径解析的融合服务。

    Args:
        tmp_path: 测试临时目录。
        multispectral_asset: 多光谱资产。
        panchromatic_asset: 全色资产。

    Returns:
        tuple[ImageryFusionService, AsyncMock]: 服务与 DAO Mock。
    """
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    asset_service = MagicMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=1)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(id=2, project_id=1)
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )
    dao.get_job.return_value = None
    dao.get_asset.side_effect = [multispectral_asset, panchromatic_asset]
    asset_service.resolve_verified_asset_path.side_effect = [
        multispectral_asset._test_path,
        panchromatic_asset._test_path,
    ]
    service = ImageryFusionService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        asset_service=asset_service,
        engine=ImageryFusionEngine(max_output_pixels=20_000),
    )
    service.storage_root = tmp_path / "fusion-output"
    return service, dao


def test_fusion_engine_writes_high_resolution_artifact(tmp_path: Path) -> None:
    """验证融合输出采用全色网格并通过光谱和空间细节门禁。"""
    multispectral_path = tmp_path / "multispectral.tif"
    panchromatic_path = tmp_path / "panchromatic.tif"
    output_path = tmp_path / "fused.tif"
    write_multispectral(multispectral_path)
    write_panchromatic(panchromatic_path)

    result = ImageryFusionEngine(max_output_pixels=20_000).execute(
        multispectral=source(multispectral_path, "MS"),
        panchromatic=source(panchromatic_path, "PAN"),
        output_path=output_path,
        multispectral_band_indexes=[1, 2, 3],
        panchromatic_band_index=1,
        resampling_method="cubic",
        minimum_overlap_ratio=0.95,
        minimum_spectral_correlation=0.75,
        minimum_spatial_detail_gain=1.05,
        gain_limit=4,
        job_code="FUSION-001",
    )

    assert output_path.is_file()
    assert result.width == 120
    assert result.height == 120
    assert result.band_count == 3
    assert result.overlap_ratio == 1
    assert result.minimum_spectral_correlation >= 0.75
    assert result.spatial_detail_gain >= 1.05
    with rasterio.open(output_path) as output:
        assert output.count == 3
        assert output.res == (15, 15)
        assert output.tags()["FUSION_ALGORITHM"] == "brovey_histogram_match"


def test_fusion_engine_rejects_non_finer_pan(tmp_path: Path) -> None:
    """验证全色分辨率没有明显优势时不能用重采样冒充融合。"""
    multispectral_path = tmp_path / "multispectral.tif"
    panchromatic_path = tmp_path / "not-finer-pan.tif"
    output_path = tmp_path / "fused.tif"
    write_multispectral(multispectral_path)
    write_multispectral(panchromatic_path)

    with pytest.raises(ValidationException, match="至少优于多光谱 1.5 倍"):
        ImageryFusionEngine().execute(
            multispectral=source(multispectral_path, "MS"),
            panchromatic=source(panchromatic_path, "PAN"),
            output_path=output_path,
            multispectral_band_indexes=[1, 2, 3],
            panchromatic_band_index=1,
            resampling_method="bilinear",
            minimum_overlap_ratio=0.95,
            minimum_spectral_correlation=0.8,
            minimum_spatial_detail_gain=1.05,
            gain_limit=4,
            job_code="FUSION-002",
        )

    assert not output_path.exists()


def test_fusion_service_persists_real_quality_evidence(tmp_path: Path) -> None:
    """验证服务重新核验同景来源并保存服务端计算的融合质量证据。"""
    multispectral_path = tmp_path / "multispectral.tif"
    panchromatic_path = tmp_path / "panchromatic.tif"
    write_multispectral(multispectral_path)
    write_panchromatic(panchromatic_path)
    acquired_at = datetime.now(UTC)
    ms_asset = SimpleNamespace(
        id=10,
        asset_code="LANDSAT-MS",
        asset_name="Landsat 多光谱",
        sensor_type="Landsat-9 OLI",
        acquired_at=acquired_at,
        data_status="operational",
        file_uri="storage://imagery/assets/LANDSAT-MS/source.tif",
        file_size_bytes=multispectral_path.stat().st_size,
        checksum_sha256=calculate_sha256(multispectral_path),
        crs="EPSG:32652",
        raster_width=60,
        raster_height=60,
        band_count=3,
    )
    pan_asset = SimpleNamespace(
        id=11,
        asset_code="LANDSAT-PAN",
        asset_name="Landsat 全色",
        sensor_type="Landsat-9 OLI",
        acquired_at=acquired_at,
        data_status="operational",
        file_uri="storage://imagery/assets/LANDSAT-PAN/source.tif",
        file_size_bytes=panchromatic_path.stat().st_size,
        checksum_sha256=calculate_sha256(panchromatic_path),
        crs="EPSG:32652",
        raster_width=120,
        raster_height=120,
        band_count=1,
    )
    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    asset_service = MagicMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=1)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(id=2, project_id=1)
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )
    dao.get_job.return_value = None
    dao.get_asset.side_effect = [ms_asset, pan_asset]
    asset_service.resolve_verified_asset_path.side_effect = [
        multispectral_path,
        panchromatic_path,
    ]

    async def add_job(_: object, job: object) -> object:
        job.id = 20
        job.created_at = acquired_at
        return job

    dao.add_job.side_effect = add_job
    service = ImageryFusionService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        asset_service=asset_service,
        engine=ImageryFusionEngine(max_output_pixels=20_000),
    )
    service.storage_root = tmp_path / "fusion-output"
    request = ImageryFusionCreateRequest(
        job_code="FUSION-REAL-001",
        job_name="Landsat 同景全色融合",
        multispectral_asset_code="LANDSAT-MS",
        panchromatic_asset_code="LANDSAT-PAN",
        multispectral_band_indexes=[1, 2, 3],
        panchromatic_band_index=1,
        resampling_method="cubic",
        minimum_overlap_ratio=0.95,
        minimum_spectral_correlation=0.75,
        minimum_spatial_detail_gain=1.05,
        gain_limit=4,
        operator_code="manager-zhao-zhiyuan",
        comment="使用同景已定标 Landsat 多光谱与全色实体执行融合验收",
    )

    response = asyncio.run(
        service.create_job(AsyncMock(), "RS-2026", "RS-2026-045", request)
    )

    assert response.artifact_verified is True
    assert response.output_resolution_x == 15
    assert response.minimum_spectral_correlation >= 0.75
    assert response.spatial_detail_gain >= 1.05
    saved_job = dao.add_job.await_args.args[1]
    assert saved_job.manifest["multispectral"]["product_identity"] == (
        "LANDSAT-SAME-SCENE"
    )
    assert saved_job.manifest["output_sha256"] == response.checksum_sha256
    event = dao.add_event.await_args.args[1]
    assert event.event_type == "fusion_completed"


def test_fusion_service_rejects_different_product_identity(tmp_path: Path) -> None:
    """验证不同产品身份的多光谱与全色实体不能被拼成同景融合。"""
    multispectral_path = tmp_path / "multispectral.tif"
    panchromatic_path = tmp_path / "panchromatic.tif"
    write_multispectral(multispectral_path)
    write_panchromatic(panchromatic_path)
    with rasterio.open(panchromatic_path, "r+") as dataset:
        dataset.update_tags(SOURCE_PRODUCT_URI="LANDSAT-OTHER-SCENE")
    acquired_at = datetime.now(UTC)
    service, dao = fusion_service(
        tmp_path,
        imagery_asset(multispectral_path, "LANDSAT-MS", acquired_at),
        imagery_asset(panchromatic_path, "LANDSAT-PAN", acquired_at),
    )

    with pytest.raises(ValidationException, match="必须来自同一可追溯产品"):
        asyncio.run(
            service.create_job(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                fusion_request("FUSION-DIFFERENT-PRODUCT"),
            )
        )

    dao.add_job.assert_not_awaited()


def test_fusion_service_rejects_demo_source(tmp_path: Path) -> None:
    """验证带实体和标签的演示影像仍不能作为正式融合来源。"""
    multispectral_path = tmp_path / "multispectral.tif"
    panchromatic_path = tmp_path / "panchromatic.tif"
    write_multispectral(multispectral_path)
    write_panchromatic(panchromatic_path)
    acquired_at = datetime.now(UTC)
    service, dao = fusion_service(
        tmp_path,
        imagery_asset(
            multispectral_path,
            "LANDSAT-MS",
            acquired_at,
            data_status="demo",
        ),
        imagery_asset(panchromatic_path, "LANDSAT-PAN", acquired_at),
    )

    with pytest.raises(ValidationException, match="演示影像不能作为正式融合输入"):
        asyncio.run(
            service.create_job(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                fusion_request("FUSION-DEMO-SOURCE"),
            )
        )

    dao.add_job.assert_not_awaited()


def test_fusion_service_rejects_acquisition_gap_over_sixty_seconds(
    tmp_path: Path,
) -> None:
    """验证同产品两类来源的采集时间相差超过一分钟时被拒绝。"""
    multispectral_path = tmp_path / "multispectral.tif"
    panchromatic_path = tmp_path / "panchromatic.tif"
    write_multispectral(multispectral_path)
    write_panchromatic(panchromatic_path)
    acquired_at = datetime.now(UTC)
    service, dao = fusion_service(
        tmp_path,
        imagery_asset(multispectral_path, "LANDSAT-MS", acquired_at),
        imagery_asset(
            panchromatic_path,
            "LANDSAT-PAN",
            acquired_at + timedelta(seconds=61),
        ),
    )

    with pytest.raises(ValidationException, match="采集时间相差超过 60 秒"):
        asyncio.run(
            service.create_job(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                fusion_request("FUSION-TIME-GAP"),
            )
        )

    dao.add_job.assert_not_awaited()


def test_fusion_download_rechecks_physical_sha256(tmp_path: Path) -> None:
    """验证下载前发现同大小实体内容被篡改时拒绝提供成果。"""
    storage_root = tmp_path / "imagery-fusion"
    output_path = storage_root / "jobs" / "FUSION-TAMPERED" / "result.tif"
    output_path.parent.mkdir(parents=True)
    write_multispectral(output_path)
    original_size = output_path.stat().st_size
    original_sha256 = calculate_sha256(output_path)
    with output_path.open("r+b") as output:
        output.seek(256)
        current = output.read(1)
        output.seek(256)
        output.write(bytes([current[0] ^ 0x01]))
    assert output_path.stat().st_size == original_size
    assert calculate_sha256(output_path) != original_sha256

    dao = AsyncMock()
    workbench_dao = AsyncMock()
    user_service = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=1)
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )
    dao.get_job.return_value = SimpleNamespace(
        id=20,
        output_uri="storage://imagery-fusion/jobs/FUSION-TAMPERED/result.tif",
        file_size_bytes=original_size,
        checksum_sha256=original_sha256,
    )
    service = ImageryFusionService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
    )
    service.storage_root = storage_root

    with pytest.raises(ValidationException, match="SHA-256 与登记值不一致"):
        asyncio.run(
            service.get_download(
                AsyncMock(),
                "RS-2026",
                "FUSION-TAMPERED",
                "manager-zhao-zhiyuan",
            )
        )

    dao.add_event.assert_not_awaited()
