"""受控地图与数据共享服务全流程业务服务。"""

import asyncio
import hashlib
import hmac
import ipaddress
import secrets
import socket
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from datetime import time as datetime_time
from urllib.parse import urlparse

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.dao.service_sharing_dao import ServiceSharingDAO
from app.models.service_sharing import (
    ServiceAccessRequest,
    ServiceCredential,
    ServiceHealthCheck,
    ServiceUsageEvent,
    SharedService,
)
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
from app.services.project_user_service import ProjectUserService


class ServiceSharingService:
    """编排共享服务注册、审批、访问、健康、调用和撤销。"""

    def __init__(
        self,
        dao: ServiceSharingDAO | None = None,
        user_service: ProjectUserService | None = None,
    ) -> None:
        """初始化共享服务业务。

        Args:
            dao: 共享服务数据访问对象。
            user_service: 项目用户与能力校验服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ServiceSharingDAO()
        self.user_service = user_service or ProjectUserService()

    async def _project(self, db: AsyncSession, project_code: str) -> object:
        """解析项目上下文。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。

        Returns:
            object: 项目 ORM 对象。
        """
        project = await self.dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        return project

    @staticmethod
    def _credential_response(
        credential: ServiceCredential | None,
    ) -> ServiceCredentialResponse | None:
        """转换不包含密钥明文的凭证摘要。

        Args:
            credential: 凭证模型或空值。

        Returns:
            ServiceCredentialResponse | None: 安全凭证摘要。
        """
        if credential is None:
            return None
        return ServiceCredentialResponse(
            credential_code=credential.credential_code,
            secret_last_four=credential.secret_last_four,
            status=credential.status,
            issued_at=credential.issued_at,
            expires_at=credential.expires_at,
        )

    @classmethod
    def _access_response(
        cls,
        request: ServiceAccessRequest,
        service_code: str,
        credential: ServiceCredential | None,
    ) -> ServiceAccessRequestResponse:
        """转换访问申请及凭证摘要。

        Args:
            request: 访问申请模型。
            service_code: 服务业务编号。
            credential: 可选访问凭证。

        Returns:
            ServiceAccessRequestResponse: 前端可展示申请。
        """
        return ServiceAccessRequestResponse(
            request_code=request.request_code,
            service_code=service_code,
            applicant_organization=request.applicant_organization,
            purpose=request.purpose,
            requested_until=request.requested_until,
            status=request.status,
            applicant=request.applicant,
            applicant_code=request.applicant_code,
            applicant_role=request.applicant_role,
            decision_comment=request.decision_comment,
            created_at=request.created_at,
            decided_at=request.decided_at,
            credential=cls._credential_response(credential),
        )

    @staticmethod
    def _health_response(
        health: ServiceHealthCheck | None,
    ) -> ServiceHealthResponse | None:
        """转换最新健康证据。

        Args:
            health: 健康记录或空值。

        Returns:
            ServiceHealthResponse | None: 健康响应。
        """
        if health is None:
            return None
        return ServiceHealthResponse(
            status=health.status,
            http_status=health.http_status,
            response_time_ms=health.response_time_ms,
            detail=health.detail,
            checked_by=health.checked_by,
            checked_at=health.checked_at,
        )

    @staticmethod
    def _event_response(row: object) -> ServiceUsageEventResponse:
        """转换事件关联行。

        Args:
            row: 包含事件和服务编号的数据库行。

        Returns:
            ServiceUsageEventResponse: 不可变事件响应。
        """
        event = row[ServiceUsageEvent]
        return ServiceUsageEventResponse(
            event_type=event.event_type,
            service_code=row["service_code"],
            actor=event.actor,
            actor_code=event.actor_code,
            actor_role=event.actor_role,
            request_method=event.request_method,
            request_path=event.request_path,
            response_status=event.response_status,
            duration_ms=event.duration_ms,
            response_bytes=event.response_bytes,
            detail=event.detail,
            created_at=event.created_at,
        )

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
        operator_code: str,
    ) -> ServiceSharingOverviewResponse:
        """查询服务、申请、凭证、健康和最近审计总览。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            operator_code: 当前项目用户编码。

        Returns:
            ServiceSharingOverviewResponse: 共享服务总览。
        """
        project = await self._project(db, project_code)
        await self.user_service.require_capability(
            db,
            project.id,
            operator_code,
            "view_services",
        )
        services = list(await self.dao.list_services(db, project.id))
        access_requests = list(
            await self.dao.list_access_requests(db, project.id)
        )
        credentials = list(await self.dao.list_credentials(db, project.id))
        health_rows = await self.dao.list_latest_health_rows(db, project.id)
        event_rows = await self.dao.list_event_rows(db, project.id)
        service_by_id = {service.id: service for service in services}
        credential_by_request_id = {
            credential.access_request_id: credential for credential in credentials
        }
        latest_health_by_service: dict[str, ServiceHealthCheck] = {}
        for row in health_rows:
            service_code = row["service_code"]
            latest_health_by_service.setdefault(
                service_code,
                row[ServiceHealthCheck],
            )
        access_counts = Counter(item.service_id for item in access_requests)
        active_credential_counts = Counter(
            item.service_id for item in credentials if item.status == "active"
        )
        usage_counts = Counter(
            row[ServiceUsageEvent].service_id
            for row in event_rows
            if row[ServiceUsageEvent].event_type == "invocation_recorded"
        )
        service_responses = [
            SharedServiceResponse(
                service_code=service.service_code,
                service_name=service.service_name,
                service_type=service.service_type,
                endpoint_url=service.endpoint_url,
                health_check_url=service.health_check_url,
                documentation_url=service.documentation_url,
                resource_type=service.resource_type,
                resource_code=service.resource_code,
                resource_checksum_sha256=service.resource_checksum_sha256,
                data_classification=service.data_classification,
                exposure_scope=service.exposure_scope,
                auth_mode=service.auth_mode,
                status=service.status,
                owner_department=service.owner_department,
                registered_by=service.registered_by,
                registered_by_code=service.registered_by_code,
                registered_by_role=service.registered_by_role,
                reviewed_by=service.reviewed_by,
                review_comment=service.review_comment,
                created_at=service.created_at,
                updated_at=service.updated_at,
                latest_health=self._health_response(
                    latest_health_by_service.get(service.service_code)
                ),
                access_request_count=access_counts[service.id],
                active_credential_count=active_credential_counts[service.id],
                usage_count=usage_counts[service.id],
            )
            for service in services
        ]
        request_responses = [
            self._access_response(
                request,
                service_by_id[request.service_id].service_code,
                credential_by_request_id.get(request.id),
            )
            for request in access_requests
            if request.service_id in service_by_id
        ]
        return ServiceSharingOverviewResponse(
            project_code=project_code,
            service_count=len(services),
            active_service_count=sum(item.status == "active" for item in services),
            pending_approval_count=sum(
                item.status == "pending_approval" for item in services
            ),
            pending_access_count=sum(
                item.status == "pending" for item in access_requests
            ),
            healthy_service_count=sum(
                item.latest_health is not None
                and item.latest_health.status == "healthy"
                for item in service_responses
            ),
            services=service_responses,
            access_requests=request_responses,
            events=[self._event_response(row) for row in event_rows],
        )

    async def register_service(
        self,
        db: AsyncSession,
        project_code: str,
        request: ServiceRegistrationRequest,
    ) -> SharedServiceResponse:
        """登记服务并进入甲方审批队列。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            request: 服务地址、资源、密级和稳定操作人。

        Returns:
            SharedServiceResponse: 已登记服务。
        """
        project = await self._project(db, project_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_services",
        )
        existing = await self.dao.get_service_by_code(
            db,
            project.id,
            request.service_code,
        )
        if existing is not None:
            raise ValidationException(f"服务编号 {request.service_code} 已存在")
        checksum = request.resource_checksum_sha256
        classification = request.data_classification
        if request.resource_type != "external_api":
            evidence = await self.dao.get_resource_evidence(
                db,
                project.id,
                request.resource_type,
                request.resource_code,
            )
            if evidence is None:
                raise ValidationException("未找到可验证的项目资源实体")
            if evidence.checksum_sha256 != checksum:
                raise ValidationException("资源 SHA-256 与数据库实体不一致")
            if evidence.data_classification != classification:
                raise ValidationException("服务密级与资源实体密级不一致")
            allowed_statuses = {
                "imagery": {"operational"},
                "thematic_map": {"completed"},
                "delivery": {"completed"},
            }
            expected = allowed_statuses.get(request.resource_type, {"verified"})
            if evidence.status not in expected:
                raise ValidationException("资源尚未达到可发布状态")
        service = SharedService(
            project_id=project.id,
            service_code=request.service_code,
            service_name=request.service_name,
            service_type=request.service_type,
            endpoint_url=request.endpoint_url,
            health_check_url=request.health_check_url,
            documentation_url=request.documentation_url,
            resource_type=request.resource_type,
            resource_code=request.resource_code,
            resource_checksum_sha256=checksum,
            data_classification=classification,
            exposure_scope=request.exposure_scope,
            auth_mode=request.auth_mode,
            status="pending_approval",
            owner_department=request.owner_department,
            registered_by=operator.display_name,
            registered_by_code=operator.user_code,
            registered_by_role=operator.role_code,
        )
        try:
            service = await self.dao.add_service(db, service)
            await self._add_event(
                db,
                service,
                "service_registered",
                operator,
                {"status": "pending_approval"},
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException("服务编号或地址登记冲突") from exc
        await db.refresh(service)
        return self._service_without_aggregates(service)

    async def review_service(
        self,
        db: AsyncSession,
        project_code: str,
        service_code: str,
        request: ServiceReviewRequest,
    ) -> SharedServiceResponse:
        """由甲方审核代表批准或驳回服务登记。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            service_code: 服务编号。
            request: 审批结论、说明和操作人。

        Returns:
            SharedServiceResponse: 审批后的服务。
        """
        project = await self._project(db, project_code)
        reviewer = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "approve_services",
        )
        service = await self.dao.get_service_by_code(
            db,
            project.id,
            service_code,
            for_update=True,
        )
        if service is None:
            raise NotFoundException(f"未找到共享服务 {service_code}")
        if service.status != "pending_approval":
            raise ValidationException("当前服务不在待审批状态")
        now = datetime.now(UTC)
        service.status = "active" if request.decision == "approve" else "rejected"
        service.reviewed_by = reviewer.display_name
        service.reviewed_by_code = reviewer.user_code
        service.reviewed_by_role = reviewer.role_code
        service.review_comment = request.comment
        service.reviewed_at = now
        await self._add_event(
            db,
            service,
            "service_approved" if request.decision == "approve" else "service_rejected",
            reviewer,
            {"comment": request.comment, "status": service.status},
        )
        await db.commit()
        await db.refresh(service)
        return self._service_without_aggregates(service)

    async def create_access_request(
        self,
        db: AsyncSession,
        project_code: str,
        service_code: str,
        request: ServiceAccessRequestCreate,
    ) -> ServiceAccessRequestResponse:
        """申请访问已激活服务。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            service_code: 服务编号。
            request: 组织、用途、期限和申请人。

        Returns:
            ServiceAccessRequestResponse: 待审批申请。
        """
        project = await self._project(db, project_code)
        applicant = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "request_service_access",
        )
        service = await self.dao.get_service_by_code(
            db,
            project.id,
            service_code,
        )
        if service is None:
            raise NotFoundException(f"未找到共享服务 {service_code}")
        if service.status != "active":
            raise ValidationException("仅已激活服务可提交访问申请")
        if request.requested_until > (datetime.now(UTC).date() + timedelta(days=365)):
            raise ValidationException("单次服务访问授权期限不得超过 365 天")
        request_code = (
            f"SVCREQ-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-"
            f"{secrets.token_hex(4).upper()}"
        )
        access_request = ServiceAccessRequest(
            service_id=service.id,
            request_code=request_code,
            applicant_organization=request.applicant_organization,
            purpose=request.purpose,
            requested_until=request.requested_until,
            status="pending",
            applicant=applicant.display_name,
            applicant_code=applicant.user_code,
            applicant_role=applicant.role_code,
        )
        access_request = await self.dao.add_access_request(db, access_request)
        await self._add_event(
            db,
            service,
            "access_requested",
            applicant,
            {
                "request_code": request_code,
                "requested_until": request.requested_until.isoformat(),
            },
            access_request=access_request,
        )
        await db.commit()
        await db.refresh(access_request)
        return self._access_response(access_request, service.service_code, None)

    async def review_access_request(
        self,
        db: AsyncSession,
        project_code: str,
        request_code: str,
        request: ServiceAccessReviewRequest,
    ) -> ServiceAccessReviewResponse:
        """审批访问申请，并在 API Key 模式下仅返回一次密钥。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            request_code: 申请编号。
            request: 审批结论、说明和操作人。

        Returns:
            ServiceAccessReviewResponse: 申请和一次性凭证密钥。
        """
        project = await self._project(db, project_code)
        reviewer = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_services",
        )
        access_request = await self.dao.get_access_request_by_code(
            db,
            project.id,
            request_code,
            for_update=True,
        )
        if access_request is None:
            raise NotFoundException(f"未找到访问申请 {request_code}")
        if access_request.status != "pending":
            raise ValidationException("当前访问申请已处理")
        service = await self.dao.get_service_by_id(
            db,
            access_request.service_id,
            for_update=True,
        )
        if service is None:
            raise NotFoundException("访问申请关联服务不存在")
        if service.status != "active" and request.decision == "approve":
            raise ValidationException("服务未激活，不能批准访问申请")
        now = datetime.now(UTC)
        access_request.status = (
            "approved" if request.decision == "approve" else "rejected"
        )
        access_request.decided_by = reviewer.display_name
        access_request.decided_by_code = reviewer.user_code
        access_request.decided_by_role = reviewer.role_code
        access_request.decision_comment = request.comment
        access_request.decided_at = now
        credential: ServiceCredential | None = None
        credential_secret: str | None = None
        if request.decision == "approve" and service.auth_mode == "api_key":
            credential_secret = secrets.token_urlsafe(32)
            credential_code = (
                f"SVCKEY-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-"
                f"{secrets.token_hex(4).upper()}"
            )
            credential = ServiceCredential(
                service_id=service.id,
                access_request_id=access_request.id,
                credential_code=credential_code,
                secret_hash=hashlib.sha256(
                    credential_secret.encode("utf-8")
                ).hexdigest(),
                secret_last_four=credential_secret[-4:],
                status="active",
                issued_by=reviewer.display_name,
                issued_by_code=reviewer.user_code,
                issued_by_role=reviewer.role_code,
                issued_at=now,
                expires_at=datetime.combine(
                    access_request.requested_until,
                    datetime_time.max,
                    tzinfo=UTC,
                ),
            )
            credential = await self.dao.add_credential(db, credential)
        await self._add_event(
            db,
            service,
            "access_approved" if request.decision == "approve" else "access_rejected",
            reviewer,
            {"request_code": request_code, "comment": request.comment},
            access_request=access_request,
            credential=credential,
        )
        await db.commit()
        await db.refresh(access_request)
        return ServiceAccessReviewResponse(
            request=self._access_response(
                access_request,
                service.service_code,
                credential,
            ),
            credential_secret=credential_secret,
        )

    async def run_health_check(
        self,
        db: AsyncSession,
        project_code: str,
        service_code: str,
        request: ServiceHealthCheckRequest,
    ) -> ServiceHealthResponse:
        """执行带 SSRF 防护的服务端真实健康探测。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            service_code: 服务编号。
            request: 稳定操作人编码。

        Returns:
            ServiceHealthResponse: 已持久化健康证据。
        """
        project = await self._project(db, project_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "run_service_health_check",
        )
        service = await self.dao.get_service_by_code(
            db,
            project.id,
            service_code,
        )
        if service is None:
            raise NotFoundException(f"未找到共享服务 {service_code}")
        if service.status not in {"active", "suspended"}:
            raise ValidationException("仅已批准服务可执行健康检查")
        await self._validate_health_target(service.health_check_url)
        status, http_status, response_time_ms, detail = await self._probe_health(
            service.health_check_url
        )
        checked_at = datetime.now(UTC)
        health = await self.dao.add_health_check(
            db,
            ServiceHealthCheck(
                service_id=service.id,
                checked_url=service.health_check_url,
                status=status,
                http_status=http_status,
                response_time_ms=response_time_ms,
                detail=detail,
                checked_by=operator.display_name,
                checked_by_code=operator.user_code,
                checked_by_role=operator.role_code,
                checked_at=checked_at,
            ),
        )
        await self._add_event(
            db,
            service,
            "health_checked",
            operator,
            {
                "status": status,
                "http_status": http_status,
                "response_time_ms": response_time_ms,
            },
        )
        await db.commit()
        await db.refresh(health)
        response = self._health_response(health)
        if response is None:
            raise ValidationException("健康检查记录转换失败")
        return response

    async def _probe_health(
        self,
        url: str,
    ) -> tuple[str, int | None, int, str]:
        """对已通过 SSRF 校验的地址执行有限响应体探测。

        Args:
            url: 已完成地址安全校验的健康检查 URL。

        Returns:
            tuple[str, int | None, int, str]: 状态、HTTP 状态、耗时和说明。
        """
        started = time.perf_counter()
        http_status: int | None = None
        try:
            timeout = httpx.Timeout(5.0, connect=3.0)
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "GET",
                    url,
                    headers={"Range": "bytes=0-0", "User-Agent": "AgriScope/1.0"},
                ) as response:
                    http_status = response.status_code
            if 200 <= http_status < 300:
                status = "healthy"
                detail = "服务端真实探测成功"
            elif 300 <= http_status < 500:
                status = "degraded"
                detail = "服务可达但返回重定向或客户端状态"
            else:
                status = "unavailable"
                detail = "服务返回服务器错误"
        except (httpx.HTTPError, OSError) as exc:
            status = "unavailable"
            detail = f"服务探测失败：{type(exc).__name__}"
        response_time_ms = max(0, int((time.perf_counter() - started) * 1000))
        return status, http_status, response_time_ms, detail

    async def revoke_service(
        self,
        db: AsyncSession,
        project_code: str,
        service_code: str,
        request: ServiceRevokeRequest,
    ) -> SharedServiceResponse:
        """撤销服务并原子吊销其全部活动凭证。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            service_code: 服务编号。
            request: 撤销原因和操作人。

        Returns:
            SharedServiceResponse: 已撤销服务。
        """
        project = await self._project(db, project_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_services",
        )
        service = await self.dao.get_service_by_code(
            db,
            project.id,
            service_code,
            for_update=True,
        )
        if service is None:
            raise NotFoundException(f"未找到共享服务 {service_code}")
        if service.status == "revoked":
            raise ValidationException("服务已经撤销")
        now = datetime.now(UTC)
        credentials = await self.dao.list_active_credentials_for_service(
            db,
            service.id,
        )
        for credential in credentials:
            self._revoke_credential_model(
                credential,
                operator,
                request.reason,
                now,
            )
        service.status = "revoked"
        service.revoked_by = operator.display_name
        service.revoked_by_code = operator.user_code
        service.revoked_by_role = operator.role_code
        service.revocation_reason = request.reason
        service.revoked_at = now
        await self._add_event(
            db,
            service,
            "service_revoked",
            operator,
            {
                "reason": request.reason,
                "revoked_credential_count": len(credentials),
            },
        )
        await db.commit()
        await db.refresh(service)
        return self._service_without_aggregates(service)

    async def revoke_credential(
        self,
        db: AsyncSession,
        project_code: str,
        credential_code: str,
        request: ServiceRevokeRequest,
    ) -> ServiceCredentialResponse:
        """单独撤销一个 API Key 凭证。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            credential_code: 凭证编号。
            request: 撤销原因和操作人。

        Returns:
            ServiceCredentialResponse: 已撤销凭证摘要。
        """
        project = await self._project(db, project_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_services",
        )
        credential = await self.dao.get_credential_by_code(
            db,
            project.id,
            credential_code,
            for_update=True,
        )
        if credential is None:
            raise NotFoundException(f"未找到访问凭证 {credential_code}")
        if credential.status != "active":
            raise ValidationException("凭证已失效或已经撤销")
        service = await self.dao.get_service_by_id(db, credential.service_id)
        if service is None:
            raise NotFoundException("凭证关联服务不存在")
        now = datetime.now(UTC)
        self._revoke_credential_model(
            credential,
            operator,
            request.reason,
            now,
        )
        await self._add_event(
            db,
            service,
            "credential_revoked",
            operator,
            {"credential_code": credential_code, "reason": request.reason},
            credential=credential,
        )
        await db.commit()
        await db.refresh(credential)
        response = self._credential_response(credential)
        if response is None:
            raise ValidationException("凭证状态转换失败")
        return response

    async def record_usage(
        self,
        db: AsyncSession,
        project_code: str,
        service_code: str,
        request: ServiceUsageRecordRequest,
    ) -> ServiceUsageEventResponse:
        """校验项目身份或 API Key 后记录一次服务调用。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            service_code: 服务编号。
            request: 调用结果和二选一身份凭据。

        Returns:
            ServiceUsageEventResponse: 已持久化调用事件。
        """
        project = await self._project(db, project_code)
        service = await self.dao.get_service_by_code(
            db,
            project.id,
            service_code,
        )
        if service is None:
            raise NotFoundException(f"未找到共享服务 {service_code}")
        if service.status != "active":
            raise ValidationException("服务未激活，不能记录有效调用")
        credential: ServiceCredential | None = None
        access_request: ServiceAccessRequest | None = None
        if request.operator_code:
            actor = await self.user_service.require_capability(
                db,
                project.id,
                request.operator_code,
                "manage_services",
            )
        else:
            if service.auth_mode != "api_key":
                raise ValidationException("当前服务不接受 API Key 调用凭据")
            credential = await self.dao.get_credential_by_code(
                db,
                project.id,
                request.credential_code or "",
            )
            if credential is None or credential.service_id != service.id:
                raise ValidationException("访问凭证不存在或不属于当前服务")
            if (
                credential.status != "active"
                or credential.expires_at <= datetime.now(UTC)
            ):
                raise ValidationException("访问凭证已失效")
            actual_hash = hashlib.sha256(
                (request.credential_secret or "").encode("utf-8")
            ).hexdigest()
            if not hmac.compare_digest(actual_hash, credential.secret_hash):
                raise ValidationException("访问凭证密钥不正确")
            actor = type(
                "CredentialActor",
                (),
                {
                    "display_name": "API Key 调用方",
                    "user_code": credential.credential_code,
                    "role_code": "service_consumer",
                },
            )()
        event = await self._add_event(
            db,
            service,
            "invocation_recorded",
            actor,
            {"authenticated_by": "api_key" if credential else "project_user"},
            access_request=access_request,
            credential=credential,
            request_method=request.request_method,
            request_path=request.request_path,
            response_status=request.response_status,
            duration_ms=request.duration_ms,
            response_bytes=request.response_bytes,
        )
        await db.commit()
        await db.refresh(event)
        row = {ServiceUsageEvent: event, "service_code": service.service_code}
        return self._event_response(row)

    @staticmethod
    def _revoke_credential_model(
        credential: ServiceCredential,
        operator: object,
        reason: str,
        revoked_at: datetime,
    ) -> None:
        """在当前事务中更新凭证撤销快照。

        Args:
            credential: 待撤销凭证。
            operator: 稳定项目用户。
            reason: 撤销原因。
            revoked_at: 撤销时间。

        Returns:
            None: 直接更新 ORM 模型。
        """
        credential.status = "revoked"
        credential.revoked_by = operator.display_name
        credential.revoked_by_code = operator.user_code
        credential.revoked_by_role = operator.role_code
        credential.revocation_reason = reason
        credential.revoked_at = revoked_at

    async def _validate_health_target(self, url: str) -> None:
        """解析目标地址并拒绝未显式放行的内网 SSRF 目标。

        Args:
            url: 待探测 HTTP(S) URL。

        Returns:
            None: 地址安全时返回。
        """
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            raise ValidationException("健康检查地址缺少主机名")
        allowlist = {
            item.strip().lower()
            for item in settings.service_health_private_host_allowlist.split(",")
            if item.strip()
        }
        if hostname.lower() in allowlist:
            return
        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise ValidationException("健康检查地址无法解析") from exc
        for address in {item[4][0] for item in addresses}:
            ip = ipaddress.ip_address(address)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise ValidationException("健康检查地址指向未放行的内网目标")

    @staticmethod
    def _service_without_aggregates(
        service: SharedService,
    ) -> SharedServiceResponse:
        """转换刚完成操作但尚无聚合查询的服务。

        Args:
            service: 共享服务模型。

        Returns:
            SharedServiceResponse: 聚合计数为零的服务响应。
        """
        return SharedServiceResponse(
            service_code=service.service_code,
            service_name=service.service_name,
            service_type=service.service_type,
            endpoint_url=service.endpoint_url,
            health_check_url=service.health_check_url,
            documentation_url=service.documentation_url,
            resource_type=service.resource_type,
            resource_code=service.resource_code,
            resource_checksum_sha256=service.resource_checksum_sha256,
            data_classification=service.data_classification,
            exposure_scope=service.exposure_scope,
            auth_mode=service.auth_mode,
            status=service.status,
            owner_department=service.owner_department,
            registered_by=service.registered_by,
            registered_by_code=service.registered_by_code,
            registered_by_role=service.registered_by_role,
            reviewed_by=service.reviewed_by,
            review_comment=service.review_comment,
            created_at=service.created_at,
            updated_at=service.updated_at,
            latest_health=None,
            access_request_count=0,
            active_credential_count=0,
            usage_count=0,
        )

    async def _add_event(
        self,
        db: AsyncSession,
        service: SharedService,
        event_type: str,
        actor: object,
        detail: dict,
        *,
        access_request: ServiceAccessRequest | None = None,
        credential: ServiceCredential | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        response_status: int | None = None,
        duration_ms: int | None = None,
        response_bytes: int | None = None,
    ) -> ServiceUsageEvent:
        """新增稳定身份、业务关联和调用指标完整的事件。

        Args:
            db: 异步数据库会话。
            service: 关联共享服务。
            event_type: 事件类型。
            actor: 稳定项目用户或凭证调用方。
            detail: 事件业务详情。
            access_request: 可选访问申请。
            credential: 可选访问凭证。
            request_method: 可选 HTTP 方法。
            request_path: 可选请求路径。
            response_status: 可选响应状态码。
            duration_ms: 可选耗时。
            response_bytes: 可选响应字节数。

        Returns:
            ServiceUsageEvent: 已刷新不可变事件。
        """
        return await self.dao.add_event(
            db,
            ServiceUsageEvent(
                service_id=service.id,
                access_request_id=(
                    access_request.id
                    if access_request
                    else credential.access_request_id
                    if credential
                    else None
                ),
                credential_id=credential.id if credential else None,
                event_type=event_type,
                request_method=request_method,
                request_path=request_path,
                response_status=response_status,
                duration_ms=duration_ms,
                response_bytes=response_bytes,
                detail=detail,
                actor=actor.display_name,
                actor_code=actor.user_code,
                actor_role=actor.role_code,
            ),
        )
