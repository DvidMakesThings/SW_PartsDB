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
    barcode = generate_barcode_svg_centered(part.dmtuid, 250, 190, width=450, height=75)
    
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
  <text x="250" y="285" font-size="20" font-family="monospace" text-anchor="middle" fill="#333">{part.dmtuid}</text>
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
  <text x="100" y="220" font-size="30" font-family="Arial, sans-serif"><tspan font-weight="bold">Value:</tspan> {value}</text>
  <text x="100" y="255" font-size="30" font-family="Arial, sans-serif"><tspan font-weight="bold">Package:</tspan> {package}</text>
  <line x1="25" y1="270" x2="725" y2="270" stroke="#999" stroke-width="1"/>
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


# =============================================================================
# Niimbot B1 Direct Printing
# =============================================================================

# Global state for connected Niimbot printer
_niimbot_connection = {
    "address": None,
    "transport": None,
    "printer": None,
}


@ui_bp.route("/labels/niimbot/scan")
def niimbot_scan():
    """
    GET /labels/niimbot/scan?filter=B1&timeout=10
    
    Scan for Niimbot Bluetooth devices.
    """
    from services.niimbot_service import NiimbotScanner
    
    name_filter = request.args.get("filter", "B1")
    timeout = float(request.args.get("timeout", "10"))
    
    try:
        devices = NiimbotScanner.scan(name_filter=name_filter, timeout=timeout)
        return jsonify({"devices": devices})
    except Exception as e:
        return jsonify({"error": str(e), "devices": []}), 500


@ui_bp.route("/labels/niimbot/connect", methods=["POST"])
def niimbot_connect():
    """
    POST /labels/niimbot/connect
    Body: {"address": "XX:XX:XX:XX:XX:XX", "model": "b1"}
    
    Connect to a Niimbot printer and keep connection open.
    """
    from services.niimbot_service import NiimbotTransport, NiimbotPrinter
    
    data = request.get_json() or {}
    address = data.get("address")
    model = data.get("model", "b1")
    
    if not address:
        return jsonify({"error": "address required"}), 400
    
    # Disconnect existing connection if any
    if _niimbot_connection["transport"]:
        try:
            _niimbot_connection["transport"].disconnect()
        except:
            pass
        _niimbot_connection["transport"] = None
        _niimbot_connection["printer"] = None
        _niimbot_connection["address"] = None
    
    try:
        transport = NiimbotTransport(address)
        if not transport.connect():
            return jsonify({"error": "Failed to connect to printer"}), 500
        
        printer = NiimbotPrinter(transport, model)
        
        _niimbot_connection["address"] = address
        _niimbot_connection["transport"] = transport
        _niimbot_connection["printer"] = printer
        
        return jsonify({"success": True, "address": address, "model": model})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@ui_bp.route("/labels/niimbot/disconnect", methods=["POST"])
def niimbot_disconnect():
    """
    POST /labels/niimbot/disconnect
    
    Disconnect from current Niimbot printer.
    """
    if _niimbot_connection["transport"]:
        try:
            _niimbot_connection["transport"].disconnect()
        except:
            pass
    
    _niimbot_connection["transport"] = None
    _niimbot_connection["printer"] = None
    _niimbot_connection["address"] = None
    
    return jsonify({"success": True})


@ui_bp.route("/labels/niimbot/status")
def niimbot_status():
    """
    GET /labels/niimbot/status
    
    Get current Niimbot connection status.
    """
    connected = _niimbot_connection["transport"] is not None
    return jsonify({
        "connected": connected,
        "address": _niimbot_connection["address"] if connected else None
    })


