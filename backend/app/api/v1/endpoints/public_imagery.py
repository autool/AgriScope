"""公开 Landsat 历史语料检索与实体入库端点。"""

from fastapi import APIRouter, status

from app.api.deps import DatabaseSession
from app.schemas.public_imagery import (
    PublicImageryBatchImportRequest,
    PublicImageryBatchImportResponse,
    PublicImageryImportRequest,
    PublicImageryImportResponse,
    PublicImagerySearchRequest,
    PublicImagerySearchResponse,
)
from app.services.public_imagery_service import PublicImageryService

router = APIRouter(prefix="/api/v1/public-imagery", tags=["公开历史影像语料"])
service = PublicImageryService()


@router.post("/search", response_model=PublicImagerySearchResponse)
async def search_public_imagery(
    request: PublicImagerySearchRequest,
    db: DatabaseSession,
) -> PublicImagerySearchResponse:
    """从固定 Planetary Computer collection 检索真实 Landsat 候选。

    Args:
        request: 日期、云量和 WGS84 检索范围。
        db: 用于 PostGIS 足迹覆盖分析的异步会话。

    Returns:
        PublicImagerySearchResponse: 不含任何 SAS Token 的候选列表。
    """
    return await service.search(db, request)


@router.post(
    "/import",
    response_model=PublicImageryImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_public_imagery(
    request: PublicImageryImportRequest,
    db: DatabaseSession,
) -> PublicImageryImportResponse:
    """服务端重取候选、裁取地表反射率实体并原子入库。

    Args:
        request: Item ID、裁取范围、资产标识和稳定操作人。
        db: 异步数据库会话。

    Returns:
        PublicImageryImportResponse: 来源证据和已入库影像资产。
    """
    return await service.import_item(db, request)


@router.post(
    "/import-batch",
    response_model=PublicImageryBatchImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_public_imagery_batch(
    request: PublicImageryBatchImportRequest,
    db: DatabaseSession,
) -> PublicImageryBatchImportResponse:
    """裁取 1–10 景公开 Landsat 并通过一次业务事务原子入库。

    Args:
        request: 批次编号、共同裁取范围、成员清单和稳定操作人。
        db: 异步数据库会话。

    Returns:
        PublicImageryBatchImportResponse: 来源清单和统一影像批次证据。
    """
    return await service.import_batch(db, request)
