import pytest

from family_hub.config import Settings


@pytest.mark.parametrize(
    "url",
    ["postgresql://u:p@db:5432/x", "postgres://u:p@db:5432/x", "postgresql+asyncpg://u:p@db:5432/x"],
)
def test_database_url_uses_asyncpg(url: str) -> None:
    assert Settings(_env_file=None, database_url=url).database_url == "postgresql+asyncpg://u:p@db:5432/x"
