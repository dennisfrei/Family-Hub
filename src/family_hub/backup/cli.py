"""Command line entry points `family-hub-backup` and `family-hub-restore`."""

import argparse
import asyncio
import logging
import sys
import tempfile
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from family_hub.backup import dump, service, storage
from family_hub.config import Settings, get_settings

logger = logging.getLogger("family_hub.backup")


def _setup_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


async def _export(url: str) -> dump.BackupData:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await dump.export_data(connection)
    finally:
        await engine.dispose()


async def _import(url: str, data: dump.BackupData) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await dump.import_data(connection, data)
    finally:
        await engine.dispose()


def run_backup(settings: Settings, *, to_s3: bool, keep_local: bool, force: bool) -> None:
    """Write a local backup and optionally upload it when the content changed."""
    data = asyncio.run(_export(settings.database_url))
    service.store(settings, data, upload=to_s3, force=force, keep_local=keep_local or not to_s3)


def run_restore(settings: Settings, *, file: Path | None, bucket: str | None, key: str | None) -> None:
    """Replace all data with a local or S3 backup.

    Raises:
        RuntimeError: If neither a file nor bucket and key are given.
    """
    if file is not None:
        asyncio.run(_import(settings.database_url, storage.read_backup(file)))
        return
    if not bucket or not key:
        raise RuntimeError("Give a backup file, or --s3 with --key (and --bucket or BACKUP_BUCKET)")
    with tempfile.TemporaryDirectory() as tmp:
        path = storage.download(storage.s3_client(settings), bucket, key, Path(tmp) / Path(key).name)
        asyncio.run(_import(settings.database_url, storage.read_backup(path)))


def _print_backups(settings: Settings, bucket: str) -> None:
    backups = storage.list_backups(storage.s3_client(settings), bucket, settings.backup_prefix)
    if not backups:
        print("No backups found")
    for backup in backups:
        print(f"{backup['key']:<70} {backup['size'] / 1024:>8.1f} KB  {backup['last_modified']:%Y-%m-%d %H:%M}")


def backup_main() -> int:
    """CLI: create a backup, optionally upload to S3."""
    settings = get_settings()
    _setup_logging(settings)
    parser = argparse.ArgumentParser(description="Back up the Family Hub database as gzipped JSON")
    parser.add_argument("--s3", action="store_true", help="Upload to S3 (skipped when unchanged)")
    parser.add_argument("--bucket", default=settings.backup_bucket, help="S3 bucket (default: BACKUP_BUCKET)")
    parser.add_argument("--keep-local", action="store_true", help="Keep the local file after uploading")
    parser.add_argument("--force", action="store_true", help="Upload even if the content is unchanged")
    parser.add_argument("--create-bucket", action="store_true", help="Create the bucket if missing")
    args = parser.parse_args()
    try:
        if args.s3 and args.create_bucket and args.bucket:
            storage.ensure_bucket(storage.s3_client(settings), args.bucket)
        run_backup(
            settings.model_copy(update={"backup_bucket": args.bucket}),
            to_s3=args.s3,
            keep_local=args.keep_local,
            force=args.force,
        )
    except Exception as exc:
        logger.error(f"Backup failed: {exc}")
        return 1
    logger.info("Backup completed")
    return 0


def restore_main() -> int:
    """CLI: restore from a local file or S3, or list S3 backups."""
    settings = get_settings()
    _setup_logging(settings)
    parser = argparse.ArgumentParser(description="Restore the Family Hub database; replaces all data")
    parser.add_argument("file", type=Path, nargs="?", help="Local backup file")
    parser.add_argument("--s3", action="store_true", help="Restore from S3")
    parser.add_argument("--bucket", default=settings.backup_bucket, help="S3 bucket (default: BACKUP_BUCKET)")
    parser.add_argument("--key", help="S3 object key")
    parser.add_argument("--list", action="store_true", help="List backups in S3 and exit")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()
    try:
        if args.list:
            if not args.bucket:
                raise RuntimeError("A bucket is required (--bucket or BACKUP_BUCKET)")
            _print_backups(settings, args.bucket)
            return 0
        if not args.yes and input("This DELETES all data and restores the backup. Type 'yes': ").lower() != "yes":
            print("Restore cancelled")
            return 0
        file = None if args.s3 else args.file
        run_restore(settings, file=file, bucket=args.bucket, key=args.key)
    except Exception as exc:
        logger.error(f"Restore failed: {exc}")
        return 1
    logger.info("Restore completed")
    return 0
