"""田间监测网络、病虫害识别复核与告警 API。"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse

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
    ExpertConsultationAnswerRequest,
    ExpertConsultationCreateRequest,
    ExpertConsultationResponse,
    FaultCreateRequest,
    FaultResolveRequest,
    FaultResponse,
    MonitoringOverviewResponse,
    PestModelCreateRequest,
    PestModelResponse,
    PestReportCreateRequest,
    PestReportResponse,
    PestReportReviewRequest,
    PestReportReviseRequest,
    PestReportSubmitRequest,
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


@router.post(
    "/reports",
    response_model=PestReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_pest_report(
    request: PestReportCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> PestReportResponse:
    """从已批准识别结果创建病虫害报告草稿。

    Args:
        request: 报告范围、周期、内容和显式识别编号。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        PestReportResponse: 已创建报告。
    """
    return await service.create_report(db, project_code, request)


@router.patch("/reports/{report_code}", response_model=PestReportResponse)
async def revise_pest_report(
    report_code: str,
    request: PestReportReviseRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> PestReportResponse:
    """修订草稿或退回后的病虫害报告。

    Args:
        report_code: 报告编号。
        request: 修订内容和依据。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        PestReportResponse: 修订后报告。
    """
    return await service.revise_report(db, project_code, report_code, request)


@router.post(
    "/reports/{report_code}/consultations",
    response_model=ExpertConsultationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_expert_consultation(
    report_code: str,
    request: ExpertConsultationCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ExpertConsultationResponse:
    """为草稿或退回报告发起专家会商。

    Args:
        report_code: 报告编号。
        request: 会商问题和操作人。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        ExpertConsultationResponse: 待答复会商。
    """
    return await service.create_consultation(
        db,
        project_code,
        report_code,
        request,
    )


@router.post(
    "/consultations/{consultation_code}/answer",
    response_model=ExpertConsultationResponse,
)
async def answer_expert_consultation(
    consultation_code: str,
    db: DatabaseSession,
    evidence_file: Annotated[UploadFile, File(description="专家会商答复实体证据")],
    expert_organization: Annotated[str, Form(min_length=2, max_length=200)],
    expert_title: Annotated[str, Form(min_length=2, max_length=120)],
    response: Annotated[str, Form(min_length=8, max_length=10_000)],
    operator_code: Annotated[str, Form(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ExpertConsultationResponse:
    """上传实体证据并登记专家会商答复。

    Args:
        consultation_code: 会商编号。
        db: 异步数据库会话。
        evidence_file: 答复实体证据。
        expert_organization: 专家所在单位。
        expert_title: 专家职称或专业身份。
        response: 会商答复。
        operator_code: 稳定项目用户编码。
        project_code: 项目编号。

    Returns:
        ExpertConsultationResponse: 已答复会商。
    """
    request = ExpertConsultationAnswerRequest(
        expert_organization=expert_organization,
        expert_title=expert_title,
        response=response,
        operator_code=operator_code,
    )
    return await service.answer_consultation(
        db,
        project_code,
        consultation_code,
        request,
        evidence_file.filename or "consultation-evidence.pdf",
        evidence_file.file,
    )


@router.post(
    "/reports/{report_code}/submit",
    response_model=PestReportResponse,
)
async def submit_pest_report(
    report_code: str,
    request: PestReportSubmitRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> PestReportResponse:
    """提交报告进入县级审核。

    Args:
        report_code: 报告编号。
        request: 提交说明和操作人。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        PestReportResponse: 已提交报告。
    """
    return await service.submit_report(db, project_code, report_code, request)


@router.post(
    "/reports/{report_code}/review",
    response_model=PestReportResponse,
)
async def review_pest_report(
    report_code: str,
    request: PestReportReviewRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> PestReportResponse:
    """执行县级、地级或省级审核与退回。

    Args:
        report_code: 报告编号。
        request: 审核动作、依据和操作人。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        PestReportResponse: 审核后报告。
    """
    return await service.review_report(db, project_code, report_code, request)


@router.get("/reports/{report_code}/download")
async def download_pest_report(
    report_code: str,
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> FileResponse:
    """复核实体大小和 SHA-256 后下载报告台账。

    Args:
        report_code: 报告编号。
        db: 异步数据库会话。
        operator_code: 当前项目用户编码。
        project_code: 项目编号。

    Returns:
        FileResponse: 校验通过的 XLSX 报告。
    """
    download = await service.get_report_download(
        db,
        project_code,
        report_code,
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
