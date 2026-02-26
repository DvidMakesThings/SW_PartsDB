"""api.routes_kicad - KiCad integration endpoints.

Two blueprints:
- api_bp: /api/v1/kicad/* - Programmatic search endpoints
- kicad_httplib_bp: /kicad/v1/* - KiCad HTTP Library protocol (no prefix)
"""

from flask import Blueprint, request, jsonify

from api import api_bp
from db import get_session
from services.kicad_service import KiCadService
import config

# Separate blueprint for KiCad HTTP Library - mounted at /kicad/v1 (no /api/v1 prefix)
# This gives cleaner URLs for KiCad configuration
kicad_httplib_bp = Blueprint("kicad_httplib", __name__, url_prefix="/kicad/v1")


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


@kicad_httplib_bp.route("/")
@kicad_httplib_bp.route("")
def kicad_http_root():
    """
    GET /kicad/v1/
    
    Root endpoint for KiCad HTTP Library validation.
    Returns API info that KiCad uses to verify the connection.
    """
    return jsonify({
        "api_version": "v1",
        "name": "DMTDB KiCad Library",
        "categories": "/categories.json",
        "parts": "/parts.json"
    })


def _get_display_name(part):
    """
    Get display name for a part in KiCad library browser.
    For passives (TT=01, FF=01/02/03 - Capacitors/Resistors/Inductors), use "value (MPN)".
    For all other parts, use MPN.
    """
    # Extract TT and FF from DMTUID (DMT-TTFFCCSSXXX)
    tt = part.dmtuid[4:6] if len(part.dmtuid) >= 6 else ""
    ff = part.dmtuid[6:8] if len(part.dmtuid) >= 8 else ""
    
    # Passive Components (TT=01, FF=01/02/03): Capacitors, Resistors, Inductors
    # Include MPN to differentiate parts with same value
    if tt == "01" and ff in ("01", "02", "03") and part.value:
        if part.mpn:
            return f"{part.value} ({part.mpn})"
        return part.value
    
    return part.mpn or part.dmtuid


@kicad_httplib_bp.route("/parts.json")
def kicad_http_parts():
    """
    GET /kicad/v1/parts.json
    
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


@kicad_httplib_bp.route("/categories.json")
def kicad_http_categories():
    """
    GET /kicad/v1/categories.json
    
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


@kicad_httplib_bp.route("/parts/category/<category_id>.json")
def kicad_http_parts_by_category(category_id):
    """
    GET /kicad/v1/parts/category/<category_id>.json
    
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


@kicad_httplib_bp.route("/parts/<part_id>.json")
def kicad_http_part_detail(part_id):
    """
    GET /kicad/v1/parts/<part_id>.json
    
    Returns detailed part info including KiCad fields.
    This is what KiCad reads when you add a part from the HTTP library.
    All values must be strings per KiCad spec.
    """
    from db.models import Part
    import json as json_module
    
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
        
        # Add distributor fields as DIST1, DIST2, etc.
        if part.distributor:
            try:
                distributors = json_module.loads(part.distributor)
                if isinstance(distributors, list):
                    for i, dist in enumerate(distributors, 1):
                        url = dist.get('url', '')
                        name = dist.get('name', '')
                        # Format: "DigiKey: https://..." or just URL if no name
                        if name and url:
                            value = f"{name}: {url}"
                        else:
                            value = url
                        fields["fields"][f"DIST{i}"] = {"value": value, "visible": "false"}
            except (json_module.JSONDecodeError, TypeError):
                # Legacy single URL format
                fields["fields"]["DIST1"] = {"value": str(part.distributor), "visible": "false"}
        
        # Add extra_json fields
        if part.extra_json:
            try:
                extra = json_module.loads(part.extra_json)
                for k, v in extra.items():
                    fields["fields"][k] = {"value": str(v), "visible": "false"}
            except (json_module.JSONDecodeError, TypeError):
                pass
        
        return jsonify(fields)
    finally:
        session.close()
