from collections.abc import Callable
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest
from litestar.testing import AsyncTestClient

from family_hub.conftest import FAKE_SESSION
from family_hub.core import service as core_service
from family_hub.core.models import PersonKind
from family_hub.core.schemas import PersonRead
from family_hub.time_capsule import service
from family_hub.time_capsule.models import EntryType
from family_hub.time_capsule.schemas import EntryChild, EntryFilter, EntryRead, EntryWrite

ENTRY = EntryRead(
    id=1,
    text="Hallo Mond",
    type=EntryType.SAYING,
    date=date(2026, 3, 1),
    children=[EntryChild(person_id=1, name="Ada", color="#e91e63", age_months=47)],
    tags=[],
    created_at=datetime(2026, 3, 1, tzinfo=UTC),
)
ADA = PersonRead(id=1, name="Ada", kind=PersonKind.CHILD, color="#e91e63", active=True)


async def test_shortcut_capture(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    create_entry = AsyncMock(return_value=ENTRY)
    monkeypatch.setattr(service, "create_entry", create_entry)

    async with api() as client:
        response = await client.post(
            "/time-capsule/entries", json={"text": "Hallo Mond", "person_ids": [1], "type": "saying"}
        )

    assert response.status_code == 201
    assert response.json()["children"][0]["name"] == "Ada"
    create_entry.assert_awaited_once_with(
        FAKE_SESSION, EntryWrite(text="Hallo Mond", person_ids=[1], type=EntryType.SAYING)
    )


async def test_markdown_export(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    list_entries = AsyncMock(return_value=[ENTRY])
    monkeypatch.setattr(service, "list_entries", list_entries)

    async with api() as client:
        response = await client.get("/time-capsule/export", params={"format": "md", "child": 1})

    assert "Hallo Mond" in response.text
    list_entries.assert_awaited_once_with(FAKE_SESSION, EntryFilter(person_id=1))


async def test_pdf_booklet(api: Callable[[], AsyncTestClient], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "list_entries", AsyncMock(return_value=[ENTRY]))
    monkeypatch.setattr(core_service, "get_person", AsyncMock(return_value=ADA))

    async with api() as client:
        booklet = await client.get("/time-capsule/export", params={"format": "pdf", "child": 1, "year": 2026})
        without_child = await client.get("/time-capsule/export", params={"format": "pdf"})

    assert booklet.content.startswith(b"%PDF")
    assert booklet.headers["content-disposition"] == 'attachment; filename="zeitkapsel-2026.pdf"'
    assert without_child.status_code == 400
