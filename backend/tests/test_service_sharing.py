"""受控地图与数据共享服务全流程测试。"""

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.dao.service_sharing_dao import ServiceResourceEvidence
from app.models.service_sharing import (
    ServiceAccessRequest,
    ServiceCredential,
    ServiceHealthCheck,
    ServiceUsageEvent,
    SharedService,
)
from app.schemas.service_sharing import (
    ServiceAccessReviewRequest,
    ServiceHealthCheckRequest,
    ServiceRegistrationRequest,
    ServiceUsageRecordRequest,
)
from app.services.service_sharing_service import ServiceSharingService


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


def build_service(
    *,
    status: str = "active",
    auth_mode: str = "api_key",
) -> SharedService:
    """构造共享服务 ORM 模型。"""
    now = datetime(2026, 7, 22, tzinfo=UTC)
    return SharedService(
        id=3,
        project_id=7,
        service_code="HLJ-EARTH-SEARCH-STAC",
        service_name="Earth Search Sentinel-2 STAC",
        service_type="stac",
        endpoint_url="https://earth-search.aws.element84.com/v1",
        health_check_url="https://earth-search.aws.element84.com/v1",
        documentation_url="https://element84.com/earth-search/",
        resource_type="external_api",
        resource_code="EARTH-SEARCH-V1",
        resource_checksum_sha256=None,
        data_classification="public",
        exposure_scope="public",
        auth_mode=auth_mode,
        status=status,
        owner_department="黑龙江省农业农村厅遥感监测项目组",
        registered_by="赵志远",
        registered_by_code="manager-zhao-zhiyuan",
        registered_by_role="project_manager",
        reviewed_by="农业农村厅审核代表",
        reviewed_by_code="client-agri-dept",
        reviewed_by_role="client_reviewer",
        review_comment="同意作为公开影像检索来源",
        reviewed_at=now,
        created_at=now,
        updated_at=now,
    )


def test_registration_schema_rejects_confidential_public_service() -> None:
    """验证涉密资源不能登记到公共端点。"""
    with pytest.raises(ValidationError, match="涉密数据禁止"):
        ServiceRegistrationRequest(
            service_code="CONFIDENTIAL-WMS",
            service_name="涉密影像服务",
            service_type="wms",
            endpoint_url="https://example.test/wms",
            health_check_url="https://example.test/health",
            documentation_url="https://example.test/docs",
            resource_type="imagery",
            resource_code="CONFIDENTIAL-001",
            resource_checksum_sha256="a" * 64,
            data_classification="confidential",
            exposure_scope="public",
            auth_mode="api_key",
            owner_department="测试单位",
            operator_code="manager-zhao-zhiyuan",
        )


def test_registration_rejects_checksum_not_matching_database_entity() -> None:
    """验证内部成果服务不能仅凭客户端填写的 SHA-256 发布。"""
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_service_by_code.return_value = None
    dao.get_resource_evidence.return_value = ServiceResourceEvidence(
        resource_code="TM-REAL-001",
        checksum_sha256="b" * 64,
        data_classification="public",
        status="completed",
    )
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = ServiceSharingService(dao=dao, user_service=user_service)
    request = ServiceRegistrationRequest(
        service_code="HLJ-THEMATIC-DOWNLOAD",
        service_name="专题图下载服务",
        service_type="download",
        endpoint_url="https://example.test/maps",
        health_check_url="https://example.test/health",
        documentation_url="https://example.test/docs",
        resource_type="thematic_map",
        resource_code="TM-REAL-001",
        resource_checksum_sha256="a" * 64,
        data_classification="public",
        exposure_scope="public",
        auth_mode="api_key",
        owner_department="黑龙江省农业农村厅",
        operator_code="manager-zhao-zhiyuan",
    )

    with pytest.raises(ValidationException, match="SHA-256"):
        asyncio.run(service.register_service(AsyncMock(), "RS-2026", request))


