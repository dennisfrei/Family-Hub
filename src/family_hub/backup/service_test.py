import gzip
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from family_hub.backup import service, storage
from family_hub.config import Settings

DATA = {"version": "1.0", "schema_revision": "0005", "exported_at": "now", "tables": {"core.person": []}}


async def test_create_backup_without_bucket_keeps_local_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "export_current", AsyncMock(return_value=DATA))

    result = await service.create_backup(Settings(backup_dir=tmp_path, _env_file=None))

    assert result.uri is None
    assert result.path is not None
    assert storage.read_backup(result.path)["tables"]["core.person"] == []


def test_to_bytes_matches_backup_format() -> None:
    data = {"version": "1.0", "schema_revision": None, "tables": {}}

    assert json.loads(gzip.decompress(service.to_bytes(data))) == data
