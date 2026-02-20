"""
db.engine - Engine bootstrap and session factory.

Designed so the connection string can be swapped to Postgres
by changing config.DB_URL; no other code needs to change.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base

_engine = None
_SessionLocal: sessionmaker | None = None


def init_db(db_url: str) -> None:
    """Create the engine, apply SQLite pragmas, and emit CREATE TABLE."""
    global _engine, _SessionLocal

    _engine = create_engine(db_url, echo=False, future=True)

    if "sqlite" in db_url:
        @event.listens_for(_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _rec):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def get_session() -> Session:
    """Return a new session.  Caller is responsible for .close()."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised - call init_db() first")
    return _SessionLocal()
