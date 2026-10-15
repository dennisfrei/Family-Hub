from datetime import date, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core import service as core_service
from family_hub.core.importing import MappingError
from family_hub.core.models import PersonKind, Sex
from family_hub.core.schemas import PersonWrite
from family_hub.fever import service
from family_hub.fever.importer import build_episodes

BACKUP: dict[str, Any] = {
    "version": "1.0",
    "tables": {
        "measurement_series": [
            {
                "id": 3,
                "name": "Erkältung",
                "description": None,
                "age_group": "child",
                "created_at": "2026-01-01T07:00:00",
            },
            {"id": 4, "name": "Test", "description": None, "age_group": None, "created_at": "2026-02-01T07:00:00"},
        ],
        "measurements": [
            {"id": 1, "series_id": 3, "temperature": 38.7, "measured_at": "2026-01-01T20:00:00", "notes": "abends"},
            {"id": 2, "series_id": 3, "temperature": 37.2, "measured_at": "2026-01-02T08:00:00", "notes": None},
        ],
    },
}


def test_unmapped_series_abort() -> None:
    with pytest.raises(MappingError, match="4"):
        build_episodes(BACKUP, {"fever": {"series": {"3": 1}}})


def test_build_episodes() -> None:
    episodes = build_episodes(BACKUP, {"fever": {"series": {"3": 1, "4": None}}})

    assert len(episodes) == 1
    assert episodes[0].import_ref == "fever-plot:3"
    assert episodes[0].started_at == datetime(2026, 1, 1, 20)
    assert episodes[0].ended_at == datetime(2026, 1, 2, 8)
    assert [r.note for r in episodes[0].readings] == ["abends", None]


async def test_import_is_idempotent(session: AsyncSession) -> None:
    person = await core_service.create_person(
        session, PersonWrite(name="Ada", kind=PersonKind.CHILD, birth_date=date(2022, 3, 15), sex=Sex.FEMALE)
    )
    episodes = build_episodes(BACKUP, {"fever": {"series": {"3": person.id, "4": None}}})

    assert await service.import_episodes(session, episodes, dry_run=True) == ["fever-plot:3"]
    assert await service.list_episodes(session) == []

    assert await service.import_episodes(session, episodes, dry_run=False) == ["fever-plot:3"]
    assert await service.import_episodes(session, episodes, dry_run=False) == []

    [episode] = await service.list_episodes(session)
    assert episode.reading_count == 2
    assert episode.ended_at is not None


async def test_import_unknown_person(session: AsyncSession) -> None:
    episodes = build_episodes(BACKUP, {"fever": {"series": {"3": 99, "4": None}}})

    with pytest.raises(core_service.PersonNotFoundError):
        await service.import_episodes(session, episodes, dry_run=False)
