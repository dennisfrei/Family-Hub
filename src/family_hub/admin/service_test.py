from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.admin import service
from family_hub.app import MODULES
from family_hub.conftest import API_SETTINGS
from family_hub.core import service as core_service
from family_hub.core.models import PersonKind, Sex
from family_hub.core.schemas import PersonRead, PersonWrite
from family_hub.errors import InvalidInputError
from family_hub.fever import service as fever_service
from family_hub.fever.schemas import QuickReadingWrite
from family_hub.growth import service as growth_service
from family_hub.growth.models import MeasurementType
from family_hub.growth.schemas import MeasurementWrite
from family_hub.rhythm import service as rhythm_service
from family_hub.rhythm.models import RotationPeriod, RuleMode, TimeOfDay
from family_hub.rhythm.schemas import DutyWrite, RuleWrite
from family_hub.time_capsule import service as time_capsule_service
from family_hub.time_capsule.schemas import EntryWrite


async def _child(session: AsyncSession, name: str) -> PersonRead:
    return await core_service.create_person(
        session, PersonWrite(name=name, kind=PersonKind.CHILD, birth_date=date(2022, 3, 15), sex=Sex.FEMALE)
    )


async def _family(session: AsyncSession) -> tuple[PersonRead, PersonRead, PersonRead, PersonRead]:
    ada = await _child(session, "Ada")
    ben = await _child(session, "Ben")
    alex = await core_service.create_person(session, PersonWrite(name="Alex", kind=PersonKind.ADULT))
    sam = await core_service.create_person(session, PersonWrite(name="Sam", kind=PersonKind.ADULT))
    await fever_service.quick_add_reading(
        session, QuickReadingWrite(person_id=ada.id, temperature=38.6, measured_at=datetime.now(UTC))
    )
    await growth_service.add_measurements(
        session,
        [MeasurementWrite(person_id=ada.id, type=MeasurementType.LENGTH, value=76.0, measured_on=date(2023, 3, 20))],
    )
    await time_capsule_service.create_entry(session, EntryWrite(text="Only Ada", person_ids=[ada.id], tags=["x"]))
    await time_capsule_service.create_entry(
        session, EntryWrite(text="Both", person_ids=[ada.id, ben.id], author_id=alex.id)
    )
    for_ada = await rhythm_service.create_duty(
        session, DutyWrite(name="Ada to school", time_of_day=TimeOfDay.MORNING, weekdays=[0], for_person_id=ada.id)
    )
    await rhythm_service.set_rules(session, for_ada.id, [RuleWrite(weekday=0, mode=RuleMode.FIXED, person_id=sam.id)])
    bedtime = await rhythm_service.create_duty(
        session, DutyWrite(name="Bedtime", time_of_day=TimeOfDay.EVENING, weekdays=[0, 1])
    )
    await rhythm_service.set_rules(
        session,
        bedtime.id,
        [
            RuleWrite(weekday=0, mode=RuleMode.FIXED, person_id=alex.id),
            RuleWrite(
                weekday=1,
                mode=RuleMode.ROTATION,
                rotation_person_ids=[alex.id, sam.id],
                rotation_period=RotationPeriod.WEEKLY,
                anchor_date=date(2026, 1, 5),
            ),
        ],
    )
    return ada, ben, alex, sam


async def test_usage_lists_data_per_module(session: AsyncSession) -> None:
    ada, _, alex, _ = await _family(session)

    ada_usage = {u.module: u.items for u in await service.person_usage(session, ada.id, MODULES)}
    alex_usage = {u.module: u.items for u in await service.person_usage(session, alex.id, MODULES)}

    assert ada_usage == {
        "fever": {"fever.data.episodes": 1, "fever.data.readings": 1},
        "growth": {"growth.data.measurements": 1},
        "rhythm": {"rhythm.data.duties": 1},
        "time_capsule": {"tc.data.entries": 1, "tc.data.shared": 1},
    }
    assert alex_usage == {"rhythm": {"rhythm.data.rules": 2}}


async def test_delete_child_removes_all_module_data(session: AsyncSession) -> None:
    ada, ben, _, _ = await _family(session)

    await service.delete_person(session, ada.id, MODULES)

    assert [p.name for p in await core_service.list_people(session, include_inactive=True)] == ["Alex", "Sam", "Ben"]
    assert await fever_service.list_episodes(session) == []
    assert [d.name for d in await rhythm_service.list_duties(session, include_inactive=True)] == ["Bedtime"]
    [entry] = await time_capsule_service.list_entries(session)
    assert entry.text == "Both"
    assert [c.person_id for c in entry.children] == [ben.id]
    assert await time_capsule_service.list_tags(session) == []
    assert await service.person_usage(session, ben.id, MODULES) != []


async def test_delete_adult_opens_rules_and_shortens_rotation(session: AsyncSession) -> None:
    _, _, alex, sam = await _family(session)

    await service.delete_person(session, alex.id, MODULES)

    bedtime = next(d for d in await rhythm_service.list_duties(session) if d.name == "Bedtime")
    monday, tuesday = bedtime.rules
    assert monday.person_id is None
    assert tuesday.rotation_person_ids == [sam.id]
    entries = await time_capsule_service.list_entries(session)
    assert all(entry.author_id is None for entry in entries)


async def test_delete_unknown_person(session: AsyncSession) -> None:
    with pytest.raises(core_service.PersonNotFoundError):
        await service.delete_person(session, 999, MODULES)


async def test_tokens_issue_list_revoke(session: AsyncSession) -> None:
    issued = await service.issue_token(session, API_SETTINGS, " Shortcut ", 30)

    assert issued.token.count(".") == 2
    assert issued.info.name == "Shortcut"
    assert issued.info.expires_at - issued.info.created_at > timedelta(days=29)
    assert await service.use_token(session, issued.info.token_id)
    assert (await service.list_tokens(session))[0].last_used_at is not None

    revoked = await service.revoke_token(session, issued.info.id)

    assert revoked.revoked_at is not None
    assert not revoked.is_active(datetime.now(UTC))
    assert not await service.use_token(session, issued.info.token_id)
    assert not await service.use_token(session, "unknown")
    assert [t.name for t in await service.list_tokens(session)] == ["Shortcut"]


@pytest.mark.parametrize(("name", "days"), [("", 30), ("x", 0), ("x", service.MAX_TOKEN_DAYS + 1)])
async def test_token_validation(session: AsyncSession, name: str, days: int) -> None:
    with pytest.raises(InvalidInputError):
        await service.issue_token(session, API_SETTINGS, name, days)


async def test_system_info(session: AsyncSession) -> None:
    await _child(session, "Ada")

    info = await service.system_info(session, API_SETTINGS)

    assert info.database.startswith("postgresql")
    assert info.schema_revision is not None
    assert {"name": "core.person", "rows": 1} in [{"name": t.name, "rows": t.rows} for t in info.tables]
    assert info.backup_target is None
