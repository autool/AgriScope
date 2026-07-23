"""应用配置模块。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量和 .env 文件加载应用配置。"""

    app_name: str = "遥感监测内业处理与成果审核平台"
    app_env: str = "development"
    log_level: str = "INFO"
    max_imagery_upload_bytes: int = 10 * 1024 * 1024 * 1024
    max_imagery_batch_upload_bytes: int = 20 * 1024 * 1024 * 1024
    max_dataset_asset_upload_bytes: int = 5 * 1024 * 1024 * 1024
    max_dataset_asset_batch_upload_bytes: int = 20 * 1024 * 1024 * 1024
    max_dataset_archive_expanded_bytes: int = 20 * 1024 * 1024 * 1024
    max_uav_upload_bytes: int = 2 * 1024 * 1024 * 1024
    max_uav_mobile_photo_bytes: int = 20 * 1024 * 1024
    max_consultation_evidence_bytes: int = 50 * 1024 * 1024
    max_field_photo_bytes: int = 20 * 1024 * 1024
    max_field_voice_bytes: int = 100 * 1024 * 1024
    max_field_form_bytes: int = 50 * 1024 * 1024
    offline_archive_default_volume_bytes: int = Field(
        default=4 * 1024 * 1024 * 1024,
        ge=64 * 1024 * 1024,
        le=16 * 1024 * 1024 * 1024,
    )
    offline_archive_max_volume_bytes: int = Field(
        default=16 * 1024 * 1024 * 1024,
        ge=64 * 1024 * 1024,
        le=64 * 1024 * 1024 * 1024,
    )
    change_preview_max_dimension: int = Field(default=1400, ge=256, le=4096)
    imagery_quicklook_max_dimension: int = Field(default=1400, ge=256, le=4096)
    max_imagery_mosaic_pixels: int = Field(
        default=10_000_000,
        ge=10_000,
        le=100_000_000,
    )
    max_imagery_registration_pixels: int = Field(
        default=10_000_000,
        ge=10_000,
        le=100_000_000,
    )
    max_imagery_fusion_pixels: int = Field(
        default=10_000_000,
        ge=10_000,
        le=100_000_000,
    )
    max_growth_monitoring_pixels: int = Field(
        default=10_000_000,
        ge=10_000,
        le=100_000_000,
    )
    imagery_registration_preview_max_dimension: int = Field(
        default=2048,
        ge=256,
        le=4096,
    )
    service_health_private_host_allowlist: str = ""
    database_url: str = Field(
        default="postgresql+asyncpg://admin:admin123@postgis:5432/farmland"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """获取单例应用配置。

    Returns:
        Settings: 已完成环境变量解析的配置对象。
    """
    return Settings()


settings = get_settings()
