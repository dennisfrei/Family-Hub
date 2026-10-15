"""Optional UI login via OpenID Connect (e.g. Pocket ID), switched on with `AUTH_ENABLED`."""

import html
import logging
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import urlencode

from authlib.integrations.base_client import OAuthError
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from fastapi import FastAPI
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from family_hub.config import Settings

logger = logging.getLogger(__name__)

AUTH_COOKIE = "family_hub_auth"
LOGIN_COOKIE = "family_hub_login"
LOGIN_MAX_AGE = 600
LOGIN_PATH = "/auth/login"
CALLBACK_PATH = "/auth/callback"
LOGOUT_PATH = "/auth/logout"
PUBLIC_PREFIXES = ("/auth/", "/api/", "/_nicegui", "/static/")
PUBLIC_PATHS = frozenset({"/api", "/manifest.webmanifest", "/sw.js", "/offline.html", "/favicon.ico"})
SECONDS_PER_DAY = 86400


class AccessDeniedError(Exception):
    """Raised when a signed-in user is not in an allowed group."""


class OidcClient(Protocol):
    """The parts of Authlib's Starlette client used here."""

    async def authorize_redirect(self, request: Request, redirect_uri: str) -> Response:
        """Redirect to the provider's login."""

    async def authorize_access_token(self, request: Request) -> dict[str, Any]:
        """Exchange the code; the result holds the validated `userinfo` claims."""

    async def load_server_metadata(self) -> dict[str, Any]:
        """Return the provider's discovery document."""


class SessionUser(BaseModel):
    """The signed-in user as kept in the login cookie."""

    model_config = ConfigDict(frozen=True)

    sub: str
    name: str
    email: str
    groups: tuple[str, ...]
    is_admin: bool

    def to_data(self) -> dict[str, Any]:
        """Plain data for the cookie."""
        return self.model_dump(mode="json")

    @classmethod
    def from_data(cls, data: object) -> "SessionUser | None":
        """Read cookie data; None if malformed."""
        try:
            return cls.model_validate(data)
        except ValidationError:
            return None


class AuthCookies:
    """Signed cookies for the login: one short-lived for the login flow, one for the signed-in user.

    They are separate from NiceGUI's session cookie, which every response rewrites, so parallel requests cannot drop
    the login.
    """

    def __init__(self, settings: Settings) -> None:
        """Sign with `STORAGE_SECRET`; `Secure` when the public URL uses HTTPS."""
        self.serializer = URLSafeTimedSerializer(settings.storage_secret, salt="family-hub-auth")
        self.max_age = settings.auth_session_days * SECONDS_PER_DAY
        self.secure = settings.public_url.startswith("https://")

    def _load(self, request: Request, name: str, max_age: int) -> dict[str, Any] | None:
        value = request.cookies.get(name)
        if not value:
            return None
        try:
            data = self.serializer.loads(value, max_age=max_age)
        except BadSignature:
            return None
        return data if isinstance(data, dict) else None

    def _set(self, response: Response, name: str, data: dict[str, Any], max_age: int) -> None:
        response.set_cookie(
            name, self.serializer.dumps(data), max_age=max_age, httponly=True, samesite="lax", secure=self.secure
        )

    def user(self, request: Request) -> SessionUser | None:
        """The signed-in user, if the cookie is valid and not expired."""
        data = self._load(request, AUTH_COOKIE, self.max_age)
        return SessionUser.from_data(data.get("user")) if data else None

    def id_token(self, request: Request) -> str | None:
        """The ID token of the login, used as logout hint."""
        data = self._load(request, AUTH_COOKIE, self.max_age)
        return data.get("id_token") if data else None

    def set_user(self, response: Response, user: SessionUser, id_token: str | None) -> None:
        """Store the signed-in user."""
        self._set(response, AUTH_COOKIE, {"user": user.to_data(), "id_token": id_token}, self.max_age)

    def login_flow(self, request: Request) -> dict[str, Any] | None:
        """State of a login started less than ten minutes ago."""
        return self._load(request, LOGIN_COOKIE, LOGIN_MAX_AGE)

    def set_login_flow(self, response: Response, data: dict[str, Any]) -> None:
        """Remember OIDC state and the return path until the callback."""
        self._set(response, LOGIN_COOKIE, data, LOGIN_MAX_AGE)

    def clear(self, response: Response, name: str) -> None:
        """Remove a cookie."""
        response.delete_cookie(name, httponly=True, samesite="lax", secure=self.secure)


