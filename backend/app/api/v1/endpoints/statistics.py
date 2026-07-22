"""种植面积统计分析端点。"""

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile

from app.api.deps import DatabaseSession
from app.schemas.statistics import (
    AreaStatisticsResponse,
    AreaStatisticsSnapshotImportMetadata,
    AreaStatisticsSnapshotImportResponse,
)
from app.services.statistics_service import StatisticsService

router = APIRouter(prefix="/api/v1/statistics", tags=["种植面积统计分析"])
service = StatisticsService()


@router.post(
    "/annual-snapshots/import-csv",
    response_model=AreaStatisticsSnapshotImportResponse,
)
async def import_area_statistics_history_csv(
    file: Annotated[UploadFile, File(description="真实历史年度统计 CSV")],
    source_name: Annotated[str, Form(min_length=1, max_length=120)],
    source_uri: Annotated[str, Form(min_length=1, max_length=500)],
    source_version: Annotated[str, Form(min_length=1, max_length=80)],
    operator_code: Annotated[str, Form(min_length=1, max_length=50)],
    comment: Annotated[str, Form(min_length=1, max_length=500)],
    conflict_strategy: Annotated[str, Form(pattern="^(reject|replace)$")],
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> AreaStatisticsSnapshotImportResponse:
    """导入真实历史年度统计并保存来源与用户审计。

    Args:
        file: 原始 UTF-8 CSV 文件。
        source_name: 统计成果来源名称。
        source_uri: 文件交接或成果系统来源 URI。
        source_version: 来源版本。
        operator_code: 项目负责人稳定用户编码。
        comment: 导入依据。
        conflict_strategy: 已有年度冲突时拒绝或替换。
        db: FastAPI 注入的异步数据库会话。
        task_code: 当前作业任务编号。

    Returns:
        AreaStatisticsSnapshotImportResponse: 导入批次与年度统计。
    """
    filename = file.filename or "area-statistics-history.csv"
    content = await file.read()
    await file.close()
    metadata = AreaStatisticsSnapshotImportMetadata(
        source_name=source_name,
        source_uri=source_uri,
        source_version=source_version,
        operator_code=operator_code,
        comment=comment,
        conflict_strategy=conflict_strategy,
    )
    return await service.import_history_csv(
        db,
        task_code,
        metadata,
        filename,
        content,
    )


@router.get("/annual-snapshots/import-template.csv", response_class=Response)
async def download_area_statistics_history_template() -> Response:
    """下载历史年度统计 CSV 标准模板。

    Returns:
        Response: UTF-8 BOM CSV 模板。
    """
    return Response(
        content=service.build_history_csv_template(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                'attachment; filename="area_statistics_history_template.csv"'
            )
        },
    )


@router.get("/area-summary/export.csv", response_class=Response)
async def export_area_statistics_csv(
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> Response:
    """导出任务作用域多维面积统计 CSV。

    Args:
        db: FastAPI 注入的异步数据库会话。
        operator_code: 导出人稳定用户编码。
        task_code: 作业任务编号。

    Returns:
        Response: UTF-8 BOM CSV 下载响应。
    """
    filename, content = await service.export_area_statistics_csv(
        db,
        task_code,
        operator_code,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/area-summary", response_model=AreaStatisticsResponse)
async def get_area_statistics(
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> AreaStatisticsResponse:
    """查询任务行政区、地类、作物、种植模式和年度变化趋势。

    Args:
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        AreaStatisticsResponse: 多维面积统计结果。
    """
    return await service.get_area_statistics(db, task_code)