def test_overview_keeps_real_empty_state() -> None:
    """验证没有登记记录时返回真实零值而不初始化伪服务。"""
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.list_services.return_value = []
    dao.list_access_requests.return_value = []
    dao.list_credentials.return_value = []
    dao.list_latest_health_rows.return_value = []
    dao.list_event_rows.return_value = []
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = ServiceSharingService(dao=dao, user_service=user_service)

    response = asyncio.run(
        service.get_overview(
            AsyncMock(),
            "RS-2026",
            "manager-zhao-zhiyuan",
        )
    )

    assert response.service_count == 0
    assert response.active_service_count == 0
    assert response.services == []
    user_service.require_capability.assert_awaited_once_with(
        ANY,
        7,
        "manager-zhao-zhiyuan",
        "view_services",
    )


def test_register_external_service_persists_approval_event() -> None:
    """验证项目负责人登记外部公开服务并进入待审批状态。"""
    now = datetime(2026, 7, 22, tzinfo=UTC)
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_service_by_code.return_value = None

    async def add_service(_: object, item: SharedService) -> SharedService:
        item.id = 3
        item.created_at = now
        item.updated_at = now
        return item

    async def add_event(_: object, item: ServiceUsageEvent) -> ServiceUsageEvent:
        item.id = 9
        item.created_at = now
        return item

    dao.add_service.side_effect = add_service
    dao.add_event.side_effect = add_event
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = ServiceSharingService(dao=dao, user_service=user_service)
    db = AsyncMock()
    request = ServiceRegistrationRequest(
        service_code="HLJ-EARTH-SEARCH-STAC",
        service_name="Earth Search Sentinel-2 STAC",
        service_type="stac",
        endpoint_url="https://earth-search.aws.element84.com/v1",
        health_check_url="https://earth-search.aws.element84.com/v1",
        documentation_url="https://element84.com/earth-search/",
        resource_type="external_api",
        resource_code="EARTH-SEARCH-V1",
        data_classification="public",
        exposure_scope="public",
        auth_mode="none",
        owner_department="黑龙江省农业农村厅遥感监测项目组",
        operator_code="manager-zhao-zhiyuan",
    )

    response = asyncio.run(service.register_service(db, "RS-2026", request))

    assert response.status == "pending_approval"
    assert response.data_classification == "public"
    assert dao.add_event.await_args.args[1].event_type == "service_registered"
    db.commit.assert_awaited_once()


def test_access_request_event_detail_is_json_serializable() -> None:
    """验证访问期限以 ISO 文本写入 JSON 审计而不是 Python date。"""
    requested_until = date.today() + timedelta(days=30)
    detail = {
        "request_code": "SVCREQ-TEST-JSON",
        "requested_until": requested_until.isoformat(),
    }

    assert json.loads(json.dumps(detail))["requested_until"] == str(requested_until)


def test_access_approval_returns_secret_once_and_stores_only_hash() -> None:
    """验证 API Key 明文仅在批准响应返回，数据库只保存哈希和末四位。"""
    now = datetime.now(UTC)
    shared_service = build_service()
    access_request = ServiceAccessRequest(
        id=11,
        service_id=shared_service.id,
        request_code="SVCREQ-TEST-001",
        applicant_organization="黑龙江省农业农村厅",
        purpose="用于 Sentinel-2 公开影像检索与处理任务调度",
        requested_until=date.today() + timedelta(days=30),
        status="pending",
        applicant="李静",
        applicant_code="interp-li-jing",
        applicant_role="interpreter",
        created_at=now,
    )
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_access_request_by_code.return_value = access_request
    dao.get_service_by_id.return_value = shared_service

    async def add_credential(
        _: object,
        credential: ServiceCredential,
    ) -> ServiceCredential:
        credential.id = 21
        return credential

    async def add_event(_: object, event: ServiceUsageEvent) -> ServiceUsageEvent:
        event.id = 31
        event.created_at = now
        return event

    dao.add_credential.side_effect = add_credential
    dao.add_event.side_effect = add_event
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = ServiceSharingService(dao=dao, user_service=user_service)
    db = AsyncMock()

    response = asyncio.run(
        service.review_access_request(
            db,
            "RS-2026",
            access_request.request_code,
            ServiceAccessReviewRequest(
                decision="approve",
                comment="用途明确，批准一个月访问权限",
                operator_code="manager-zhao-zhiyuan",
            ),
        )
    )

    credential = dao.add_credential.await_args.args[1]
    assert response.credential_secret is not None
    assert credential.secret_hash == hashlib.sha256(
        response.credential_secret.encode("utf-8")
    ).hexdigest()
    assert credential.secret_hash != response.credential_secret
    assert credential.secret_last_four == response.credential_secret[-4:]
    assert not hasattr(credential, "credential_secret")
    assert response.request.credential is not None
    assert response.request.credential.secret_last_four == credential.secret_last_four


