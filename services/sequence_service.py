"""
services.sequence_service - XXX sequence allocation.

Isolated so both the API "create part" flow and the import engine
can share the same logic.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import Part


def next_xxx(session: Session, tt: str, ff: str, cc: str, ss: str) -> str:
    """
    Return the next available XXX (zero-padded 3 digits) for the
    given TTFFCCSS group.  Raises ValueError on overflow (>999).
    """
    db_max = session.query(func.max(Part.xxx)).filter(
        Part.tt == tt, Part.ff == ff,
        Part.cc == cc, Part.ss == ss,
    ).scalar()
    nxt = (int(db_max) if db_max else 0) + 1
    if nxt > 999:
        raise ValueError(f"XXX overflow for group {tt}{ff}{cc}{ss}")
    return f"{nxt:03d}"
