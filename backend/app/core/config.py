from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AI 多人旅行规划助手"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://travel:travel@localhost:5432/travel_assistant"
    jwt_secret: str = "replace-with-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    llm_use_fake: bool = True
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-flash"
    deepseek_timeout_seconds: float = 120.0

    amap_base_url: str = "https://restapi.amap.com"
    amap_api_key: str = ""
    amap_timeout_seconds: float = 10.0
    amap_min_interval_seconds: float = 1.1
    amap_rate_limit_retries: int = 3

    qweather_api_host: str = ""
    qweather_auth_type: Literal["api_key", "jwt"] = "api_key"
    qweather_api_key: str = ""
    qweather_jwt_token: str = ""
    qweather_timeout_seconds: float = 10.0

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
