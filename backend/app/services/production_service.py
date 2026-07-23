"""多源数据目录、生产批次与县区作业包业务服务。"""

import asyncio
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.production_dao import ProductionDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.workbench import (
    DatasetAsset,
    DatasetLineage,
    ProductionAuditEvent,
    ProductionBatch,
    ProjectRuleConfig,
    WorkPackage,
    WorkPackagePlot,
)
from app.schemas.production import (
    DatasetAssetCreateRequest,
    DatasetAssetResponse,
    ProductionBatchCreateRequest,
    ProductionBatchResponse,
    ProductionBatchStatusUpdateRequest,
    ProductionMetricsResponse,
    ProductionOverviewResponse,
    WorkAreaResponse,
    WorkPackageCreateRequest,
    WorkPackageCreateResponse,
    WorkPackageResponse,
    WorkPackageUpdateRequest,
)
from app.services.dataset_asset_service import DatasetAssetService
from app.services.project_user_service import ProjectUserService
from app.services.rule_config_service import RuleConfigService

BATCH_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"planned", "cancelled"},
    "planned": {"in_progress", "cancelled"},
    "in_progress": {"reconciling", "cancelled"},
    "reconciling": {"in_progress", "completed"},
    "completed": set(),
    "cancelled": set(),
}
PACKAGE_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in_progress", "blocked"},
    "in_progress": {"blocked", "completed"},
    "blocked": {"in_progress"},
    "completed": set(),
}
RECONCILIATION_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"checking"},
    "checking": {"passed", "conflict"},
    "conflict": {"checking"},
    "passed": set(),
}
DELIVERY_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"submitted"},
    "submitted": {"accepted", "returned"},
    "returned": {"submitted"},
    "accepted": set(),
}


