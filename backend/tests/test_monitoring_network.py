"""田间监测网络与病虫害预警业务测试。"""

import asyncio
import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.dao.monitoring_network_dao import (
    AlertRecord,
    ConsultationRecord,
    ReportAssessmentRecord,
)
from app.models.monitoring_network import (
    DeviceTelemetry,
    ExpertConsultation,
    MonitoringDevice,
    MonitoringEvent,
    MonitoringStation,
    PestAlert,
    PestAssessment,
    PestModelVersion,
    PestReport,
    PestReportItem,
)
from app.schemas.monitoring_network import (
    AlertCreateRequest,
    AlertDeliverRequest,
    ExpertConsultationAnswerRequest,
    PestModelCreateRequest,
    PestReportCreateRequest,
    PestReportReviewRequest,
    PestReportSubmitRequest,
    StationCreateRequest,
    TelemetryCreateRequest,
)
from app.services.monitoring_network_service import MonitoringNetworkService


def build_project() -> SimpleNamespace:
    """构造项目上下文。"""
    return SimpleNamespace(id=7, project_code="RS-2026")


def build_user(role_code: str = "project_manager") -> SimpleNamespace:
    """构造稳定项目用户。"""
    return SimpleNamespace(
        user_code="manager-zhao-zhiyuan",
        display_name="赵志远",
        role_code=role_code,
    )


def build_device(status: str = "offline") -> MonitoringDevice:
    """构造监测设备。"""
    now = datetime.now(UTC)
    return MonitoringDevice(
        id=11,
        project_id=7,
        station_id=3,
        device_code="HLJ-DEVICE-001",
        device_name="虫情测报灯一号",
        device_type="insect_trap",
        vendor="设备供应单位",
        model_number="PST-01",
        serial_number="SN-REAL-001",
        owner_department="黑龙江省农业农村厅",
        installed_at=now,
        photo_uri="storage://monitoring/device-001.jpg",
        photo_size_bytes=1024,
        photo_sha256="a" * 64,
        status=status,
        registered_by="赵志远",
        registered_by_code="manager-zhao-zhiyuan",
        registered_by_role="project_manager",
        created_at=now,
        updated_at=now,
    )


def build_model(status: str = "active") -> PestModelVersion:
    """构造病虫害模型版本。"""
    now = datetime.now(UTC)
    return PestModelVersion(
        id=21,
        project_id=7,
        model_code="PEST-RICE",
        model_version="1.0.0",
        model_name="水稻虫害识别模型",
        target_type="pest",
        deployment_target="server",
        training_source_uri="storage://models/train-manifest.json",
        evaluation_source_uri="storage://models/evaluation.json",
        artifact_uri="storage://models/pest-rice.onnx",
        artifact_size_bytes=2048,
        artifact_sha256="b" * 64,
        accuracy=Decimal("0.95"),
        recall=Decimal("0.92"),
        f1_score=Decimal("0.93"),
        roc_auc=Decimal("0.97"),
        status=status,
        registered_by="赵志远",
        registered_by_code="manager-zhao-zhiyuan",
        registered_by_role="project_manager",
        created_at=now,
    )


def build_assessment(status: str = "approved") -> PestAssessment:
    """构造病虫害识别结果。"""
    now = datetime.now(UTC)
    return PestAssessment(
        id=31,
        project_id=7,
        device_id=11,
        model_version_id=21,
        assessment_code="ASSESS-001",
        observed_at=now,
        input_uri="storage://monitoring/input-001.jpg",
        input_size_bytes=4096,
        input_sha256="c" * 64,
        input_summary={"source": "device"},
        target_name="稻飞虱",
        prediction_label="高风险",
        confidence=Decimal("0.91"),
        prediction_basis="虫体密度和图像分类概率超过模型阈值",
        status=status,
        submitted_by="外业核查员",
        submitted_by_code="field-wang-qiang",
        submitted_by_role="field_inspector",
        created_at=now,
        updated_at=now,
    )


