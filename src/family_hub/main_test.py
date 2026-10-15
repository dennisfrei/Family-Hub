from alembic import command
from alembic.config import Config

from family_hub.config import Settings


def _config(database: str) -> Config:
    settings = Settings(_env_file=None, database_url=database)
    config = Config(str(settings.alembic_ini))
    config.attributes["configure_logger"] = False
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def test_models_match_migrations(database: str) -> None:
    command.check(_config(database))


def test_downgrade_and_upgrade_again(database: str) -> None:
    config = _config(database)

    command.downgrade(config, "base")
    command.upgrade(config, "head")
