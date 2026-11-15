from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from litestar.testing import AsyncTestClient

from family_hub.blood_pressure import service
from family_hub.blood_pressure.levels import Level
from family_hub.blood_pressure.schemas import ReadingRead, ReadingWrite
from family_hub.conftest import FAKE_SESSION
from family_hub.core.service import PersonNotFoundError
from family_hub.errors import InvalidInputError

READING = ReadingRead(
    id=4,
    person_id=1,
    systolic=124,
    diastolic=81,
    pulse=64,
    measured_at=datetime(2026, 10, 1, 8, tzinfo=UTC),
    level=Level.NORMAL,
)


async def test_add_reading(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    add = AsyncMock(return_value=READING)
    monkeypatch.setattr(service, "add_reading", add)

    async with api() as client:
        response = await client.post(
            "/blood-pressure/readings", json={"person_id": 1, "systolic": 124, "diastolic": 81, "pulse": 64}
        )

    assert response.status_code == 201
    assert response.json()["level"] == "normal"
    add.assert_awaited_once_with(FAKE_SESSION, ReadingWrite(person_id=1, systolic=124, diastolic=81, pulse=64))


@pytest.mark.parametrize(
    ("error", "status"),
    [(InvalidInputError("error.blood_pressure_order"), 400), (PersonNotFoundError("Person 99 not found"), 404)],
)
async def test_add_reading_errors(
    api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch, error: Exception, status: int
) -> None:
    monkeypatch.setattr(service, "add_reading", AsyncMock(side_effect=error))

    async with api() as client:
        response = await client.post(
            "/blood-pressure/readings", json={"person_id": 99, "systolic": 80, "diastolic": 120}
        )

    assert response.status_code == status


async def test_list_readings_filter(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    list_readings = AsyncMock(return_value=[READING])
    monkeypatch.setattr(service, "list_readings", list_readings)

    async with api() as client:
        response = await client.get("/blood-pressure/readings", params={"person_id": 1, "limit": 5, "offset": 10})

    assert [r["systolic"] for r in response.json()] == [124]
    list_readings.assert_awaited_once_with(FAKE_SESSION, person_id=1, limit=5, offset=10)


async def test_delete_unknown_reading(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "delete_reading", AsyncMock(side_effect=service.NotFoundError("Reading 7")))

    async with api() as client:
        response = await client.delete("/blood-pressure/readings/7")

    assert response.status_code == 404
