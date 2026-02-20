"""
api.routes_kicad - /api/v1/kicad/* endpoints.

Lightweight, KiCad-friendly responses that include symbol/footprint
fields alongside part identifiers.
"""

from flask import request, jsonify

from api import api_bp
from db import get_session
from services.kicad_service import KiCadService
import config


@api_bp.route("/kicad/search")
def kicad_search():
    """
    GET /api/v1/kicad/search?q=&mpn=&value=&manufacturer=

    Multi-criteria search returning KiCad-friendly records.
    """
    session = get_session()
    try:
        results = KiCadService.search(
            session,
            q=request.args.get("q", "").strip(),
            mpn=request.args.get("mpn", "").strip(),
            value=request.args.get("value", "").strip(),
            manufacturer=request.args.get("manufacturer", "").strip(),
            limit=config.KICAD_SEARCH_LIMIT,
        )
        return jsonify(results)
    finally:
        session.close()


@api_bp.route("/kicad/instock")
def kicad_instock():
    """
    GET /api/v1/kicad/instock

    List all parts with Quantity > 0 (for BOM cross-checking).
    """
    session = get_session()
    try:
        return jsonify(KiCadService.in_stock(session))
    finally:
        session.close()
