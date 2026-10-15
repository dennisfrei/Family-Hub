"""Import from a backup of the earlier fever app with an explicit series → person mapping."""

import argparse
import asyncio
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from family_hub import db
from family_hub.config import get_settings
from family_hub.core.importing import load_json, resolve_mapping
from family_hub.fever import service
from family_hub.fever.schemas import ImportedEpisode, ReadingWrite

logger = logging.getLogger("family_hub.fever.import")

SOURCE = "fever-plot"


def build_episodes(backup: dict[str, Any], mapping: dict[str, Any]) -> list[ImportedEpisode]:
    """Convert series and measurements of the old backup into episodes.

    Every series id must be in `mapping["fever"]["series"]`: a person id, or `null` to skip it on purpose.

    Raises:
        MappingError: If series are missing from the mapping.
    """
    tables = backup.get("tables", {})
    series_list = tables.get("measurement_series", [])
    series_mapping: dict[str, int | None] = mapping.get("fever", {}).get("series", {})

    series_mapping = resolve_mapping([str(s["id"]) for s in series_list], series_mapping, "Series")

    readings_by_series: dict[int, list[dict[str, Any]]] = {}
    for measurement in tables.get("measurements", []):
        readings_by_series.setdefault(measurement["series_id"], []).append(measurement)

    episodes = []
    for series in series_list:
        person_id = series_mapping[str(series["id"])]
        if person_id is None:
            logger.info(f"Skipping series {series['id']} ({series['name']}) as mapped to null")
            continue
        readings = [
            ReadingWrite(
                temperature=m["temperature"],
                measured_at=datetime.fromisoformat(m["measured_at"]),
                note=m.get("notes") or None,
            )
            for m in sorted(readings_by_series.get(series["id"], []), key=lambda m: m["measured_at"])
        ]
        created_at = datetime.fromisoformat(series["created_at"]) if series.get("created_at") else datetime.now()
        times = [r.measured_at for r in readings if r.measured_at is not None]
        episodes.append(
            ImportedEpisode(
                import_ref=f"{SOURCE}:{series['id']}",
                person_id=person_id,
                label=series["name"],
                description=series.get("description") or None,
                started_at=min(times, default=created_at),
                ended_at=max(times, default=created_at),
                readings=readings,
            )
        )
    return episodes


async def run_import(backup_path: Path, mapping_path: Path, *, dry_run: bool) -> list[str]:
    """Import the backup; returns the imported refs."""
    episodes = build_episodes(load_json(backup_path), load_json(mapping_path))
    counts: Counter[int] = Counter()
    for episode in episodes:
        counts[episode.person_id] += len(episode.readings)
    for person_id, count in sorted(counts.items()):
        logger.info(f"Person {person_id}: {sum(e.person_id == person_id for e in episodes)} episodes, {count} readings")

    db.init_engine(get_settings().database_url)
    try:
        async with db.session() as session:
            return await service.import_episodes(session, episodes, dry_run=dry_run)
    finally:
        await db.dispose_engine()


def import_main() -> int:
    """CLI: `family-hub-import-fever BACKUP --mapping MAPPING [--dry-run]`."""
    logging.basicConfig(level=get_settings().log_level.upper(), format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Import a fever-plot backup with an explicit person mapping")
    parser.add_argument("backup", type=Path, help="fever-plot backup (.json or .json.gz)")
    parser.add_argument("--mapping", type=Path, required=True, help="JSON mapping file")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report, write nothing")
    args = parser.parse_args()
    try:
        imported = asyncio.run(run_import(args.backup, args.mapping, dry_run=args.dry_run))
    except Exception as exc:
        logger.error(f"Import failed: {exc}")
        return 1
    verb = "Would import" if args.dry_run else "Imported"
    logger.info(f"{verb} {len(imported)} episodes")
    return 0


if __name__ == "__main__":
    sys.exit(import_main())
