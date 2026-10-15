"""Descriptor every feature module provides to register itself with the app."""

from collections.abc import Awaitable, Callable

from litestar import Controller
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession


class PersonData(BaseModel):
    """How a module reports and removes the data it keeps about one person.

    Attributes:
        count: Returns the number of affected items per translation key.
        delete: Removes or detaches the data; must not commit.
    """

    model_config = ConfigDict(frozen=True)

    count: Callable[[AsyncSession, int], Awaitable[dict[str, int]]]
    delete: Callable[[AsyncSession, int], Awaitable[None]]


class Module(BaseModel):
    """A feature module: navigation entry, NiceGUI pages and API handlers.

    Attributes:
        name: English identifier, used in code and routes.
        label_key: Translation key of the label shown in the UI.
        icon: Material icon name.
        path: Page path of the module's entry page.
        register_pages: Registers the module's NiceGUI pages.
        api_handlers: Litestar controllers mounted under `/api`.
        in_navigation: Whether the module appears in the main navigation.
        person_data: Hooks used when a person is deleted for good.
        admin_only: With login enabled, only admins see and open the module.
        navigation_bottom: Shown at the bottom of the navigation, apart from the feature modules.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    label_key: str
    icon: str
    path: str
    register_pages: Callable[[], None]
    api_handlers: list[type[Controller]] = Field(default_factory=list)
    in_navigation: bool = True
    person_data: PersonData | None = None
    admin_only: bool = False
    navigation_bottom: bool = False


_registered: list[Module] = []


def register_modules(modules: list[Module]) -> None:
    """Remember the active modules so cross-module features can reach them."""
    _registered[:] = modules


def registered_modules() -> list[Module]:
    """Return the active modules in navigation order."""
    return list(_registered)
