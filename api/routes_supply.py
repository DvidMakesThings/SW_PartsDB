"""
api.routes_supply - Supply-chain / pricing endpoints.

GET  /api/v1/parts/<dmtuid>/pricing          → cached pricing data
POST /api/v1/parts/<dmtuid>/pricing/refresh   → fetch fresh data from sources
POST /api/v1/supply/refresh                   → bulk-refresh all parts with JLCPCB codes
"""

from flask import jsonify, request

from api import api_bp
from db import get_session
from services.supply_chain_service import get_pricing, refresh_part, refresh_all


@api_bp.route("/parts/<dmtuid>/pricing")
def part_pricing(dmtuid: str):
    """Return cached pricing rows for this part."""
    session = get_session()
    try:
        rows = get_pricing(session, dmtuid)
        return jsonify(rows)
    finally:
        session.close()


@api_bp.route("/parts/<dmtuid>/pricing/refresh", methods=["POST"])
def part_pricing_refresh(dmtuid: str):
    """Fetch fresh pricing from all sources for this part."""
    session = get_session()
    try:
        results = refresh_part(session, dmtuid)
        session.commit()
        return jsonify(results)
    finally:
        session.close()


@api_bp.route("/supply/refresh", methods=["POST"])
def supply_refresh_all():
    """Bulk-refresh pricing for all parts that have distributor codes."""
    session = get_session()
    try:
        limit = request.args.get("limit", 0, type=int)
        summary = refresh_all(session, limit=limit)
        return jsonify(summary)
    finally:
        session.close()
