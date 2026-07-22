"""多源数据目录、生产批次与县区作业包端点。"""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DatabaseSession
from app.schemas.production import (
    DatasetAssetCreateRequest,
    DatasetAssetResponse,
    ProductionBatchCreateRequest,
    ProductionBatchResponse,
    ProductionBatchStatusUpdateRequest,
    ProductionOverviewResponse,
    WorkPackageCreateRequest,
    WorkPackageCreateResponse,
    WorkPackageResponse,
    WorkPackageUpdateRequest,
)
from app.services.production_service import ProductionService

router = APIRouter(prefix="/api/v1/production", tags=["遥感生产调度"])
service = ProductionService()


@router.get("/overview", response_model=ProductionOverviewResponse)
async def get_production_overview(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ProductionOverviewResponse:
    """查询多源数据目录、生产批次和县区作业包。

    Args:
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ProductionOverviewResponse: 生产调度实时聚合结果。
    """
    return await service.get_overview(db, project_code, task_code)


@router.post(
    "/dataset-assets",
    response_model=DatasetAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_dataset_asset(
    request: DatasetAssetCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DatasetAssetResponse:
    """登记多源数据来源、版本、校验值、密级和派生血缘。

    Args:
        request: 资产来源证据和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        DatasetAssetResponse: 已登记、待实体核验的数据资产。
    """
    return await service.register_asset(db, project_code, task_code, request)


@router.post(
    "/batches",
    response_model=ProductionBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_production_batch(
    request: ProductionBatchCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ProductionBatchResponse:
    """按当前规则版本创建生产批次。

    Args:
        request: 批次编号、时相资产和计划周期。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ProductionBatchResponse: 新建生产批次。
    """
    return await service.create_batch(db, project_code, task_code, request)


@router.post(
    "/batches/{batch_code}/work-packages",
    response_model=WorkPackageCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_work_packages(
    batch_code: str,
    request: WorkPackageCreateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> WorkPackageCreateResponse:
    """按真实县区创建作业包并显式关联任务图斑。

    Args:
        batch_code: 生产批次编号。
        request: 县区、负责人、期限和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        WorkPackageCreateResponse: 创建数量和显式分配图斑统计。
    """
    return await service.create_work_packages(
        db,
        project_code,
        task_code,
        batch_code,
        request,
    )


@router.patch(
    "/batches/{batch_code}/status",
    response_model=ProductionBatchResponse,
)
async def update_production_batch_status(
    batch_code: str,
    request: ProductionBatchStatusUpdateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> ProductionBatchResponse:
    """按状态机流转生产批次。

    Args:
        batch_code: 生产批次编号。
        request: 目标状态和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        ProductionBatchResponse: 更新后的批次。
    """
    return await service.update_batch_status(
        db,
        project_code,
        task_code,
        batch_code,
        request,
    )


@router.patch(
    "/work-packages/{package_code}",
    response_model=WorkPackageResponse,
)
async def update_work_package(
    package_code: str,
    request: WorkPackageUpdateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> WorkPackageResponse:
    """更新作业包负责人、期限和生产状态。

    Args:
        package_code: 作业包编号。
        request: 待修改字段和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。
        task_code: 作业任务编号。

    Returns:
        WorkPackageResponse: 更新后的作业包实时进度。
    """
    return await service.update_work_package(
        db,
        project_code,
        task_code,
        package_code,
        request,
    )
