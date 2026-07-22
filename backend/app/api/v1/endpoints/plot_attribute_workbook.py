"""任务地块属性 Excel 导入导出端点。"""

from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile

from app.api.deps import DatabaseSession
from app.schemas.plot_attribute_workbook import (
    PlotAttributeImportBatchListResponse,
    PlotAttributeImportBatchResponse,
    PlotAttributeWorkbookExportRequest,
    PlotAttributeWorkbookImportMetadata,
)
from app.services.plot_attribute_workbook_parser import XLSX_MEDIA_TYPE
from app.services.plot_attribute_workbook_service import (
    PlotAttributeWorkbookService,
)

router = APIRouter(
    prefix="/api/v1/plot-attribute-workbooks",
    tags=["地块属性 Excel"],
)
service = PlotAttributeWorkbookService()


@router.post(
    "/tasks/{task_code}/export.xlsx",
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}},
)
async def export_plot_attribute_workbook(
    task_code: str,
    request: PlotAttributeWorkbookExportRequest,
    db: DatabaseSession,
) -> Response:
    """导出任务全部或显式选择图斑的当前属性工作簿。

    Args:
        task_code: 作业任务编号。
        request: 操作人编码和可选显式图斑编号。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        Response: 包含当前版本和逐行属性的 XLSX 实体。
    """
    workbook = await service.export_workbook(db, task_code, request)
    return Response(
        content=workbook.content,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{workbook.filename}"',
            "X-Workbook-Row-Count": str(workbook.row_count),
        },
    )


@router.post(
    "/tasks/{task_code}/import",
    response_model=PlotAttributeImportBatchResponse,
)
async def import_plot_attribute_workbook(
    task_code: str,
    file: Annotated[UploadFile, File(description="地块属性 XLSX 实体文件")],
    operator_code: Annotated[str, Form(min_length=1, max_length=50)],
    comment: Annotated[str, Form(min_length=2, max_length=500)],
    db: DatabaseSession,
) -> PlotAttributeImportBatchResponse:
    """严格校验并原子导入逐图斑属性工作簿。

    Args:
        task_code: 作业任务编号。
        file: 服务端解析的原始 XLSX 实体。
        operator_code: 项目用户稳定编码。
        comment: 影像、外业或调查表证据说明。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        PlotAttributeImportBatchResponse: 批次、变更数量和实体校验值。
    """
    filename = file.filename or "plot_attributes.xlsx"
    content = await file.read()
    await file.close()
    metadata = PlotAttributeWorkbookImportMetadata(
        operator_code=operator_code,
        comment=comment,
    )
    return await service.import_workbook(
        db,
        task_code,
        metadata,
        filename,
        content,
    )


@router.get(
    "/tasks/{task_code}/imports",
    response_model=PlotAttributeImportBatchListResponse,
)
async def list_plot_attribute_import_batches(
    task_code: str,
    db: DatabaseSession,
) -> PlotAttributeImportBatchListResponse:
    """查询任务最近的地块属性 Excel 导入证据。

    Args:
        task_code: 作业任务编号。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        PlotAttributeImportBatchListResponse: 最近 20 个实体导入批次。
    """
    return await service.list_import_batches(db, task_code)
