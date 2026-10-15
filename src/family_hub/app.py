"""App assembly: NiceGUI hosts the pages, Litestar is mounted under `/api`."""

import logging
from typing import cast

from litestar import Litestar
from litestar.di import Provide
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.openapi.spec import Server
from nicegui import app as nicegui_app
from starlette.types import ASGIApp

from family_hub import admin, app_version, core, db, fever, growth, health, home, oidc, rhythm, time_capsule
from family_hub.admin.service import token_is_valid
from family_hub.auth import TokenCheck, create_jwt_auth
from family_hub.config import Settings
from family_hub.module import Module, register_modules
from family_hub.proxy_prefix import ForwardedPrefixMiddleware
from family_hub.ui import pwa
from family_hub.ui.layout import set_navigation

logger = logging.getLogger(__name__)

API_PATH = "/api"

MODULES: list[Module] = [
    home.MODULE,
    rhythm.MODULE,
    time_capsule.MODULE,
    fever.MODULE,
    growth.MODULE,
    core.MODULE,
    admin.MODULE,
]


def create_api(modules: list[Module], settings: Settings, token_check: TokenCheck = token_is_valid) -> Litestar:
    """Build the Litestar app with every module's API handlers, protected by JWT.

    Args:
        modules: Modules whose handlers are mounted.
        settings: App settings.
        token_check: Decides whether an issued token id is still valid.
    """
    handlers = [handler for module in modules for handler in module.api_handlers]
    return Litestar(
        route_handlers=[*health.create_handlers(settings.alembic_ini), *handlers],
        on_app_init=[create_jwt_auth(settings, token_check).on_app_init],
        dependencies={"session": Provide(db.provide_session)},
        openapi_config=OpenAPIConfig(
            title="Family Hub API",
            version=app_version(),
            path="/docs",
            servers=[Server(url=f"{settings.forwarded_prefix.rstrip('/')}{API_PATH}")],
            render_plugins=[SwaggerRenderPlugin(path="/swagger")],
        ),
    )


def setup(settings: Settings) -> None:
    """Initialise the database, register all pages and mount the API."""
    db.init_engine(settings.database_url, pool_pre_ping=True)
    register_modules(MODULES)
    for module in MODULES:
        module.register_pages()
        logger.info(f"Registered module {module.name}")
    set_navigation(MODULES)
    pwa.register(settings.forwarded_prefix)
    # Litestar's ASGI signature uses typed scopes, Starlette expects plain mappings
    nicegui_app.mount(API_PATH, cast("ASGIApp", create_api(MODULES, settings)))
    if settings.auth_enabled:
        admin_paths = [module.path for module in MODULES if module.admin_only]
        oidc.setup(nicegui_app, settings, oidc.create_client(settings), admin_paths)
        logger.info(f"Login enabled with provider {settings.oidc_issuer}")
    if settings.forwarded_prefix:
        nicegui_app.add_middleware(ForwardedPrefixMiddleware, prefix=settings.forwarded_prefix)
        logger.info(f"Serving behind path prefix {settings.forwarded_prefix}")
    nicegui_app.on_shutdown(db.dispose_engine)
