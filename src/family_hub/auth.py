"""JWT bearer authentication for the external API."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from uuid import uuid4

from litestar.connection import ASGIConnection
from litestar.security.jwt import JWTAuth, Token
from pydantic import BaseModel, ConfigDict

from family_hub.config import Settings

TOKEN_ISSUER = "family-hub"
MIN_SECRET_LENGTH = 32


class ApiClient(BaseModel):
    """An authenticated API client, identified by the token subject."""

    model_config = ConfigDict(frozen=True)

    name: str


async def _retrieve_client(token: Token, connection: ASGIConnection) -> ApiClient:
    return ApiClient(name=token.sub)


type TokenCheck = Callable[[str], Awaitable[bool]]


def create_jwt_auth(settings: Settings, is_valid: TokenCheck | None = None) -> JWTAuth[ApiClient, Token]:
    """Build the Litestar JWT config.

    Args:
        settings: App settings with the signing secret.
        is_valid: Checks a token id against the issued tokens; without it every signed token is accepted.

    Raises:
        RuntimeError: If `JWT_SECRET` is missing or too short.
    """
    secret = settings.jwt_secret.get_secret_value() if settings.jwt_secret else ""
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(f"JWT_SECRET must be set to at least {MIN_SECRET_LENGTH} characters")

    async def is_revoked(token: Token, connection: ASGIConnection) -> bool:
        token_id = token.jti
        if not isinstance(token_id, str):
            return True
        return is_valid is not None and not await is_valid(token_id)

    return JWTAuth[ApiClient, Token](
        token_secret=secret,
        retrieve_user_handler=_retrieve_client,
        revoked_token_handler=is_revoked,
        accepted_issuers=[TOKEN_ISSUER],
        require_claims=["jti"],
        exclude=["/docs"],
    )


def create_token(settings: Settings, client: str, valid_for: timedelta) -> tuple[str, str]:
    """Issue a token for an API client.

    Returns:
        The encoded token and its id (`jti`).
    """
    token_id = uuid4().hex
    token = create_jwt_auth(settings).create_token(
        identifier=client,
        token_expiration=valid_for,
        token_issuer=TOKEN_ISSUER,
        token_unique_jwt_id=token_id,
    )
    return token, token_id