@ui_bp.route("/labels/niimbot/print", methods=["POST"])
def niimbot_print():
    """
    POST /labels/niimbot/print
    Body: {"dmtuid": "...", "size": "50x30", "density": 3, "address": "XX:XX:XX:XX:XX:XX"}
    
    Print label to Niimbot printer.
    If address is provided and different from current, reconnect.
    If no address and not connected, return error.
    """
    from services.niimbot_service import NiimbotTransport, NiimbotPrinter, svg_to_image
    
    data = request.get_json() or {}
    dmtuid = (data.get("dmtuid") or "").strip().upper()
    size = data.get("size", "50x30")
    density = int(data.get("density", 3))
    address = data.get("address")
    model = data.get("model", "b1")
    
    if not dmtuid:
        return jsonify({"error": "dmtuid required"}), 400
    
    if size not in LABEL_GENERATORS:
        return jsonify({"error": f"Invalid size. Valid: {list(LABEL_SIZES.keys())}"}), 400
    
    # Handle connection
    printer = _niimbot_connection["printer"]
    
    if address and address != _niimbot_connection["address"]:
        # Need to connect/reconnect
        if _niimbot_connection["transport"]:
            try:
                _niimbot_connection["transport"].disconnect()
            except:
                pass
        
        transport = NiimbotTransport(address)
        if not transport.connect():
            return jsonify({"error": "Failed to connect to printer"}), 500
        
        printer = NiimbotPrinter(transport, model)
        _niimbot_connection["address"] = address
        _niimbot_connection["transport"] = transport
        _niimbot_connection["printer"] = printer
    
    if not printer:
        return jsonify({"error": "Not connected to printer. Provide address or connect first."}), 400
    
    # Get part and generate SVG
    session = get_session()
    try:
        part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
        if not part:
            return jsonify({"error": "Part not found"}), 404
        
        svg = LABEL_GENERATORS[size](part, for_print=True)
        
        # Convert SVG to image and print
        # DPI: B1 is 203 DPI (8 dots/mm)
        # 50x30mm = 400x240px, 75x50mm = 600x400px, 100x50mm = 800x400px
        dpi_map = {
            "50x30": 203,
            "75x50": 203,
            "100x50": 203,
            "4x6": 203,
        }
        dpi = dpi_map.get(size, 203)
        
        image = svg_to_image(svg, dpi=dpi)
        
        # Ensure image fits printhead (384px for B1)
        max_width = 384
        if image.width > max_width:
            ratio = max_width / image.width
            new_height = int(image.height * ratio)
            from PIL import Image as PILImage
            image = image.resize((max_width, new_height), PILImage.Resampling.LANCZOS)
        
        printer.print_image(image, density=density)
        
        return jsonify({"success": True, "dmtuid": dmtuid, "size": size})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@ui_bp.route("/labels/niimbot/batch", methods=["POST"])
def niimbot_batch_print():
    """
    POST /labels/niimbot/batch
    Body: {"dmtuids": ["...", "..."], "size": "50x30", "density": 3}
    
    Batch print multiple labels to Niimbot printer.
    Requires existing connection.
    """
    from services.niimbot_service import svg_to_image
    import time
    
    data = request.get_json() or {}
    dmtuids = data.get("dmtuids", [])
    size = data.get("size", "50x30")
    density = int(data.get("density", 3))
    
    if not dmtuids:
        return jsonify({"error": "dmtuids required"}), 400
    
    if size not in LABEL_GENERATORS:
        return jsonify({"error": f"Invalid size"}), 400
    
    printer = _niimbot_connection["printer"]
    if not printer:
        return jsonify({"error": "Not connected to printer"}), 400
    
    session = get_session()
    results = {"success": [], "failed": []}
    
    try:
        for dmtuid in dmtuids:
            dmtuid = dmtuid.strip().upper()
            try:
                part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
                if not part:
                    results["failed"].append({"dmtuid": dmtuid, "error": "Not found"})
                    continue
                
                svg = LABEL_GENERATORS[size](part, for_print=True)
                image = svg_to_image(svg, dpi=203)
                
                # Resize if needed
                max_width = 384
                if image.width > max_width:
                    ratio = max_width / image.width
                    new_height = int(image.height * ratio)
                    from PIL import Image as PILImage
                    image = image.resize((max_width, new_height), PILImage.Resampling.LANCZOS)
                
                printer.print_image(image, density=density)
                results["success"].append(dmtuid)
                
                # Small delay between prints to let printer catch up
                time.sleep(0.5)
                
            except Exception as e:
                results["failed"].append({"dmtuid": dmtuid, "error": str(e)})
        
        return jsonify({
            "success": True,
            "printed": len(results["success"]),
            "failed": len(results["failed"]),
            "details": results
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()
