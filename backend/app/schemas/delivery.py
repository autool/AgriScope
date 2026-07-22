"""成果交付包生成、清单与下载响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class DeliveryGenerateRequest(BaseModel):
    """生成成果交付包请求。"""

    operator_code: str
    package_name: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code")
    @classmethod
    def validate_operator_code(cls, value: str) -> str:
        """校验成果包生成人稳定编码。

        Args:
            value: 项目用户编码。

        Returns:
            str: 清理后的用户编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("成果包生成人编码不得为空")
        return normalized


class DeliveryManifestItem(BaseModel):
    """交付包内单个成果文件清单项。"""

    path: str
    category: str
    format: str
    record_count: int | None
    description: str


class DeliveryPackageResponse(BaseModel):
    """成果交付包响应。"""

    package_code: str
    package_name: str
    version: int
    status: str
    generated_by: str
    generated_by_code: str | None
    generated_by_role: str | None
    file_size_bytes: int | None
    checksum_sha256: str | None
    manifest: list[DeliveryManifestItem]
    quality_summary: dict
    created_at: datetime
    completed_at: datetime | None
    download_url: str | None
    is_current: bool
    stale_reason: str | None


class DeliveryListResponse(BaseModel):
    """任务成果交付包列表响应。"""

    task_code: str
    can_generate: bool
    generate_blocker: str | None
    packages: list[DeliveryPackageResponse]
