"""Import from a backup of the earlier growth app with an explicit profile → person mapping."""

import argparse
import asyncio
import logging
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from family_hub import db
from family_hub.config import get_settings
from family_hub.core import service as core_service
from family_hub.core.importing import MappingError, load_json, resolve_mapping
from family_hub.core.models import Sex
from family_hub.growth import service
from family_hub.growth.models import MeasurementType
from family_hub.growth.schemas import ImportedMeasurement, MeasurementWrite

logger = logging.getLogger("family_hub.growth.import")

SOURCE = "kiggs-plot"
TYPES = {"weight": MeasurementType.WEIGHT, "length": MeasurementType.LENGTH}
UNIT_FACTORS = {"kg": 1.0, "g": 0.001, "cm": 1.0, "m": 100.0}
SEXES = {"female": Sex.FEMALE, "male": Sex.MALE}


def build_measurements(backup: dict[str, Any], mapping: dict[str, Any]) -> list[ImportedMeasurement]:
    """Convert profiles and measurements of the old backup.

    Every profile id must be in `mapping["growth"]["profiles"]`: a person id, or `null` to skip it on purpose.

    Raises:
        MappingError: If profiles are missing from the mapping.
        ValueError: If a measurement has an unknown type or unit.
    """
    tables = backup.get("tables", {})
    profiles = {str(p["id"]): p for p in tables.get("profile", [])}
    profile_mapping = resolve_mapping(list(profiles), mapping.get("growth", {}).get("profiles", {}), "Profiles")

    items = []
    for row in tables.get("measurement", []):
        person_id = profile_mapping.get(str(row["profile_id"]))
        if person_id is None:
            continue
        if row["type"] not in TYPES or row["unit"] not in UNIT_FACTORS:
            raise ValueError(f"Unknown type or unit in measurement {row['id']}: {row['type']} {row['unit']}")
        items.append(
            ImportedMeasurement(
                import_ref=f"{SOURCE}:{row['id']}",
                measurement=MeasurementWrite(
                    person_id=person_id,
                    type=TYPES[row["type"]],
                    value=round(float(row["value"]) * UNIT_FACTORS[row["unit"]], 3),
                    measured_on=date.fromisoformat(row["date"]),
                    official=row.get("official") is not False,
                ),
            )
        )
    return items


def profile_mismatches(backup: dict[str, Any], mapping: dict[str, Any], people: dict[int, Any]) -> list[str]:
    """Compare birth date and sex of each mapped profile with the hub's child profile."""
    problems = []
    for profile in backup.get("tables", {}).get("profile", []):
        person_id = mapping.get("growth", {}).get("profiles", {}).get(str(profile["id"]))
        if person_id is None:
            continue
        person = people.get(person_id)
        if person is None:
            problems.append(f"Profile {profile['name']}: person {person_id} does not exist")
            continue
        if profile.get("birthday") and person.birth_date != date.fromisoformat(profile["birthday"]):
            problems.append(f"Profile {profile['name']}: birth date differs from {person.name}")
        if profile.get("gender") in SEXES and person.sex != SEXES[profile["gender"]]:
            problems.append(f"Profile {profile['name']}: sex differs from {person.name}")
    return problems


async def run_import(backup_path: Path, mapping_path: Path, *, dry_run: bool) -> list[str]:
    """Import the backup; returns the imported refs.

    Raises:
        MappingError: If the mapping is incomplete or does not match the children.
    """
    backup, mapping = load_json(backup_path), load_json(mapping_path)
    items = build_measurements(backup, mapping)
    counts: Counter[int] = Counter(item.measurement.person_id for item in items)
    for person_id, count in sorted(counts.items()):
        logger.info(f"Person {person_id}: {count} measurements")

    db.init_engine(get_settings().database_url)
    try:
        async with db.session() as session:
            people = {p.id: p for p in await core_service.list_people(session, include_inactive=True)}
            problems = profile_mismatches(backup, mapping, people)
            if problems:
                raise MappingError("; ".join(problems))
            return await service.import_measurements(session, items, dry_run=dry_run)
    finally:
        await db.dispose_engine()


def import_main() -> int:
    """CLI: `family-hub-import-growth BACKUP --mapping MAPPING [--dry-run]`."""
    logging.basicConfig(level=get_settings().log_level.upper(), format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Import a kiggs-plot backup with an explicit person mapping")
    parser.add_argument("backup", type=Path, help="kiggs-plot backup (.json or .json.gz)")
    parser.add_argument("--mapping", type=Path, required=True, help="JSON mapping file")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report, write nothing")
    args = parser.parse_args()
    try:
        imported = asyncio.run(run_import(args.backup, args.mapping, dry_run=args.dry_run))
    except Exception as exc:
        logger.error(f"Import failed: {exc}")
        return 1
    verb = "Would import" if args.dry_run else "Imported"
    logger.info(f"{verb} {len(imported)} measurements")
    return 0


if __name__ == "__main__":
    sys.exit(import_main())
