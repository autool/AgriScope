"""项目用户、角色与能力响应模型。"""

from pydantic import BaseModel, ConfigDict


class ProjectUserResponse(BaseModel):
    """项目成员身份及可执行能力。"""

    user_code: str
    display_name: str
    role_code: str
    role_name: str
    status: str
    is_default: bool
    capabilities: list[str]

    model_config = ConfigDict(from_attributes=True)


class ProjectUserListResponse(BaseModel):
    """项目当前启用成员列表。"""

    project_code: str
    users: list[ProjectUserResponse]
