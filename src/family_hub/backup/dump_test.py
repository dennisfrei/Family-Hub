import json
from datetime import date
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.backup import dump
from family_hub.core import service
from family_hub.core.models import PersonKind, Sex
from family_hub.core.schemas import PersonWrite


async def test_roundtrip_replaces_data_and_resets_sequences(session: AsyncSession) -> None:
    child = await service.create_person(
        session, PersonWrite(name="Ada", kind=PersonKind.CHILD, birth_date=date(2022, 3, 15), sex=Sex.FEMALE)
    )
    connection = await session.connection()
    data = json.loads(json.dumps(await dump.export_data(connection), default=dump.json_default))
    await session.commit()
    await service.create_person(session, PersonWrite(name="Later", kind=PersonKind.ADULT))
    await service.create_person(session, PersonWrite(name="Even later", kind=PersonKind.ADULT))

    await dump.import_data(await session.connection(), data)
    await session.commit()
    after_restore = await service.create_person(session, PersonWrite(name="New", kind=PersonKind.ADULT))

    people = await service.list_people(session, include_inactive=True)
    assert [(p.name, p.birth_date) for p in people if p.kind is PersonKind.CHILD] == [("Ada", date(2022, 3, 15))]
    assert after_restore.id == child.id + 1
    assert data["schema_revision"] == await dump.schema_revision(await session.connection())
    assert {"core.person", "core.child_profile", "fever.episode", "fever.reading"} <= set(data["tables"])


def test_hash_ignores_timestamp() -> None:
    data = {"version": "1.0", "schema_revision": "0005", "exported_at": "now", "tables": {"core.person": []}}

    assert dump.content_hash(data) == dump.content_hash({**data, "exported_at": "later"})
    assert dump.content_hash(data) != dump.content_hash({**data, "tables": {"core.person": [{"id": 1}]}})


async def test_import_requires_migrated_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dump, "schema_revision", AsyncMock(return_value=None))

    with pytest.raises(RuntimeError, match="migrations"):
        await dump.import_data(AsyncMock(), {"tables": {}})


async def test_import_rejects_malformed_backup() -> None:
    with pytest.raises(RuntimeError, match="tables"):
        await dump.import_data(AsyncMock(), {"version": "1.0"})
