"""
Async SQLAlchemy engine.

Neon / Postgres when DATABASE_URL is set (production and staging). In local
development without DATABASE_URL, a SQLite file (api/executive_admin.db) keeps
records persistent so every workflow can be exercised end to end.
"""

from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    """Declarative base for Executive Admin tables."""


def _asyncpg_url(url: str) -> tuple[str, dict]:
    """Normalise a Neon/Postgres URL for asyncpg: driver prefix, and sslmode → ssl connect arg."""
    parts = urlsplit(url)
    scheme = "postgresql+asyncpg"
    query = dict(parse_qsl(parts.query))
    connect_args: dict = {}
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)  # not understood by asyncpg
    if sslmode in {"require", "verify-ca", "verify-full"} or parts.hostname and parts.hostname.endswith(".neon.tech"):
        connect_args["ssl"] = True
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)), connect_args


_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def configure_engine(url: str | None = None) -> AsyncEngine:
    """Create (or replace) the engine. Tests call this with their own URL."""
    global _engine, _sessions
    url = url or get_settings().effective_database_url
    if is_sqlite(url):
        engine = create_async_engine(url, connect_args={"timeout": 30})

        @event.listens_for(engine.sync_engine, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite enforces foreign keys only when asked
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
            # The sqlite driver opens transactions lazily, so a SAVEPOINT could become the outermost
            # transaction and its RELEASE would commit on its own. Hand transaction control to
            # SQLAlchemy so savepoints nest inside a real BEGIN (all-or-nothing imports rely on it).
            dbapi_conn.isolation_level = None

        @event.listens_for(engine.sync_engine, "begin")
        def _begin(conn):
            # IMMEDIATE takes the write lock up front, so concurrent requests queue (busy timeout) instead of
            # failing with "database is locked" when a read transaction later tries to write.
            conn.exec_driver_sql("BEGIN IMMEDIATE")
    else:
        dsn, connect_args = _asyncpg_url(url)
        # Neon's pooler handles pooling; keep the app-side pool small and pre-pinged.
        engine = create_async_engine(dsn, connect_args=connect_args, pool_size=5, max_overflow=5, pool_pre_ping=True)
    _engine = engine
    _sessions = async_sessionmaker(engine, expire_on_commit=False)
    return engine


def get_engine() -> AsyncEngine:
    return _engine or configure_engine()


def session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessions is not None
    return _sessions


async def create_schema() -> None:
    from . import models, models_ops, models_ops2, models_ops3  # noqa: F401  (register tables)

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(sync_conn) -> None:
    """create_all never alters existing tables, so add new nullable/defaulted columns at startup.

    Additive changes only (new tables and new nullable or defaulted columns). Renames, drops and type
    changes need a hand-written migration (Alembic is the planned follow-up before such a change)."""
    from sqlalchemy import inspect
    from sqlalchemy.schema import CreateColumn

    insp = inspect(sync_conn)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            ddl = CreateColumn(col).compile(dialect=sync_conn.dialect)
            sync_conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN {ddl}')


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session
