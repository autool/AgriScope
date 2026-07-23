"""成果审核与图斑版本管理请求响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.workbench import TaskSummary


class ReviewActionRequest(BaseModel):
    """任务审核动作请求。"""

    action: str
    reviewer_code: str
    comment: str | None = None
    issue_type: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        """校验审核动作。

        Args:
            value: 审核动作。

        Returns:
            str: 合法审核动作。
        """
        if value not in {"pass", "return", "reject"}:
            raise ValueError("审核动作必须为 pass、return 或 reject")
        return value

    @field_validator("reviewer_code")
    @classmethod
    def validate_reviewer_code(cls, value: str) -> str:
        """校验审核人稳定编码。

        Args:
            value: 项目用户编码。

        Returns:
            str: 清理后的用户编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("审核人编码不得为空")
        return normalized


class ReviewActionResponse(BaseModel):
    """任务审核动作响应。"""

    task: TaskSummary
    previous_status: str
    current_status: str
    action: str
    record_id: int
    reviewer_code: str
    reviewer_name: str
    reviewer_role: str


class PlotVersionResponse(BaseModel):
    """图斑历史版本响应。"""

    plot_code: str
    version: int
    owner_village: str | None = None
    land_class: str | None
    crop_type: str | None
    planting_mode: str | None
    irrigation_condition: str | None
    custom_attributes: dict[str, object]
    interpretation_status: str
    change_summary: str | None
    created_by: str
    created_by_code: str | None
    created_by_role: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlotVersionListResponse(BaseModel):
    """图斑版本列表。"""

    plot_code: str
    current_version: int
    versions: list[PlotVersionResponse]


class PlotRollbackRequest(BaseModel):
    """图斑版本回退请求。"""

    target_version: int
    operator_code: str
    comment: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code")
    @classmethod
    def validate_operator_code(cls, value: str) -> str:
        """校验版本回退操作人编码。

        Args:
            value: 项目用户编码。

        Returns:
            str: 清理后的用户编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人编码不得为空")
        return normalized
