from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User
from sqlalchemy.pool import NullPool

from family_hub import db
from family_hub.admin import service as admin_service
from family_hub.config import Settings, get_settings
from family_hub.conftest import reset_database
from family_hub.core import service as core_service
from family_hub.demo_data import seed

pytestmark = pytest.mark.nicegui_main_file("src/family_hub/simulation.py")


@pytest.fixture
async def app_user(user: User, database: str) -> AsyncIterator[User]:
    """A simulated user on an app with demo data."""
    engine = db.init_engine(database, poolclass=NullPool)
    await reset_database(engine)
    await seed()
    yield user
    await db.dispose_engine()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/", "Heute im Takt"),
        ("/rhythm", "Diese Woche"),
        ("/rhythm/print", "Bedtime"),
        ("/time-capsule", "Der Mond ist angebissen"),
        ("/fever", "Ada"),
        ("/fever/episodes/1", "Fieberkurve"),
        ("/growth", "Neue Messung"),
        ("/people", "Alex"),
        ("/admin", "Personen löschen"),
    ],
)
async def test_pages_render(app_user: User, path: str, expected: str) -> None:
    await app_user.open(path)

    await app_user.should_see(expected)


async def test_capture_memory(app_user: User) -> None:
    await app_user.open("/time-capsule")
    app_user.find(ui.textarea).type("Ich will Astronaut werden")
    app_user.find("Ada").click()
    app_user.find("Speichern").click()

    await app_user.should_see("Ich will Astronaut werden")


async def test_add_person_validation_is_translated(app_user: User) -> None:
    await app_user.open("/people")
    app_user.find("Person hinzufügen").click()
    app_user.find("Speichern").click()

    await app_user.should_see("Der Name darf nicht leer sein.")


async def test_language_switch(app_user: User) -> None:
    await app_user.open("/")
    app_user.find("DE").click()
    await app_user.open("/rhythm")

    await app_user.should_see("This week")


@pytest.fixture
def admin_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Settings]:
    """Process settings with backups in a temporary directory."""
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    monkeypatch.setenv("JWT_SECRET", "s" * 32)
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


async def test_delete_person_needs_typed_name_and_backs_up_first(app_user: User, admin_settings: Settings) -> None:
    await app_user.open("/admin")
    app_user.find(marker="delete-person-1").click()
    await app_user.should_see("Messungen")
    confirm_button = app_user.find(marker="confirm-delete").elements.pop()
    assert isinstance(confirm_button, ui.button)
    assert not confirm_button.enabled

    app_user.find(ui.input).type("Ada")
    app_user.find(marker="confirm-delete").click()

    await app_user.should_see("Ada gelöscht")
    async with db.session() as session:
        assert [p.name for p in await core_service.list_people(session, include_inactive=True)] == ["Alex"]
    assert list(admin_settings.backup_dir.glob("*.json.gz"))


async def test_issue_token_shows_it_once(app_user: User, admin_settings: Settings) -> None:
    await app_user.open("/admin")
    app_user.find(ui.tab_panels).elements.pop().set_value("tokens")
    app_user.find("Neues Token").click()
    await app_user.should_see("Gültig (Tage)")
    app_user.find(ui.input).type("Shortcut")
    app_user.find("Anlegen").click()

    await app_user.should_see("das Token wird nicht noch einmal angezeigt")
    async with db.session() as session:
        assert [t.name for t in await admin_service.list_tokens(session)] == ["Shortcut"]


@pytest.fixture
async def new_install_user(user: User, database: str) -> AsyncIterator[User]:
    """A simulated user on an empty app."""
    engine = db.init_engine(database, poolclass=NullPool)
    await reset_database(engine)
    yield user
    await db.dispose_engine()


async def test_onboarding_on_new_install(new_install_user: User) -> None:
    await new_install_user.open("/")
    await new_install_user.should_see("Willkommen bei Family Hub")
    await new_install_user.should_not_see("Heute im Takt")

    new_install_user.find("Erwachsene Person hinzufügen").click()
    await new_install_user.should_see("Neue Person")
    new_install_user.find(marker="person-name").type("Alex")
    new_install_user.find("Speichern").click()

    await new_install_user.should_not_see("Neue Person")
    async with db.session() as session:
        assert [p.name for p in await core_service.list_people(session)] == ["Alex"]


async def test_no_onboarding_when_set_up(app_user: User) -> None:
    await app_user.open("/")

    await app_user.should_not_see("Willkommen bei Family Hub")
