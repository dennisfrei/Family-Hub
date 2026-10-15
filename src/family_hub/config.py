"""Application settings read from the environment and an optional `.env` file."""

from functools import cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_STORAGE_SECRET = "change-me"


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://family_hub:family_hub@localhost:5432/family_hub"
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    storage_secret: str = DEFAULT_STORAGE_SECRET
    run_migrations: bool = True
    alembic_ini: Path = Path("alembic.ini")
    timezone: str = "Europe/Berlin"
    forwarded_prefix: str = ""

    jwt_secret: SecretStr | None = None

    auth_enabled: bool = False
    public_url: str = ""
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: SecretStr | None = None
    oidc_internal_url: str = ""
    oidc_scopes: str = "openid profile email groups"
    oidc_allowed_groups: Annotated[list[str], NoDecode] = []
    oidc_admin_groups: Annotated[list[str], NoDecode] = []
    auth_session_days: int = 14

    s3_endpoint_url: str | None = None
    aws_region: str = "eu-central-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: SecretStr | None = None
    backup_bucket: str | None = None
    backup_prefix: str = "family-hub/"
    backup_dir: Path = Path("backups")

    fever_threshold_infant: float = 38.0
    elevated_threshold_infant: float = 37.5
    fever_threshold_child: float = 38.5
    elevated_threshold_child: float = 37.5
    fever_threshold_adult: float = 38.2
    elevated_threshold_adult: float = 37.5

    growth_reference_dir: Path | None = None
    growth_reference_name: str = ""

    @field_validator("database_url")
    @classmethod
    def _use_async_driver(cls, value: str) -> str:
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value.removeprefix(prefix)
        return value

    @field_validator("oidc_allowed_groups", "oidc_admin_groups", mode="before")
    @classmethod
    def _split_groups(cls, value: object) -> object:
        if isinstance(value, str):
            return [group.strip() for group in value.split(",") if group.strip()]
        return value

    @model_validator(mode="after")
    def _check_auth(self) -> Self:
        if not self.auth_enabled:
            return self
        missing = [
            name.upper() for name in ("public_url", "oidc_issuer", "oidc_client_id") if not getattr(self, name).strip()
        ]
        if missing:
            raise ValueError(f"AUTH_ENABLED needs {', '.join(missing)}")
        if self.storage_secret == DEFAULT_STORAGE_SECRET:
            raise ValueError("AUTH_ENABLED needs a random STORAGE_SECRET, it signs the login cookie")
        return self


@cache
def get_settings() -> Settings:
    """Return the process-wide settings."""
    return Settings()
