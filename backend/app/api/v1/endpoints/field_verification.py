"""内外业联动核查端点。"""

from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import DatabaseSession
from app.schemas.field_verification import (
    FieldRematchRequest,
    FieldRematchResponse,
    FieldReopenRequest,
    FieldResolutionRequest,
    FieldVerificationArtifactResponse,
    FieldVerificationArtifactUploadRequest,
    FieldVerificationBatchImportRequest,
    FieldVerificationBatchImportResponse,
    FieldVerificationCreateRequest,
    FieldVerificationFileImportMetadata,
    FieldVerificationListResponse,
    FieldVerificationResponse,
)
from app.services.field_verification_artifact_service import (
    FieldVerificationArtifactService,
)
from app.services.field_verification_service import FieldVerificationService
from app.services.field_workbook_parser import XLSX_MEDIA_TYPE

router = APIRouter(prefix="/api/v1/field-verifications", tags=["内外业联动核查"])
service = FieldVerificationService()
artifact_service = FieldVerificationArtifactService()


@router.post("/import-csv", response_model=FieldVerificationBatchImportResponse)
async def import_field_verification_csv(
    request: FieldVerificationBatchImportRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> FieldVerificationBatchImportResponse:
    """批量导入外业 CSV 记录并立即执行空间匹配。

    Args:
        request: 来源、上传人和已解析的 CSV 记录。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        FieldVerificationBatchImportResponse: 导入批次和匹配状态统计。
    """
    return await service.import_batch(db, task_code, request)


@router.post("/import-xlsx", response_model=FieldVerificationBatchImportResponse)
async def import_field_verification_xlsx(
    file: Annotated[UploadFile, File(description="外业核查 XLSX 实体文件")],
    source_name: Annotated[str, Form(min_length=1, max_length=120)],
    source_uri: Annotated[str, Form(min_length=1, max_length=500)],
    source_version: Annotated[str, Form(min_length=1, max_length=80)],
    uploader_code: Annotated[str, Form(min_length=1, max_length=50)],
    comment: Annotated[str, Form(min_length=1, max_length=500)],
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> FieldVerificationBatchImportResponse:
    """批量导入外业 XLSX 文件并立即执行空间匹配。

    Args:
        file: 原始 Excel 工作簿。
        source_name: 采集系统或数据源名称。
        source_uri: 文件交接或采集系统来源 URI。
        source_version: 数据版本。
        uploader_code: 上传人稳定项目用户编码。
        comment: 导入依据。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        FieldVerificationBatchImportResponse: 导入批次和匹配状态统计。
    """
    filename = file.filename or "field-verifications.xlsx"
    content = await file.read()
    await file.close()
    metadata = FieldVerificationFileImportMetadata(
        source_name=source_name,
        source_uri=source_uri,
        source_version=source_version,
        uploader_code=uploader_code,
        comment=comment,
    )
    return await service.import_xlsx(
        db,
        task_code,
        metadata,
        filename,
        content,
    )


@router.get(
    "/import-template.xlsx",
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}}},
)
async def download_field_verification_xlsx_template() -> Response:
    """下载外业核查 Excel 标准模板。

    Returns:
        Response: XLSX 二进制模板。
    """
    return Response(
        content=service.build_xlsx_template(),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                'attachment; filename="field_verification_import_template.xlsx"'
            )
        },
    )