def _groups(claims: Mapping[str, Any]) -> tuple[str, ...]:
    groups = claims.get("groups") or []
    return tuple(str(group) for group in groups) if isinstance(groups, list) else (str(groups),)


def user_from_claims(claims: Mapping[str, Any], settings: Settings) -> SessionUser:
    """Build the signed-in user from ID token claims.

    Raises:
        AccessDeniedError: If allowed groups are configured and the user is in none of them.
    """
    groups = _groups(claims)
    allowed = set(settings.oidc_allowed_groups) | set(settings.oidc_admin_groups)
    if settings.oidc_allowed_groups and not set(groups) & allowed:
        raise AccessDeniedError(f"User {claims.get('sub')} is not in an allowed group")
    is_admin = not settings.oidc_admin_groups or bool(set(groups) & set(settings.oidc_admin_groups))
    return SessionUser(
        sub=str(claims["sub"]),
        name=str(claims.get("name") or claims.get("preferred_username") or claims.get("email") or claims["sub"]),
        email=str(claims.get("email") or ""),
        groups=groups,
        is_admin=is_admin,
    )


def is_public(path: str) -> bool:
    """Paths reachable without login: auth routes, the JWT-protected API, assets and PWA files."""
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def safe_next(target: str | None) -> str:
    """A local path to return to after login; anything else becomes `/`."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


def _matches(path: str, prefixes: Sequence[str]) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes)


def _page(status: int, title: str, text: str, *, sign_out: bool = False) -> HTMLResponse:
    links = '<a href="/">Family Hub</a>'
    if sign_out:
        links += f' · <a href="{LOGOUT_PATH}">Mit anderem Konto anmelden / Use another account</a>'
    body = (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title></head>"
        '<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 16px">'
        f"<h1>{html.escape(title)}</h1><p>{html.escape(text)}</p>"
        f"<p>{links}</p></body></html>"
    )
    return HTMLResponse(body, status_code=status)


def current_user(request: Request) -> SessionUser | None:
    """The signed-in user of a request; None without login or when login is off."""
    cookies: AuthCookies | None = getattr(request.app.state, "auth_cookies", None) if "app" in request.scope else None
    return cookies.user(request) if cookies else None


class LoginRequiredMiddleware:
    """Sends visitors without a valid login to the provider; admin paths also need an admin user."""

    def __init__(self, app: ASGIApp, cookies: AuthCookies, admin_paths: Sequence[str] = ()) -> None:
        """Wrap `app`; `admin_paths` are page prefixes only admins may open."""
        self.app = app
        self.cookies = cookies
        self.admin_paths = tuple(admin_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Check HTTP requests; other scopes pass through."""
        if scope["type"] != "http" or is_public(scope["path"]):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        user = self.cookies.user(request)
        response: Response | None = None
        if user is None:
            if request.method == "GET":
                target = scope["path"] + (f"?{request.url.query}" if request.url.query else "")
                response = RedirectResponse(f"{LOGIN_PATH}?{urlencode({'next': target})}", status_code=302)
            else:
                response = PlainTextResponse("Login required", status_code=401)
        elif not user.is_admin and _matches(scope["path"], self.admin_paths):
            response = _page(
                403, "Kein Zugriff / No access", "Dieser Bereich ist Admins vorbehalten. / Admins only.", sign_out=True
            )
        if response is not None:
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


SERVER_SIDE_ENDPOINTS = (
    "token_endpoint",
    "jwks_uri",
    "userinfo_endpoint",
    "introspection_endpoint",
    "revocation_endpoint",
)


def internal_endpoints(metadata: dict[str, Any], public_url: str, internal_url: str) -> dict[str, Any]:
    """Point the endpoints the server calls itself at the internal URL; browser redirects and the issuer stay public."""
    public, internal = public_url.rstrip("/"), internal_url.rstrip("/")
    rewritten = dict(metadata)
    for key in SERVER_SIDE_ENDPOINTS:
        value = rewritten.get(key)
        if isinstance(value, str) and value.startswith(public):
            rewritten[key] = internal + value.removeprefix(public)
    return rewritten


def _internal_client_class(public_url: str, internal_url: str) -> type[StarletteOAuth2App]:
    class InternalOAuth2App(StarletteOAuth2App):
        """Reaches the provider over an internal URL, e.g. a cluster service, while users see the public one."""

        async def load_server_metadata(self) -> dict[str, Any]:
            loaded = "_loaded_at" in self.server_metadata
            metadata = await super().load_server_metadata()
            if not loaded:
                self.server_metadata = internal_endpoints(metadata, public_url, internal_url)
            return self.server_metadata

    return InternalOAuth2App


