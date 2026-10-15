"""Command line entry point `family-hub-token`."""

import argparse
import asyncio
import sys

from family_hub import db
from family_hub.admin import service
from family_hub.admin.schemas import IssuedToken
from family_hub.config import Settings, get_settings


async def _issue(settings: Settings, name: str, days: int) -> IssuedToken:
    db.init_engine(settings.database_url)
    try:
        async with db.session() as session:
            return await service.issue_token(session, settings, name, days)
    finally:
        await db.dispose_engine()


def token_main() -> None:
    """CLI: issue an API token (`family-hub-token <client> [--days N]`); tokens are revoked in the admin area."""
    parser = argparse.ArgumentParser(description="Issue a Family Hub API token")
    parser.add_argument("client", help="Name of the client, e.g. 'ios-shortcut'")
    parser.add_argument("--days", type=int, default=365, help="Validity in days (default: 365)")
    args = parser.parse_args()
    issued = asyncio.run(_issue(get_settings(), args.client, args.days))
    print(f"Token id: {issued.info.token_id}", file=sys.stderr)
    print(issued.token)