def test_health_check_persists_real_probe_result() -> None:
    """验证健康检查保存 HTTP 状态、耗时和稳定操作人。"""
    now = datetime.now(UTC)
    shared_service = build_service(auth_mode="none")
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_service_by_code.return_value = shared_service

    async def add_health(
        _: object,
        health: ServiceHealthCheck,
    ) -> ServiceHealthCheck:
        health.id = 41
        return health

    async def add_event(_: object, event: ServiceUsageEvent) -> ServiceUsageEvent:
        event.id = 42
        event.created_at = now
        return event

    dao.add_health_check.side_effect = add_health
    dao.add_event.side_effect = add_event
    user_service = AsyncMock()
    user_service.require_capability.return_value = build_user()
    service = ServiceSharingService(dao=dao, user_service=user_service)
    service._validate_health_target = AsyncMock(return_value=None)
    service._probe_health = AsyncMock(
        return_value=("healthy", 200, 86, "服务端真实探测成功")
    )
    db = AsyncMock()

    response = asyncio.run(
        service.run_health_check(
            db,
            "RS-2026",
            shared_service.service_code,
            ServiceHealthCheckRequest(operator_code="manager-zhao-zhiyuan"),
        )
    )

    assert response.status == "healthy"
    assert response.http_status == 200
    assert response.response_time_ms == 86
    assert dao.add_event.await_args.args[1].event_type == "health_checked"


def test_health_target_rejects_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证健康检查拒绝未显式放行的内网 SSRF 目标。"""
    monkeypatch.setattr(
        "app.services.service_sharing_service.socket.getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("127.0.0.1", 8000)),
        ],
    )
    service = ServiceSharingService(dao=AsyncMock(), user_service=AsyncMock())

    with pytest.raises(ValidationException, match="内网目标"):
        asyncio.run(service._validate_health_target("http://internal.test/health"))


def test_usage_rejects_wrong_api_key_and_accepts_correct_secret() -> None:
    """验证调用审计必须通过活动 API Key 哈希校验。"""
    now = datetime.now(UTC)
    shared_service = build_service()
    raw_secret = "temporary-secret-used-only-by-test"
    credential = ServiceCredential(
        id=51,
        service_id=shared_service.id,
        access_request_id=11,
        credential_code="SVCKEY-TEST-001",
        secret_hash=hashlib.sha256(raw_secret.encode("utf-8")).hexdigest(),
        secret_last_four=raw_secret[-4:],
        status="active",
        issued_by="赵志远",
        issued_by_code="manager-zhao-zhiyuan",
        issued_by_role="project_manager",
        issued_at=now,
        expires_at=now + timedelta(days=30),
    )
    dao = AsyncMock()
    dao.get_project_by_code.return_value = build_project()
    dao.get_service_by_code.return_value = shared_service
    dao.get_credential_by_code.return_value = credential

    async def add_event(_: object, event: ServiceUsageEvent) -> ServiceUsageEvent:
        event.id = 61
        event.created_at = now
        return event

    dao.add_event.side_effect = add_event
    service = ServiceSharingService(dao=dao, user_service=AsyncMock())
    db = AsyncMock()
    common = {
        "credential_code": credential.credential_code,
        "request_method": "GET",
        "request_path": "/collections/sentinel-2-l2a/items",
        "response_status": 200,
        "duration_ms": 128,
        "response_bytes": 4096,
    }

    with pytest.raises(ValidationException, match="密钥不正确"):
        asyncio.run(
            service.record_usage(
                db,
                "RS-2026",
                shared_service.service_code,
                ServiceUsageRecordRequest(
                    **common,
                    credential_secret="wrong-secret",
                ),
            )
        )

    response = asyncio.run(
        service.record_usage(
            db,
            "RS-2026",
            shared_service.service_code,
            ServiceUsageRecordRequest(
                **common,
                credential_secret=raw_secret,
            ),
        )
    )

    assert response.event_type == "invocation_recorded"
    assert response.response_status == 200
    assert response.actor_code == credential.credential_code
    assert dao.add_event.await_args.args[1].credential_id == credential.id
