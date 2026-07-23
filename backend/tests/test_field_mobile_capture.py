"""移动外业采集定位精度与幂等创建测试。"""

import asyncio
import json
from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.schemas.field_verification import FieldVerificationCreateRequest
from app.services.field_verification_service import FieldVerificationService


def build_request(**overrides: object) -> FieldVerificationCreateRequest:
    """构造移动外业端直接采集请求。

    Args:
        overrides: 需要覆盖的请求字段。

    Returns:
        FieldVerificationCreateRequest: 带 GPS 精度和稳定采集人编码的请求。
    """
    values: dict[str, object] = {
        "verification_code": "FV-MOB-20260723-0001",
        "source_record_id": "FV-MOB-20260723-0001",
        "lon": 126.6103,
        "lat": 45.8056,
        "location_accuracy_m": 8.25,
        "observed_land_class": "耕地",
        "observed_crop_type": "玉米",
        "photo_urls": [],
        "voice_url": None,
        "remark": "田埂清晰，长势正常",
        "captured_at": datetime(2026, 7, 23, 8, 30, tzinfo=UTC),
        "investigator_code": "field-zhang-qiang",
        "source_name": "AgriScope 移动外业端",
        "source_uri": "app://field-capture/mobile-v1",
        "source_version": "mobile-v1",
    }
    values.update(overrides)
    return FieldVerificationCreateRequest.model_validate(values)


def build_service() -> tuple[
    FieldVerificationService,
    AsyncMock,
    AsyncMock,
    AsyncMock,
]:
    """构造移动采集服务及其数据访问替身。

    Returns:
        tuple: 服务、外业 DAO、工作台 DAO、实体证据 DAO。
    """
    dao = AsyncMock()
    dao.get_by_code.return_value = None
    dao.is_point_within_project.return_value = True
    dao.get_coordinates.return_value = (126.6103, 45.8056)

    async def create_record(_db: object, record: object, _lon: float, _lat: float):
        record.id = 7
        return record

    dao.create.side_effect = create_record
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = SimpleNamespace(
        id=3,
        project_id=9,
        status="interpreting",
        assignee="李静",
        updated_at=datetime.now(UTC),
    )
    workbench_dao.get_latest_imagery.return_value = None
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        display_name="张强",
        user_code="field-zhang-qiang",
        role_code="field_inspector",
    )
    rule_service = AsyncMock()
    rule_service.ensure_for_project.return_value = SimpleNamespace(
        field_offset_threshold_m=5,
        field_search_radius_m=1000,
        max_capture_image_days=15,
    )
    artifact_dao = AsyncMock()
    artifact_dao.list_by_verification_ids.return_value = []
    service = FieldVerificationService(
        dao=dao,
        workbench_dao=workbench_dao,
        rule_config_service=rule_service,
        project_user_service=user_service,
        artifact_dao=artifact_dao,
    )
    service._match_record = AsyncMock()
    return service, dao, workbench_dao, artifact_dao


def test_location_accuracy_validation_rejects_invalid_terminal_values() -> None:
    """验证终端定位精度必须为合理正值。"""
    with pytest.raises(ValidationError, match="location_accuracy_m"):
        build_request(location_accuracy_m=0)
    with pytest.raises(ValidationError, match="location_accuracy_m"):
        build_request(location_accuracy_m=10001)


def test_mobile_capture_persists_accuracy_and_returns_match_state() -> None:
    """验证移动采集保存精度、稳定用户来源并返回点斑结果。"""
    service, dao, _workbench_dao, _artifact_dao = build_service()

    async def match_record(
        _db: object,
        _task: object,
        record: object,
        _config: object,
        _imagery: object,
    ) -> bool:
        record.matched_plot_code = "OSM-HLJ-100"
        record.offset_distance_m = 0
        record.match_status = "consistent"
        record.resolution_status = "not_required"
        return False

    service._match_record.side_effect = match_record
    db = AsyncMock()
    request = build_request()

    response = asyncio.run(service.create_record(db, "RS-2026-045", request))

    record = dao.create.await_args.args[1]
    assert float(record.location_accuracy_m) == pytest.approx(8.25)
    assert record.investigator_code == "field-zhang-qiang"
    assert record.source_name == "AgriScope 移动外业端"
    assert response.location_accuracy_m == pytest.approx(8.25)
    assert response.match_status == "consistent"
    assert response.matched_plot_code == "OSM-HLJ-100"
    db.commit.assert_awaited_once()


def test_mobile_capture_retry_is_idempotent_for_same_payload() -> None:
    """验证移动网络重试不会创建第二条相同外业记录。"""
    service, dao, _workbench_dao, artifact_dao = build_service()
    request = build_request()
    payload = request.model_dump(mode="json")
    checksum = sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    existing = SimpleNamespace(
        id=7,
        task_id=3,
        verification_code=request.verification_code,
        investigator="张强",
        investigator_code="field-zhang-qiang",
        location_accuracy_m=8.25,
        observed_land_class="耕地",
        observed_crop_type="玉米",
        photo_urls=[],
        voice_url=None,
        remark="田埂清晰，长势正常",
        captured_at=request.captured_at,
        source_name=request.source_name,
        source_uri=request.source_uri,
        source_version=request.source_version,
        source_record_id=request.source_record_id,
        source_checksum_sha256=checksum,
        source_file_uri=None,
        source_file_size_bytes=None,
        import_batch_code="FIELD-MOBILE-001",
        imported_by="张强",
        imported_by_code="field-zhang-qiang",
        imported_by_role="field_inspector",
        matched_plot_code="OSM-HLJ-100",
        offset_distance_m=0,
        match_status="consistent",
        resolution_status="not_required",
        resolution_decision=None,
        resolution_comment=None,
        resolved_by=None,
        resolved_by_code=None,
        resolved_by_role=None,
    )
    dao.get_by_code.return_value = existing

    response = asyncio.run(
        service.create_record(AsyncMock(), "RS-2026-045", request)
    )

    assert response.verification_code == request.verification_code
    assert response.verified_artifact_count == 0
    dao.create.assert_not_awaited()
    service._match_record.assert_not_awaited()
    artifact_dao.list_by_verification_ids.assert_awaited_once()


def test_mobile_capture_retry_rejects_conflicting_payload() -> None:
    """验证相同编号但不同载荷不能借幂等逻辑覆盖原始采集。"""
    service, dao, _workbench_dao, _artifact_dao = build_service()
    request = build_request()
    dao.get_by_code.return_value = SimpleNamespace(
        id=7,
        task_id=3,
        investigator_code="field-zhang-qiang",
        source_checksum_sha256="0" * 64,
    )

    with pytest.raises(ValidationException, match="采集载荷不一致"):
        asyncio.run(
            service.create_record(AsyncMock(), "RS-2026-045", request)
        )

    dao.create.assert_not_awaited()
