"""成果验收正式报告端点。"""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import DatabaseSession
from app.schemas.acceptance_report import (
    AcceptanceReportGenerateRequest,
    AcceptanceReportListResponse,
    AcceptanceReportResponse,
)
from app.services.acceptance_report_service import AcceptanceReportService

router = APIRouter(
    prefix="/api/v1/acceptance-reports",
    tags=["成果验收报告"],
)
service = AcceptanceReportService()


@router.get("", response_model=AcceptanceReportListResponse)
async def list_acceptance_reports(
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> AcceptanceReportListResponse:
    """查询任务验收报告门禁与版本历史。

    Args:
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        AcceptanceReportListResponse: 生成条件和报告版本。
    """
    return await service.list_reports(db, task_code)


@router.post("/generate", response_model=AcceptanceReportResponse)
async def generate_acceptance_report(
    request: AcceptanceReportGenerateRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> AcceptanceReportResponse:
    """基于当前有效成果包生成 DOCX/PDF 验收报告。

    Args:
        request: 报告标题、操作人和生成依据。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        AcceptanceReportResponse: 新生成报告摘要。
    """
    return await service.generate_report(db, task_code, request)


@router.get("/{report_code}/download", response_class=FileResponse)
async def download_acceptance_report(
    report_code: str,
    db: DatabaseSession,
    requester_code: Annotated[str, Query(min_length=1, max_length=50)],
) -> FileResponse:
    """鉴权并完整复核后下载验收报告 ZIP。

    Args:
        report_code: 验收报告编号。
        db: FastAPI 注入的异步数据库会话。
        requester_code: 下载人稳定项目用户编码。

    Returns:
        FileResponse: 包含 DOCX、PDF 和 manifest 的 ZIP。
    """
    download = await service.authorize_download(
        db,
        report_code,
        requester_code,
    )
    return FileResponse(
        path=download.path,
        filename=download.filename,
        media_type="application/zip",
        headers={"ETag": f'"{download.checksum_sha256}"'},
    )
