"""Shared helpers for importing data from the earlier standalone apps."""

import gzip
import json
from pathlib import Path
from typing import Any


class MappingError(ValueError):
    """Raised when the mapping file does not cover the backup."""


def load_json(path: Path) -> dict[str, Any]:
    """Read plain or gzipped JSON."""
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def resolve_mapping(source_ids: list[str], mapping: dict[str, int | None], what: str) -> dict[str, int | None]:
    """Return the mapping for every source id; `None` means skipped on purpose.

    Raises:
        MappingError: If ids are missing from the mapping.
    """
    unmapped = sorted(set(source_ids) - set(mapping))
    if unmapped:
        raise MappingError(f"{what} without mapping: {', '.join(unmapped)}")
    return {source_id: mapping[source_id] for source_id in source_ids}
