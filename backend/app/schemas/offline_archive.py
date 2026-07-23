"""源栅格离线介质封存请求与响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings


class OfflineArchiveGenerateRequest(BaseModel):
    """生成离线介质分卷封存请求。"""

    operator_code: str
    archive_name: str | None = Field(default=None, max_length=200)
    volume_capacity_bytes: int | None = None
    comment: str = Field(max_length=500)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operator_code")
    @classmethod
    def validate_operator_code(cls, value: str) -> str:
        """校验稳定操作人编码。

        Args:
            value: 项目用户编码。

        Returns:
            str: 去除首尾空白后的编码。
        """
        normalized = value.strip()
        if not normalized:
            raise ValueError("离线封存操作人编码不得为空")
        return normalized

    @field_validator("archive_name")
    @classmethod
    def validate_archive_name(cls, value: str | None) -> str | None:
        """清理可选封存名称。

        Args:
            value: 用户输入的封存名称。

        Returns:
            str | None: 清理后的名称或空值。
        """
        normalized = value.strip() if value is not None else None
        return normalized or None

    @field_validator("volume_capacity_bytes")
    @classmethod
    def validate_volume_capacity(cls, value: int | None) -> int | None:
        """限制单卷容量在部署配置允许范围内。

        Args:
            value: 单卷最大物理字节数。

        Returns:
            int | None: 通过校验的容量或默认空值。
        """
        if value is None:
            return None
        minimum = 64 * 1024 * 1024
        if value < minimum:
            raise ValueError("离线介质单卷容量不得低于 64 MiB")
        if value > settings.offline_archive_max_volume_bytes:
            raise ValueError("离线介质单卷容量超过部署配置上限")
        return value

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str) -> str:
        """校验生成依据不是空白占位。

        Args:
            value: 离线封存生成依据。

        Returns:
            str: 清理后的生成依据。
        """
        normalized = value.strip()
        if len(normalized) < 10:
            raise ValueError("离线封存生成依据至少填写 10 个字符")
        return normalized


class OfflineArchiveSourceSummary(BaseModel):
    """离线封存来源类别容量摘要。"""

    source_kind: str
    source_count: int
    file_size_bytes: int


class OfflineArchiveVolumeResponse(BaseModel):
    """单个离线封存分卷响应。"""

    sequence: int
    filename: str
    file_size_bytes: int
    checksum_sha256: str
    member_count: int
    source_size_bytes: int
    download_url: str | None


class OfflineArchiveResponse(BaseModel):
    """离线封存版本及其分卷响应。"""

    archive_code: str
    archive_name: str
    version: int
    status: str
    volume_capacity_bytes: int
    volume_count: int
    source_count: int
    total_source_bytes: int
    total_archive_bytes: int
    source_snapshot_sha256: str
    manifest_size_bytes: int
    manifest_checksum_sha256: str
    delivery_package_code: str
    delivery_package_checksum_sha256: str
    generated_by: str
    generated_by_code: str
    generated_by_role: str
    generation_comment: str
    generated_at: datetime
    superseded_at: datetime | None
    is_current: bool
    stale_reason: str | None
    manifest_download_url: str | None
    volumes: list[OfflineArchiveVolumeResponse]


class OfflineArchiveOverviewResponse(BaseModel):
    """离线封存容量预估、生成门禁和版本历史。"""

    task_code: str
    can_generate: bool
    generate_blocker: str | None
    recommended_volume_capacity_bytes: int
    max_volume_capacity_bytes: int
    source_count: int
    total_source_bytes: int
    largest_source_bytes: int
    source_summaries: list[OfflineArchiveSourceSummary]
    archives: list[OfflineArchiveResponse]
