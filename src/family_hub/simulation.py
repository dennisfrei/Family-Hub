"""App entry point for UI tests, run by NiceGUI's user simulation; tests seed the data via `demo_data.seed`."""

from nicegui import ui
from pydantic import SecretStr

from family_hub.app import setup
from family_hub.config import Settings
from family_hub.conftest import TEST_DATABASE_URL

SETTINGS = Settings(
    database_url=TEST_DATABASE_URL, jwt_secret=SecretStr("s" * 32), run_migrations=False, _env_file=None
)

setup(SETTINGS)
ui.run(storage_secret="simulation", reload=False, show=False)
