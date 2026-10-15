from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.core import service
from family_hub.core.models import PersonKind, Sex
from family_hub.core.schemas import PersonWrite

CHILD = PersonWrite(name="Ada", kind=PersonKind.CHILD, birth_date=date(2022, 3, 15), sex=Sex.FEMALE)
ADULT = PersonWrite(name="Alex", kind=PersonKind.ADULT)


@pytest.mark.parametrize(
    ("birth_date", "on", "expected"),
    [
        (date(2022, 3, 15), date(2022, 3, 15), 0),
        (date(2022, 3, 15), date(2022, 4, 14), 0),
        (date(2022, 3, 15), date(2022, 4, 15), 1),
        (date(2022, 3, 15), date(2025, 7, 20), 40),
        (date(2022, 3, 15), date(2022, 1, 1), 0),
    ],
)
def test_age_in_months(birth_date: date, on: date, expected: int) -> None:
    assert service.age_in_months(birth_date, on) == expected


async def test_create_child_and_list(session: AsyncSession) -> None:
    created = await service.create_person(session, CHILD)
    await service.create_person(session, ADULT)

    children = await service.list_children(session, on=date(2025, 7, 20))

    assert [c.id for c in children] == [created.id]
    assert children[0].age_months == 40
    assert len(await service.list_people(session)) == 2


async def test_child_requires_birth_date_and_sex(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="birth date"):
        await service.create_person(session, PersonWrite(name="Bo", kind=PersonKind.CHILD))


async def test_empty_name_rejected(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="Name"):
        await service.create_person(session, PersonWrite(name="  ", kind=PersonKind.ADULT))


async def test_update_child_to_adult_drops_profile(session: AsyncSession) -> None:
    created = await service.create_person(session, CHILD)

    updated = await service.update_person(session, created.id, PersonWrite(name="Ada", kind=PersonKind.ADULT))

    assert updated.kind is PersonKind.ADULT
    assert updated.birth_date is None
    assert await service.list_children(session) == []


async def test_deactivated_person_hidden(session: AsyncSession) -> None:
    created = await service.create_person(session, CHILD)

    await service.set_active(session, created.id, active=False)

    assert await service.list_children(session) == []
    assert await service.list_people(session) == []
    assert len(await service.list_people(session, include_inactive=True)) == 1


async def test_unknown_person(session: AsyncSession) -> None:
    with pytest.raises(service.PersonNotFoundError):
        await service.get_person(session, 999)
