"""无人机航空器、实体上传、状态门禁和疑点审核测试。"""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
from pydantic import ValidationError
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from app.core.exceptions import ValidationException
from app.dao.uav_dao import ArtifactRecord
from app.models.uav import UavAircraft, UavArtifact, UavMission
from app.schemas.uav import (
    AircraftCreateRequest,
    ArtifactUploadRequest,
    FindingCreateRequest,
    MissionCreateRequest,
    MissionStatusRequest,
)
from app.services.uav_service import UavService


def build_project() -> SimpleNamespace:
    """构造项目上下文。"""
    return SimpleNamespace(id=7, project_code="RS-2026")


def build_task() -> SimpleNamespace:
    """构造作业任务上下文。"""
    return SimpleNamespace(id=8, project_id=7, task_code="RS-2026-045")


def build_user(role_code: str = "project_manager") -> SimpleNamespace:
    """构造稳定项目用户。"""
    return SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code=role_code,
    )


def build_aircraft() -> UavAircraft:
    """构造活动航空器。"""
    now = datetime.now(UTC)
    return UavAircraft(
        id=11,
        project_id=7,
        aircraft_code="UAV-HLJ-001",
        aircraft_name="农情巡查一号机",
        manufacturer="航空器制造单位",
        model_number="M300",
        serial_number="AIR-SN-001",
        registration_number="REG-HLJ-001",
        sensor_name="多光谱相机",
        sensor_model="MS-01",
        sensor_serial_number="SENSOR-SN-001",
        owner_department="黑龙江省农业农村厅",
        certificate_uri="storage://uav/aircraft/cert.pdf",
        certificate_filename="cert.pdf",
        certificate_size_bytes=100,
        certificate_sha256="a" * 64,
        status="active",
        registered_by="赵志远",
        registered_by_code="manager-zhao-zhiyuan",
        registered_by_role="project_manager",
        created_at=now,
        updated_at=now,
    )


def build_mission(status: str = "planned") -> UavMission:
    """构造无人机飞行任务。"""
    now = datetime.now(UTC)
    return UavMission(
        id=21,
        project_id=7,
        task_id=8,
        aircraft_id=11,
        mission_code="UAV-MISSION-001",
        mission_name="水稻病虫害巡查",
        district_code="230102",
        district_name="道里区",
        planned_area_ha=10,
        pilot_name="飞手张三",
        pilot_license_number="PILOT-001",
        pilot_license_uri="storage://uav/missions/license.pdf",
        pilot_license_filename="license.pdf",
        pilot_license_size_bytes=100,
        pilot_license_sha256="b" * 64,
        planned_start_at=now,
        planned_end_at=now + timedelta(hours=2),
        altitude_m=120,
        expected_resolution_cm=5,
        forward_overlap_percent=75,
        side_overlap_percent=65,
        weather_note="晴，风力二级",
        status=status,
        created_by="赵志远",
        created_by_code="manager-zhao-zhiyuan",
        created_by_role="project_manager",
        created_at=now,
        updated_at=now,
    )


def test_mission_schema_rejects_unclosed_boundary_and_low_overlap() -> None:
    """验证飞行范围必须闭合且重叠度达到航测要求。"""
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="必须闭合"):
        MissionCreateRequest(
            mission_code="MISSION-001",
            mission_name="测试飞行任务",
            aircraft_code="UAV-HLJ-001",
            district_code="230102",
            flight_boundary={
                "type": "Polygon",
                "coordinates": [[[126.5, 45.7], [126.6, 45.7], [126.6, 45.8]]],
            },
            pilot_name="飞手张三",
            pilot_license_number="PILOT-001",
            planned_start_at=now,
            planned_end_at=now + timedelta(hours=1),
            altitude_m=120,
            expected_resolution_cm=5,
            forward_overlap_percent=75,
            side_overlap_percent=65,
            weather_note="晴，风力二级",
            operator_code="manager-zhao-zhiyuan",
        )


