"""
services.search_service - Text search and filtered listing.

Builds SQLAlchemy queries with optional filters and full-text-like
ILIKE matching across indexed columns.
"""

from __future__ import annotations
import re

from sqlalchemy.orm import Session, Query

from db.models import Part, PartField


# Metric prefix multipliers for smart value sorting
VALUE_PREFIXES = {
    'p': 1e-12,   # pico
    'n': 1e-9,    # nano
    'u': 1e-6,    # micro
    'µ': 1e-6,    # micro (unicode)
    'm': 1e-3,    # milli
    'R': 1,       # ohm (for resistors like 10R)
    'K': 1e3,     # kilo
    'k': 1e3,     # kilo (lowercase)
    'M': 1e6,     # mega
    'G': 1e9,     # giga
}


def parse_value_sortkey(value_str: str) -> float:
    """
    Parse a component value string and return a numeric sort key.
    Handles: 100pF, 10nF, 4.7uF, 10R, 4K7, 1M, 10K, "3.3R 1%", "10R 5% 2W", etc.
    """
    if not value_str:
        return float('inf')  # Empty values sort last
    
    value_str = value_str.strip()
    
    # Strip trailing specs like "1%", "5% 2W", voltage ratings, etc.
    # Keep only the value part (number + prefix + optional decimal)
    value_str = re.split(r'\s+', value_str)[0]  # Take only first word
    
    # Try pattern: number + prefix + optional decimal (e.g., "4K7" = 4.7K)
    # Handles: 100nF, 4.7uF, 10R, 4K7, 1.8K, 0.1R, etc.
    match = re.match(r'^([\d.]+)([pnuµmRKkMG])(\d*)', value_str)
    if match:
        num_part = match.group(1)
        prefix = match.group(2)
        decimal_part = match.group(3)
        
        try:
            num = float(num_part)
            # Handle "4K7" format -> 4.7K
            if decimal_part:
                num = float(f"{num_part}.{decimal_part}")
            
            # Get multiplier - handle case sensitivity
            # R = ohm (1), K/k = kilo, M = mega, m = milli
            if prefix in ('K', 'k'):
                multiplier = 1e3
            elif prefix == 'M':
                multiplier = 1e6
            elif prefix == 'm':
                multiplier = 1e-3
            elif prefix == 'R':
                multiplier = 1  # Ohm
            else:
                multiplier = VALUE_PREFIXES.get(prefix, 1)
            
            return num * multiplier
        except ValueError:
            pass
    
    # Try simple number (no prefix)
    try:
        num_match = re.match(r'^([\d.]+)', value_str)
        if num_match:
            return float(num_match.group(1))
    except ValueError:
        pass
    
    return float('inf')


class SearchService:

    # Sortable columns mapping
    SORTABLE_COLUMNS = {
        "dmtuid": Part.dmtuid,
        "mpn": Part.mpn,
        "value": Part.value,
        "quantity": Part.quantity,
        "location": Part.location,
        "manufacturer": Part.manufacturer,
        "description": Part.description,
        "created_at": Part.created_at,
    }

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
        sort_by: str = "dmtuid",
        sort_order: str = "asc",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Part], int]:
        """
        Search parts.  Returns (parts_list, total_count).
        """
        query = session.query(Part)
        query = SearchService._apply_filters(query, q=q, tt=tt, ff=ff, cc=cc, ss=ss, props=props)
        total = query.count()
        
        # Special handling for "value" column - needs smart metric prefix sorting
        if sort_by == "value":
            # Fetch all matching parts and sort in Python
            all_parts = query.all()
            reverse = (sort_order == "desc")
            all_parts.sort(key=lambda p: parse_value_sortkey(p.value or ""), reverse=reverse)
            # Apply pagination
            parts = all_parts[offset:offset + limit]
        else:
            # Standard SQL sorting for other columns
            sort_col = SearchService.SORTABLE_COLUMNS.get(sort_by, Part.dmtuid)
            if sort_order == "desc":
                query = query.order_by(sort_col.desc())
            else:
                query = query.order_by(sort_col.asc())
            parts = query.offset(offset).limit(limit).all()
        
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
                    col = direct_cols[field_name]
                    # Special handling for "(Empty)" values
                    if "(Empty)" in search_values:
                        other_values = [v for v in search_values if v != "(Empty)"]
                        if other_values:
                            query = query.filter(or_(
                                col.in_(other_values),
                                col == None,
                                col == ""
                            ))
                        else:
                            query = query.filter(or_(col == None, col == ""))
                    else:
                        query = query.filter(col.in_(search_values))
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
