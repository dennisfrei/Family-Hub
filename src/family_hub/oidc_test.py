from typing import Any

import pytest
from authlib.integrations.base_client import OAuthError
from fastapi import FastAPI
from httpx2 import Response as HttpResponse
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.testclient import TestClient

from family_hub import oidc
from family_hub.config import Settings

SETTINGS = Settings(
    _env_file=None,
    auth_enabled=True,
    public_url="https://hub.example.org",
    oidc_issuer="https://id.example.org",
    oidc_client_id="family-hub",
    storage_secret="s" * 32,
    oidc_admin_groups=["parents"],
)
CLAIMS = {"sub": "u1", "name": "Alex", "email": "alex@example.org", "groups": ["parents"]}


class FakeClient:
    """Stands in for the provider."""

    def __init__(self, claims: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.claims = claims or CLAIMS
        self.error = error
        self.redirect_uri = ""

    async def authorize_redirect(self, request: Request, redirect_uri: str) -> Response:
        self.redirect_uri = redirect_uri
        return RedirectResponse("https://id.example.org/authorize", status_code=302)

    async def authorize_access_token(self, request: Request) -> dict[str, Any]:
        if self.error:
            raise OAuthError(error=self.error)
        return {"userinfo": self.claims, "id_token": "id.token.value"}

    async def load_server_metadata(self) -> dict[str, Any]:
        return {"end_session_endpoint": "https://id.example.org/end-session"}


def _client(fake: FakeClient, settings: Settings = SETTINGS) -> TestClient:
    app = FastAPI()
    oidc.setup(app, settings, fake, admin_paths=["/admin"])

    @app.get("/")
    @app.get("/fever")
    @app.get("/admin")
    @app.get("/api/core/children")
    async def page() -> PlainTextResponse:
        return PlainTextResponse("page")

    return TestClient(app, base_url="https://hub.example.org", follow_redirects=False)


def _login(client: TestClient, target: str = "/fever") -> HttpResponse:
    client.get(f"/auth/login?next={target}")
    return client.get("/auth/callback?code=c&state=s")


def test_page_redirects_to_login_with_target() -> None:
    response = _client(FakeClient()).get("/fever?tab=2")

    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login?next=%2Ffever%3Ftab%3D2"


def test_public_paths_pass() -> None:
    client = _client(FakeClient())

    assert client.get("/api/core/children").status_code == 200
    assert client.post("/fever").status_code == 401


def test_login_returns_to_target_and_opens_pages() -> None:
    fake = FakeClient()
    client = _client(fake)

    response = _login(client)

    assert fake.redirect_uri == "https://hub.example.org/auth/callback"
    assert response.headers["location"] == "/fever"
    assert client.get("/fever").text == "page"
    assert client.get("/admin").status_code == 200


def test_non_admin_cannot_open_admin_paths() -> None:
    client = _client(FakeClient({**CLAIMS, "groups": ["caregivers"]}))
    _login(client)

    assert client.get("/fever").status_code == 200
    assert client.get("/admin").status_code == 403


def test_user_outside_allowed_groups_is_rejected() -> None:
    settings = SETTINGS.model_copy(update={"oidc_allowed_groups": ["family"]})
    client = _client(FakeClient({**CLAIMS, "groups": ["guests"]}), settings)

    assert _login(client).status_code == 403
    assert client.get("/fever").status_code == 302


def test_failed_login_shows_error() -> None:
    client = _client(FakeClient(error="access_denied"))

    response = _login(client)

    assert response.status_code == 400
    assert "access_denied" in response.text


def test_logout_ends_session_at_provider() -> None:
    client = _client(FakeClient())
    _login(client)

    response = client.get("/auth/logout")

    assert response.headers["location"].startswith("https://id.example.org/end-session?client_id=family-hub")
    assert "id_token_hint=id.token.value" in response.headers["location"]
    assert client.get("/fever").status_code == 302


@pytest.mark.parametrize(
    ("target", "expected"),
    [("/fever?x=1", "/fever?x=1"), ("//evil.example", "/"), ("https://evil.example", "/"), (None, "/"), ("/\\x", "/")],
)
def test_safe_next(target: str | None, expected: str) -> None:
    assert oidc.safe_next(target) == expected


def test_tampered_cookie_is_ignored() -> None:
    client = _client(FakeClient())
    _login(client)
    value = client.cookies[oidc.AUTH_COOKIE]

    client.cookies.set(oidc.AUTH_COOKIE, value[:-2] + "xx")
    assert client.get("/fever").status_code == 302


def test_callback_without_login_flow_fails() -> None:
    response = _client(FakeClient()).get("/auth/callback?code=c&state=s")

    assert response.status_code == 400


def test_login_survives_stale_session_cookie() -> None:
    client = _client(FakeClient())
    client.get("/auth/login?next=/fever")
    client.cookies.set("session", "stale")

    assert _login(client, "/fever").headers["location"] == "/fever"


def test_admin_group_is_always_allowed() -> None:
    settings = SETTINGS.model_copy(update={"oidc_allowed_groups": ["family"]})

    assert oidc.user_from_claims(CLAIMS, settings).is_admin


def test_denied_page_offers_sign_out() -> None:
    settings = SETTINGS.model_copy(update={"oidc_allowed_groups": ["family"]})
    client = _client(FakeClient({**CLAIMS, "groups": ["guests"]}), settings)

    response = _login(client)

    assert response.status_code == 403
    assert oidc.LOGOUT_PATH in response.text


def test_admin_without_admin_groups_configured() -> None:
    settings = SETTINGS.model_copy(update={"oidc_admin_groups": []})

    assert oidc.user_from_claims({"sub": "u2"}, settings).is_admin


@pytest.mark.parametrize(
    "overrides",
    [{"oidc_issuer": ""}, {"public_url": ""}, {"storage_secret": "change-me"}],
)
def test_enabled_auth_needs_config(overrides: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="AUTH_ENABLED"):
        Settings.model_validate({**SETTINGS.model_dump(), **overrides})


def test_groups_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_ADMIN_GROUPS", "parents, admins")

    assert Settings(_env_file=None).oidc_admin_groups == ["parents", "admins"]


def test_internal_url_only_for_server_side_endpoints() -> None:
    metadata = {
        "issuer": "https://id.example.org",
        "authorization_endpoint": "https://id.example.org/authorize",
        "end_session_endpoint": "https://id.example.org/api/oidc/end-session",
        "token_endpoint": "https://id.example.org/api/oidc/token",
        "jwks_uri": "https://id.example.org/.well-known/jwks.json",
        "userinfo_endpoint": "https://id.example.org/api/oidc/userinfo",
    }

    rewritten = oidc.internal_endpoints(metadata, "https://id.example.org/", "http://pocket-id:1411")

    assert rewritten["token_endpoint"] == "http://pocket-id:1411/api/oidc/token"
    assert rewritten["jwks_uri"] == "http://pocket-id:1411/.well-known/jwks.json"
    assert rewritten["userinfo_endpoint"] == "http://pocket-id:1411/api/oidc/userinfo"
    assert rewritten["issuer"] == metadata["issuer"]
    assert rewritten["authorization_endpoint"] == metadata["authorization_endpoint"]
    assert rewritten["end_session_endpoint"] == metadata["end_session_endpoint"]


async def test_internal_client_rewrites_after_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SETTINGS.model_copy(update={"oidc_internal_url": "http://pocket-id:1411"})
    client = oidc.create_client(settings)
    assert isinstance(client, oidc.StarletteOAuth2App)
    discovered = {"issuer": "https://id.example.org", "token_endpoint": "https://id.example.org/api/oidc/token"}

    async def fake_load(self: object) -> dict[str, object]:
        client.server_metadata.update({**discovered, "_loaded_at": 1})
        return client.server_metadata

    monkeypatch.setattr(oidc.StarletteOAuth2App, "load_server_metadata", fake_load)
    metadata = await client.load_server_metadata()

    assert client._server_metadata_url == "http://pocket-id:1411/.well-known/openid-configuration"
    assert metadata["token_endpoint"] == "http://pocket-id:1411/api/oidc/token"
    assert metadata["issuer"] == "https://id.example.org"
