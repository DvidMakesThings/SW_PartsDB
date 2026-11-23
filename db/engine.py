"""
db.engine - Engine bootstrap and session factory.

Designed so the connection string can be swapped to Postgres
by changing config.DB_URL; no other code needs to change.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from db.migrations import ensure_schema

_engine = None
_SessionLocal: sessionmaker | None = None


def init_db(db_url: str) -> None:
    """Validate schema before opening application sessions."""
    global _engine, _SessionLocal

    _SessionLocal = None
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(db_url, echo=False, future=True)

    # Check before enabling WAL or applying any application schema changes.
    ensure_schema(_engine)
    # Discard the schema-check connection so connect listeners below apply
    # to every connection used by application sessions.
    _engine.dispose()

    if "sqlite" in db_url:
        @event.listens_for(_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _rec):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    # ensure_schema already applied versioned migrations for a fresh database.
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def get_session() -> Session:
    """Return a new session.  Caller is responsible for .close()."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised - call init_db() first")
    return _SessionLocal()
