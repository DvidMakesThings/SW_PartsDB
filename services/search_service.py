"""
services.search_service - Text search and filtered listing.

Builds SQLAlchemy queries with optional filters and full-text-like
ILIKE matching across indexed columns.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, Query

from db.models import Part, PartField


class SearchService:

    @staticmethod
    def search(
        session: Session,
        *,
        q: str = "",
        tt: str = "",
        ff: str = "",
        cc: str = "",
        ss: str = "",
        props: dict = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Part], int]:
        """
        Search parts.  Returns (parts_list, total_count).
        """
        query = session.query(Part)
        query = SearchService._apply_filters(query, q=q, tt=tt, ff=ff, cc=cc, ss=ss, props=props)
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
    def _apply_filters(query: Query, *, q: str, tt: str, ff: str, cc: str, ss: str, props: dict = None) -> Query:
        if tt:
            query = query.filter(Part.tt == tt)
        if ff:
            query = query.filter(Part.ff == ff)
        if cc:
            query = query.filter(Part.cc == cc)
        if ss:
            query = query.filter(Part.ss == ss)
        if q:
            query = SearchService._apply_text_filter(query, q)
        if props:
            query = SearchService._apply_prop_filters(query, props)
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

    @staticmethod
    def _apply_prop_filters(query: Query, props: dict) -> Query:
        """
        Filter by property values.
        
        Props format: {field_name: [value1, value2, ...]} for multi-select (OR within field)
        Or legacy: {field_name: "search_value"} for ILIKE matching
        
        For direct columns (MPN, Value, etc.), filter on Part directly.
        For EAV fields, filter via PartField subqueries.
        """
        from sqlalchemy import or_
        
        direct_cols = {
            "MPN": Part.mpn,
            "Value": Part.value,
            "Manufacturer": Part.manufacturer,
            "Location": Part.location,
            "Description": Part.description,
        }

        for field_name, search_values in props.items():
            if not search_values:
                continue

            # Handle both list (multi-select) and string (legacy ILIKE)
            if isinstance(search_values, list):
                # Multi-select: exact match, OR between values
                if field_name in direct_cols:
                    query = query.filter(direct_cols[field_name].in_(search_values))
                else:
                    # EAV field
                    subq = query.session.query(PartField.dmtuid).filter(
                        PartField.field_name == field_name,
                        PartField.field_value.in_(search_values)
                    ).subquery()
                    query = query.filter(Part.dmtuid.in_(subq))
            else:
                # Legacy: ILIKE search
                like = f"%{search_values}%"
                if field_name in direct_cols:
                    query = query.filter(direct_cols[field_name].ilike(like))
                else:
                    subq = query.session.query(PartField.dmtuid).filter(
                        PartField.field_name == field_name,
                        PartField.field_value.ilike(like)
                    ).subquery()
                    query = query.filter(Part.dmtuid.in_(subq))

        return query
