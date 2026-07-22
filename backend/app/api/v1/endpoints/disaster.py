"""灾害斑块监测与受灾范围评估端点。"""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import DatabaseSession
from app.schemas.disaster import (
    DisasterGeoJsonImportRequest,
    DisasterGeoJsonImportResponse,
    DisasterPatchResponse,
    DisasterPatchUpdateRequest,
    DisasterReportGenerateRequest,
    DisasterReportListResponse,
    DisasterReportResponse,
    DisasterSummaryResponse,
)
from app.services.disaster_report_service import DisasterReportService
from app.services.disaster_service import DisasterService

router = APIRouter(prefix="/api/v1/disasters", tags=["灾害斑块监测"])
service = DisasterService()
report_service = DisasterReportService()


@router.post("/import-geojson", response_model=DisasterGeoJsonImportResponse)
async def import_disaster_geojson(
    request: DisasterGeoJsonImportRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DisasterGeoJsonImportResponse:
    """导入外部灾害模型 GeoJSON FeatureCollection。

    Args:
        request: 灾害斑块、来源元数据、冲突策略和操作人编码。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        DisasterGeoJsonImportResponse: 导入批次、数量和来源校验摘要。
    """
    return await service.import_geojson(db, task_code, request)


@router.get("/summary", response_model=DisasterSummaryResponse)
async def get_disaster_summary(
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DisasterSummaryResponse:
    """查询灾害斑块、受灾面积和专题图层。

    Args:
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        DisasterSummaryResponse: 灾害评估汇总。
    """
    return await service.get_summary(db, task_code)


@router.get("/reports", response_model=DisasterReportListResponse)
async def list_disaster_reports(
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DisasterReportListResponse:
    """查询任务灾害监测专题报告及实体状态。

    Args:
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        DisasterReportListResponse: 报告列表。
    """
    return await report_service.list_reports(db, task_code)


@router.post("/reports", response_model=DisasterReportResponse)
async def generate_disaster_report(
    request: DisasterReportGenerateRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DisasterReportResponse:
    """通过全部灾害斑块复核门禁后生成 XLSX 专题报告。

    Args:
        request: 报告标题、操作人和生成依据。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        DisasterReportResponse: 新生成报告实体摘要。
    """
    return await report_service.generate_report(db, task_code, request)


@router.get("/reports/{report_code}/download", response_class=FileResponse)
async def download_disaster_report(
    report_code: str,
    db: DatabaseSession,
    requester_code: Annotated[str, Query(min_length=1, max_length=50)],
) -> FileResponse:
    """鉴权并重新校验灾害专题报告后下载。

    Args:
        report_code: 报告业务编号。
        db: FastAPI 注入的异步数据库会话。
        requester_code: 下载人稳定项目用户编码。

    Returns:
        FileResponse: 通过大小和 SHA-256 校验的 XLSX 文件。
    """
    download = await report_service.authorize_download(
        db,
        report_code,
        requester_code,
    )
    return FileResponse(
        path=download.path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        filename=download.filename,
        headers={"ETag": f'"{download.checksum_sha256}"'},
    )


@router.patch("/{patch_code}", response_model=DisasterPatchResponse)
async def update_disaster_patch(
    patch_code: str,
    request: DisasterPatchUpdateRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> DisasterPatchResponse:
    """人工修正灾害等级和确认状态。

    Args:
        patch_code: 灾害斑块编号。
        request: 修正内容和审核信息。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        DisasterPatchResponse: 修正后的灾害斑块。
    """
    return await service.update_patch(db, task_code, patch_code, request)