def create_client(settings: Settings) -> OidcClient:
    """Register the provider from its discovery document; PKCE is always used.

    With `OIDC_INTERNAL_URL`, discovery, token exchange, keys and user info go to that URL instead of the issuer.
    """
    secret = settings.oidc_client_secret.get_secret_value() if settings.oidc_client_secret else None
    client_kwargs: dict[str, str] = {"scope": settings.oidc_scopes, "code_challenge_method": "S256"}
    if secret is None:
        client_kwargs["token_endpoint_auth_method"] = "none"
    discovery_base = (settings.oidc_internal_url or settings.oidc_issuer).rstrip("/")
    extra: dict[str, Any] = {}
    if settings.oidc_internal_url:
        extra["client_cls"] = _internal_client_class(settings.oidc_issuer, settings.oidc_internal_url)
    oauth = OAuth()
    return oauth.register(
        name="oidc",
        client_id=settings.oidc_client_id,
        client_secret=secret,
        server_metadata_url=f"{discovery_base}/.well-known/openid-configuration",
        client_kwargs=client_kwargs,
        **extra,
    )


def _with_session(request: Request, session: dict[str, Any]) -> Request:
    return Request({**request.scope, "session": session}, request.receive)


def _login_failed(text: str) -> HTMLResponse:
    return _page(400, "Anmeldung fehlgeschlagen / Login failed", text)


def setup(app: FastAPI, settings: Settings, client: OidcClient, admin_paths: Sequence[str]) -> None:
    """Add the login middleware and the login, callback and logout routes."""
    public_url = settings.public_url.rstrip("/")
    cookies = AuthCookies(settings)
    app.state.auth_cookies = cookies
    app.add_middleware(LoginRequiredMiddleware, cookies=cookies, admin_paths=admin_paths)

    @app.get(LOGIN_PATH, include_in_schema=False)
    async def login(request: Request) -> Response:
        state: dict[str, Any] = {}
        response = await client.authorize_redirect(_with_session(request, state), f"{public_url}{CALLBACK_PATH}")
        cookies.set_login_flow(response, {"state": state, "next": safe_next(request.query_params.get("next"))})
        return response

    @app.get(CALLBACK_PATH, include_in_schema=False)
    async def callback(request: Request) -> Response:
        flow = cookies.login_flow(request)
        if flow is None:
            logger.warning("Login failed: no or expired login flow")
            return _login_failed("Die Anmeldung ist abgelaufen. Bitte erneut versuchen.")
        try:
            token = await client.authorize_access_token(_with_session(request, flow.get("state", {})))
        except OAuthError as exc:
            logger.warning(f"Login failed: {exc.error}")
            return _login_failed(f"{exc.error}. Bitte erneut versuchen.")
        claims = token.get("userinfo") or {}
        if "sub" not in claims:
            logger.warning("Login failed: no ID token claims")
            return _login_failed("Keine Benutzerdaten erhalten.")
        try:
            user = user_from_claims(claims, settings)
        except AccessDeniedError as exc:
            logger.warning(str(exc))
            return _page(
                403, "Kein Zugriff / No access", "Dieses Konto hat keinen Zugriff auf Family Hub.", sign_out=True
            )
        response = RedirectResponse(safe_next(flow.get("next")), status_code=302)
        cookies.set_user(response, user, token.get("id_token"))
        cookies.clear(response, LOGIN_COOKIE)
        logger.info(f"User {user.sub} signed in")
        return response

    @app.get(LOGOUT_PATH, include_in_schema=False)
    async def logout(request: Request) -> Response:
        id_token = cookies.id_token(request)
        try:
            end_session = (await client.load_server_metadata()).get("end_session_endpoint")
        except Exception as exc:
            logger.warning(f"Provider metadata not available for logout: {exc}")
            end_session = None
        target = "/"
        if end_session:
            params = {"client_id": settings.oidc_client_id, "post_logout_redirect_uri": f"{public_url}/"}
            if id_token:
                params["id_token_hint"] = id_token
            target = f"{end_session}?{urlencode(params)}"
        response = RedirectResponse(target, status_code=302)
        cookies.clear(response, AUTH_COOKIE)
        return response
