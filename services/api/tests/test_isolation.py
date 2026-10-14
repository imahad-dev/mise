"""Test database isolation from process start."""

from src.config import settings
from src.database import engine


def test_app_engine_database_name_ends_in_test():
    """Assert app engine points at an isolated test database from process start."""
    assert settings.postgres_db.endswith("_test"), (
        f"settings.postgres_db {settings.postgres_db!r} must end in '_test'"
    )
    db_name = engine.url.database
    assert db_name is not None and db_name.endswith("_test"), (
        f"Database engine URL {engine.url} must point to a database ending in '_test', "
        f"got {db_name!r}"
    )
