"""无人机航空器、飞行任务、实体成果和疑点审核 API。"""

import json
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import DatabaseSession
from app.core.exceptions import ValidationException
from app.schemas.uav import (
    AircraftCreateRequest,
    AircraftResponse,
    ArtifactResponse,
    ArtifactUploadRequest,
    FindingCreateRequest,
    FindingResponse,
    FindingReviewRequest,
    MissionCreateRequest,
    MissionResponse,
    MissionStatusRequest,
    UavOverviewResponse,
)
from app.services.uav_service import UavService

router = APIRouter(prefix="/api/v1/uav", tags=["无人机任务"])
service = UavService()


def parse_json_object(value: str, field_name: str) -> dict:
    """把表单 JSON 文本解析为对象。

    Args:
        value: JSON 文本。
        field_name: 用户可读字段名。

    Returns:
        dict: JSON 对象。
    """
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationException(f"{field_name}不是合法 JSON") from exc
    if not isinstance(parsed, dict):
        raise ValidationException(f"{field_name}必须是 JSON 对象")
    return parsed


@router.get("/overview", response_model=UavOverviewResponse)
async def get_uav_overview(
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> UavOverviewResponse:
    """查询航空器、任务、实体成果和疑点总览。

    Args:
        db: 异步数据库会话。
        operator_code: 当前项目用户稳定编码。
        project_code: 项目编号。

    Returns:
        UavOverviewResponse: 无人机工作台真实总览。
    """
    return await service.get_overview(db, project_code, operator_code)


@router.post(
    "/aircraft",
    response_model=AircraftResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_uav_aircraft(
    db: DatabaseSession,
    certificate_file: Annotated[
        UploadFile,
        File(description="航空器登记或适航证书实体文件"),
    ],
    aircraft_code: Annotated[
        str,
        Form(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
    aircraft_name: Annotated[str, Form(min_length=2, max_length=200)],
    manufacturer: Annotated[str, Form(min_length=1, max_length=150)],
    model_number: Annotated[str, Form(min_length=1, max_length=100)],
    serial_number: Annotated[str, Form(min_length=1, max_length=120)],
    registration_number: Annotated[str, Form(min_length=1, max_length=120)],
    sensor_name: Annotated[str, Form(min_length=1, max_length=150)],
    sensor_model: Annotated[str, Form(min_length=1, max_length=120)],
    sensor_serial_number: Annotated[str, Form(min_length=1, max_length=120)],
    owner_department: Annotated[str, Form(min_length=2, max_length=200)],
    operator_code: Annotated[str, Form(min_length=1, max_length=50)],
    aircraft_status: Annotated[
        Literal["active", "maintenance", "retired"],
        Form(),
    ] = "active",
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> AircraftResponse:
    """上传证书并登记航空器和传感器真实身份。

    Args:
        db: 异步数据库会话。
        certificate_file: 航空器证书实体。
        aircraft_code: 航空器编号。
        aircraft_name: 航空器名称。
        manufacturer: 制造商。
        model_number: 航空器型号。
        serial_number: 航空器序列号。
        registration_number: 登记或实名编号。
        sensor_name: 挂载传感器名称。
        sensor_model: 传感器型号。
        sensor_serial_number: 传感器序列号。
        owner_department: 权属单位。
        operator_code: 当前项目用户编码。
        aircraft_status: 航空器初始状态。
        project_code: 项目编号。

    Returns:
        AircraftResponse: 已登记航空器。
    """
    request = AircraftCreateRequest(
        aircraft_code=aircraft_code,
        aircraft_name=aircraft_name,
        manufacturer=manufacturer,
        model_number=model_number,
        serial_number=serial_number,
        registration_number=registration_number,
        sensor_name=sensor_name,
        sensor_model=sensor_model,
        sensor_serial_number=sensor_serial_number,
        owner_department=owner_department,
        status=aircraft_status,
        operator_code=operator_code,
    )
    return await service.register_aircraft(
        db,
        project_code,
        request,
        certificate_file.filename or "certificate.pdf",
        certificate_file.file,
    )


@router.post(
    "/missions",
    response_model=MissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_uav_mission(
    db: DatabaseSession,
    pilot_license_file: Annotated[
        UploadFile,
        File(description="飞手执照或资质实体文件"),
    ],
    mission_code: Annotated[
        str,
        Form(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
    mission_name: Annotated[str, Form(min_length=2, max_length=200)],
    aircraft_code: Annotated[str, Form(min_length=1, max_length=80)],
    district_code: Annotated[str, Form(min_length=1, max_length=50)],
    flight_boundary_json: Annotated[str, Form(min_length=20)],
    pilot_name: Annotated[str, Form(min_length=2, max_length=100)],
    pilot_license_number: Annotated[str, Form(min_length=1, max_length=120)],
    planned_start_at: Annotated[datetime, Form()],
    planned_end_at: Annotated[datetime, Form()],
    altitude_m: Annotated[float, Form(gt=0, le=10_000)],
    expected_resolution_cm: Annotated[float, Form(gt=0, le=1000)],
    forward_overlap_percent: Annotated[float, Form(ge=0, le=100)],
    side_overlap_percent: Annotated[float, Form(ge=0, le=100)],
    weather_note: Annotated[str, Form(min_length=2, max_length=2000)],
    operator_code: Annotated[str, Form(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> MissionResponse:
    """上传飞手资质并创建县界内飞行任务。

    Args:
        db: 异步数据库会话。
        pilot_license_file: 飞手资质实体。
        mission_code: 任务编号。
        mission_name: 任务名称。
        aircraft_code: 航空器编号。
        district_code: 县区编码。
        flight_boundary_json: WGS84 GeoJSON Polygon 文本。
        pilot_name: 飞手姓名。
        pilot_license_number: 飞手资质编号。
        planned_start_at: 计划开始时间。
        planned_end_at: 计划结束时间。
        altitude_m: 计划航高。
        expected_resolution_cm: 计划地面分辨率。
        forward_overlap_percent: 航向重叠度。
        side_overlap_percent: 旁向重叠度。
        weather_note: 气象和作业条件。
        operator_code: 当前项目用户编码。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        MissionResponse: 已创建任务。
    """
    request = MissionCreateRequest(
        mission_code=mission_code,
        mission_name=mission_name,
        aircraft_code=aircraft_code,
        district_code=district_code,
        flight_boundary=parse_json_object(
            flight_boundary_json,
            "飞行范围",
        ),
        pilot_name=pilot_name,
        pilot_license_number=pilot_license_number,
        planned_start_at=planned_start_at,
        planned_end_at=planned_end_at,
        altitude_m=altitude_m,
        expected_resolution_cm=expected_resolution_cm,
        forward_overlap_percent=forward_overlap_percent,
        side_overlap_percent=side_overlap_percent,
        weather_note=weather_note,
        operator_code=operator_code,
    )
    return await service.create_mission(
        db,
        project_code,
        task_code,
        request,
        pilot_license_file.filename or "pilot-license.pdf",
        pilot_license_file.file,
    )


@router.post(
    "/missions/{mission_code}/artifacts",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_uav_artifact(
    mission_code: str,
    db: DatabaseSession,
    file: Annotated[UploadFile, File(description="无人机任务实体成果")],
    artifact_code: Annotated[
        str,
        Form(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$"),
    ],
    artifact_type: Annotated[
        Literal[
            "raw_imagery",
            "flight_log",
            "photo",
            "video",
            "orthomosaic",
            "dem",
            "report",
        ],
        Form(),
    ],
    source_name: Annotated[str, Form(min_length=1, max_length=120)],
    source_version: Annotated[str, Form(min_length=1, max_length=80)],
    operator_code: Annotated[str, Form(min_length=1, max_length=50)],
    captured_at: Annotated[datetime | None, Form()] = None,
    metadata_json: Annotated[str, Form()] = "{}",
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ArtifactResponse:
    """上传任务原始数据、航迹、照片、视频或正射实体。

    Args:
        mission_code: 任务编号。
        db: 异步数据库会话。
        file: 任务成果实体文件。
        artifact_code: 成果编号。
        artifact_type: 成果类型。
        source_name: 文件来源名称。
        source_version: 文件来源版本。
        operator_code: 当前项目用户编码。
        captured_at: 可选采集时间。
        metadata_json: 结构化扩展元数据。
        project_code: 项目编号。

    Returns:
        ArtifactResponse: 已校验成果。
    """
    request = ArtifactUploadRequest(
        artifact_code=artifact_code,
        artifact_type=artifact_type,
        captured_at=captured_at,
        source_name=source_name,
        source_version=source_version,
        metadata=parse_json_object(metadata_json, "成果元数据"),
        operator_code=operator_code,
    )
    return await service.upload_artifact(
        db,
        project_code,
        mission_code,
        request,
        file.filename or "artifact.bin",
        file.file,
    )


@router.post(
    "/missions/{mission_code}/status",
    response_model=MissionResponse,
)
async def transition_uav_mission(
    mission_code: str,
    request: MissionStatusRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> MissionResponse:
    """按实体成果和疑点门禁执行任务状态动作。

    Args:
        mission_code: 任务编号。
        request: 状态动作、实际时间和说明。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        MissionResponse: 更新后的任务。
    """
    return await service.transition_mission(db, project_code, mission_code, request)


@router.post(
    "/missions/{mission_code}/findings",
    response_model=FindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_uav_finding(
    mission_code: str,
    request: FindingCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> FindingResponse:
    """登记任务范围内且绑定实体成果的空间疑点。

    Args:
        mission_code: 任务编号。
        request: 疑点坐标、证据和说明。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        FindingResponse: 待人工复核疑点。
    """
    return await service.create_finding(db, project_code, mission_code, request)


@router.post(
    "/missions/{mission_code}/findings/{finding_code}/review",
    response_model=FindingResponse,
)
async def review_uav_finding(
    mission_code: str,
    finding_code: str,
    request: FindingReviewRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> FindingResponse:
    """人工确认或排除无人机疑点。

    Args:
        mission_code: 任务编号。
        finding_code: 疑点编号。
        request: 复核结论、说明和操作人。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        FindingResponse: 已复核疑点。
    """
    return await service.review_finding(
        db,
        project_code,
        mission_code,
        finding_code,
        request,
    )


@router.get("/artifacts/{artifact_code}/download")
async def download_uav_artifact(
    artifact_code: str,
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> FileResponse:
    """复核实体大小和 SHA-256 后下载无人机成果。

    Args:
        artifact_code: 成果编号。
        db: 异步数据库会话。
        operator_code: 当前项目用户编码。
        project_code: 项目编号。

    Returns:
        FileResponse: 已校验实体文件。
    """
    download = await service.get_artifact_download(
        db,
        project_code,
        artifact_code,
        operator_code,
    )
    return FileResponse(
        download.path,
        media_type=download.media_type,
        headers={
            "ETag": f'"{download.checksum_sha256}"',
            "Content-Disposition": (
                "attachment; filename*=UTF-8''"
                f"{quote(download.filename)}"
            ),
        },
    )