@router.get("", response_model=FieldVerificationListResponse)
async def list_field_verifications(
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> FieldVerificationListResponse:
    """查询任务外业核查记录和状态统计。

    Args:
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        FieldVerificationListResponse: 外业核查列表和统计。
    """
    return await service.list_records(db, task_code)


@router.post("", response_model=FieldVerificationResponse)
async def create_field_verification(
    request: FieldVerificationCreateRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> FieldVerificationResponse:
    """创建外业核查记录并立即执行空间匹配。

    Args:
        request: GPS、现场属性和附件元数据。
        db: FastAPI 注入的异步数据库会话。
        task_code: 作业任务编号。

    Returns:
        FieldVerificationResponse: 已完成空间匹配的外业记录。
    """
    return await service.create_record(db, task_code, request)


@router.post("/rematch", response_model=FieldRematchResponse)
async def rematch_field_verifications(
    request: FieldRematchRequest,
    db: DatabaseSession,
    task_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026-045",
) -> FieldRematchResponse:
    """按项目当前空间和时间阈值重新匹配全部外业记录。

    Args:
        db: FastAPI 注入的异步数据库会话。
        request: 重新匹配操作人编码。
        task_code: 作业任务编号。

    Returns:
        FieldRematchResponse: 匹配数量和疑点结果。
    """
    return await service.rematch_task(db, task_code, request)


@router.patch(
    "/{verification_code}/resolve",
    response_model=FieldVerificationResponse,
)
async def resolve_field_verification(
    verification_code: str,
    request: FieldResolutionRequest,
    db: DatabaseSession,
) -> FieldVerificationResponse:
    """人工处置外业疑点并关闭问题。

    Args:
        verification_code: 外业记录编号。
        request: 处置决策、审核人和说明。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        FieldVerificationResponse: 处置后的外业记录。
    """
    return await service.resolve_record(db, verification_code, request)


@router.patch(
    "/{verification_code}/reopen",
    response_model=FieldVerificationResponse,
)
async def reopen_field_verification(
    verification_code: str,
    request: FieldReopenRequest,
    db: DatabaseSession,
) -> FieldVerificationResponse:
    """重新打开已处置外业疑点并回退任务质量门禁。

    Args:
        verification_code: 外业记录编号。
        request: 操作人稳定编码和重开依据。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        FieldVerificationResponse: 已恢复待处置状态的外业记录。
    """
    return await service.reopen_record(db, verification_code, request)


@router.post(
    "/{verification_code}/artifacts",
    response_model=FieldVerificationArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_field_verification_artifact(
    verification_code: str,
    file: Annotated[UploadFile, File(description="现场照片、语音或调查表实体")],
    artifact_type: Annotated[
        Literal["photo", "voice", "form"],
        Form(),
    ],
    uploader_code: Annotated[str, Form(min_length=1, max_length=50)],
    comment: Annotated[str, Form(min_length=2, max_length=500)],
    db: DatabaseSession,
) -> FieldVerificationArtifactResponse:
    """上传并登记可复核的外业实体证据。

    Args:
        verification_code: 外业记录业务编号。
        file: 照片、语音或调查表二进制实体。
        artifact_type: 证据业务类型。
        uploader_code: 上传人稳定项目用户编码。
        comment: 证据来源与用途说明。
        db: FastAPI 注入的异步数据库会话。

    Returns:
        FieldVerificationArtifactResponse: 已登记实体证据摘要。
    """
    metadata = FieldVerificationArtifactUploadRequest(
        artifact_type=artifact_type,
        uploader_code=uploader_code,
        comment=comment,
    )
    try:
        return await artifact_service.upload_artifact(
            db,
            verification_code,
            metadata.artifact_type,
            metadata.uploader_code,
            metadata.comment,
            file.filename or "field-evidence.bin",
            file.content_type,
            file.file,
        )
    finally:
        await file.close()


@router.get(
    "/{verification_code}/artifacts/{artifact_code}/download",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "image/jpeg": {},
                "image/png": {},
                "image/webp": {},
                "audio/wav": {},
                "audio/mpeg": {},
                "audio/mp4": {},
                "audio/ogg": {},
                "application/pdf": {},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
            }
        }
    },
)
async def download_field_verification_artifact(
    verification_code: str,
    artifact_code: str,
    db: DatabaseSession,
    operator_code: Annotated[str, Query(min_length=1, max_length=50)],
) -> FileResponse:
    """授权下载并重新校验外业实体证据。

    Args:
        verification_code: 外业记录业务编号。
        artifact_code: 实体证据业务编号。
        db: FastAPI 注入的异步数据库会话。
        operator_code: 下载人稳定项目用户编码。

    Returns:
        FileResponse: 已通过路径、签名、大小和 SHA-256 复核的文件。
    """
    download = await artifact_service.get_artifact_for_download(
        db,
        verification_code,
        artifact_code,
        operator_code,
    )
    return FileResponse(
        path=download.path,
        media_type=download.media_type,
        filename=download.filename,
        headers={"ETag": f'"{download.checksum_sha256}"'},
    )
