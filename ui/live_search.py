"""
ui.live_search - Fast JSON endpoints consumed by the browser JS.

Separate from the REST API so UI-specific concerns (dropdown formatting,
template field hints) stay out of the public API.
"""

from __future__ import annotations

import json as _json

from flask import request

from ui import ui_bp
from db import get_session
from db.models import Part, PartField
from services.search_service import SearchService
from schema.loader import get_cc_ss_guidelines
from schema.templates import get_fields
import config
from sqlalchemy import func, distinct


@ui_bp.route("/ui-api/search")
def ui_search():
    """Quick search for the live-search dropdown."""
    q = request.args.get("q", "").strip()
    if not q:
        return _json_response([])

    session = get_session()
    try:
        parts = SearchService.quick_search(
            session, q, limit=config.SEARCH_DROPDOWN_LIMIT,
        )
        results = [
            {
                "dmtuid": p.dmtuid,
                "mpn": p.mpn,
                "value": p.value,
                "manufacturer": p.manufacturer,
                "description": (p.description or "")[:80],
                "quantity": p.quantity,
                "has_datasheet": bool(p.datasheet),
            }
            for p in parts
        ]
        return _json_response(results)
    finally:
        session.close()


@ui_bp.route("/ui-api/template_fields")
def ui_template_fields():
    """Return template fields + CC/SS guidelines for a TT+FF pair."""
    tt = request.args.get("tt", "").zfill(2)
    ff = request.args.get("ff", "").zfill(2)
    return _json_response({
        "fields": get_fields(tt, ff),
        "guidelines": get_cc_ss_guidelines(tt, ff),
    })


@ui_bp.route("/ui-api/facets")
def ui_facets():
    """
    Return distinct values for each property in the current category.
    DigiKey-style parametric filter data.
    """
    tt = request.args.get("tt", "").strip()
    ff = request.args.get("ff", "").strip()
    cc = request.args.get("cc", "").strip()
    ss = request.args.get("ss", "").strip()

    if not tt:
        return _json_response({"facets": {}})

    session = get_session()
    try:
        # Build base query with category filters
        query = session.query(Part)
        if tt:
            query = query.filter(Part.tt == tt)
        if ff:
            query = query.filter(Part.ff == ff)
        if cc:
            query = query.filter(Part.cc == cc)
        if ss:
            query = query.filter(Part.ss == ss)

        # Get all matching part IDs
        part_ids = [p.dmtuid for p in query.all()]
        if not part_ids:
            return _json_response({"facets": {}, "total": 0})

        # Get core field facets from Part table
        facets = {}

        # Value facet
        value_counts = (
            session.query(Part.value, func.count(Part.dmtuid))
            .filter(Part.dmtuid.in_(part_ids))
            .filter(Part.value != None, Part.value != "")
            .group_by(Part.value)
            .order_by(func.count(Part.dmtuid).desc())
            .limit(50)
            .all()
        )
        if value_counts:
            facets["Value"] = [{"value": v, "count": c} for v, c in value_counts if v]

        # Manufacturer facet
        mfr_counts = (
            session.query(Part.manufacturer, func.count(Part.dmtuid))
            .filter(Part.dmtuid.in_(part_ids))
            .filter(Part.manufacturer != None, Part.manufacturer != "")
            .group_by(Part.manufacturer)
            .order_by(func.count(Part.dmtuid).desc())
            .limit(50)
            .all()
        )
        if mfr_counts:
            facets["Manufacturer"] = [{"value": v, "count": c} for v, c in mfr_counts if v]

        # Get EAV field facets from PartField table
        eav_facets = (
            session.query(
                PartField.field_name,
                PartField.field_value,
                func.count(PartField.dmtuid)
            )
            .filter(PartField.dmtuid.in_(part_ids))
            .filter(PartField.field_value != None, PartField.field_value != "")
            .group_by(PartField.field_name, PartField.field_value)
            .order_by(PartField.field_name, func.count(PartField.dmtuid).desc())
            .all()
        )

        for field_name, field_value, count in eav_facets:
            if field_name not in facets:
                facets[field_name] = []
            if len(facets[field_name]) < 50:  # Limit values per facet
                facets[field_name].append({"value": field_value, "count": count})

        return _json_response({"facets": facets, "total": len(part_ids)})
    finally:
        session.close()


def _json_response(data) -> tuple:
    return _json.dumps(data), 200, {"Content-Type": "application/json"}
