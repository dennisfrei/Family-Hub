from collections.abc import Callable
from datetime import date
from unittest.mock import AsyncMock

import pytest
from litestar.testing import AsyncTestClient

from family_hub.conftest import FAKE_SESSION
from family_hub.errors import InvalidInputError
from family_hub.rhythm import service
from family_hub.rhythm.schemas import DayRead, WeekRead


async def test_week(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    start = date(2026, 10, 12)
    week = AsyncMock(return_value=WeekRead(start=start, days=[DayRead(date=start, slots=[])]))
    monkeypatch.setattr(service, "week", week)

    async with api() as client:
        response = await client.get("/rhythm/week", params={"start": "2026-10-14"})

    assert response.json() == {"start": "2026-10-12", "days": [{"date": "2026-10-12", "slots": []}]}
    week.assert_awaited_once_with(FAKE_SESSION, date(2026, 10, 14))


@pytest.mark.parametrize(
    ("error", "status"),
    [(InvalidInputError("error.swap_window"), 400), (service.NotFoundError("Duty 3"), 404)],
)
async def test_swap_errors(
    api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch, error: Exception, status: int
) -> None:
    monkeypatch.setattr(service, "set_swap", AsyncMock(side_effect=error))

    async with api() as client:
        response = await client.post("/rhythm/swaps", json={"duty_id": 3, "date": "2026-10-14", "person_id": 1})

    assert response.status_code == status
