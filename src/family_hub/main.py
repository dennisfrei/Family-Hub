"""Entry point: run migrations, then start the combined NiceGUI + Litestar server."""

import logging
import sys

from alembic import command
from alembic.config import Config
from nicegui import ui

from family_hub.app import setup
from family_hub.config import Settings, get_settings
from family_hub.ui import pwa

logger = logging.getLogger("family_hub")


def run_migrations(settings: Settings) -> None:
    """Upgrade the database to the latest Alembic revision."""
    logger.info("Running database migrations")
    config = Config(str(settings.alembic_ini))
    config.attributes["configure_logger"] = False
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    logger.info("Database migrations completed")


def main() -> None:
    """Start Family Hub."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    if settings.run_migrations:
        run_migrations(settings)
    setup(settings)
    ui.run(
        title="Family Hub",
        host=settings.host,
        port=settings.port,
        language="de",
        favicon=pwa.STATIC_DIR / "favicon.png",
        viewport="width=device-width, initial-scale=1, viewport-fit=cover",
        reload=False,
        show=False,
        storage_secret=settings.storage_secret,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
