"""Backup files on local disk and in S3-compatible object storage."""

import gzip
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from family_hub.backup.dump import BackupData, json_default
from family_hub.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = logging.getLogger(__name__)

S3_CONFIG = Config(connect_timeout=5, read_timeout=60, retries={"max_attempts": 3})

BACKUP_FILE_PREFIX = "family_hub_backup_"
METADATA_FILENAME = ".backup_metadata.json"


def write_backup(data: BackupData, directory: Path) -> Path:
    """Write gzipped JSON to a timestamped file in `directory`."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{BACKUP_FILE_PREFIX}{datetime.now():%Y%m%d_%H%M%S}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as file:
        json.dump(data, file, default=json_default, indent=2, sort_keys=True)
    logger.info(f"Backup written: {path} ({path.stat().st_size / 1024:.1f} KB)")
    return path


def read_backup(path: Path) -> BackupData:
    """Read a gzipped JSON backup.

    Raises:
        RuntimeError: If the file is not a valid backup.
    """
    try:
        with gzip.open(path, "rt", encoding="utf-8") as file:
            return json.load(file)
    except (gzip.BadGzipFile, json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Invalid backup file {path}: {exc}") from exc


def load_metadata(directory: Path) -> dict[str, Any]:
    """Return metadata of the last upload, or an empty dict."""
    path = directory / METADATA_FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        if not isinstance(exc, FileNotFoundError):
            logger.warning(f"Ignoring unreadable metadata {path}: {exc}")
        return {}


def save_metadata(directory: Path, digest: str, uri: str) -> None:
    """Remember hash and location of the last upload."""
    metadata = {"last_backup_hash": digest, "last_backup_timestamp": datetime.now().isoformat(), "last_backup_uri": uri}
    (directory / METADATA_FILENAME).write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def s3_client(settings: Settings) -> "S3Client":
    """Create an S3 client from the settings (credentials fall back to the AWS defaults)."""
    secret = settings.aws_secret_access_key.get_secret_value() if settings.aws_secret_access_key else None
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=secret,
        config=S3_CONFIG,
    )


def s3_key(prefix: str, filename: str) -> str:
    """Join prefix and filename into an object key."""
    return f"{prefix.rstrip('/')}/{filename}" if prefix else filename


def ensure_bucket(client: "S3Client", bucket: str) -> None:
    """Create the bucket if it does not exist."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)
        logger.info(f"Created bucket {bucket}")


def upload(client: "S3Client", path: Path, bucket: str, prefix: str) -> str:
    """Upload a backup file and return its `s3://` URI."""
    key = s3_key(prefix, path.name)
    client.upload_file(str(path), bucket, key)
    uri = f"s3://{bucket}/{key}"
    logger.info(f"Uploaded {uri}")
    return uri


def download(client: "S3Client", bucket: str, key: str, path: Path) -> Path:
    """Download a backup object to `path`."""
    client.download_file(bucket, key, str(path))
    logger.info(f"Downloaded s3://{bucket}/{key}")
    return path


def list_backups(client: "S3Client", bucket: str, prefix: str) -> list[dict[str, Any]]:
    """List backup objects, newest first."""
    paginator = client.get_paginator("list_objects_v2")
    backups = [
        {"key": obj["Key"], "size": obj["Size"], "last_modified": obj["LastModified"]}
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
        for obj in page.get("Contents", [])
        if obj["Key"].endswith(".json.gz")
    ]
    return sorted(backups, key=lambda backup: backup["last_modified"], reverse=True)
