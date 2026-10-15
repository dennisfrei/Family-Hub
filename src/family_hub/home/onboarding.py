"""First steps after installing: what is set up already, derived from the data."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.config import Settings
from family_hub.core import service as core_service
from family_hub.core.models import PersonKind
from family_hub.rhythm import service as rhythm_service


class StepKey(StrEnum):
    """Setup steps in display order."""

    ADULTS = "adults"
    CHILDREN = "children"
    RHYTHM = "rhythm"
    REFERENCE = "reference"
    BACKUP = "backup"


OPTIONAL_STEPS = frozenset({StepKey.REFERENCE, StepKey.BACKUP})


class SetupState(BaseModel):
    """Counts the steps are derived from."""

    model_config = ConfigDict(frozen=True)

    adults: int
    children: int
    duties_with_rules: int
    reference_files: int
    backup_bucket: bool


class SetupStep(BaseModel):
    """One step and whether it is done."""

    model_config = ConfigDict(frozen=True)

    key: StepKey
    done: bool

    @property
    def optional(self) -> bool:
        """Optional steps are server settings and never block completion."""
        return self.key in OPTIONAL_STEPS


def setup_steps(state: SetupState) -> list[SetupStep]:
    """All steps with their state."""
    done = {
        StepKey.ADULTS: state.adults > 0,
        StepKey.CHILDREN: state.children > 0,
        StepKey.RHYTHM: state.duties_with_rules > 0,
        StepKey.REFERENCE: state.reference_files > 0,
        StepKey.BACKUP: state.backup_bucket,
    }
    return [SetupStep(key=key, done=done[key]) for key in StepKey]


def is_complete(steps: list[SetupStep]) -> bool:
    """Whether all required steps are done."""
    return all(step.done for step in steps if not step.optional)


async def load_state(session: AsyncSession, settings: Settings) -> SetupState:
    """Read the counts from the database and the settings."""
    people = await core_service.list_people(session)
    duties = await rhythm_service.list_duties(session)
    reference_dir = settings.growth_reference_dir
    reference_files = len(list(reference_dir.glob("*.csv"))) if reference_dir and reference_dir.is_dir() else 0
    return SetupState(
        adults=sum(person.kind is PersonKind.ADULT for person in people),
        children=sum(person.kind is PersonKind.CHILD for person in people),
        duties_with_rules=sum(bool(duty.rules) for duty in duties),
        reference_files=reference_files,
        backup_bucket=settings.backup_bucket is not None,
    )
