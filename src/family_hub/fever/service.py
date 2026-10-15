"""Business logic for episodes and readings; the only place touching fever tables."""

import csv
import io
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from family_hub.config import get_settings
from family_hub.core import service as core_service
from family_hub.errors import InvalidInputError
from family_hub.fever.models import Episode, Reading
from family_hub.fever.schemas import (
    MAX_TEMPERATURE,
    MIN_TEMPERATURE,
    EpisodeDetail,
    EpisodeRead,
    EpisodeUpdate,
    EpisodeWrite,
    ImportedEpisode,
    QuickReadingWrite,
    ReadingRead,
    ReadingWrite,
)
from family_hub.fever.thresholds import Thresholds, age_group, thresholds_for

logger = logging.getLogger(__name__)


class NotFoundError(LookupError):
    """Raised when an episode or reading does not exist."""


def local_timezone() -> ZoneInfo:
    """Return the configured display timezone."""
    return ZoneInfo(get_settings().timezone)


def to_utc(value: datetime) -> datetime:
    """Convert to UTC; naive values are interpreted in the configured timezone."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=local_timezone())
    return value.astimezone(UTC)


def _validate_temperature(temperature: float) -> None:
    if not MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE:
        raise InvalidInputError("error.temperature_range", low=f"{MIN_TEMPERATURE:.0f}", high=f"{MAX_TEMPERATURE:.0f}")


def _validate_label(label: str) -> str:
    label = label.strip()
    if not label:
        raise InvalidInputError("error.label_required")
    return label


async def _thresholds(session: AsyncSession, episode: Episode) -> Thresholds:
    person = await core_service.get_person(session, episode.person_id)
    started_on = episode.started_at.astimezone(local_timezone()).date()
    return thresholds_for(age_group(person.birth_date, started_on))


def _reading_read(reading: Reading, thresholds: Thresholds) -> ReadingRead:
    return ReadingRead(
        id=reading.id,
        episode_id=reading.episode_id,
        temperature=reading.temperature,
        measured_at=reading.measured_at,
        level=thresholds.level(reading.temperature),
        method=reading.method,
        note=reading.note,
    )


def _sorted_readings(episode: Episode) -> list[Reading]:
    return sorted(episode.readings, key=lambda reading: reading.measured_at)


async def _episode_read(session: AsyncSession, episode: Episode) -> EpisodeRead:
    thresholds = await _thresholds(session, episode)
    readings = _sorted_readings(episode)
    return EpisodeRead(
        id=episode.id,
        person_id=episode.person_id,
        label=episode.label,
        description=episode.description,
        started_at=episode.started_at,
        ended_at=episode.ended_at if episode.ended_at else None,
        reading_count=len(readings),
        thresholds=thresholds,
        max_temperature=max((r.temperature for r in readings), default=None),
        last_reading=_reading_read(readings[-1], thresholds) if readings else None,
    )


async def _load_episode(session: AsyncSession, episode_id: int) -> Episode:
    episode = await session.get(Episode, episode_id)
    if episode is None:
        raise NotFoundError(f"Episode {episode_id} not found")
    return episode


async def list_episodes(
    session: AsyncSession, *, person_id: int | None = None, open_only: bool = False
) -> list[EpisodeRead]:
    """List episodes, newest first."""
    query = select(Episode).order_by(Episode.started_at.desc())
    if person_id is not None:
        query = query.where(Episode.person_id == person_id)
    if open_only:
        query = query.where(Episode.ended_at.is_(None))
    return [await _episode_read(session, episode) for episode in await session.scalars(query)]


async def get_episode(session: AsyncSession, episode_id: int) -> EpisodeDetail:
    """Return an episode with all readings.

    Raises:
        NotFoundError: If the episode does not exist.
    """
    episode = await _load_episode(session, episode_id)
    summary = await _episode_read(session, episode)
    return EpisodeDetail(
        episode=summary, readings=[_reading_read(r, summary.thresholds) for r in _sorted_readings(episode)]
    )


async def export_all(session: AsyncSession) -> list[EpisodeDetail]:
    """Return every episode with its readings."""
    return [await get_episode(session, episode.id) for episode in await list_episodes(session)]


async def create_episode(
    session: AsyncSession, data: EpisodeWrite, *, started_at: datetime | None = None
) -> EpisodeRead:
    """Start a new episode for a person.

    Raises:
        core_service.PersonNotFoundError: If the person does not exist.
        ValueError: If the label is empty.
    """
    await core_service.get_person(session, data.person_id)
    episode = Episode(
        person_id=data.person_id,
        label=_validate_label(data.label),
        description=data.description or None,
        started_at=to_utc(started_at or datetime.now(UTC)),
        readings=[],
    )
    session.add(episode)
    await session.commit()
    logger.info(f"Created episode {episode.id} for person {data.person_id}")
    return await _episode_read(session, episode)


async def update_episode(session: AsyncSession, episode_id: int, data: EpisodeUpdate) -> EpisodeRead:
    """Change label and description.

    Raises:
        NotFoundError: If the episode does not exist.
        ValueError: If the label is empty.
    """
    episode = await _load_episode(session, episode_id)
    episode.label = _validate_label(data.label)
    episode.description = data.description or None
    await session.commit()
    return await _episode_read(session, episode)


async def set_closed(session: AsyncSession, episode_id: int, *, closed: bool) -> EpisodeRead:
    """Close an episode (now) or reopen it.

    Raises:
        NotFoundError: If the episode does not exist.
    """
    episode = await _load_episode(session, episode_id)
    episode.ended_at = datetime.now(UTC) if closed else None
    await session.commit()
    logger.info(f"Episode {episode_id} closed={closed}")
    return await _episode_read(session, episode)


async def delete_episode(session: AsyncSession, episode_id: int) -> None:
    """Delete an episode with all readings.

    Raises:
        NotFoundError: If the episode does not exist.
    """
    await session.delete(await _load_episode(session, episode_id))
    await session.commit()
    logger.info(f"Deleted episode {episode_id}")


async def add_reading(session: AsyncSession, episode_id: int, data: ReadingWrite) -> ReadingRead:
    """Add a reading to an episode.

    Raises:
        NotFoundError: If the episode does not exist.
        ValueError: If the temperature is out of range.
    """
    _validate_temperature(data.temperature)
    episode = await _load_episode(session, episode_id)
    reading = Reading(
        temperature=round(data.temperature, 1),
        measured_at=to_utc(data.measured_at or datetime.now(UTC)),
        method=data.method,
        note=(data.note or "").strip() or None,
    )
    episode.readings.append(reading)
    await session.commit()
    logger.info(f"Added reading {reading.id} to episode {episode_id}")
    return _reading_read(reading, await _thresholds(session, episode))


async def quick_add_reading(session: AsyncSession, data: QuickReadingWrite) -> ReadingRead:
    """Add a reading to the person's newest open episode, starting one if there is none.

    Raises:
        core_service.PersonNotFoundError: If the person does not exist.
        ValueError: If the temperature is out of range.
    """
    _validate_temperature(data.temperature)
    open_episodes = await list_episodes(session, person_id=data.person_id, open_only=True)
    if open_episodes:
        episode_id = open_episodes[0].id
    else:
        measured_at = to_utc(data.measured_at or datetime.now(UTC))
        label = f"Fieber {measured_at.astimezone(local_timezone()):%d.%m.%Y}"
        episode_id = (
            await create_episode(session, EpisodeWrite(person_id=data.person_id, label=label), started_at=measured_at)
        ).id
    reading = ReadingWrite(
        temperature=data.temperature, measured_at=data.measured_at, method=data.method, note=data.note
    )
    return await add_reading(session, episode_id, reading)


async def delete_reading(session: AsyncSession, reading_id: int) -> None:
    """Delete a reading.

    Raises:
        NotFoundError: If the reading does not exist.
    """
    reading = await session.get(Reading, reading_id)
    if reading is None:
        raise NotFoundError(f"Reading {reading_id} not found")
    await session.delete(reading)
    await session.commit()
    logger.info(f"Deleted reading {reading_id}")


def readings_csv(detail: EpisodeDetail) -> str:
    """Render the readings of an episode as CSV in local time."""
    tz = local_timezone()
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["measured_at", "temperature", "level", "method", "note"])
    for reading in detail.readings:
        writer.writerow(
            [
                reading.measured_at.astimezone(tz).strftime("%Y-%m-%d %H:%M"),
                f"{reading.temperature:.1f}",
                reading.level.value,
                reading.method.value if reading.method else "",
                reading.note or "",
            ]
        )
    return buffer.getvalue()


async def import_episodes(session: AsyncSession, episodes: list[ImportedEpisode], *, dry_run: bool) -> list[str]:
    """Insert imported episodes in one transaction, skipping refs that already exist.

    Returns:
        The refs that were (or, in a dry run, would be) imported.

    Raises:
        core_service.PersonNotFoundError: If a mapped person does not exist.
        ValueError: If a temperature is out of range.
    """
    existing = set(await session.scalars(select(Episode.import_ref).where(Episode.import_ref.is_not(None))))
    imported = []
    for item in episodes:
        await core_service.get_person(session, item.person_id)
        if item.import_ref in existing:
            logger.info(f"Skipping {item.import_ref}, already imported")
            continue
        for reading in item.readings:
            _validate_temperature(reading.temperature)
        session.add(
            Episode(
                person_id=item.person_id,
                label=_validate_label(item.label),
                description=item.description,
                started_at=to_utc(item.started_at),
                ended_at=to_utc(item.ended_at),
                import_ref=item.import_ref,
                readings=[
                    Reading(
                        temperature=round(r.temperature, 1),
                        measured_at=to_utc(r.measured_at or item.started_at),
                        method=r.method,
                        note=r.note,
                    )
                    for r in item.readings
                ],
            )
        )
        imported.append(item.import_ref)
    if dry_run:
        await session.rollback()
    else:
        await session.commit()
    return imported


async def count_person_data(session: AsyncSession, person_id: int) -> dict[str, int]:
    """Episodes and readings of one person."""
    episodes = select(Episode.id).where(Episode.person_id == person_id)
    return {
        "fever.data.episodes": await session.scalar(select(func.count()).select_from(episodes.subquery())) or 0,
        "fever.data.readings": await session.scalar(
            select(func.count()).select_from(Reading).where(Reading.episode_id.in_(episodes))
        )
        or 0,
    }


async def delete_person_data(session: AsyncSession, person_id: int) -> None:
    """Delete all episodes and readings of one person; the caller commits."""
    episodes = select(Episode.id).where(Episode.person_id == person_id)
    await session.execute(delete(Reading).where(Reading.episode_id.in_(episodes)))
    await session.execute(delete(Episode).where(Episode.person_id == person_id))
