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
        
        # Determine reference designator based on part type (DMTUID format: DMT-TTFFCCSSXXX)
        # TT = Domain, FF = Family
        ref = "IC"  # Default for ICs
        if part.dmtuid and len(part.dmtuid) >= 8:
            tt = part.dmtuid[4:6]
            ff = part.dmtuid[6:8]
            
            # 01 - Passive Components
            if tt == "01":
                if ff == "01":
                    ref = "C"   # Capacitors
                elif ff == "02":
                    ref = "R"   # Resistors
                elif ff == "03":
                    ref = "L"   # Inductors
                elif ff == "04":
                    ref = "FL"  # EMI and Filters
                else:
                    ref = "R"   # Default for passives
            
            # 02 - Discrete Semiconductors
            elif tt == "02":
                if ff == "01":
                    ref = "D"   # Diodes
                elif ff == "02":
                    ref = "Q"   # BJTs
                elif ff == "03":
                    ref = "Q"   # MOSFETs
                elif ff == "04":
                    ref = "Q"   # IGBTs
                elif ff == "05":
                    ref = "Q"   # Thyristors
                elif ff == "06":
                    ref = "D"   # Bridge Rectifiers
                else:
                    ref = "Q"   # Default for discretes
            
            # 03 - Integrated Circuits
            elif tt == "03":
                ref = "IC"
            
            # 04 - RF and Wireless
            elif tt == "04":
                if ff == "04":
                    ref = "ANT"  # Antennas
                else:
                    ref = "IC"   # RF ICs and modules
            
            # 05 - Optoelectronics and Displays
            elif tt == "05":
                if ff in ("01", "02", "03", "04"):
                    ref = "LED"  # LEDs and related
                elif ff == "05":
                    ref = "LD"   # Laser Diodes
                elif ff in ("07", "08"):
                    ref = "DS"   # Displays
                else:
                    ref = "LED"
            
            # 06 - Sensors and Transducers
            elif tt == "06":
                ref = "SEN"  # Sensors
            
            # 07 - Power Supplies and Magnetics
            elif tt == "07":
                if ff == "06":
                    ref = "T"   # Transformers
                elif ff == "07":
                    ref = "L"   # Magnetics/inductors
                else:
                    ref = "PS"  # Power supplies
            
            # 08 - Circuit Protection
            elif tt == "08":
                if ff == "01":
                    ref = "F"   # Fuses
                elif ff == "02":
                    ref = "CB"  # Circuit Breakers
                elif ff in ("03", "04"):
                    ref = "TVS" # TVS/MOV
                elif ff == "05":
                    ref = "PTC" # PTC/Resettable
                else:
                    ref = "F"
            
            # 09 - Connectors and Interconnects
            elif tt == "09":
                ref = "J"  # Connectors
            
            # 10 - Cables and Wiring
            elif tt == "10":
                ref = "W"  # Wires/Cables
            
            # 11 - Switches and HMI
            elif tt == "11":
                ref = "SW"  # Switches
            
            # 12 - Relays and Contactors
            elif tt == "12":
                ref = "K"  # Relays
            
            # 13 - Mechanical and Hardware
            elif tt == "13":
                ref = "H"  # Hardware
            
            # 14 - Thermal Management
            elif tt == "14":
                ref = "HS"  # Heat sinks/thermal
            
            # 15 - Enclosures and Racks
            elif tt == "15":
                ref = "ENC"  # Enclosures
            
            # 16 - Industrial Automation
            elif tt == "16":
                ref = "PLC"  # PLCs and industrial
            
            # 17 - Test and Measurement
            elif tt == "17":
                ref = "TM"  # Test and measurement
            
            # 18 - Prototyping and Fabrication
            elif tt == "18":
                ref = "PCB"  # Prototyping
            
            # 19 - Development and Programming
            elif tt == "19":
                ref = "BRD"  # Development boards
            
            # 20+ - Computing, Networking, etc.
            elif tt in ("20", "21", "22", "23", "24", "25", "26", "27", "28"):
                ref = "MOD"  # Modules
            
            # 29 - Project PCBs and Assemblies
            elif tt == "29":
                ref = "BRD"  # Boards/Assemblies
        
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
        
        # Add LCSC_PART if available
        if part.kicad_libref:
            fields["fields"]["LCSC_PART"] = {"value": str(part.kicad_libref), "visible": "false"}
        
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
