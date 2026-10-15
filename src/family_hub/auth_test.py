from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from litestar.testing import AsyncTestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub import db
from family_hub.app import MODULES, create_api
from family_hub.auth import TOKEN_ISSUER, create_jwt_auth, create_token
from family_hub.config import Settings
from family_hub.core import service as core_service

SECRET = SecretStr("x" * 32)


@pytest.mark.parametrize("secret", [None, SecretStr("too-short")])
def test_secret_required(secret: SecretStr | None) -> None:
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        create_jwt_auth(Settings(_env_file=None, jwt_secret=secret))


async def test_healthz_is_public() -> None:
    async with AsyncTestClient(app=create_api(MODULES, Settings(_env_file=None, jwt_secret=SECRET))) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200


async def test_missing_token_rejected() -> None:
    async with AsyncTestClient(app=create_api(MODULES, Settings(_env_file=None, jwt_secret=SECRET))) as client:
        response = await client.get("/core/children")

    assert response.status_code == 401


async def test_token_from_other_secret_rejected() -> None:
    token, _ = create_token(Settings(_env_file=None, jwt_secret=SecretStr("y" * 32)), "test", timedelta(days=1))

    async with AsyncTestClient(app=create_api(MODULES, Settings(_env_file=None, jwt_secret=SECRET))) as client:
        response = await client.get("/core/children", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_expired_token_rejected() -> None:
    settings = Settings(_env_file=None, jwt_secret=SECRET)
    past = datetime.now(UTC) - timedelta(hours=1)
    claims = {"sub": "test", "iss": TOKEN_ISSUER, "jti": "1", "iat": past, "exp": past}
    token = jwt.encode(claims, SECRET.get_secret_value(), algorithm="HS256")

    async with AsyncTestClient(app=create_api(MODULES, settings)) as client:
        response = await client.get("/core/children", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


@pytest.mark.parametrize(("known", "status"), [(True, 200), (False, 401)])
async def test_token_check_decides(monkeypatch: pytest.MonkeyPatch, known: bool, status: int) -> None:
    token, token_id = create_token(Settings(_env_file=None, jwt_secret=SECRET), "test", timedelta(days=1))
    checked: list[str] = []

    async def token_check(candidate: str) -> bool:
        checked.append(candidate)
        return known

    monkeypatch.setattr(core_service, "list_children", AsyncMock(return_value=[]))
    monkeypatch.setattr(db, "provide_session", _no_session)
    api = create_api(MODULES, Settings(_env_file=None, jwt_secret=SECRET), token_check=token_check)
    async with AsyncTestClient(app=api) as client:
        response = await client.get("/core/children", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == status
    assert checked == [token_id]


async def _no_session() -> AsyncIterator[AsyncSession]:
    yield MagicMock(spec=AsyncSession)
