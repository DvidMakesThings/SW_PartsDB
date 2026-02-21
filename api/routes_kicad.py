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


# ============================================================================
# KiCad HTTP Library API (for Preferences > Manage Symbol/Footprint Libraries)
# ============================================================================
# To configure in KiCad:
# 1. Go to Preferences > Manage Symbol Libraries
# 2. Add a new library with type "KiCad HTTP Library"
# 3. Set the URL to: http://localhost:5000/kicad/v1
# ============================================================================

from schema.loader import domain_name, family_name, list_domain_codes, list_family_codes


@api_bp.route("/kicad/v1")
@api_bp.route("/kicad/v1/")
def kicad_http_root():
    """
    GET /api/v1/kicad/v1/
    
    Root endpoint for KiCad HTTP Library validation.
    KiCad expects a dict with "categories" and "parts" keys.
    """
    return jsonify({
        "categories": "",
        "parts": ""
    })


def _get_display_name(part):
    """
    Get display name for a part in KiCad library browser.
    For passives (TT=01, FF=01/02/03 - Capacitors/Resistors/Inductors), use value.
    For all other parts, use MPN.
    """
    # Extract TT and FF from DMTUID (DMT-TTFFCCSSXXX)
    tt = part.dmtuid[4:6] if len(part.dmtuid) >= 6 else ""
    ff = part.dmtuid[6:8] if len(part.dmtuid) >= 8 else ""
    
    # Passive Components (TT=01, FF=01/02/03): Capacitors, Resistors, Inductors
    if tt == "01" and ff in ("01", "02", "03") and part.value:
        return part.value
    
    return part.mpn or part.dmtuid


@api_bp.route("/kicad/v1/parts.json")
def kicad_http_parts():
    """
    GET /api/v1/kicad/v1/parts.json
    
    Returns list of ALL parts with KiCad symbols defined.
    This is what KiCad queries to populate the library browser.
    """
    from db.models import Part
    
    session = get_session()
    try:
        parts = session.query(Part).filter(Part.kicad_symbol != "").filter(Part.kicad_symbol != None).all()
        
        result = []
        for p in parts:
            result.append({
                "id": p.dmtuid,
                "name": _get_display_name(p)
            })
        
        return jsonify(result)
    finally:
        session.close()


@api_bp.route("/kicad/v1/categories.json")
def kicad_http_categories():
    """
    GET /api/v1/kicad/v1/categories.json
    
    Returns list of categories (Domain > Family hierarchy).
    Only includes categories that actually have parts with symbols.
    """
    from db.models import Part
    from sqlalchemy import func
    
    session = get_session()
    try:
        # Query distinct TT/FF combinations that have parts with symbols
        # DMTUID format: DMT-TTFFCCSSXXX, so TT is chars 4-6, FF is chars 6-8
        parts_with_symbols = session.query(
            func.substr(Part.dmtuid, 5, 2).label('tt'),
            func.substr(Part.dmtuid, 7, 2).label('ff')
        ).filter(
            Part.kicad_symbol != "",
            Part.kicad_symbol != None
        ).distinct().all()
        
        categories = []
        seen = set()
        
        for row in parts_with_symbols:
            tt, ff = row.tt, row.ff
            key = f"{tt}{ff}"
            if key not in seen:
                seen.add(key)
                dom = domain_name(tt)
                fam = family_name(tt, ff)
                categories.append({
                    "id": key,
                    "name": f"{dom} / {fam}"
                })
        
        # Sort by name for consistent ordering
        categories.sort(key=lambda x: x["name"])
        
        return jsonify(categories)
    finally:
        session.close()


@api_bp.route("/kicad/v1/parts/category/<category_id>.json")
def kicad_http_parts_by_category(category_id):
    """
    GET /api/v1/kicad/v1/parts/category/<category_id>.json
    
    Returns parts in a category. category_id is TTFF (e.g., "0102" for Passives/Resistors).
    """
    from db.models import Part
    
    if len(category_id) != 4:
        return jsonify({"error": "Invalid category ID"}), 400
    
    tt = category_id[:2]
    ff = category_id[2:4]
    
    session = get_session()
    try:
        # Find parts where DMTUID matches pattern DMT-TTFF*
        pattern = f"DMT-{tt}{ff}%"
        parts = session.query(Part).filter(Part.dmtuid.like(pattern)).all()
        
        result = []
        for p in parts:
            # Only include parts that have a symbol defined
            if p.kicad_symbol:
                result.append({
                    "id": p.dmtuid,
                    "name": _get_display_name(p)
                })
        
        return jsonify(result)
    finally:
        session.close()


@api_bp.route("/kicad/v1/parts/<part_id>.json")
def kicad_http_part_detail(part_id):
    """
    GET /api/v1/kicad/v1/parts/<part_id>.json
    
    Returns detailed part info including KiCad fields.
    This is what KiCad reads when you add a part from the HTTP library.
    All values must be strings per KiCad spec.
    """
    from db.models import Part
    
    session = get_session()
    try:
        part = session.query(Part).filter(Part.dmtuid == part_id).first()
        if not part:
            return jsonify({"error": "Part not found"}), 404
        
        # Determine reference designator based on part type
        # TT=01 is Passives: 01=Capacitors(C), 02=Resistors(R), 03=Inductors(L)
        ref = "U"  # Default
        if part.dmtuid and len(part.dmtuid) >= 8:
            tt = part.dmtuid[4:6]
            ff = part.dmtuid[6:8]
            if tt == "01":
                if ff == "01":
                    ref = "C"
                elif ff == "02":
                    ref = "R"
                elif ff == "03":
                    ref = "L"
        
        # Build KiCad fields - all values must be strings
        # Field names should be lowercase per KiCad spec
        fields = {
            "id": str(part.dmtuid),
            "name": _get_display_name(part),
            "symbolIdStr": str(part.kicad_symbol or ""),
            "fields": {
                "reference": {"value": ref},
                "value": {"value": str(part.value or part.mpn or "")},
                "footprint": {"value": str(part.kicad_footprint or ""), "visible": "false"},
                "datasheet": {"value": str(part.datasheet or ""), "visible": "false"},
                "description": {"value": str(part.description or ""), "visible": "false"},
                "DMTUID": {"value": str(part.dmtuid), "visible": "false"},
                "MPN": {"value": str(part.mpn or ""), "visible": "false"},
                "Manufacturer": {"value": str(part.manufacturer or ""), "visible": "false"},
            }
        }
        
        # Add LCSC if available
        if part.kicad_libref:
            fields["fields"]["LCSC"] = {"value": str(part.kicad_libref), "visible": "false"}
        
        # Add extra_json fields (DIST1, etc.)
        if part.extra_json:
            import json
            try:
                extra = json.loads(part.extra_json)
                for k, v in extra.items():
                    fields["fields"][k] = {"value": str(v), "visible": "false"}
            except (json.JSONDecodeError, TypeError):
                pass
        
        return jsonify(fields)
    finally:
        session.close()
