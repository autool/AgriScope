"""双景自动配准、残差门禁和实体证据测试。"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.transform import from_origin

from app.core.exceptions import ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.imagery_registration_dao import RegistrationSourceRecord
from app.schemas.imagery_registration import (
    ImageryRegistrationCreateRequest,
    ImageryRegistrationSourceRequest,
)
from app.services.imagery_registration_engine import (
    ImageryRegistrationEngine,
    RegistrationSource,
)
from app.services.imagery_registration_service import ImageryRegistrationService
from app.services.imagery_service import ImageryService


def textured_raster() -> np.ndarray:
    """构造具有多尺度纹理且可重复的两波段测试栅格。"""
    generator = np.random.default_rng(20260722)
    noise = generator.normal(0, 1, (128, 128)).astype("float32")
    first = (
        noise
        + np.roll(noise, 1, axis=0) * 0.45
        + np.roll(noise, 2, axis=1) * 0.3
    ).astype("float32")
    second = (
        first * 0.7
        + np.roll(first, 3, axis=0) * 0.2
        + np.roll(first, 2, axis=1) * 0.1
    ).astype("float32")
    return np.stack([first, second])


def write_registration_raster(path: Path, data: np.ndarray) -> None:
    """写出统一参考网格的两波段浮点 GeoTIFF。"""
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[2],
        height=data.shape[1],
        count=data.shape[0],
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(126, 46, 0.001, 0.001),
        nodata=np.nan,
    ) as output:
        output.write(data)
        output.descriptions = ("red", "nir")


def registration_sources(
    tmp_path: Path,
) -> tuple[RegistrationSource, RegistrationSource]:
    """写出参考景和向右 5、向下 3 像素偏移的待配准景。"""
    reference_path = tmp_path / "reference.tif"
    moving_path = tmp_path / "moving.tif"
    reference_data = textured_raster()
    moving_data = np.full(reference_data.shape, np.nan, dtype="float32")
    moving_data[:, 3:, 5:] = reference_data[:, :-3, :-5]
    write_registration_raster(reference_path, reference_data)
    write_registration_raster(moving_path, moving_data)
    return (
        RegistrationSource(
            asset_id=1,
            asset_code="REFERENCE-A",
            asset_name="参考影像 A",
            step_code="clip",
            step_name="行政区裁剪",
            path=reference_path,
            source_uri="storage://imagery/reference.tif",
            source_size_bytes=reference_path.stat().st_size,
            source_sha256=calculate_sha256(reference_path),
        ),
        RegistrationSource(
            asset_id=2,
            asset_code="MOVING-B",
            asset_name="待配准影像 B",
            step_code="clip",
            step_name="行政区裁剪",
            path=moving_path,
            source_uri="storage://imagery/moving.tif",
            source_size_bytes=moving_path.stat().st_size,
            source_sha256=calculate_sha256(moving_path),
        ),
    )


def test_registration_engine_estimates_shift_and_passes_residual_gate(
    tmp_path: Path,
) -> None:
    """验证服务端自动估计位移、写出参考网格实体并复算残差。"""
    reference, moving = registration_sources(tmp_path)
    output_path = tmp_path / "registered.tif"

    result = ImageryRegistrationEngine(
        max_output_pixels=100_000,
        preview_max_dimension=512,
    ).execute(
        reference,
        moving,
        output_path,
        1,
        1,
        "bilinear",
        20,
        0.75,
        0.5,
        3,
        "REG-TEST-001",
    )

    assert output_path.is_file()
    assert result.initial_shift_x_pixels == pytest.approx(-5, abs=0.4)
    assert result.initial_shift_y_pixels == pytest.approx(-3, abs=0.4)
    assert result.initial_offset_pixels == pytest.approx(5.83, abs=0.5)
    assert result.residual_offset_pixels <= 0.75
    assert result.peak_to_sidelobe_ratio >= 3
    with rasterio.open(output_path) as output:
        assert output.transform == from_origin(126, 46, 0.001, 0.001)
        assert output.tags()["PROCESSING_STEP"] == "imagery_registration"
        assert output.tags()["REFERENCE_SHA256"] == reference.source_sha256
        assert output.tags()["MOVING_SHA256"] == moving.source_sha256


def test_registration_engine_rejects_constant_band_and_pixel_limit(
    tmp_path: Path,
) -> None:
    """验证无纹理波段和超限网格不会留下部分配准文件。"""
    reference, moving = registration_sources(tmp_path)
    constant_path = tmp_path / "constant.tif"
    write_registration_raster(
        constant_path,
        np.ones((2, 128, 128), dtype="float32"),
    )
    constant_source = RegistrationSource(
        asset_id=3,
        asset_code="CONSTANT-C",
        asset_name="常量影像 C",
        step_code="clip",
        step_name="行政区裁剪",
        path=constant_path,
        source_uri="storage://imagery/constant.tif",
        source_size_bytes=constant_path.stat().st_size,
        source_sha256=calculate_sha256(constant_path),
    )
    constant_output = tmp_path / "constant-output.tif"
    with pytest.raises(ValidationException, match="动态范围"):
        ImageryRegistrationEngine(max_output_pixels=100_000).execute(
            reference,
            constant_source,
            constant_output,
            1,
            1,
            "nearest",
            20,
            1,
            0.5,
            3,
            "REG-CONSTANT",
        )
    assert not constant_output.exists()

    oversized_output = tmp_path / "oversized.tif"
    with pytest.raises(ValidationException, match="超过上限"):
        ImageryRegistrationEngine(max_output_pixels=10_000).execute(
            reference,
            moving,
            oversized_output,
            1,
            1,
            "nearest",
            20,
            1,
            0.5,
            3,
            "REG-LARGE",
        )
    assert not oversized_output.exists()


def test_registration_schema_rejects_same_asset() -> None:
    """验证同一资产不能同时充当参考景和待配准景。"""
    source = ImageryRegistrationSourceRequest(
        asset_code="SAME-ASSET",
        step_code="clip",
        band_index=1,
    )
    with pytest.raises(ValidationError, match="不能相同"):
        ImageryRegistrationCreateRequest(
            job_code="REG-SAME",
            job_name="同景配准拒绝测试",
            reference=source,
            moving=source,
            operator_code="manager-zhao-zhiyuan",
            comment="验证服务端拒绝同一影像资产自我配准",
        )


def test_registration_service_persists_rule_checksum_and_role(
    tmp_path: Path,
) -> None:
    """验证服务层保存项目规则门槛、双景校验值和稳定用户角色。"""
    reference, moving = registration_sources(tmp_path)
    records = []
    for source in (reference, moving):
        records.append(RegistrationSourceRecord(
            asset=SimpleNamespace(
                id=source.asset_id,
                asset_code=source.asset_code,
                asset_name=source.asset_name,
                data_status="operational",
                acquired_at=datetime.now(UTC),
            ),
            step=SimpleNamespace(
                step_code=source.step_code,
                step_name=source.step_name,
                output_uri=source.source_uri,
                sequence=4,
                parameters={
                    "artifact_evidence": {
                        "relative_path": source.path.name,
                        "file_size_bytes": source.source_size_bytes,
                        "checksum_sha256": source.source_sha256,
                    }
                },
            ),
        ))
    dao = AsyncMock()
    dao.get_job_by_code.return_value = None
    dao.list_source_records.return_value = records

    async def add_job(_: object, job: object) -> object:
        job.id = 5
        job.created_at = datetime.now(UTC)
        return job

    dao.add_job.side_effect = add_job
    workbench_dao = AsyncMock()
    workbench_dao.get_project_by_code.return_value = SimpleNamespace(id=7)
    workbench_dao.get_task_by_code.return_value = SimpleNamespace(id=3, project_id=7)
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )
    rule_service = AsyncMock()
    rule_service.ensure_for_project.return_value = SimpleNamespace(
        positional_accuracy_pixels=2,
        version=4,
    )
    imagery_service = ImageryService()
    imagery_service.storage_dir = tmp_path
    service = ImageryRegistrationService(
        dao=dao,
        workbench_dao=workbench_dao,
        user_service=user_service,
        rule_service=rule_service,
        imagery_service=imagery_service,
        engine=ImageryRegistrationEngine(
            max_output_pixels=100_000,
            preview_max_dimension=512,
        ),
    )
    service.storage_root = tmp_path / "registrations"
    db = AsyncMock()

    response = asyncio.run(service.create_job(
        db,
        "RS-2026",
        "RS-2026-045",
        ImageryRegistrationCreateRequest(
            job_code="REG-SERVICE-001",
            job_name="服务层实体配准测试",
            reference=ImageryRegistrationSourceRequest(
                asset_code=reference.asset_code,
                step_code="clip",
                band_index=1,
            ),
            moving=ImageryRegistrationSourceRequest(
                asset_code=moving.asset_code,
                step_code="clip",
                band_index=1,
            ),
            max_residual_pixels=3,
            minimum_overlap_ratio=0.5,
            minimum_peak_to_sidelobe_ratio=3,
            operator_code="manager-zhao-zhiyuan",
            comment="使用两景真实步骤实体执行自动配准并按项目规则验收",
        ),
    ))

    assert response.residual_threshold_pixels == 2
    assert response.residual_offset_pixels <= 2
    assert len(response.checksum_sha256) == 64
    assert response.created_by_code == "manager-zhao-zhiyuan"
    assert response.created_by_role == "project_manager"
    saved_job = dao.add_job.await_args.args[1]
    assert saved_job.reference_sha256 == reference.source_sha256
    assert saved_job.moving_sha256 == moving.source_sha256
    assert saved_job.manifest["project_rule_version"] == 4
    dao.add_event.assert_awaited_once()
    db.commit.assert_awaited_once()
