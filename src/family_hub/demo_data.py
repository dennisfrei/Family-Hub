"""Demo data for UI tests."""

from datetime import UTC, date, datetime, timedelta

from family_hub import db
from family_hub.core import service as core_service
from family_hub.core.models import PersonKind, Sex
from family_hub.core.schemas import PersonWrite
from family_hub.fever import service as fever_service
from family_hub.fever.schemas import QuickReadingWrite
from family_hub.growth import service as growth_service
from family_hub.growth.models import MeasurementType
from family_hub.growth.schemas import MeasurementWrite
from family_hub.rhythm import service as rhythm_service
from family_hub.rhythm.models import RuleMode, TimeOfDay
from family_hub.rhythm.schemas import DutyWrite, RuleWrite
from family_hub.time_capsule import service as time_capsule_service
from family_hub.time_capsule.models import EntryType
from family_hub.time_capsule.schemas import EntryWrite


async def seed() -> None:
    """Add one child, one adult and a little data in every module to an empty database."""
    async with db.session() as session:
        child = await core_service.create_person(
            session, PersonWrite(name="Ada", kind=PersonKind.CHILD, birth_date=date(2022, 3, 15), sex=Sex.FEMALE)
        )
        adult = await core_service.create_person(session, PersonWrite(name="Alex", kind=PersonKind.ADULT))
        await fever_service.quick_add_reading(
            session,
            QuickReadingWrite(person_id=child.id, temperature=38.6, measured_at=datetime.now(UTC) - timedelta(hours=2)),
        )
        await growth_service.add_measurements(
            session,
            [
                MeasurementWrite(person_id=child.id, type=MeasurementType.LENGTH, value=v, measured_on=d)
                for v, d in ((52.0, date(2022, 3, 15)), (76.0, date(2023, 3, 20)), (97.0, date(2025, 3, 17)))
            ],
        )
        duty = await rhythm_service.create_duty(
            session, DutyWrite(name="Bedtime", time_of_day=TimeOfDay.EVENING, weekdays=list(range(7)))
        )
        await rhythm_service.set_rules(
            session, duty.id, [RuleWrite(weekday=d, mode=RuleMode.FIXED, person_id=adult.id) for d in range(7)]
        )
        await time_capsule_service.create_entry(
            session, EntryWrite(text="Der Mond ist angebissen", person_ids=[child.id], type=EntryType.SAYING)
        )
