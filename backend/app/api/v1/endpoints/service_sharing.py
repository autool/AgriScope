"""受控地图与数据共享服务 API。"""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DatabaseSession
from app.schemas.service_sharing import (
    ServiceAccessRequestCreate,
    ServiceAccessRequestResponse,
    ServiceAccessReviewRequest,
    ServiceAccessReviewResponse,
    ServiceCredentialResponse,
    ServiceHealthCheckRequest,
    ServiceHealthResponse,
    ServiceRegistrationRequest,
    ServiceReviewRequest,
    ServiceRevokeRequest,
    ServiceSharingOverviewResponse,
    ServiceUsageEventResponse,
    ServiceUsageRecordRequest,
    SharedServiceResponse,
)
from app.services.service_sharing_service import ServiceSharingService

router = APIRouter(prefix="/api/v1/service-sharing", tags=["数据共享服务"])
service = ServiceSharingService()


@router.get("/overview", response_model=ServiceSharingOverviewResponse)
async def get_service_sharing_overview(
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ServiceSharingOverviewResponse:
    """查询共享服务、访问申请、健康和调用审计。

    Args:
        db: 异步数据库会话。
        operator_code: 当前项目用户稳定编码。
        project_code: 项目编号。

    Returns:
        ServiceSharingOverviewResponse: 共享服务总览。
    """
    return await service.get_overview(db, project_code, operator_code)


@router.post(
    "/services",
    response_model=SharedServiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_shared_service(
    request: ServiceRegistrationRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> SharedServiceResponse:
    """项目负责人登记服务并提交甲方审批。

    Args:
        request: 服务、资源、密级和操作人信息。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        SharedServiceResponse: 已登记服务。
    """
    return await service.register_service(db, project_code, request)


@router.post(
    "/services/{service_code}/review",
    response_model=SharedServiceResponse,
)
async def review_shared_service(
    service_code: str,
    request: ServiceReviewRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> SharedServiceResponse:
    """甲方审核代表批准或驳回服务登记。

    Args:
        service_code: 服务编号。
        request: 审批结论和依据。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        SharedServiceResponse: 审批后服务。
    """
    return await service.review_service(db, project_code, service_code, request)


@router.post(
    "/services/{service_code}/access-requests",
    response_model=ServiceAccessRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_access_request(
    service_code: str,
    request: ServiceAccessRequestCreate,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ServiceAccessRequestResponse:
    """项目成员申请访问已激活服务。

    Args:
        service_code: 服务编号。
        request: 申请组织、用途、期限和申请人。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        ServiceAccessRequestResponse: 待审批申请。
    """
    return await service.create_access_request(
        db,
        project_code,
        service_code,
        request,
    )


@router.post(
    "/access-requests/{request_code}/review",
    response_model=ServiceAccessReviewResponse,
)
async def review_service_access_request(
    request_code: str,
    request: ServiceAccessReviewRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ServiceAccessReviewResponse:
    """审批访问申请并按需签发一次性显示的 API Key。

    Args:
        request_code: 申请编号。
        request: 审批结论、说明和操作人。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        ServiceAccessReviewResponse: 申请状态和一次性密钥。
    """
    return await service.review_access_request(
        db,
        project_code,
        request_code,
        request,
    )


@router.post(
    "/services/{service_code}/health-check",
    response_model=ServiceHealthResponse,
)
async def check_shared_service_health(
    service_code: str,
    request: ServiceHealthCheckRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ServiceHealthResponse:
    """执行带 SSRF 防护的真实服务健康探测。

    Args:
        service_code: 服务编号。
        request: 操作人编码。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        ServiceHealthResponse: 健康探测证据。
    """
    return await service.run_health_check(db, project_code, service_code, request)


@router.post(
    "/services/{service_code}/usage",
    response_model=ServiceUsageEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_shared_service_usage(
    service_code: str,
    request: ServiceUsageRecordRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ServiceUsageEventResponse:
    """校验项目身份或 API Key 后记录一次调用审计。

    Args:
        service_code: 服务编号。
        request: 调用结果和身份凭据。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        ServiceUsageEventResponse: 调用审计事件。
    """
    return await service.record_usage(db, project_code, service_code, request)


@router.post(
    "/services/{service_code}/revoke",
    response_model=SharedServiceResponse,
)
async def revoke_shared_service(
    service_code: str,
    request: ServiceRevokeRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> SharedServiceResponse:
    """撤销服务并吊销其全部活动凭证。

    Args:
        service_code: 服务编号。
        request: 撤销原因和操作人。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        SharedServiceResponse: 已撤销服务。
    """
    return await service.revoke_service(db, project_code, service_code, request)


@router.post(
    "/credentials/{credential_code}/revoke",
    response_model=ServiceCredentialResponse,
)
async def revoke_service_credential(
    credential_code: str,
    request: ServiceRevokeRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ServiceCredentialResponse:
    """单独撤销一个访问凭证。

    Args:
        credential_code: 凭证编号。
        request: 撤销原因和操作人。
        db: 异步数据库会话。
        project_code: 项目编号。

    Returns:
        ServiceCredentialResponse: 已撤销凭证摘要。
    """
    return await service.revoke_credential(
        db,
        project_code,
        credential_code,
        request,
    )
