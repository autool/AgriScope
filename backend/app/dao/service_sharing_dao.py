"""共享服务注册、申请、凭证、健康和审计数据访问层。"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_sharing import (
    ServiceAccessRequest,
    ServiceCredential,
    ServiceHealthCheck,
    ServiceUsageEvent,
    SharedService,
)
from app.models.thematic_map import ThematicMapProduct
from app.models.workbench import (
    DatasetAsset,
    DeliveryPackage,
    ImageryAsset,
    MonitoringProject,
    MonitoringTask,
)


@dataclass(frozen=True)
class ServiceResourceEvidence:
    """共享服务绑定的真实资源证据。"""

    resource_code: str
    checksum_sha256: str
    data_classification: str
    status: str


class ServiceSharingDAO:
    """封装受控共享服务工作流全部数据库操作。"""

    async def get_project_by_code(
        self,
        db: AsyncSession,
        project_code: str,
    ) -> MonitoringProject | None:
        """按业务编号查询项目。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。

        Returns:
            MonitoringProject | None: 项目或空值。
        """
        result = await db.execute(
            select(MonitoringProject).where(
                MonitoringProject.project_code == project_code
            )
        )
        return result.scalar_one_or_none()

    async def get_resource_evidence(
        self,
        db: AsyncSession,
        project_id: int,
        resource_type: str,
        resource_code: str,
    ) -> ServiceResourceEvidence | None:
        """按资源类型查询项目真实实体及其校验值。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            resource_type: 影像、专题图、交付包或数据目录类型。
            resource_code: 资源业务编号。

        Returns:
            ServiceResourceEvidence | None: 已登记资源证据或空值。
        """
        if resource_type == "imagery":
            result = await db.execute(
                select(ImageryAsset).where(
                    ImageryAsset.project_id == project_id,
                    ImageryAsset.asset_code == resource_code,
                )
            )
            asset = result.scalar_one_or_none()
            if asset is None or not asset.checksum_sha256:
                return None
            classification = str(
                (asset.raster_metadata or {})
                .get("tags", {})
                .get("SECURITY_CLASSIFICATION", "internal")
            ).lower()
            return ServiceResourceEvidence(
                resource_code=asset.asset_code,
                checksum_sha256=asset.checksum_sha256,
                data_classification=classification,
                status=asset.data_status,
            )
        if resource_type == "thematic_map":
            result = await db.execute(
                select(ThematicMapProduct)
                .join(
                    MonitoringTask,
                    MonitoringTask.id == ThematicMapProduct.task_id,
                )
                .where(
                    MonitoringTask.project_id == project_id,
                    ThematicMapProduct.product_code == resource_code,
                )
            )
            product = result.scalar_one_or_none()
            if product is None:
                return None
            return ServiceResourceEvidence(
                resource_code=product.product_code,
                checksum_sha256=product.checksum_sha256,
                data_classification=str(
                    product.render_manifest.get(
                        "security_classification",
                        "internal",
                    )
                ),
                status=product.status,
            )
        if resource_type == "delivery":
            result = await db.execute(
                select(DeliveryPackage)
                .join(
                    MonitoringTask,
                    MonitoringTask.id == DeliveryPackage.task_id,
                )
                .where(
                    MonitoringTask.project_id == project_id,
                    DeliveryPackage.package_code == resource_code,
                )
            )
            package = result.scalar_one_or_none()
            if package is None or not package.checksum_sha256:
                return None
            return ServiceResourceEvidence(
                resource_code=package.package_code,
                checksum_sha256=package.checksum_sha256,
                data_classification="internal",
                status=package.status,
            )
        result = await db.execute(
            select(DatasetAsset).where(
                DatasetAsset.project_id == project_id,
                DatasetAsset.asset_code == resource_code,
            )
        )
        dataset = result.scalar_one_or_none()
        if dataset is None:
            return None
        return ServiceResourceEvidence(
            resource_code=dataset.asset_code,
            checksum_sha256=dataset.checksum_sha256,
            data_classification=dataset.security_classification,
            status=dataset.verification_status,
        )

    async def list_services(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[SharedService]:
        """查询项目共享服务目录。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[SharedService]: 按创建时间倒序排列的服务。
        """
        result = await db.execute(
            select(SharedService)
            .where(SharedService.project_id == project_id)
            .order_by(SharedService.created_at.desc())
        )
        return result.scalars().all()

    async def get_service_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        service_code: str,
        *,
        for_update: bool = False,
    ) -> SharedService | None:
        """按项目和服务编号查询，可选加行锁。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            service_code: 服务编号。
            for_update: 是否锁定服务行。

        Returns:
            SharedService | None: 服务或空值。
        """
        statement = select(SharedService).where(
            SharedService.project_id == project_id,
            SharedService.service_code == service_code,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_service_by_id(
        self,
        db: AsyncSession,
        service_id: int,
        *,
        for_update: bool = False,
    ) -> SharedService | None:
        """按主键查询共享服务，可选加行锁。

        Args:
            db: 异步数据库会话。
            service_id: 服务主键。
            for_update: 是否锁定服务行。

        Returns:
            SharedService | None: 服务或空值。
        """
        statement = select(SharedService).where(SharedService.id == service_id)
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def add_service(
        self,
        db: AsyncSession,
        service: SharedService,
    ) -> SharedService:
        """新增服务登记。

        Args:
            db: 异步数据库会话。
            service: 待登记服务。

        Returns:
            SharedService: 已刷新服务。
        """
        db.add(service)
        await db.flush()
        await db.refresh(service)
        return service

    async def list_access_requests(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[ServiceAccessRequest]:
        """查询项目全部服务访问申请。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[ServiceAccessRequest]: 按申请时间倒序排列的记录。
        """
        result = await db.execute(
            select(ServiceAccessRequest)
            .join(
                SharedService,
                SharedService.id == ServiceAccessRequest.service_id,
            )
            .where(SharedService.project_id == project_id)
            .order_by(ServiceAccessRequest.created_at.desc())
        )
        return result.scalars().all()

    async def get_access_request_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        request_code: str,
        *,
        for_update: bool = False,
    ) -> ServiceAccessRequest | None:
        """按项目查询访问申请，可选加行锁。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            request_code: 申请编号。
            for_update: 是否锁定申请行。

        Returns:
            ServiceAccessRequest | None: 申请记录或空值。
        """
        statement = (
            select(ServiceAccessRequest)
            .join(
                SharedService,
                SharedService.id == ServiceAccessRequest.service_id,
            )
            .where(
                SharedService.project_id == project_id,
                ServiceAccessRequest.request_code == request_code,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def add_access_request(
        self,
        db: AsyncSession,
        request: ServiceAccessRequest,
    ) -> ServiceAccessRequest:
        """新增服务访问申请。

        Args:
            db: 异步数据库会话。
            request: 访问申请模型。

        Returns:
            ServiceAccessRequest: 已刷新申请。
        """
        db.add(request)
        await db.flush()
        await db.refresh(request)
        return request

    async def list_credentials(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[ServiceCredential]:
        """查询项目全部凭证摘要。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[ServiceCredential]: 凭证记录。
        """
        result = await db.execute(
            select(ServiceCredential)
            .join(SharedService, SharedService.id == ServiceCredential.service_id)
            .where(SharedService.project_id == project_id)
            .order_by(ServiceCredential.issued_at.desc())
        )
        return result.scalars().all()

    async def get_credential_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        credential_code: str,
        *,
        for_update: bool = False,
    ) -> ServiceCredential | None:
        """按项目和凭证编号查询，可选加行锁。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            credential_code: 凭证编号。
            for_update: 是否锁定凭证行。

        Returns:
            ServiceCredential | None: 凭证或空值。
        """
        statement = (
            select(ServiceCredential)
            .join(SharedService, SharedService.id == ServiceCredential.service_id)
            .where(
                SharedService.project_id == project_id,
                ServiceCredential.credential_code == credential_code,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def list_active_credentials_for_service(
        self,
        db: AsyncSession,
        service_id: int,
    ) -> Sequence[ServiceCredential]:
        """锁定并查询服务全部活动凭证。

        Args:
            db: 异步数据库会话。
            service_id: 服务主键。

        Returns:
            Sequence[ServiceCredential]: 活动凭证。
        """
        result = await db.execute(
            select(ServiceCredential)
            .where(
                ServiceCredential.service_id == service_id,
                ServiceCredential.status == "active",
            )
            .with_for_update()
        )
        return result.scalars().all()

    async def add_credential(
        self,
        db: AsyncSession,
        credential: ServiceCredential,
    ) -> ServiceCredential:
        """新增只存哈希的访问凭证。

        Args:
            db: 异步数据库会话。
            credential: 凭证模型。

        Returns:
            ServiceCredential: 已刷新凭证。
        """
        db.add(credential)
        await db.flush()
        await db.refresh(credential)
        return credential

    async def list_latest_health_rows(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[RowMapping]:
        """查询项目全部健康记录，供服务层选取每项最新值。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[RowMapping]: 健康记录和服务编号。
        """
        result = await db.execute(
            select(ServiceHealthCheck, SharedService.service_code)
            .join(SharedService, SharedService.id == ServiceHealthCheck.service_id)
            .where(SharedService.project_id == project_id)
            .order_by(ServiceHealthCheck.checked_at.desc())
        )
        return result.mappings().all()

    async def add_health_check(
        self,
        db: AsyncSession,
        health: ServiceHealthCheck,
    ) -> ServiceHealthCheck:
        """新增不可变健康探测记录。

        Args:
            db: 异步数据库会话。
            health: 健康记录。

        Returns:
            ServiceHealthCheck: 已刷新健康记录。
        """
        db.add(health)
        await db.flush()
        await db.refresh(health)
        return health

    async def list_event_rows(
        self,
        db: AsyncSession,
        project_id: int,
        limit: int = 100,
    ) -> Sequence[RowMapping]:
        """查询项目最近共享服务事件。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            limit: 最大返回数量。

        Returns:
            Sequence[RowMapping]: 事件与服务编号关联行。
        """
        result = await db.execute(
            select(ServiceUsageEvent, SharedService.service_code)
            .join(SharedService, SharedService.id == ServiceUsageEvent.service_id)
            .where(SharedService.project_id == project_id)
            .order_by(ServiceUsageEvent.created_at.desc())
            .limit(limit)
        )
        return result.mappings().all()

    async def add_event(
        self,
        db: AsyncSession,
        event: ServiceUsageEvent,
    ) -> ServiceUsageEvent:
        """新增不可变共享服务事件。

        Args:
            db: 异步数据库会话。
            event: 审计事件。

        Returns:
            ServiceUsageEvent: 已刷新事件。
        """
        db.add(event)
        await db.flush()
        await db.refresh(event)
        return event
