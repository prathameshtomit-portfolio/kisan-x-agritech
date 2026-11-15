from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "KISAN X API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./kisanx.db"
    auto_create_tables: bool = True
    log_level: str = "INFO"
    cors_origins: str = (
        "http://localhost:3000,http://localhost:5173,http://localhost:8080,"
        "https://localhost,http://localhost,http://tauri.localhost,tauri://localhost"
    )
    owner_pin: str = Field(default="", validation_alias="KISANX_OWNER_PIN")
    owner_email: str = Field(default="prathamesh.arc@gmail.com", validation_alias="KISANX_OWNER_EMAIL")
    enable_public_payment_claims: bool = Field(
        default=False, validation_alias="KISANX_ENABLE_PUBLIC_PAYMENT_CLAIMS"
    )

    nasa_power_base_url: str = "https://power.larc.nasa.gov/api/temporal/daily/point"
    nasa_power_timeout_seconds: float = Field(default=25.0, gt=0, le=120)
    nasa_power_cache_ttl_seconds: int = Field(default=1800, ge=0, le=86400)
    nasa_power_retries: int = Field(default=2, ge=0, le=5)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def crop_catalog_dir(self) -> Path:
        return BACKEND_DIR / "data" / "crop_profiles"


@lru_cache

def get_settings() -> Settings:
    return Settings()


settings = get_settings()
