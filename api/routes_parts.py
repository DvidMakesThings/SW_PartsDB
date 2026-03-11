"""
api.routes_parts - /api/v1/parts CRUD endpoints.
"""

import json
from flask import request, jsonify

from api import api_bp
from db import get_session
from services.parts_service import PartsService
from services.search_service import SearchService
import config


@api_bp.route("/parts")
def list_parts():
    """
    GET /api/v1/parts?q=&tt=&ff=&cc=&ss=&props=&limit=100&offset=0

    Search / list parts.  Supports text query, domain/family/class/style filter,
    property filters (JSON), and pagination.
    """
    q      = request.args.get("q", "").strip()
    tt     = request.args.get("tt", "").strip()
    ff     = request.args.get("ff", "").strip()
    cc     = request.args.get("cc", "").strip()
    ss     = request.args.get("ss", "").strip()
    props_str = request.args.get("props", "").strip()
    sort_by = request.args.get("sort", "dmtuid").strip()
    sort_order = request.args.get("order", "asc").strip()
    limit  = min(int(request.args.get("limit", config.API_DEFAULT_LIMIT)),
                 config.API_MAX_LIMIT)
    offset = int(request.args.get("offset", 0))

    # Validate sort params
    if sort_by not in SearchService.SORTABLE_COLUMNS:
        sort_by = "dmtuid"
    if sort_order not in ("asc", "desc"):
        sort_order = "asc"

    # Parse property filters from JSON
    props = {}
    if props_str:
        try:
            props = json.loads(props_str)
        except json.JSONDecodeError:
            props = {}

    session = get_session()
    try:
        parts, total = SearchService.search(
            session, q=q, tt=tt, ff=ff, cc=cc, ss=ss, props=props,
            sort_by=sort_by, sort_order=sort_order,
            limit=limit, offset=offset,
        )
        return jsonify({
            "total": total,
            "offset": offset,
            "limit": limit,
            "parts": [p.to_dict() for p in parts],
        })
    finally:
        session.close()


@api_bp.route("/parts/<dmtuid>")
def get_part(dmtuid: str):
    """GET /api/v1/parts/{DMTUID}"""
    session = get_session()
    try:
        part = PartsService.get(session, dmtuid)
        if not part:
            return jsonify({"error": "not found"}), 404
        return jsonify(part.to_dict())
    finally:
        session.close()


@api_bp.route("/parts", methods=["POST"])
def create_part():
    """
    POST /api/v1/parts

    JSON body: {tt, ff, cc, ss, …fields}.  XXX is auto-assigned.
    """
    data = request.get_json(force=True)
    session = get_session()
    try:
        part = PartsService.create(session, data)
        session.commit()
        return jsonify(part.to_dict()), 201
    except Exception as exc:
        session.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        session.close()


@api_bp.route("/parts/<dmtuid>", methods=["PUT"])
def update_part(dmtuid: str):
    """PUT /api/v1/parts/{DMTUID}  (JSON body with fields to update)"""
    data = request.get_json(force=True)
    session = get_session()
    try:
        part = PartsService.get(session, dmtuid)
        if not part:
            return jsonify({"error": "not found"}), 404
        PartsService.update(session, part, data)
        session.commit()
        session.refresh(part)
        return jsonify(part.to_dict())
    except Exception as exc:
        session.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        session.close()


@api_bp.route("/parts/<dmtuid>", methods=["DELETE"])
def delete_part(dmtuid: str):
    """DELETE /api/v1/parts/{DMTUID}"""
    session = get_session()
    try:
        part = PartsService.get(session, dmtuid)
        if not part:
            return jsonify({"error": "not found"}), 404
        PartsService.delete(session, part)
        session.commit()
        return jsonify({"deleted": dmtuid.upper()})
    except Exception as exc:
        session.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        session.close()


@api_bp.route("/parts/suggestions")
def part_suggestions():
    """
    GET /api/v1/parts/suggestions

    Returns distinct values for distributor names and locations,
    useful for auto-complete / datalist dropdowns in the add/edit form.
    """
    import json as _json
    from sqlalchemy import distinct
    from db.models import Part

    session = get_session()
    try:
        # Distinct non-empty locations
        locations = sorted({
            row[0].strip()
            for row in session.query(distinct(Part.location)).all()
            if row[0] and row[0].strip()
        })

        # Distinct non-empty distributor names (stored as JSON arrays)
        dist_names: set[str] = set()
        for (raw,) in session.query(distinct(Part.distributor)).all():
            if not raw or not raw.strip():
                continue
            try:
                entries = _json.loads(raw)
                if isinstance(entries, list):
                    for entry in entries:
                        name = (entry.get("name") or "").strip()
                        if name:
                            dist_names.add(name)
            except (_json.JSONDecodeError, TypeError):
                pass

        return jsonify({
            "locations": locations,
            "distributor_names": sorted(dist_names),
        })
    finally:
        session.close()
