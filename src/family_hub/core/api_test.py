from collections.abc import Callable
from datetime import date
from unittest.mock import AsyncMock

import pytest
from litestar.testing import AsyncTestClient

from family_hub.conftest import FAKE_SESSION
from family_hub.core import service
from family_hub.core.models import Sex
from family_hub.core.schemas import ChildRead

ADA = ChildRead(id=1, name="Ada", color="#e91e63", birth_date=date(2022, 3, 15), sex=Sex.FEMALE, age_months=30)


async def test_children(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    list_children = AsyncMock(return_value=[ADA])
    monkeypatch.setattr(service, "list_children", list_children)

    async with api() as client:
        response = await client.get("/core/children")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "name": "Ada", "color": "#e91e63", "birth_date": "2022-03-15", "sex": "female", "age_months": 30}
    ]
    list_children.assert_awaited_once_with(FAKE_SESSION)


async def test_people_passes_filter(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    list_people = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "list_people", list_people)

    async with api() as client:
        await client.get("/core/people", params={"include_inactive": True})

    list_people.assert_awaited_once_with(FAKE_SESSION, include_inactive=True)


async def test_person_not_found(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "get_person", AsyncMock(side_effect=service.PersonNotFoundError("Person 9")))

    async with api() as client:
        response = await client.get("/core/people/9")

    assert response.status_code == 404
