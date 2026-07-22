"""项目级业务规则配置端点。"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DatabaseSession
from app.schemas.rule_config import RuleConfigResponse, RuleConfigUpdateRequest
from app.services.rule_config_service import RuleConfigService

router = APIRouter(prefix="/api/v1/rule-configs", tags=["业务规则配置"])
service = RuleConfigService()


@router.get("", response_model=RuleConfigResponse)
async def get_rule_config(
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> RuleConfigResponse:
    """查询项目当前生效的质量和外业校核规则。

    Args:
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。

    Returns:
        RuleConfigResponse: 当前生效规则。
    """
    return await service.get_config(db, project_code)


@router.patch("", response_model=RuleConfigResponse)
async def update_rule_config(
    request: RuleConfigUpdateRequest,
    db: DatabaseSession,
    project_code: Annotated[str, Query(min_length=1, max_length=50)] = "RS-2026",
) -> RuleConfigResponse:
    """更新项目规则并保存修改审计。

    Args:
        request: 新规则值和操作人。
        db: FastAPI 注入的异步数据库会话。
        project_code: 项目编号。

    Returns:
        RuleConfigResponse: 更新后的当前规则。
    """
    return await service.update_config(db, project_code, request)