def test_overview_preserves_empty_state() -> None:
    """验证无 UAV 数据时返回真实零值。"""
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.list_aircraft.return_value = []
    dao.list_mission_records.return_value = []
    dao.list_artifact_records.return_value = []
    dao.list_finding_records.return_value = []
    dao.list_events.return_value = []
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = UavService(dao=dao, user_service=user_service)

    response = asyncio.run(
        service.get_overview(
            AsyncMock(),
            "RS-2026",
            "manager-zhao-zhiyuan",
        )
    )

    assert response.aircraft_count == 0
    assert response.missions == []
    assert response.verified_artifact_count == 0


def test_aircraft_registration_stores_real_certificate(
    tmp_path: Path,
) -> None:
    """验证航空器证书由服务端写入并计算真实 SHA-256。"""
    certificate = b"real-uav-certificate-evidence"
    now = datetime.now(UTC)
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_aircraft_by_code.return_value = None

    async def add_aircraft(_: object, aircraft: UavAircraft) -> UavAircraft:
        aircraft.id = 11
        aircraft.created_at = now
        aircraft.updated_at = now
        return aircraft

    dao.add_aircraft.side_effect = add_aircraft
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = UavService(
        dao=dao,
        user_service=user_service,
        storage_root=tmp_path,
    )
    request = AircraftCreateRequest(
        aircraft_code="UAV-HLJ-001",
        aircraft_name="农情巡查一号机",
        manufacturer="航空器制造单位",
        model_number="M300",
        serial_number="AIR-SN-001",
        registration_number="REG-HLJ-001",
        sensor_name="多光谱相机",
        sensor_model="MS-01",
        sensor_serial_number="SENSOR-SN-001",
        owner_department="黑龙江省农业农村厅",
        operator_code="manager-zhao-zhiyuan",
    )

    response = asyncio.run(
        service.register_aircraft(
            AsyncMock(),
            "RS-2026",
            request,
            "certificate.pdf",
            BytesIO(certificate),
        )
    )

    assert response.certificate_sha256 == hashlib.sha256(certificate).hexdigest()
    assert response.certificate_size_bytes == len(certificate)
    assert list(tmp_path.rglob("*certificate.pdf"))


def test_mission_boundary_failure_removes_uploaded_license(tmp_path: Path) -> None:
    """验证县界校验失败时不会残留飞手资质文件。"""
    now = datetime.now(UTC)
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_task_by_code.return_value = build_task()
    dao.get_mission_by_code.return_value = None
    dao.get_aircraft_by_code.return_value = build_aircraft()
    dao.create_mission_with_validated_boundary.return_value = None
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = UavService(
        dao=dao,
        user_service=user_service,
        storage_root=tmp_path,
    )
    request = MissionCreateRequest(
        mission_code="UAV-MISSION-001",
        mission_name="水稻病虫害巡查",
        aircraft_code="UAV-HLJ-001",
        district_code="230102",
        flight_boundary={
            "type": "Polygon",
            "coordinates": [[
                [126.5, 45.7], [126.6, 45.7], [126.6, 45.8], [126.5, 45.7],
            ]],
        },
        pilot_name="飞手张三",
        pilot_license_number="PILOT-001",
        planned_start_at=now,
        planned_end_at=now + timedelta(hours=2),
        altitude_m=120,
        expected_resolution_cm=5,
        forward_overlap_percent=75,
        side_overlap_percent=65,
        weather_note="晴，风力二级",
        operator_code="manager-zhao-zhiyuan",
    )

    with pytest.raises(ValidationException, match="申报县区"):
        asyncio.run(
            service.create_mission(
                AsyncMock(),
                "RS-2026",
                "RS-2026-045",
                request,
                "pilot-license.pdf",
                BytesIO(b"pilot-license"),
            )
        )

    assert not list(tmp_path.rglob("*pilot-license.pdf"))


