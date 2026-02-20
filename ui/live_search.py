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
from services.search_service import SearchService
from schema.loader import get_cc_ss_guidelines
from schema.templates import get_fields
import config


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


def _json_response(data) -> tuple:
    return _json.dumps(data), 200, {"Content-Type": "application/json"}
