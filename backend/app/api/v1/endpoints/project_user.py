"""项目用户与角色能力查询端点。"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DatabaseSession
from app.schemas.project_user import ProjectUserListResponse
from app.services.project_user_service import ProjectUserService

router = APIRouter(prefix="/api/v1/project-users", tags=["项目用户与角色"])
service = ProjectUserService()


@router.get("", response_model=ProjectUserListResponse)
async def list_project_users(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> ProjectUserListResponse:
    """查询项目启用成员及其业务能力。

    Args:
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。

    Returns:
        ProjectUserListResponse: 项目成员与能力列表。
    """
    return await service.list_project_users(db, project_code)