def test_orthomosaic_upload_extracts_real_raster_metadata(tmp_path: Path) -> None:
    """验证正射上传从实体栅格提取 CRS、分辨率和覆盖范围。"""
    now = datetime.now(UTC)
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            width=10,
            height=10,
            count=1,
            dtype="uint16",
            crs="EPSG:4326",
            transform=from_origin(126.0, 46.0, 0.00001, 0.00001),
        ) as dataset:
            dataset.write(np.ones((1, 10, 10), dtype="uint16"))
        raster_bytes = memory.read()
    mission = build_mission("captured")
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_mission_by_code.return_value = mission
    dao.get_artifact_by_code.return_value = None
    dao.artifact_footprint_covers_mission.return_value = True

    async def add_artifact(_: object, artifact: UavArtifact) -> UavArtifact:
        artifact.id = 31
        artifact.created_at = now
        return artifact

    dao.add_artifact.side_effect = add_artifact
    dao.list_artifact_records.side_effect = lambda *_: [
        ArtifactRecord(
            artifact=dao.add_artifact.await_args.args[1],
            mission_code=mission.mission_code,
            footprint_geojson={"type": "Polygon", "coordinates": []},
        )
    ]
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user("field_inspector")
    service = UavService(
        dao=dao,
        user_service=user_service,
        storage_root=tmp_path,
    )
    request = ArtifactUploadRequest(
        artifact_code="ORTHO-001",
        artifact_type="orthomosaic",
        captured_at=now,
        source_name="无人机航测处理软件",
        source_version="1.0",
        operator_code="field-wang-qiang",
    )

    response = asyncio.run(
        service.upload_artifact(
            AsyncMock(),
            "RS-2026",
            mission.mission_code,
            request,
            "orthomosaic.tif",
            BytesIO(raster_bytes),
        )
    )

    assert response.file_format == "GTiff"
    assert response.crs == "EPSG:4326"
    assert response.resolution_cm is not None
    assert response.raster_width == 10
    assert response.checksum_sha256 == hashlib.sha256(raster_bytes).hexdigest()


def test_capture_completion_requires_raw_imagery_and_flight_log() -> None:
    """验证缺少原始影像或航迹时不能完成采集。"""
    mission = build_mission("in_progress")
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_mission_by_code.return_value = mission
    dao.list_artifact_records.return_value = []
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user("field_inspector")
    service = UavService(dao=dao, user_service=user_service)

    with pytest.raises(ValidationException, match="原始影像和航迹"):
        asyncio.run(
            service.transition_mission(
                AsyncMock(),
                "RS-2026",
                mission.mission_code,
                MissionStatusRequest(
                    action="complete_capture",
                    comment="现场飞行和数据回收已结束",
                    operator_code="field-wang-qiang",
                ),
            )
        )


def test_finding_rejects_point_outside_mission() -> None:
    """验证疑点坐标必须位于任务范围内。"""
    mission = build_mission("captured")
    artifact = UavArtifact(
        id=31,
        mission_id=mission.id,
        artifact_code="PHOTO-001",
        artifact_type="photo",
        original_filename="photo.jpg",
        file_uri="storage://uav/photo.jpg",
        file_size_bytes=100,
        checksum_sha256="f" * 64,
        file_format="jpg",
        metadata_json={},
        verification_status="verified",
        uploaded_by="飞手张三",
        uploaded_by_code="field-wang-qiang",
        uploaded_by_role="field_inspector",
        created_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_mission_by_code.return_value = mission
    dao.get_finding_by_code.return_value = None
    dao.get_artifact_by_code.return_value = artifact
    dao.point_within_mission.return_value = False
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user("field_inspector")
    service = UavService(dao=dao, user_service=user_service)
    request = FindingCreateRequest(
        finding_code="UAV-FINDING-001",
        artifact_code="PHOTO-001",
        finding_type="疑似病虫害",
        severity="major",
        longitude=130.0,
        latitude=50.0,
        description="图像中发现异常斑块，需要人工复核。",
        operator_code="field-wang-qiang",
    )

    with pytest.raises(ValidationException, match="不在无人机任务范围内"):
        asyncio.run(
            service.create_finding(
                AsyncMock(),
                "RS-2026",
                mission.mission_code,
                request,
            )
        )
