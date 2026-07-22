"""成果验收正式报告请求与响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AcceptanceReportGenerateRequest(BaseModel):
    """基于当前有效成果包生成正式验收报告请求。"""

    operator_code: str = Field(min_length=1, max_length=50)
    report_title: str = Field(min_length=2, max_length=200)
    comment: str = Field(min_length=4, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code", "report_title", "comment")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """清理请求文本并拒绝空白值。

        Args:
            value: 原始文本。

        Returns:
            str: 去除首尾空白后的文本。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("操作人、报告标题和生成依据不得为空")
        return normalized


class AcceptanceReportFileEvidence(BaseModel):
    """验收报告包内单个正式文件证据。"""

    path: str
    format: Literal["DOCX", "PDF"]
    file_size_bytes: int
    checksum_sha256: str
    page_count: int | None = None


class AcceptanceReportResponse(BaseModel):
    """成果验收正式报告版本摘要。"""

    report_code: str
    report_title: str
    version: int
    status: Literal["completed", "superseded", "invalid"]
    delivery_package_code: str
    delivery_package_checksum_sha256: str
    task_plot_count: int
    task_updated_at_snapshot: datetime
    delivery_manifest_count: int
    bundle_size_bytes: int
    bundle_checksum_sha256: str
    files: list[AcceptanceReportFileEvidence]
    generation_comment: str
    generated_by: str
    generated_by_code: str
    generated_by_role: str
    generated_at: datetime
    download_url: str | None
    is_current: bool
    stale_reason: str | None


class AcceptanceReportListResponse(BaseModel):
    """任务验收报告生成门禁与版本列表。"""

    task_code: str
    can_generate: bool
    generate_blocker: str | None
    current_delivery_package_code: str | None
    items: list[AcceptanceReportResponse]
