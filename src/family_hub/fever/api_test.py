from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from litestar.testing import AsyncTestClient

from family_hub.conftest import FAKE_SESSION
from family_hub.core.service import PersonNotFoundError
from family_hub.errors import InvalidInputError
from family_hub.fever import service
from family_hub.fever.schemas import QuickReadingWrite, ReadingRead
from family_hub.fever.thresholds import Level

READING = ReadingRead(
    id=5, episode_id=2, temperature=38.9, measured_at=datetime(2026, 10, 1, 8, tzinfo=UTC), level=Level.FEVER
)


async def test_quick_reading(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    quick_add = AsyncMock(return_value=READING)
    monkeypatch.setattr(service, "quick_add_reading", quick_add)

    async with api() as client:
        response = await client.post("/fever/readings", json={"person_id": 1, "temperature": 38.9})

    assert response.status_code == 201
    assert response.json()["level"] == "fever"
    assert response.json()["episode_id"] == 2
    quick_add.assert_awaited_once_with(FAKE_SESSION, QuickReadingWrite(person_id=1, temperature=38.9))


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (InvalidInputError("error.temperature_range", low=34, high=43), 400),
        (PersonNotFoundError("Person 99 not found"), 404),
    ],
)
async def test_quick_reading_errors(
    api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch, error: Exception, status: int
) -> None:
    monkeypatch.setattr(service, "quick_add_reading", AsyncMock(side_effect=error))

    async with api() as client:
        response = await client.post("/fever/readings", json={"person_id": 99, "temperature": 38.0})

    assert response.status_code == status


async def test_open_episodes_filter(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    list_episodes = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "list_episodes", list_episodes)

    async with api() as client:
        response = await client.get("/fever/episodes", params={"open_only": True, "person_id": 3})

    assert response.json() == []
    list_episodes.assert_awaited_once_with(FAKE_SESSION, person_id=3, open_only=True)


async def test_episode_not_found(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "get_episode", AsyncMock(side_effect=service.NotFoundError("Episode 7")))

    async with api() as client:
        response = await client.get("/fever/episodes/7")

    assert response.status_code == 404
