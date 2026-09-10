"""Startup schema guard — refuse to serve against a database that is not at this
image's migration head.

Migrations are a deploy step (the ``migrate`` / ``cellar_migrate`` one-shot job runs
``alembic upgrade head``); the app never migrates itself. What the app owns is the
precondition: on a Swarm deploy the API can come up before that job has finished,
and without this check the first symptom is a burst of "column does not exist"
errors. Instead we compare ``alembic_version`` with the newest migration script
shipped in this image, wait a bounded time for the migrate job in production, and
otherwise fail the boot with a message that names both revisions and the fix.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import cellar

logger = structlog.get_logger(__name__)

# <repo>/backend/alembic in dev, /app/alembic in the image (both hold alembic/ next
# to the ``src`` tree the package is imported from).
_ALEMBIC_DIR = Path(cellar.__file__).resolve().parents[2] / "alembic"


class SchemaOutOfDate(RuntimeError):
    """The database's alembic revision does not match this image's head."""


def _scripts() -> ScriptDirectory:
    return ScriptDirectory(str(_ALEMBIC_DIR))


def expected_head() -> str:
    """The migration head shipped in this image."""
    head = _scripts().get_current_head()
    if head is None:
        raise RuntimeError(f"No migration scripts found under {_ALEMBIC_DIR}")
    return head


async def database_revision(session_factory: async_sessionmaker[AsyncSession]) -> str | None:
    """Current ``alembic_version``; None when no migration has ever been applied."""
    async with session_factory() as session:
        try:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
        except ProgrammingError:
            return None  # table absent: nothing applied yet
        return result.scalar_one_or_none()


def _explain(db: str | None, head: str) -> str:
    known = {r.revision for r in _scripts().walk_revisions()}
    if db is None:
        state = "no migrations have been applied"
    elif db in known:
        state = "a migration is pending"
    else:
        state = "the database is ahead of this image (revision unknown to it)"
    fix = (
        "Deploy the image whose migrations produced that revision."
        if db is not None and db not in known
        else "Run `alembic upgrade head` (ned: the cellar_migrate service; "
        "docker-compose.prod.yml: the migrate service) and restart."
    )
    return (
        "Database schema is not at this image's migration head — refusing to start.\n"
        f"  database revision : {db or '(none)'}\n"
        f"  image expects     : {head}\n"
        f"  {state}. {fix}"
    )


async def ensure_schema_current(
    session_factory: async_sessionmaker[AsyncSession] | None,
    *,
    wait_seconds: float | None = None,
    poll_seconds: float = 2.0,
    read_revision: Callable[[], Awaitable[str | None]] | None = None,
) -> str:
    """Return the head revision once the database is at it; raise SchemaOutOfDate otherwise.

    ``wait_seconds`` defaults to ``SCHEMA_WAIT_SECONDS`` (90 s in production, where the
    migrate job usually lands moments later; 0 elsewhere, so a developer sees the
    message at once). Called by the API lifespan and the Temporal worker.
    """
    if read_revision is None:
        if session_factory is None:
            raise ValueError("session_factory is required without read_revision")
        factory = session_factory

        async def read_revision() -> str | None:
            return await database_revision(factory)

    head = expected_head()
    if wait_seconds is None:
        production = os.environ.get("APP_ENV") == "production"
        wait_seconds = float(os.environ.get("SCHEMA_WAIT_SECONDS", "90" if production else "0"))
    deadline = time.monotonic() + wait_seconds

    while True:
        db = await read_revision()
        if db == head:
            logger.info("schema.current", revision=head)
            return head
        if time.monotonic() >= deadline:
            break
        logger.warning(
            "schema.migration_pending",
            database_revision=db,
            expected_head=head,
            retry_in_seconds=poll_seconds,
        )
        await asyncio.sleep(poll_seconds)

    message = _explain(db, head)
    logger.error("schema.out_of_date", database_revision=db, expected_head=head)
    raise SchemaOutOfDate(message)