class ProductionService:
    """编排多源资产、生产批次、作业分包和审计。"""

    def __init__(
        self,
        dao: ProductionDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        user_service: ProjectUserService | None = None,
        rule_service: RuleConfigService | None = None,
        dataset_asset_service: DatasetAssetService | None = None,
    ) -> None:
        """初始化生产调度服务。

        Args:
            dao: 生产模块 DAO。
            workbench_dao: 项目任务公共查询 DAO。
            user_service: 项目成员与能力服务。
            rule_service: 项目规则配置服务。
            dataset_asset_service: 数据资产实体复核服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ProductionDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.user_service = user_service or ProjectUserService()
        self.rule_service = rule_service or RuleConfigService()
        self.dataset_asset_service = dataset_asset_service or DatasetAssetService()

    async def _resolve_context(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
    ) -> tuple[object, object]:
        """解析并校验项目与任务归属关系。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。

        Returns:
            tuple[object, object]: 项目和任务 ORM 对象。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None or task.project_id != project.id:
            raise NotFoundException(f"项目内未找到任务 {task_code}")
        return project, task

    @staticmethod
    def _rule_snapshot(
        config: ProjectRuleConfig,
    ) -> dict[str, float | int | str | None]:
        """生成批次不可变规则快照。

        Args:
            config: 当前项目规则配置。

        Returns:
            dict[str, float | int | str | None]: 规则版本和量化阈值快照。
        """
        return {
            "field_offset_threshold_m": float(config.field_offset_threshold_m),
            "field_search_radius_m": float(config.field_search_radius_m),
            "positional_accuracy_pixels": float(config.positional_accuracy_pixels),
            "max_capture_image_days": config.max_capture_image_days,
            "construction_min_area_sqm": float(config.construction_min_area_sqm),
            "other_agricultural_min_area_sqm": float(
                config.other_agricultural_min_area_sqm
            ),
            "completeness_rate_min": float(config.completeness_rate_min),
            "boundary_agreement_rate_min": float(
                config.boundary_agreement_rate_min
            ),
            "land_class_accuracy_min": float(config.land_class_accuracy_min),
            "key_field_accuracy_min": float(config.key_field_accuracy_min),
            "max_cloud_cover_percent": (
                float(config.max_cloud_cover_percent)
                if config.max_cloud_cover_percent is not None
                else None
            ),
            "output_crs": config.output_crs,
            "output_projection": config.output_projection,
        }

    @staticmethod
    def _asset_response(
        row: object,
        parent_codes: list[str],
    ) -> DatasetAssetResponse:
        """将资产查询行转换为目录响应。

        Args:
            row: 包含资产 ORM 和范围坐标的映射行。
            parent_codes: 显式父资产编号。

        Returns:
            DatasetAssetResponse: 多源资产目录项。
        """
        return DatasetAssetService.to_response(row, parent_codes)

    @staticmethod
    def _package_response(row: object) -> WorkPackageResponse:
        """将作业包查询行转换为实时进度响应。

        Args:
            row: 作业包和实时图斑计数映射行。

        Returns:
            WorkPackageResponse: 作业包实时状态。
        """
        package = row[WorkPackage]
        active_count = int(row["active_plot_count"] or 0)
        completed_count = int(row["completed_plot_count"] or 0)
        progress = round(completed_count / active_count * 100, 2) if active_count else 0
        return WorkPackageResponse(
            package_code=package.package_code,
            package_name=package.package_name,
            region_code=package.region_code,
            region_name=package.region_name,
            region_level=package.region_level,
            planned_area_ha=float(package.planned_area_ha),
            planned_plot_count=package.planned_plot_count,
            active_plot_count=active_count,
            completed_plot_count=completed_count,
            progress=progress,
            assignee_code=package.assignee_code,
            assignee_name=package.assignee_name,
            deadline=package.deadline,
            overdue=package.deadline < date.today() and package.status != "completed",
            status=package.status,
            reconciliation_status=package.reconciliation_status,
            delivery_status=package.delivery_status,
            updated_at=package.updated_at,
        )

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
    ) -> ProductionOverviewResponse:
        """查询生产调度和多源数据目录聚合状态。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。

        Returns:
            ProductionOverviewResponse: 当前任务生产调度完整视图。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        asset_rows = await self.dao.list_assets(db, project.id)
        lineage_rows = await self.dao.list_lineages(db, project.id)
        work_area_rows = await self.dao.list_work_areas(db, project.id, task.id)
        assignment_rows = await self.dao.list_region_batch_assignments(db, task.id)
        batches = await self.dao.list_batches(db, task.id)
        package_rows = await self.dao.list_package_metrics(db, task.id)

        lineage_by_derived: dict[str, list[str]] = defaultdict(list)
        for row in lineage_rows:
            lineage_by_derived[row["derived_asset_code"]].append(
                row["parent_asset_code"]
            )
        assets = [
            self._asset_response(
                row,
                lineage_by_derived.get(row[DatasetAsset].asset_code, []),
            )
            for row in asset_rows
        ]
        asset_codes_by_id = {
            row[DatasetAsset].id: row[DatasetAsset].asset_code for row in asset_rows
        }
        package_responses = [self._package_response(row) for row in package_rows]
        package_by_id = {
            row[WorkPackage].id: response
            for row, response in zip(package_rows, package_responses, strict=True)
        }
        packages_by_batch: dict[int, list[WorkPackageResponse]] = defaultdict(list)
        for row in package_rows:
            package = row[WorkPackage]
            packages_by_batch[package.batch_id].append(package_by_id[package.id])

        batch_responses: list[ProductionBatchResponse] = []
        for batch in batches:
            packages = packages_by_batch.get(batch.id, [])
            planned_plot_count = sum(item.planned_plot_count for item in packages)
            active_plot_count = sum(item.active_plot_count for item in packages)
            completed_plot_count = sum(item.completed_plot_count for item in packages)
            progress = (
                round(completed_plot_count / active_plot_count * 100, 2)
                if active_plot_count
                else 0
            )
            batch_responses.append(
                ProductionBatchResponse(
                    batch_code=batch.batch_code,
                    batch_name=batch.batch_name,
                    source_asset_code=asset_codes_by_id.get(batch.source_asset_id),
                    target_asset_code=asset_codes_by_id.get(batch.target_asset_id),
                    rule_config_version=batch.rule_config_version,
                    rule_profile_snapshot=batch.rule_profile_snapshot or {},
                    planned_start_date=batch.planned_start_date,
                    planned_end_date=batch.planned_end_date,
                    status=batch.status,
                    package_count=len(packages),
                    planned_plot_count=planned_plot_count,
                    completed_plot_count=completed_plot_count,
                    progress=progress,
                    created_by=batch.created_by,
                    created_by_code=batch.created_by_code,
                    created_at=batch.created_at,
                    packages=packages,
                )
            )

        assigned_batches: dict[str, list[str]] = defaultdict(list)
        for row in assignment_rows:
            assigned_batches[row["region_code"]].append(row["batch_code"])
        work_areas = [
            WorkAreaResponse(
                city_code=row["city_code"],
                city_name=row["city_name"],
                region_code=row["region_code"],
                region_name=row["region_name"],
                plot_count=int(row["plot_count"] or 0),
                area_ha=float(row["area_ha"] or 0),
                assigned_batch_codes=assigned_batches.get(row["region_code"], []),
            )
            for row in work_area_rows
        ]
        asset_type_counts: dict[str, int] = defaultdict(int)
        for asset in assets:
            asset_type_counts[asset.asset_type] += 1
        active_batches = {
            "planned",
            "in_progress",
            "reconciling",
        }
        return ProductionOverviewResponse(
            project_code=project_code,
            task_code=task_code,
            metrics=ProductionMetricsResponse(
                asset_count=len(assets),
                pending_asset_verification_count=sum(
                    asset.verification_status != "verified" for asset in assets
                ),
                batch_count=len(batch_responses),
                active_batch_count=sum(
                    batch.status in active_batches for batch in batch_responses
                ),
                package_count=len(package_responses),
                overdue_package_count=sum(item.overdue for item in package_responses),
                assigned_plot_count=sum(
                    item.active_plot_count for item in package_responses
                ),
                completed_plot_count=sum(
                    item.completed_plot_count for item in package_responses
                ),
            ),
            asset_type_counts=dict(asset_type_counts),
            assets=assets,
            work_areas=work_areas,
            batches=batch_responses,
        )

    async def register_asset(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: DatasetAssetCreateRequest,
    ) -> DatasetAssetResponse:
        """登记多源数据资产、父资产血缘和操作审计。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            request: 来源、版本、校验值、密级和血缘。

        Returns:
            DatasetAssetResponse: 已登记但尚待实体核验的资产。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_datasets",
        )
        if await self.dao.get_asset_by_code(db, project.id, request.asset_code):
            raise ValidationException(f"资产编号 {request.asset_code} 已存在")
        duplicate = await self.dao.get_asset_by_checksum(
            db,
            project.id,
            request.checksum_sha256.lower(),
        )
        if duplicate is not None:
            raise ValidationException(
                f"相同内容已登记为资产 {duplicate.asset_code}，请建立血缘而非重复入库"
            )
        parent_assets = await self.dao.get_assets_by_codes(
            db,
            project.id,
            request.parent_asset_codes,
        )
        if len(parent_assets) != len(request.parent_asset_codes):
            found = {asset.asset_code for asset in parent_assets}
            missing = [code for code in request.parent_asset_codes if code not in found]
            raise ValidationException(f"父资产不存在：{', '.join(missing)}")
        extent = (
            func.ST_MakeEnvelope(*request.extent_bbox, 4326)
            if request.extent_bbox
            else None
        )
        asset = await self.dao.add_asset(
            db,
            DatasetAsset(
                project_id=project.id,
                task_id=task.id,
                asset_code=request.asset_code,
                asset_name=request.asset_name,
                asset_type=request.asset_type,
                source_name=request.source_name,
                source_uri=request.source_uri,
                source_version=request.source_version,
                checksum_sha256=request.checksum_sha256.lower(),
                crs=request.crs,
                extent=extent,
                time_start=request.time_start,
                time_end=request.time_end,
                security_classification=request.security_classification,
                data_status=request.data_status,
                verification_status="pending",
                metadata_payload=request.metadata,
                registered_by=operator.display_name,
                registered_by_code=operator.user_code,
                registered_by_role=operator.role_code,
            ),
        )
        await self.dao.add_lineages(
            db,
            [
                DatasetLineage(
                    parent_asset_id=parent.id,
                    derived_asset_id=asset.id,
                    relation_type=request.lineage_relation_type,
                    process_code=request.process_code,
                )
                for parent in parent_assets
            ],
        )
        await self.dao.add_audit_event(
            db,
            ProductionAuditEvent(
                project_id=project.id,
                task_id=task.id,
                entity_type="dataset_asset",
                entity_code=asset.asset_code,
                action="registered",
                previous_values={},
                new_values={
                    "asset_type": asset.asset_type,
                    "source_name": asset.source_name,
                    "source_version": asset.source_version,
                    "checksum_sha256": asset.checksum_sha256,
                    "verification_status": asset.verification_status,
                    "parent_asset_codes": request.parent_asset_codes,
                },
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
            ),
        )
        await db.commit()
        overview = await self.get_overview(db, project_code, task_code)
        return next(
            item for item in overview.assets if item.asset_code == asset.asset_code
        )

    async def create_batch(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: ProductionBatchCreateRequest,
    ) -> ProductionBatchResponse:
        """按当前规则版本创建可审计生产批次。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            request: 批次编号、时相资产和计划日期。

        Returns:
            ProductionBatchResponse: 新建生产批次。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_production",
        )
        if await self.dao.get_batch_by_code(db, task.id, request.batch_code):
            raise ValidationException(f"生产批次 {request.batch_code} 已存在")

        async def resolve_asset(asset_code: str | None) -> DatasetAsset | None:
            if asset_code is None:
                return None
            asset = await self.dao.get_asset_by_code(db, project.id, asset_code)
            if asset is None:
                raise ValidationException(f"未找到批次关联资产 {asset_code}")
            if asset.asset_type != "imagery":
                raise ValidationException(f"批次时相资产 {asset_code} 不是影像类型")
            if asset.verification_status != "verified":
                raise ValidationException(
                    f"批次时相资产 {asset_code} 尚未通过实体核验"
                )
            await asyncio.to_thread(
                self.dataset_asset_service.resolve_verified_file,
                asset,
            )
            return asset

        source_asset = await resolve_asset(request.source_asset_code)
        target_asset = await resolve_asset(request.target_asset_code)
        config = await self.rule_service.ensure_for_project(db, project.id)
        batch = await self.dao.add_batch(
            db,
            ProductionBatch(
                project_id=project.id,
                task_id=task.id,
                batch_code=request.batch_code,
                batch_name=request.batch_name.strip(),
                source_asset_id=source_asset.id if source_asset else None,
                target_asset_id=target_asset.id if target_asset else None,
                rule_config_version=config.version,
                rule_profile_snapshot=self._rule_snapshot(config),
                planned_start_date=request.planned_start_date,
                planned_end_date=request.planned_end_date,
                status="planned",
                created_by=operator.display_name,
                created_by_code=operator.user_code,
                created_by_role=operator.role_code,
            ),
        )
        await self.dao.add_audit_event(
            db,
            ProductionAuditEvent(
                project_id=project.id,
                task_id=task.id,
                entity_type="production_batch",
                entity_code=batch.batch_code,
                action="created",
                previous_values={},
                new_values={
                    "status": batch.status,
                    "source_asset_code": request.source_asset_code,
                    "target_asset_code": request.target_asset_code,
                    "rule_config_version": config.version,
                    "planned_start_date": request.planned_start_date.isoformat(),
                    "planned_end_date": request.planned_end_date.isoformat(),
                },
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
            ),
        )
        await db.commit()
        overview = await self.get_overview(db, project_code, task_code)
        return next(
            item for item in overview.batches if item.batch_code == batch.batch_code
        )

    async def create_work_packages(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        batch_code: str,
        request: WorkPackageCreateRequest,
    ) -> WorkPackageCreateResponse:
        """按真实县区生成作业包并显式固化任务图斑范围。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            batch_code: 目标生产批次编号。
            request: 县区列表、负责人、期限和操作人。

        Returns:
            WorkPackageCreateResponse: 新建包和显式分配图斑统计。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_production",
        )
        assignee = await self.dao.get_active_project_user(
            db,
            project.id,
            request.assignee_code,
        )
        if assignee is None:
            raise ValidationException("作业包负责人不属于当前项目或账号已停用")
        batch = await self.dao.get_batch_by_code_for_update(db, task.id, batch_code)
        if batch is None:
            raise NotFoundException(f"未找到生产批次 {batch_code}")
        if batch.status in {"completed", "cancelled"}:
            raise ValidationException("已完成或已取消批次不能新增作业包")
        if not batch.planned_start_date <= request.deadline <= batch.planned_end_date:
            raise ValidationException("作业包期限必须位于生产批次计划周期内")
        package_rows = await self.dao.list_package_metrics(db, task.id)
        existing_regions = {
            row[WorkPackage].region_code
            for row in package_rows
            if row[WorkPackage].batch_id == batch.id
        }
        duplicates = [code for code in request.region_codes if code in existing_regions]
        if duplicates:
            raise ValidationException(f"当前批次已包含县区：{', '.join(duplicates)}")

        created_packages: list[WorkPackage] = []
        assigned_plot_count = 0
        for region_code in request.region_codes:
            district = await self.dao.get_district(db, project.id, region_code)
            if district is None:
                raise ValidationException(f"未找到真实县区 {region_code}")
            plots = await self.dao.list_task_region_plots(db, task.id, region_code)
            if not plots:
                raise ValidationException(
                    f"县区 {district.boundary_name} 当前任务没有可分配图斑"
                )
            planned_area = sum(
                (Decimal(str(row["area_ha"] or 0)) for row in plots),
                start=Decimal("0"),
            )
            package_code = f"{batch.batch_code[:48]}-{region_code[:50]}"
            package = await self.dao.add_package(
                db,
                WorkPackage(
                    batch_id=batch.id,
                    package_code=package_code,
                    package_name=f"{district.boundary_name}生产作业包",
                    region_code=region_code,
                    region_name=district.boundary_name,
                    region_level="district",
                    planned_area_ha=planned_area,
                    planned_plot_count=len(plots),
                    assignee_code=assignee.user_code,
                    assignee_name=assignee.display_name,
                    deadline=request.deadline,
                    status="pending",
                    reconciliation_status="pending",
                    delivery_status="pending",
                    created_by=operator.display_name,
                    created_by_code=operator.user_code,
                    created_by_role=operator.role_code,
                ),
            )
            await self.dao.add_package_plots(
                db,
                [
                    WorkPackagePlot(
                        work_package_id=package.id,
                        plot_code=row["plot_code"],
                    )
                    for row in plots
                ],
            )
            await self.dao.add_audit_event(
                db,
                ProductionAuditEvent(
                    project_id=project.id,
                    task_id=task.id,
                    entity_type="work_package",
                    entity_code=package.package_code,
                    action="created",
                    previous_values={},
                    new_values={
                        "batch_code": batch.batch_code,
                        "region_code": region_code,
                        "assignee_code": assignee.user_code,
                        "deadline": request.deadline.isoformat(),
                        "planned_plot_count": len(plots),
                        "planned_area_ha": float(planned_area),
                    },
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                ),
            )
            created_packages.append(package)
            assigned_plot_count += len(plots)
        await db.commit()
        overview = await self.get_overview(db, project_code, task_code)
        response_batch = next(
            item for item in overview.batches if item.batch_code == batch_code
        )
        created_codes = {package.package_code for package in created_packages}
        responses = [
            package
            for package in response_batch.packages
            if package.package_code in created_codes
        ]
        return WorkPackageCreateResponse(
            batch_code=batch_code,
            created_count=len(responses),
            assigned_plot_count=assigned_plot_count,
            packages=responses,
        )

    async def update_batch_status(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        batch_code: str,
        request: ProductionBatchStatusUpdateRequest,
    ) -> ProductionBatchResponse:
        """按受控状态机更新生产批次并写入审计。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            batch_code: 批次编号。
            request: 目标状态和操作人。

        Returns:
            ProductionBatchResponse: 更新后的批次。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_production",
        )
        batch = await self.dao.get_batch_by_code_for_update(db, task.id, batch_code)
        if batch is None:
            raise NotFoundException(f"未找到生产批次 {batch_code}")
        if request.status == batch.status:
            raise ValidationException("生产批次已经处于目标状态")
        if request.status not in BATCH_TRANSITIONS.get(batch.status, set()):
            raise ValidationException(
                f"生产批次不能从 {batch.status} 直接变更为 {request.status}"
            )
        overview = await self.get_overview(db, project_code, task_code)
        current = next(
            item for item in overview.batches if item.batch_code == batch_code
        )
        if request.status == "completed":
            if not current.packages:
                raise ValidationException("没有作业包的生产批次不能完成")
            if any(package.status != "completed" for package in current.packages):
                raise ValidationException("仍有未完成作业包，不能完成生产批次")
            if any(
                package.reconciliation_status != "passed"
                for package in current.packages
            ):
                raise ValidationException("仍有作业包未通过合并校核")
        previous_status = batch.status
        batch.status = request.status
        batch.updated_at = datetime.now(UTC)
        await self.dao.add_audit_event(
            db,
            ProductionAuditEvent(
                project_id=project.id,
                task_id=task.id,
                entity_type="production_batch",
                entity_code=batch.batch_code,
                action="status_updated",
                previous_values={"status": previous_status},
                new_values={"status": request.status},
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
            ),
        )
        await db.commit()
        updated = await self.get_overview(db, project_code, task_code)
        return next(item for item in updated.batches if item.batch_code == batch_code)

    async def update_work_package(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        package_code: str,
        request: WorkPackageUpdateRequest,
    ) -> WorkPackageResponse:
        """更新作业包调度字段并保留修改前后值。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 任务编号。
            package_code: 作业包编号。
            request: 负责人、期限或状态变更。

        Returns:
            WorkPackageResponse: 更新后的作业包实时状态。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_production",
        )
        package = await self.dao.get_package_by_code_for_update(
            db,
            task.id,
            package_code,
        )
        if package is None:
            raise NotFoundException(f"未找到作业包 {package_code}")
        batch = await self.dao.get_batch_by_id(db, package.batch_id)
        if batch is None:
            raise NotFoundException("作业包所属生产批次不存在")
        if batch.status in {"completed", "cancelled"}:
            raise ValidationException("已完成或已取消批次不能修改作业包")
        previous_values = {
            "assignee_code": package.assignee_code,
            "deadline": package.deadline.isoformat(),
            "status": package.status,
            "reconciliation_status": package.reconciliation_status,
            "delivery_status": package.delivery_status,
        }
        if request.assignee_code:
            assignee = await self.dao.get_active_project_user(
                db,
                project.id,
                request.assignee_code,
            )
            if assignee is None:
                raise ValidationException("新负责人不属于当前项目或账号已停用")
            package.assignee_code = assignee.user_code
            package.assignee_name = assignee.display_name
        if request.deadline:
            if not (
                batch.planned_start_date
                <= request.deadline
                <= batch.planned_end_date
            ):
                raise ValidationException("作业包期限必须位于生产批次计划周期内")
            package.deadline = request.deadline
        if request.status and request.status != package.status:
            if request.status not in PACKAGE_TRANSITIONS.get(package.status, set()):
                raise ValidationException(
                    f"作业包不能从 {package.status} 直接变更为 {request.status}"
                )
        if (
            request.reconciliation_status
            and request.reconciliation_status != package.reconciliation_status
            and request.reconciliation_status
            not in RECONCILIATION_TRANSITIONS.get(
                package.reconciliation_status,
                set(),
            )
        ):
            raise ValidationException(
                "作业包合并校核状态不允许直接跳转到目标状态"
            )
        if (
            request.delivery_status
            and request.delivery_status != package.delivery_status
            and request.delivery_status
            not in DELIVERY_TRANSITIONS.get(package.delivery_status, set())
        ):
            raise ValidationException("作业包交付状态不允许直接跳转到目标状态")
        if request.status == "completed":
            active_count, completed_count = await self.dao.get_package_progress(
                db,
                package.id,
            )
            if active_count == 0 or completed_count != active_count:
                raise ValidationException("作业包图斑尚未全部解译，不能标记完成")
            reconciliation_status = (
                request.reconciliation_status or package.reconciliation_status
            )
            if reconciliation_status != "passed":
                raise ValidationException("作业包合并校核未通过，不能标记完成")
        if request.delivery_status == "accepted" and (
            request.status or package.status
        ) != "completed":
            raise ValidationException("作业包尚未完成，不能确认接收")
        if request.status:
            package.status = request.status
        if request.reconciliation_status:
            package.reconciliation_status = request.reconciliation_status
        if request.delivery_status:
            package.delivery_status = request.delivery_status
        package.updated_at = datetime.now(UTC)
        new_values = {
            "assignee_code": package.assignee_code,
            "deadline": package.deadline.isoformat(),
            "status": package.status,
            "reconciliation_status": package.reconciliation_status,
            "delivery_status": package.delivery_status,
        }
        await self.dao.add_audit_event(
            db,
            ProductionAuditEvent(
                project_id=project.id,
                task_id=task.id,
                entity_type="work_package",
                entity_code=package.package_code,
                action="updated",
                previous_values=previous_values,
                new_values=new_values,
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
            ),
        )
        await db.commit()
        overview = await self.get_overview(db, project_code, task_code)
        return next(
            item
            for batch in overview.batches
            for item in batch.packages
            if item.package_code == package_code
        )
