"""Database configuration and session management."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    """WAL lets readers proceed while a run's writes are in flight, instead
    of the default rollback-journal mode where every write locks the whole
    file against readers and other writers. busy_timeout makes a writer
    that does hit contention retry instead of failing immediately with
    "database is locked"."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for a request-scoped database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def _sync_settings_columns(conn: AsyncConnection) -> None:
    """Add any Settings model columns missing from an existing settings table.

    create_all() only creates tables that don't exist yet -- it never alters
    an existing one, so an upgrader's settings.db (predating a newly added
    column) would otherwise 500 on the first query that references it. Diff
    the live table against the model and ALTER TABLE ADD COLUMN for the
    difference, still without pulling in Alembic for a one-table schema.

    Reads the table from Base.metadata rather than importing the Settings
    model directly -- app.models.settings already imports Base from this
    module, so importing it back here would be circular.
    """
    result = await conn.execute(text("PRAGMA table_info(settings)"))
    existing_columns = {row[1] for row in result.fetchall()}

    for column in Base.metadata.tables["settings"].columns:
        if column.name in existing_columns:
            continue

        default = column.default.arg if column.default is not None else None
        if isinstance(default, bool):
            default_sql = "1" if default else "0"
        elif isinstance(default, int | float):
            default_sql = str(default)
        elif isinstance(default, str):
            default_sql = "'" + default.replace("'", "''") + "'"
        else:
            default_sql = "NULL"

        sql_type = column.type.compile(dialect=conn.dialect)
        await conn.execute(
            text(
                f"ALTER TABLE settings ADD COLUMN {column.name} "
                f"{sql_type} DEFAULT {default_sql}"
            )
        )
        logger.info("Added missing settings column: %s", column.name)


async def init_db() -> None:
    """Create tables if they don't exist, then bring settings up to date.

    No Alembic: the schema is small (three tables) with no migration
    history beyond the settings column sync above.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _sync_settings_columns(conn)
