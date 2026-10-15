"""Create backups from the running app and the CLI alike."""

import asyncio
import gzip
import json
import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from family_hub import db
from family_hub.backup import dump, storage
from family_hub.config import Settings

logger = logging.getLogger(__name__)


class BackupResult(BaseModel):
    """Where a backup ended up; `unchanged` means the upload was skipped."""

    model_config = ConfigDict(frozen=True)

    path: Path | None
    uri: str | None
    unchanged: bool = False


def store(settings: Settings, data: dump.BackupData, *, upload: bool, force: bool, keep_local: bool) -> BackupResult:
    """Write a local backup and upload it when S3 is wanted and the content changed.

    Raises:
        RuntimeError: If an upload is requested without a bucket.
    """
    bucket = settings.backup_bucket
    if upload and not bucket:
        raise RuntimeError("A bucket is required for S3 (--bucket or BACKUP_BUCKET)")
    path = storage.write_backup(data, settings.backup_dir)
    if not upload or bucket is None:
        return BackupResult(path=path, uri=None)
    digest = dump.content_hash(data)
    if not force and storage.load_metadata(settings.backup_dir).get("last_backup_hash") == digest:
        logger.info("Content unchanged since last upload, skipping")
        path.unlink()
        return BackupResult(path=None, uri=None, unchanged=True)
    uri = storage.upload(storage.s3_client(settings), path, bucket, settings.backup_prefix)
    storage.save_metadata(settings.backup_dir, digest, uri)
    if keep_local:
        return BackupResult(path=path, uri=uri)
    path.unlink()
    return BackupResult(path=None, uri=uri)


async def export_current() -> dump.BackupData:
    """Read all data through the app's engine."""
    async with db.session() as session:
        return await dump.export_data(await session.connection())


async def create_backup(settings: Settings, *, force: bool = False) -> BackupResult:
    """Back up the running app's data; uploads to S3 when a bucket is configured."""
    data = await export_current()
    upload = settings.backup_bucket is not None
    return await asyncio.to_thread(store, settings, data, upload=upload, force=force, keep_local=not upload)


def to_bytes(data: dump.BackupData) -> bytes:
    """Gzipped JSON in the same format as backup files."""
    payload = json.dumps(data, default=dump.json_default, indent=2, sort_keys=True)
    return gzip.compress(payload.encode("utf-8"))
