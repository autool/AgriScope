"""田间监测网络、病虫害识别复核与告警 API。"""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DatabaseSession
from app.schemas.monitoring_network import (
    AlertCreateRequest,
    AlertDeliverRequest,
    AlertResponse,
    AssessmentCreateRequest,
    AssessmentResponse,
    AssessmentReviewRequest,
    DeviceCreateRequest,
    DeviceResponse,
    FaultCreateRequest,
    FaultResolveRequest,
    FaultResponse,
    MonitoringOverviewResponse,
    PestModelCreateRequest,
    PestModelResponse,
    StationCreateRequest,
    StationResponse,
    TelemetryCreateRequest,
    TelemetryResponse,
)
from app.services.monitoring_network_service import MonitoringNetworkService

router = APIRouter(prefix="/api/v1/monitoring-network", tags=["田间监测网络"])
service = MonitoringNetworkService()


@router.get("/overview", response_model=MonitoringOverviewResponse)
async def get_monitoring_overview(
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> MonitoringOverviewResponse:
    """查询监测站、设备、遥测、故障、模型和告警总览。

    Args:
        db: 异步数据库会话。
        operator_code: 当前项目用户稳定编码。
        project_code: 项目编号。

    Returns:
        MonitoringOverviewResponse: 真实监测业务总览。
    """
    return await service.get_overview(db, project_code, operator_code)


@router.post(
    "/stations",
    response_model=StationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitoring_station(
    request: StationCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> StationResponse:
    """登记坐标位于真实县区内的监测站。

    Args:
        request: 站点来源、坐标和实体证据。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        StationResponse: 已登记监测站。
    """
    return await service.create_station(db, project_code, request)


@router.post(
    "/stations/{station_code}/devices",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitoring_device(
    station_code: str,
    request: DeviceCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> DeviceResponse:
    """在监测站下登记设备身份与照片证据。

    Args:
        station_code: 监测站编号。
        request: 设备身份、归属和证据。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        DeviceResponse: 已登记设备。
    """
    return await service.create_device(db, project_code, station_code, request)


@router.post(
    "/devices/{device_code}/telemetry",
    response_model=TelemetryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_device_telemetry(
    device_code: str,
    request: TelemetryCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> TelemetryResponse:
    """通过幂等键写入设备数值、载荷或图像证据。

    Args:
        device_code: 设备编号。
        request: 遥测载荷与操作人。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        TelemetryResponse: 新增或幂等命中的遥测。
    """
    return await service.ingest_telemetry(db, project_code, device_code, request)


@router.post(
    "/devices/{device_code}/faults",
    response_model=FaultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_device_fault(
    device_code: str,
    request: FaultCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> FaultResponse:
    """登记设备故障并把设备标记为异常。

    Args:
        device_code: 设备编号。
        request: 故障严重度、原因和时间。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        FaultResponse: 已登记故障。
    """
    return await service.create_fault(db, project_code, device_code, request)


@router.post("/faults/{fault_code}/resolve", response_model=FaultResponse)
async def resolve_device_fault(
    fault_code: str,
    request: FaultResolveRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> FaultResponse:
    """提交故障处置实体证据并关闭故障。

    Args:
        fault_code: 故障编号。
        request: 处置说明和实体证据。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        FaultResponse: 已关闭故障。
    """
    return await service.resolve_fault(db, project_code, fault_code, request)


@router.post(
    "/models",
    response_model=PestModelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_pest_model(
    request: PestModelCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> PestModelResponse:
    """登记模型实体、评估指标并替代旧活动版本。

    Args:
        request: 模型来源、实体和评估指标。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        PestModelResponse: 已登记模型版本。
    """
    return await service.register_model(db, project_code, request)


@router.post(
    "/assessments",
    response_model=AssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_pest_assessment(
    request: AssessmentCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> AssessmentResponse:
    """登记模型识别结果并进入人工复核队列。

    Args:
        request: 模型、输入实体、预测和依据。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        AssessmentResponse: 待复核识别结果。
    """
    return await service.create_assessment(db, project_code, request)


@router.post(
    "/assessments/{assessment_code}/review",
    response_model=AssessmentResponse,
)
async def review_pest_assessment(
    assessment_code: str,
    request: AssessmentReviewRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> AssessmentResponse:
    """人工批准或驳回模型识别结果。

    Args:
        assessment_code: 识别结果编号。
        request: 复核结论和依据。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        AssessmentResponse: 已复核识别结果。
    """
    return await service.review_assessment(
        db,
        project_code,
        assessment_code,
        request,
    )


@router.post(
    "/assessments/{assessment_code}/alerts",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_pest_alert(
    assessment_code: str,
    request: AlertCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> AlertResponse:
    """基于人工批准结果创建待发送告警。

    Args:
        assessment_code: 已批准识别结果编号。
        request: 风险、渠道、接收对象和告警正文。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        AlertResponse: 待送达告警。
    """
    return await service.create_alert(db, project_code, assessment_code, request)


@router.post("/alerts/{alert_code}/deliver", response_model=AlertResponse)
async def deliver_pest_alert(
    alert_code: str,
    request: AlertDeliverRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> AlertResponse:
    """登记告警真实送达回执。

    Args:
        alert_code: 告警编号。
        request: 送达回执实体和操作人。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        AlertResponse: 已送达告警。
    """
    return await service.deliver_alert(db, project_code, alert_code, request)
