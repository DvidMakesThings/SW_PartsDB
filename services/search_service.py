"""
services.search_service - Text search and filtered listing.

Builds SQLAlchemy queries with optional filters and full-text-like
ILIKE matching across indexed columns.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, Query

from db.models import Part


class SearchService:

    @staticmethod
    def search(
        session: Session,
        *,
        q: str = "",
        tt: str = "",
        ff: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Part], int]:
        """
        Search parts.  Returns (parts_list, total_count).
        """
        query = session.query(Part)
        query = SearchService._apply_filters(query, q=q, tt=tt, ff=ff)
        total = query.count()
        parts = query.order_by(Part.dmtuid).offset(offset).limit(limit).all()
        return parts, total

    @staticmethod
    def quick_search(session: Session, q: str, limit: int = 20) -> list[Part]:
        """
        Fast search for the live-search dropdown.
        Returns a small list, no total count.
        """
        if not q:
            return []
        query = session.query(Part)
        query = SearchService._apply_text_filter(query, q)
        return query.order_by(Part.dmtuid).limit(limit).all()

    # ── Internal ───────────────────────────────────────────────────────

    @staticmethod
    def _apply_filters(query: Query, *, q: str, tt: str, ff: str) -> Query:
        if tt:
            query = query.filter(Part.tt == tt)
        if ff:
            query = query.filter(Part.ff == ff)
        if q:
            query = SearchService._apply_text_filter(query, q)
        return query

    @staticmethod
    def _apply_text_filter(query: Query, q: str) -> Query:
        like = f"%{q}%"
        return query.filter(
            Part.dmtuid.ilike(like)
            | Part.mpn.ilike(like)
            | Part.value.ilike(like)
            | Part.description.ilike(like)
            | Part.manufacturer.ilike(like)
            | Part.location.ilike(like)
        )