def build_station() -> MonitoringStation:
    """构造带完整行政区上下文的监测站。"""
    now = datetime.now(UTC)
    return MonitoringStation(
        id=3,
        project_id=7,
        station_code="HLJ-STATION-001",
        station_name="水稻病虫监测站",
        province_code="230000",
        province_name="黑龙江省",
        city_code="230100",
        city_name="哈尔滨市",
        district_code="230102",
        district_name="道里区",
        longitude=Decimal("126.6"),
        latitude=Decimal("45.8"),
        station_type="pest",
        owner_department="黑龙江省农业农村厅",
        source_name="农业监测建设项目",
        source_uri="storage://monitoring/station.json",
        source_version="2026-01",
        evidence_uri="storage://monitoring/station.jpg",
        evidence_size_bytes=1024,
        evidence_sha256="a" * 64,
        status="active",
        registered_by="赵志远",
        registered_by_code="manager-zhao-zhiyuan",
        registered_by_role="project_manager",
        created_at=now,
        updated_at=now,
    )


def build_report(status: str = "draft") -> PestReport:
    """构造病虫害报告。"""
    now = datetime.now(UTC)
    return PestReport(
        id=61,
        project_id=7,
        report_code="PEST-REPORT-001",
        report_title="哈尔滨市病虫害监测报告",
        scope_level="prefecture",
        region_code="230100",
        region_name="哈尔滨市",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
        summary="本期监测覆盖真实站点和人工批准识别结果。",
        conclusion="建议结合告警送达情况开展现场复核和防控。",
        status=status,
        revision_number=1,
        assessment_count=1,
        alert_count=1,
        snapshot_at=now,
        created_by="赵志远",
        created_by_code="manager-zhao-zhiyuan",
        created_by_role="project_manager",
        created_at=now,
        updated_at=now,
    )


def test_telemetry_schema_requires_timezone() -> None:
    """验证遥测时间必须携带时区。"""
    with pytest.raises(ValidationError, match="必须包含时区"):
        TelemetryCreateRequest(
            idempotency_key="device:20260722:001",
            observed_at=datetime(2026, 7, 22, 10, 0),
            metric_code="air.temperature",
            metric_value=25.6,
            metric_unit="C",
            operator_code="field-wang-qiang",
        )


def test_overview_preserves_real_empty_state() -> None:
    """验证无监测数据时总览返回真实零值。"""
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.list_stations.return_value = []
    dao.list_device_records.return_value = []
    dao.list_telemetry_records.return_value = []
    dao.list_fault_records.return_value = []
    dao.list_model_versions.return_value = []
    dao.list_assessment_records.return_value = []
    dao.list_alert_records.return_value = []
    dao.list_events.return_value = []
    dao.count_telemetry.return_value = 0
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = MonitoringNetworkService(dao=dao, user_service=user_service)

    response = asyncio.run(
        service.get_overview(
            AsyncMock(),
            "RS-2026",
            "manager-zhao-zhiyuan",
        )
    )

    assert response.station_count == 0
    assert response.device_count == 0
    assert response.assessments == []
    user_service.require_capability.assert_awaited_once_with(
        ANY,
        7,
        "manager-zhao-zhiyuan",
        "view_monitoring_network",
    )


def test_station_rejects_coordinate_outside_declared_district() -> None:
    """验证站点坐标必须落在申报县区真实边界内。"""
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_station_by_code.return_value = None
    dao.get_administrative_context.return_value = None
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = MonitoringNetworkService(dao=dao, user_service=user_service)
    request = StationCreateRequest(
        station_code="HLJ-STATION-001",
        station_name="水稻病虫监测站",
        district_code="230102",
        longitude=126.6,
        latitude=45.8,
        station_type="pest",
        owner_department="黑龙江省农业农村厅",
        source_name="农业监测建设项目",
        source_uri="storage://monitoring/station-manifest.json",
        source_version="2026-01",
        evidence_uri="storage://monitoring/station-photo.jpg",
        evidence_size_bytes=2048,
        evidence_sha256="a" * 64,
        operator_code="manager-zhao-zhiyuan",
    )

    with pytest.raises(ValidationException, match="真实边界"):
        asyncio.run(service.create_station(AsyncMock(), "RS-2026", request))


