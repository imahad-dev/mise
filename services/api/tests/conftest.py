"""Pytest configuration — isolated test database, Alembic schema, per-test rollback."""

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession

import src.database as db_module
from src.config import settings
from src.database import get_db
from src.main import app

# Abort the whole session unless the configured database name ends in _test
if not settings.postgres_db.endswith("_test"):
    pytest.exit(
        f"SAFETY ABORT: Test database name {settings.postgres_db!r} must end in '_test'",
        returncode=1,
    )


def _get_maintenance_connection():
    """Connect to postgres maintenance database with autocommit for DDL."""
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        dbname="postgres",
        autocommit=True,
    )


def _ensure_test_database_exists() -> None:
    """Create <POSTGRES_DB>_test if missing via maintenance connection."""
    if not settings.postgres_db.endswith("_test"):
        pytest.exit(
            f"SAFETY ABORT: Refusing to create non-test database {settings.postgres_db!r}",
            returncode=1,
        )
    with _get_maintenance_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.postgres_db,))
        if not cur.fetchone():
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.postgres_db)))


def _drop_test_database() -> None:
    """Drop <POSTGRES_DB>_test via maintenance connection."""
    if not settings.postgres_db.endswith("_test"):
        raise RuntimeError(
            f"SAFETY ABORT: Refusing to drop database {settings.postgres_db!r} "
            "not ending in '_test'"
        )

    with _get_maintenance_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (settings.postgres_db,),
        )
        cur.execute(
            sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(settings.postgres_db))
        )


def _run_alembic_migrations() -> None:
    """Apply schema migrations using `alembic upgrade head` (not create_all)."""
    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    if not ini_path.exists():
        ini_path = Path("alembic.ini").resolve()

    alembic_cfg = Config(str(ini_path))
    alembic_dir = ini_path.parent / "alembic"
    alembic_cfg.set_main_option("script_location", str(alembic_dir))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url_sync.replace("%", "%%"))
    command.upgrade(alembic_cfg, "head")


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Ensure test database exists, run migrations, and provide app engine."""
    if not settings.postgres_db.endswith("_test"):
        pytest.exit(
            f"SAFETY ABORT: settings.postgres_db {settings.postgres_db!r} does not end in '_test'",
            returncode=1,
        )

    _ensure_test_database_exists()
    _run_alembic_migrations()

    yield db_module.engine

    await db_module.engine.dispose()

    # Drop test database at session end when DROP_TEST_DB is enabled (default off for step 8)
    if os.environ.get("DROP_TEST_DB", "0").lower() in ("1", "true", "yes"):
        _drop_test_database()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test database session with transaction rollback."""
    async with test_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        yield session
        await session.close()
        await trans.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Test HTTP client with DB session override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
