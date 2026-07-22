"""田间监测网络与病虫害预警业务测试。"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.dao.monitoring_network_dao import AlertRecord
from app.models.monitoring_network import (
    DeviceTelemetry,
    MonitoringDevice,
    PestAlert,
    PestAssessment,
    PestModelVersion,
)
from app.schemas.monitoring_network import (
    AlertCreateRequest,
    AlertDeliverRequest,
    PestModelCreateRequest,
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