def test_telemetry_idempotency_rejects_conflicting_payload() -> None:
    """验证同一幂等键不能对应不同遥测载荷。"""
    request = TelemetryCreateRequest(
        idempotency_key="device:20260722:001",
        observed_at=datetime.now(UTC),
        metric_code="air.temperature",
        metric_value=25.6,
        metric_unit="C",
        operator_code="field-wang-qiang",
    )
    existing = DeviceTelemetry(
        id=41,
        device_id=11,
        idempotency_key=request.idempotency_key,
        request_sha256="0" * 64,
        observed_at=request.observed_at,
        metric_code=request.metric_code,
        metric_value=Decimal("22.0"),
        payload={},
        ingested_by="外业核查员",
        ingested_by_code="field-wang-qiang",
        ingested_by_role="field_inspector",
        received_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_device_by_code.return_value = build_device()
    dao.get_telemetry_by_idempotency_key.return_value = existing
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user("field_inspector")
    service = MonitoringNetworkService(dao=dao, user_service=user_service)

    with pytest.raises(ValidationException, match="不同遥测载荷"):
        asyncio.run(
            service.ingest_telemetry(
                AsyncMock(),
                "RS-2026",
                "HLJ-DEVICE-001",
                request,
            )
        )


def test_telemetry_idempotency_returns_existing_record() -> None:
    """验证完全相同的幂等请求不会重复写入。"""
    request = TelemetryCreateRequest(
        idempotency_key="device:20260722:002",
        observed_at=datetime.now(UTC),
        metric_code="soil.moisture",
        metric_value=38.5,
        metric_unit="percent",
        payload={"quality": "valid"},
        operator_code="field-wang-qiang",
    )
    canonical = request.model_dump(mode="json", exclude={"operator_code"})
    import hashlib
    import json

    digest = hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    existing = DeviceTelemetry(
        id=42,
        device_id=11,
        idempotency_key=request.idempotency_key,
        request_sha256=digest,
        observed_at=request.observed_at,
        metric_code=request.metric_code,
        metric_value=Decimal("38.5"),
        metric_unit=request.metric_unit,
        payload=request.payload,
        ingested_by="外业核查员",
        ingested_by_code="field-wang-qiang",
        ingested_by_role="field_inspector",
        received_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_device_by_code.return_value = build_device()
    dao.get_telemetry_by_idempotency_key.return_value = existing
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user("field_inspector")
    service = MonitoringNetworkService(dao=dao, user_service=user_service)
    db = AsyncMock()

    response = asyncio.run(
        service.ingest_telemetry(
            db,
            "RS-2026",
            "HLJ-DEVICE-001",
            request,
        )
    )

    assert response.metric_value == 38.5
    dao.add_telemetry.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_register_model_supersedes_old_active_version() -> None:
    """验证登记新模型版本会审计替代同编码旧活动版本。"""
    old_model = build_model()
    now = datetime.now(UTC)
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_model_version.return_value = None
    dao.list_active_model_versions_by_code.return_value = [old_model]

    async def add_model(_: object, model: PestModelVersion) -> PestModelVersion:
        model.id = 22
        model.created_at = now
        return model

    dao.add_model_version.side_effect = add_model
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = MonitoringNetworkService(dao=dao, user_service=user_service)
    request = PestModelCreateRequest(
        model_code="PEST-RICE",
        model_version="2.0.0",
        model_name="水稻虫害识别模型",
        target_type="pest",
        deployment_target="server",
        training_source_uri="storage://models/v2/train.json",
        evaluation_source_uri="storage://models/v2/evaluation.json",
        artifact_uri="storage://models/v2/model.onnx",
        artifact_size_bytes=4096,
        artifact_sha256="d" * 64,
        accuracy=0.96,
        recall=0.94,
        f1_score=0.95,
        roc_auc=0.98,
        operator_code="manager-zhao-zhiyuan",
    )

    response = asyncio.run(service.register_model(AsyncMock(), "RS-2026", request))

    assert response.model_version == "2.0.0"
    assert old_model.status == "superseded"
    assert old_model.superseded_by_version == "2.0.0"
    assert dao.add_event.await_args.args[1].event_type == "model_registered"


def test_alert_rejects_unreviewed_assessment() -> None:
    """验证未经人工批准的模型结果不能创建告警。"""
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_assessment_by_code.return_value = build_assessment("pending_review")
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = MonitoringNetworkService(dao=dao, user_service=user_service)
    request = AlertCreateRequest(
        alert_code="ALERT-001",
        risk_level="high",
        message="监测结果达到高风险阈值，请组织现场核查与防控。",
        channels=["platform"],
        recipients=["黑龙江省农业农村厅植保部门"],
        operator_code="manager-zhao-zhiyuan",
    )

    with pytest.raises(ValidationException, match="人工批准"):
        asyncio.run(
            service.create_alert(
                AsyncMock(),
                "RS-2026",
                "ASSESS-001",
                request,
            )
        )


def test_deliver_alert_persists_receipt_and_identity() -> None:
    """验证告警送达保存回执校验值和稳定用户身份。"""
    now = datetime.now(UTC)
    alert = PestAlert(
        id=51,
        project_id=7,
        assessment_id=31,
        alert_code="ALERT-001",
        risk_level="high",
        message="监测结果达到高风险阈值，请组织现场核查与防控。",
        channels=["platform", "sms"],
        recipients=["植保部门"],
        status="pending",
        created_by="赵志远",
        created_by_code="manager-zhao-zhiyuan",
        created_by_role="project_manager",
        created_at=now,
        updated_at=now,
    )
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_alert_by_code.return_value = alert
    dao.list_alert_records.return_value = [
        AlertRecord(alert=alert, assessment_code="ASSESS-001")
    ]
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = MonitoringNetworkService(dao=dao, user_service=user_service)
    db = AsyncMock()
    request = AlertDeliverRequest(
        delivery_receipt_uri="storage://alerts/alert-001-receipt.json",
        delivery_receipt_size_bytes=1024,
        delivery_receipt_sha256="e" * 64,
        operator_code="manager-zhao-zhiyuan",
    )

    response = asyncio.run(
        service.deliver_alert(db, "RS-2026", "ALERT-001", request)
    )

    assert response.status == "delivered"
    assert response.delivery_receipt_sha256 == "e" * 64
    assert response.delivered_by_code == "manager-zhao-zhiyuan"
    db.commit.assert_awaited_once()


def test_report_rejects_unapproved_assessment() -> None:
    """验证报告只能显式纳入已人工批准且属于申报区域的识别结果。"""
    assessment = build_assessment("pending_review")
    assessment.observed_at = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_report_by_code.return_value = None
    dao.get_region_boundary.return_value = SimpleNamespace(
        boundary_name="哈尔滨市"
    )
    dao.get_report_assessment_records.return_value = [
        ReportAssessmentRecord(
            assessment=assessment,
            station=build_station(),
            model_code="PEST-RICE",
            model_version="1.0.0",
            alert=None,
        )
    ]
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = MonitoringNetworkService(dao=dao, user_service=user_service)
    request = PestReportCreateRequest(
        report_code="PEST-REPORT-001",
        report_title="哈尔滨市病虫害监测报告",
        scope_level="prefecture",
        region_code="230100",
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
        summary="本期监测覆盖真实站点和识别结果。",
        conclusion="建议开展现场复核并形成防控闭环。",
        assessment_codes=["ASSESS-001"],
        operator_code="manager-zhao-zhiyuan",
    )

    with pytest.raises(ValidationException, match="尚未人工批准"):
        asyncio.run(service.create_report(AsyncMock(), "RS-2026", request))


def test_report_submit_blocks_open_consultation() -> None:
    """验证未答复专家会商会阻断报告提交。"""
    report = build_report()
    consultation = ExpertConsultation(
        id=71,
        project_id=7,
        report_id=report.id,
        consultation_code="CONSULT-001",
        question="请研判本期高风险识别是否需要扩大外业调查范围。",
        status="open",
        requested_by="赵志远",
        requested_by_code="manager-zhao-zhiyuan",
        requested_by_role="project_manager",
        requested_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_report_by_code.return_value = report
    dao.list_consultation_records.return_value = [
        ConsultationRecord(
            consultation=consultation,
            report_code=report.report_code,
        )
    ]
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = MonitoringNetworkService(dao=dao, user_service=user_service)
    request = PestReportSubmitRequest(
        comment="报告内容和识别台账已复核，申请进入分级审核。",
        operator_code="manager-zhao-zhiyuan",
    )

    with pytest.raises(ValidationException, match="未答复专家会商"):
        asyncio.run(
            service.submit_report(
                AsyncMock(),
                "RS-2026",
                report.report_code,
                request,
            )
        )


def test_county_report_review_advances_to_prefecture() -> None:
    """验证县级审核通过后只能进入地级审核而不能直接完成。"""
    report = build_report("county_review")
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_report_by_code.return_value = report
    dao.list_report_items.return_value = []
    dao.list_consultation_records.return_value = []
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user("quality_inspector")
    service = MonitoringNetworkService(dao=dao, user_service=user_service)
    request = PestReportReviewRequest(
        action="approve",
        comment="县级监测范围、识别台账和会商结论核验通过。",
        operator_code="quality-wang-haifeng",
    )

    response = asyncio.run(
        service.review_report(
            AsyncMock(),
            "RS-2026",
            report.report_code,
            request,
        )
    )

    assert response.status == "prefecture_review"
    user_service.require_capability.assert_awaited_once_with(
        ANY,
        7,
        "quality-wang-haifeng",
        "review_county_pest_report",
    )


def test_province_report_review_generates_checksum_workbook(tmp_path) -> None:
    """验证省级通过会生成可复核 SHA-256 的 XLSX 电子台账。"""
    report = build_report("province_review")
    item = PestReportItem(
        id=81,
        report_id=report.id,
        assessment_id=31,
        assessment_code="ASSESS-001",
        district_code="230102",
        district_name="道里区",
        snapshot={
            "city_name": "哈尔滨市",
            "observed_at": "2026-07-15T08:00:00+00:00",
            "model_code": "PEST-RICE",
            "model_version": "1.0.0",
            "target_name": "稻飞虱",
            "prediction_label": "高风险",
            "confidence": 0.91,
            "risk_level": "high",
            "alert_status": "delivered",
            "input_sha256": "c" * 64,
            "reviewed_by_code": "quality-wang-haifeng",
        },
        created_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_report_by_code.return_value = report
    dao.list_report_items.return_value = [item]
    dao.list_consultation_records.return_value = []
    dao.list_events.return_value = [
        MonitoringEvent(
            id=91,
            project_id=7,
            entity_type="pest_report",
            entity_code=report.report_code,
            event_type="report_approved_stage",
            detail={"next_status": "approved"},
            actor="农业农村厅审核代表",
            actor_code="client-agri-dept",
            actor_role="client_reviewer",
            created_at=datetime.now(UTC),
        )
    ]
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user("client_reviewer")
    service = MonitoringNetworkService(
        dao=dao,
        user_service=user_service,
        storage_root=tmp_path,
    )
    db = AsyncMock()
    request = PestReportReviewRequest(
        action="approve",
        comment="省级审核确认报告范围、结论和台账证据完整。",
        operator_code="client-agri-dept",
    )

    response = asyncio.run(
        service.review_report(
            db,
            "RS-2026",
            report.report_code,
            request,
        )
    )

    assert response.status == "approved"
    assert response.original_filename == "PEST-REPORT-001-v1.xlsx"
    assert response.checksum_sha256 is not None
    generated = tmp_path / "reports" / report.report_code / response.original_filename
    assert generated.is_file()
    assert generated.read_bytes().startswith(b"PK")
    assert (
        hashlib.sha256(generated.read_bytes()).hexdigest()
        == response.checksum_sha256
    )


def test_answer_consultation_persists_server_checksum(tmp_path) -> None:
    """验证专家答复实体由服务端计算大小和 SHA-256。"""
    import io

    report = build_report()
    consultation = ExpertConsultation(
        id=71,
        project_id=7,
        report_id=report.id,
        consultation_code="CONSULT-001",
        question="请研判是否需要扩大外业调查范围。",
        status="open",
        requested_by="赵志远",
        requested_by_code="manager-zhao-zhiyuan",
        requested_by_role="project_manager",
        requested_at=datetime.now(UTC),
    )
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_consultation_by_code.return_value = consultation
    dao.get_report_by_id.return_value = report
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user("quality_inspector")
    service = MonitoringNetworkService(
        dao=dao,
        user_service=user_service,
        storage_root=tmp_path,
    )
    request = ExpertConsultationAnswerRequest(
        expert_organization="黑龙江省植保技术单位",
        expert_title="高级农艺师",
        response="建议扩大重点县区灯诱和田间踏查范围，并保留原始调查表。",
        operator_code="quality-wang-haifeng",
    )
    evidence = b"%PDF-1.7\nreal consultation evidence\n"

    response = asyncio.run(
        service.answer_consultation(
            AsyncMock(),
            "RS-2026",
            consultation.consultation_code,
            request,
            "consultation.pdf",
            io.BytesIO(evidence),
        )
    )

    assert response.status == "answered"
    assert response.evidence_size_bytes == len(evidence)
    assert response.evidence_sha256 == hashlib.sha256(evidence).hexdigest()
    assert response.answered_by_code == "manager-zhao-zhiyuan"
