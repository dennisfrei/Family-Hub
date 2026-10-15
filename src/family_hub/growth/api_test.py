from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest
from litestar.testing import AsyncTestClient

from family_hub.core.service import PersonNotFoundError
from family_hub.growth import service


@pytest.mark.parametrize(
    ("error", "status"),
    [(PersonNotFoundError("Person 9"), 404), (service.NotAChildError("Person 2 is no child"), 400)],
)
async def test_status_errors(
    api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch, error: Exception, status: int
) -> None:
    monkeypatch.setattr(service, "status", AsyncMock(side_effect=error))

    async with api() as client:
        response = await client.get("/growth/status", params={"person_id": 9})

    assert response.status_code == status
