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
