from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GTFS On Time"
    app_version: str = "0.1.0"
    environment: str = "development"

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432

    cittati_base_url: str = "https://servicos.cittati.com.br/WSIntegracaoCittati"
    cittati_company: str | None = None
    cittati_username: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CITTATI_USER", "CITTATI_USERNAME"),
    )
    cittati_password: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CITTATI_PASS", "CITTATI_PASSWORD"),
    )
    cittati_timeout_seconds: float = 30.0
    cittati_poll_interval_seconds: float = 10.0
    cittati_retry_initial_seconds: float = 2.0
    cittati_retry_max_seconds: float = 30.0
    cittati_operational_stale_after_seconds: float = 60.0

    gtfs_static_url: str = "https://servicos.cittati.com.br/GTFS_PLATAFORMA/URBI/GTFS_URBI.zip"
    gtfs_static_timeout_seconds: float = 60.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
        hide_input_in_errors=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
