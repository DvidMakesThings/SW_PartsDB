"""
ui.routes_labels - Label printing functionality.

Generate SVG labels for ESD bags and reels with DMTUID barcodes.
"""

from flask import render_template, request, Response, jsonify

from ui import ui_bp
from db import get_session
from db.models import Part
from services.barcode_service import generate_barcode_svg_centered
from schema.loader import get_domains


# Label size definitions: (width_mm, height_mm, name)
LABEL_SIZES = {
    "50x30": (50, 30, "50 × 30 mm (Small)"),
    "75x50": (75, 50, "75 × 50 mm (Medium)"),
    "100x50": (100, 50, "100 × 50 mm (Large)"),
    "4x6": (101.6, 152.4, "4\" × 6\" (Shipping)"),  # 4" x 6" in mm
}


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if too long."""
    if not text:
        return ""
    return text[:max_len-1] + "…" if len(text) > max_len else text


def _get_package(part: Part) -> str:
    """Get package value from EAV fields or extra_json."""
    import json
    # First check EAV fields
    for f in part.fields:
        if f.field_name in ("Package / Case", "Package"):
            return f.field_value or ""
    # Fallback to extra_json
    if part.extra_json:
        try:
            extra = json.loads(part.extra_json)
            return extra.get("Package / Case", "") or extra.get("Package", "")
        except:
            pass
    return ""


def _generate_label_50x30(part: Part, for_print: bool = False) -> str:
    """
    Generate 50x30mm label SVG.
    Compact label for small ESD bags.
    """
    # Scale: viewBox 500x300 = 50x30mm (10 units per mm)
    barcode = generate_barcode_svg_centered(part.dmtuid, 250, 210, width=400, height=50)
    
    mpn = _truncate(part.mpn or "", 25)
    mfr = _truncate(part.manufacturer or "", 25)
    desc = _truncate(part.description or "", 35)
    value = part.value or ""
    package = _get_package(part)
    
    frame = '' if for_print else '<rect x="5" y="5" width="490" height="290" fill="none" stroke="#ccc" stroke-width="1" stroke-dasharray="5,5"/>'
    
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="50mm" height="30mm" viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
  {frame}
  <text x="15" y="35" font-size="24" font-family="Arial, sans-serif"><tspan font-weight="bold">DMTUID:</tspan> {part.dmtuid}</text>
  <line x1="15" y1="49" x2="485" y2="49" stroke="#999" stroke-width="1"/>
  
  <text x="15" y="77" font-size="20" font-family="Arial, sans-serif"><tspan font-weight="bold">MPN:</tspan> {mpn}</text>
  <text x="15" y="105" font-size="20" font-family="Arial, sans-serif"><tspan font-weight="bold">MFR:</tspan> {mfr}</text>
  <text x="50" y="143" font-size="23" font-family="Arial, sans-serif"><tspan font-weight="bold">Value:</tspan> {value}</text>
  <text x="260" y="143" font-size="23" font-family="Arial, sans-serif"><tspan font-weight="bold">Package:</tspan> {package}</text>
  <line x1="15" y1="155" x2="485" y2="155" stroke="#999" stroke-width="1"/>  
  <text x="15" y="180" font-size="17" font-family="Arial, sans-serif"><tspan font-weight="bold">Desc:</tspan> {desc}</text>
  
  {barcode}
  <text x="250" y="285" font-size="14" font-family="monospace" text-anchor="middle" fill="#333">{part.dmtuid}</text>
</svg>'''
    return svg


def _generate_label_75x50(part: Part, for_print: bool = False) -> str:
    """
    Generate 75x50mm label SVG.
    Medium label with more room for details.
    """
    # Scale: viewBox 750x500 = 75x50mm (10 units per mm)
    barcode = generate_barcode_svg_centered(part.dmtuid, 375, 350, width=620, height=85)
    
    mpn = _truncate(part.mpn or "", 35)
    mfr = _truncate(part.manufacturer or "", 35)
    desc = _truncate(part.description or "", 50)
    value = part.value or ""
    package = _get_package(part)
    
    frame = '' if for_print else '<rect x="5" y="5" width="740" height="490" fill="none" stroke="#ccc" stroke-width="1" stroke-dasharray="5,5"/>'
    
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="75mm" height="50mm" viewBox="0 0 750 500" xmlns="http://www.w3.org/2000/svg">
  {frame}
  <text x="25" y="58" font-size="36" font-family="Arial, sans-serif"><tspan font-weight="bold">DMTUID:</tspan> {part.dmtuid}</text>
  <line x1="25" y1="82" x2="725" y2="82" stroke="#999" stroke-width="1"/>
  
  <text x="25" y="128" font-size="30" font-family="Arial, sans-serif"><tspan font-weight="bold">MPN:</tspan> {mpn}</text>
  <text x="25" y="175" font-size="30" font-family="Arial, sans-serif"><tspan font-weight="bold">MFR:</tspan> {mfr}</text>
  <text x="75" y="238" font-size="35" font-family="Arial, sans-serif"><tspan font-weight="bold">Value:</tspan> {value}</text>
  <text x="390" y="238" font-size="35" font-family="Arial, sans-serif"><tspan font-weight="bold">Package:</tspan> {package}</text>
  <line x1="25" y1="258" x2="725" y2="258" stroke="#999" stroke-width="1"/>
  <text x="25" y="300" font-size="25" font-family="Arial, sans-serif"><tspan font-weight="bold">Desc:</tspan> {desc}</text>
  
  {barcode}
  <text x="375" y="475" font-size="22" font-family="monospace" text-anchor="middle" fill="#333">{part.dmtuid}</text>
</svg>'''
    return svg


def _generate_label_100x50(part: Part, for_print: bool = False) -> str:
    """
    Generate 100x50mm label SVG.
    Large label with full details.
    """
    # Scale: viewBox 1000x500 = 100x50mm (10 units per mm)
    barcode = generate_barcode_svg_centered(part.dmtuid, 500, 350, width=800, height=85)
    
    mpn = _truncate(part.mpn or "", 45)
    mfr = _truncate(part.manufacturer or "", 45)
    desc = _truncate(part.description or "", 70)
    value = part.value or ""
    package = _get_package(part)
    
    frame = '' if for_print else '<rect x="5" y="5" width="990" height="490" fill="none" stroke="#ccc" stroke-width="1" stroke-dasharray="5,5"/>'
    
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="100mm" height="50mm" viewBox="0 0 1000 500" xmlns="http://www.w3.org/2000/svg">
  {frame}
  <text x="30" y="58" font-size="36" font-family="Arial, sans-serif"><tspan font-weight="bold">DMTUID:</tspan> {part.dmtuid}</text>
  <line x1="30" y1="82" x2="970" y2="82" stroke="#999" stroke-width="1"/>
  
  <text x="30" y="128" font-size="30" font-family="Arial, sans-serif"><tspan font-weight="bold">MPN:</tspan> {mpn}</text>
  <text x="30" y="175" font-size="30" font-family="Arial, sans-serif"><tspan font-weight="bold">MFR:</tspan> {mfr}</text>
  <text x="100" y="238" font-size="35" font-family="Arial, sans-serif"><tspan font-weight="bold">Value:</tspan> {value}</text>
  <text x="520" y="238" font-size="35" font-family="Arial, sans-serif"><tspan font-weight="bold">Package:</tspan> {package}</text>
  <line x1="30" y1="258" x2="970" y2="258" stroke="#999" stroke-width="1"/>
  <text x="30" y="300" font-size="25" font-family="Arial, sans-serif"><tspan font-weight="bold">Desc:</tspan> {desc}</text>
  
  {barcode}
  <text x="500" y="475" font-size="22" font-family="monospace" text-anchor="middle" fill="#333">{part.dmtuid}</text>
</svg>'''
    return svg


def _generate_label_4x6(part: Part, for_print: bool = False) -> str:
    """
    Generate 4"x6" (101.6x152.4mm) shipping label SVG.
    Large format with full details.
    """
    # Scale: viewBox 1016x1524 = 101.6x152.4mm (10 units per mm)
    barcode = generate_barcode_svg_centered(part.dmtuid, 508, 1300, width=850, height=150)
    
    mpn = part.mpn or ""
    mfr = part.manufacturer or ""
    desc = part.description or ""
    value = part.value or ""
    package = _get_package(part)
    
    frame = '' if for_print else '<rect x="10" y="10" width="996" height="1504" fill="none" stroke="#ccc" stroke-width="2" stroke-dasharray="10,10"/>'
    
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="101.6mm" height="152.4mm" viewBox="0 0 1016 1524" xmlns="http://www.w3.org/2000/svg">
  {frame}
  <text x="40" y="70" font-size="56" font-family="Arial, sans-serif"><tspan font-weight="bold">DMTUID:</tspan> {part.dmtuid}</text>
  <line x1="40" y1="100" x2="976" y2="100" stroke="#999" stroke-width="2"/>
  
  <text x="40" y="170" font-size="48" font-family="Arial, sans-serif"><tspan font-weight="bold">MPN:</tspan> {mpn}</text>
  <text x="40" y="250" font-size="48" font-family="Arial, sans-serif"><tspan font-weight="bold">MFR:</tspan> {mfr}</text>
  
  <text x="40" y="340" font-size="48" font-family="Arial, sans-serif"><tspan font-weight="bold">Value:</tspan> {value}</text>
  <text x="40" y="420" font-size="48" font-family="Arial, sans-serif"><tspan font-weight="bold">Package:</tspan> {package}</text>
  
  <text x="40" y="520" font-size="40" font-family="Arial, sans-serif"><tspan font-weight="bold">Description:</tspan></text>
  <text x="40" y="580" font-size="36" font-family="Arial, sans-serif" fill="#333">{_truncate(desc, 50)}</text>
  <text x="40" y="640" font-size="36" font-family="Arial, sans-serif" fill="#333">{_truncate(desc[50:] if len(desc) > 50 else "", 50)}</text>
  
  <rect x="40" y="720" width="936" height="400" fill="#fafafa" stroke="#ddd" stroke-width="1"/>
  <text x="55" y="770" font-size="32" font-family="Arial, sans-serif" fill="#999">Notes:</text>
  
  {barcode}
  <text x="508" y="1480" font-size="36" font-family="monospace" text-anchor="middle" fill="#333">{part.dmtuid}</text>
</svg>'''
    return svg


# Label generator dispatch
LABEL_GENERATORS = {
    "50x30": _generate_label_50x30,
    "75x50": _generate_label_75x50,
    "100x50": _generate_label_100x50,
    "4x6": _generate_label_4x6,
}


@ui_bp.route("/labels")
def labels_page():
    """Label printing page."""
    return render_template("labels.html", sizes=LABEL_SIZES, domains=get_domains())


@ui_bp.route("/labels/preview")
def label_preview():
    """
    GET /labels/preview?dmtuid=...&size=50x30&print=1
    
    Generate label SVG for preview. Add print=1 to omit preview frame.
    """
    dmtuid = request.args.get("dmtuid", "").strip().upper()
    size = request.args.get("size", "50x30")
    for_print = request.args.get("print", "0") == "1"
    
    if not dmtuid:
        return jsonify({"error": "dmtuid required"}), 400
    
    if size not in LABEL_GENERATORS:
        return jsonify({"error": f"Invalid size. Valid: {list(LABEL_SIZES.keys())}"}), 400
    
    session = get_session()
    try:
        part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
        if not part:
            return jsonify({"error": "Part not found"}), 404
        
        svg = LABEL_GENERATORS[size](part, for_print=for_print)
        return Response(svg, mimetype="image/svg+xml")
    finally:
        session.close()


@ui_bp.route("/labels/download")
def label_download():
    """
    GET /labels/download?dmtuid=...&size=50x30
    
    Download label as SVG file.
    """
    dmtuid = request.args.get("dmtuid", "").strip().upper()
    size = request.args.get("size", "50x30")
    
    if not dmtuid:
        return jsonify({"error": "dmtuid required"}), 400
    
    if size not in LABEL_GENERATORS:
        return jsonify({"error": f"Invalid size"}), 400
    
    session = get_session()
    try:
        part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
        if not part:
            return jsonify({"error": "Part not found"}), 404
        
        svg = LABEL_GENERATORS[size](part, for_print=True)
        
        # Sanitize filename
        safe_dmtuid = dmtuid.replace("-", "_")
        filename = f"label_{safe_dmtuid}_{size}.svg"
        
        return Response(
            svg,
            mimetype="image/svg+xml",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    finally:
        session.close()
