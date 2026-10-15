"""DTOs for the admin service."""

from datetime import datetime

from pydantic import BaseModel


class ApiTokenRead(BaseModel):
    """An issued token without its secret value."""

    id: int
    token_id: str
    name: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        """Whether the token is neither revoked nor expired."""
        return self.revoked_at is None and self.expires_at > now


class IssuedToken(BaseModel):
    """A new token; `token` is shown once and never stored."""

    token: str
    info: ApiTokenRead


class ModuleUsage(BaseModel):
    """What one module keeps about a person, as counts per translation key."""

    module: str
    label_key: str
    items: dict[str, int]


class TableCount(BaseModel):
    """Rows in one table."""

    name: str
    rows: int


class SystemInfo(BaseModel):
    """Facts shown on the system tab."""

    version: str
    schema_revision: str | None
    database: str
    timezone: str
    reference_files: int
    backup_target: str | None
    tables: list[TableCount]
