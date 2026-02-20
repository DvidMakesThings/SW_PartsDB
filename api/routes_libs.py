"""
api.routes_libs - /api/v1/libs/* endpoints for KiCad library management.

Handles listing and uploading symbol, footprint, and 3D model files.
"""

import os
import re
from pathlib import Path

from flask import request, jsonify
from werkzeug.utils import secure_filename

from api import api_bp
import config


# Library directories
LIBS_DIR = config.BASE_DIR / "kicad_libs"
SYMBOLS_DIR = LIBS_DIR / "symbols"
FOOTPRINTS_DIR = LIBS_DIR / "footprints"
MODELS_DIR = LIBS_DIR / "3dmodels"

# File extension to type mapping
EXT_MAP = {
    ".kicad_sym": ("symbols", SYMBOLS_DIR),
    ".kicad_mod": ("footprints", FOOTPRINTS_DIR),
    ".step": ("3dmodels", MODELS_DIR),
    ".stp": ("3dmodels", MODELS_DIR),
    ".wrl": ("3dmodels", MODELS_DIR),
}


def _generate_symbol_value(part_data: dict) -> str:
    """
    Generate a symbol Value property from part database fields.
    
    For passives: {Resistance|Capacitance|Inductance} {Tolerance}
    For non-passives: MPN
    """
    # Check for passive component fields
    resistance = part_data.get("Resistance", "").strip()
    capacitance = part_data.get("Capacitance", "").strip()
    inductance = part_data.get("Inductance", "").strip()
    tolerance = part_data.get("Tolerance", "").strip()
    
    if resistance:
        return f"{resistance} {tolerance}".strip()
    elif capacitance:
        return f"{capacitance} {tolerance}".strip()
    elif inductance:
        return f"{inductance} {tolerance}".strip()
    else:
        # Non-passive: use MPN
        return part_data.get("mpn", "") or part_data.get("MPN", "") or ""


@api_bp.route("/libs")
def list_libs():
    """
    GET /api/v1/libs
    
    List all KiCad library files organized by type.
    """
    result = {
        "symbols": [],
        "footprints": [],
        "3dmodels": [],
    }
    
    # Symbols (.kicad_sym)
    if SYMBOLS_DIR.exists():
        for f in SYMBOLS_DIR.iterdir():
            if f.suffix == ".kicad_sym":
                result["symbols"].append({
                    "name": f.stem,
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "url": f"/kicad_libs/symbols/{f.name}",
                })
    
    # Footprints (.kicad_mod) - can be in root or in .pretty folders
    if FOOTPRINTS_DIR.exists():
        for item in FOOTPRINTS_DIR.iterdir():
            if item.suffix == ".kicad_mod":
                result["footprints"].append({
                    "name": item.stem,
                    "filename": item.name,
                    "size": item.stat().st_size,
                    "url": f"/kicad_libs/footprints/{item.name}",
                })
            elif item.is_dir() and item.suffix == ".pretty":
                # .pretty folder containing .kicad_mod files
                for mod in item.iterdir():
                    if mod.suffix == ".kicad_mod":
                        result["footprints"].append({
                            "name": mod.stem,
                            "filename": mod.name,
                            "library": item.name,
                            "size": mod.stat().st_size,
                            "url": f"/kicad_libs/footprints/{item.name}/{mod.name}",
                        })
    
    # 3D Models (.step, .stp, .wrl)
    if MODELS_DIR.exists():
        for f in MODELS_DIR.iterdir():
            if f.suffix.lower() in (".step", ".stp", ".wrl"):
                result["3dmodels"].append({
                    "name": f.stem,
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "url": f"/kicad_libs/3dmodels/{f.name}",
                })
    
    return jsonify(result)


@api_bp.route("/libs/upload", methods=["POST"])
def upload_lib_file():
    """
    POST /api/v1/libs/upload
    
    Upload a KiCad library file. Auto-detects type from extension.
    
    Form data:
      - file: The file to upload
      - dmtuid: (optional) Link to a part's kicad_symbol/footprint field
      - preview: (optional) If "true", parse symbol but don't save yet
      - symbol_props: (optional) JSON of properties to write into symbol
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    
    filename = secure_filename(file.filename)
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    if ext not in EXT_MAP:
        return jsonify({
            "error": f"Unknown file type: {ext}",
            "allowed": list(EXT_MAP.keys()),
        }), 400
    
    file_type, dest_dir = EXT_MAP[ext]
    preview_mode = request.form.get("preview", "").lower() == "true"
    
    # Ensure directory exists
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize custom_props for potential symbol uploads
    custom_props = {}
    
    # Handle text vs binary files differently
    is_text_file = file_type in ("symbols", "footprints")
    
    if is_text_file:
        # Read as text for symbols and footprints
        content = file.read().decode("utf-8")
        
        # For symbols, handle preview mode (parse and return properties without saving)
        if file_type == "symbols" and preview_mode:
            from services.kicad_symbol_processor import KiCadSymbolProcessor
            props = KiCadSymbolProcessor.extract_properties(content)
            symbol_name = KiCadSymbolProcessor.get_symbol_name(content)
            
            return jsonify({
                "preview": True,
                "type": file_type,
                "filename": filename,
                "name": Path(filename).stem,
                "symbol_name": symbol_name,
                "properties": props,
            })
        
        # Apply custom properties to symbol if provided
        symbol_props_json = request.form.get("symbol_props", "").strip()
        dmtuid = request.form.get("dmtuid", "").strip()
        
        # For symbols: auto-generate Value from database if dmtuid provided
        if file_type == "symbols" and dmtuid:
            import json as json_mod
            from db import get_session
            from db.models import Part
            
            session = get_session()
            try:
                part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
                if part:
                    part_data = part.to_dict()
                    auto_value = _generate_symbol_value(part_data)
                    
                    # Parse existing symbol_props and add auto-value if no Value specified
                    if symbol_props_json:
                        try:
                            custom_props = json_mod.loads(symbol_props_json)
                        except json_mod.JSONDecodeError:
                            custom_props = {}
                    
                    # Only auto-set Value if not explicitly provided
                    if auto_value and not custom_props.get("Value"):
                        custom_props["Value"] = auto_value
                    
                    # Also auto-set MPN if not provided
                    if part_data.get("mpn") and not custom_props.get("MPN"):
                        custom_props["MPN"] = part_data.get("mpn")
                    
                    # Re-serialize for the property-setting loop below
                    symbol_props_json = json_mod.dumps(custom_props)
            finally:
                session.close()
        
        if file_type == "symbols" and symbol_props_json:
            import json
            from services.kicad_symbol_processor import KiCadSymbolProcessor
            try:
                custom_props = json.loads(symbol_props_json)
                for prop_name, prop_value in custom_props.items():
                    if prop_value:  # Only set non-empty values
                        content = KiCadSymbolProcessor._set_property(content, prop_name, prop_value)
            except json.JSONDecodeError:
                pass
        
        # For symbols, generate filename from Value + package
        if file_type == "symbols" and custom_props:
            value = custom_props.get("Value", "").strip()
            # Try to extract package from Footprint (e.g., "DMTDB:C_1206_3216Metric" -> "1206")
            footprint = custom_props.get("Footprint", "")
            package = ""
            if footprint:
                # Extract package size (e.g., 1206, 0805, etc.)
                pkg_match = re.search(r'(\d{4})(?:_|Metric|$)', footprint)
                if pkg_match:
                    package = pkg_match.group(1)
            
            if value:
                # Combine Value and package for filename
                if package and package not in value:
                    new_name = f"{value} {package}"
                else:
                    new_name = value
                
                # Sanitize filename (replace chars not allowed in filenames)
                new_name = re.sub(r'[<>:"/\\|?*]', '_', new_name)
                new_name = new_name.strip()
                
                if new_name:
                    filename = f"{new_name}.kicad_sym"
        
        # Handle duplicates differently based on file type
        dest_path = dest_dir / filename
        if dest_path.exists():
            if file_type == "footprints":
                # For footprints: if file already exists, just reuse it (no duplication)
                # But still link to the part if dmtuid provided
                result = {
                    "success": True,
                    "type": file_type,
                    "filename": filename,
                    "name": Path(filename).stem,
                    "url": f"/kicad_libs/{file_type}/{filename}",
                    "size": dest_path.stat().st_size,
                    "reused": True,
                    "message": f"File already exists, using existing {filename}",
                }
                dmtuid = request.form.get("dmtuid", "").strip()
                if dmtuid:
                    from db import get_session
                    from db.models import Part
                    session = get_session()
                    try:
                        part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
                        if part:
                            part.kicad_footprint = f"DMTDB:{Path(filename).stem}"
                            result["linked_field"] = "kicad_footprint"
                            result["linked_value"] = part.kicad_footprint
                            session.commit()
                    finally:
                        session.close()
                return jsonify(result), 200
            
            elif file_type == "symbols":
                # For symbols, try MPN suffix first
                base_name = Path(filename).stem
                mpn = custom_props.get("MPN", "").strip() if custom_props else ""
                mpn = re.sub(r'[<>:"/\\|?*]', '_', mpn)  # Sanitize MPN
                
                if mpn:
                    filename = f"{base_name} {mpn}.kicad_sym"
                    dest_path = dest_dir / filename
                
                # If still exists (same Value+MPN), fall back to counter
                if dest_path.exists():
                    counter = 2
                    base_with_mpn = Path(filename).stem
                    while dest_path.exists():
                        filename = f"{base_with_mpn}_{counter}{ext}"
                        dest_path = dest_dir / filename
                        counter += 1
        
        # Update symbol name inside the file to match filename
        if file_type == "symbols":
            from services.kicad_symbol_processor import KiCadSymbolProcessor
            symbol_name = Path(filename).stem
            content = KiCadSymbolProcessor.set_symbol_name(content, symbol_name)
            
            # Update Footprint property to use DMTDB: prefix
            footprint = custom_props.get("Footprint", "") if custom_props else ""
            if footprint and not footprint.startswith("DMTDB:"):
                # Extract just the footprint name (e.g., "C_1206_3216Metric" from "Capacitor_SMD:C_1206_3216Metric")
                fp_name = footprint.split(":")[-1] if ":" in footprint else footprint
                dmtdb_footprint = f"DMTDB:{fp_name}"
                content = KiCadSymbolProcessor._set_property(content, "Footprint", dmtdb_footprint)
        
        # Update 3D model path in footprints to use DMTDB environment variable
        if file_type == "footprints":
            # Replace absolute model paths with ${DMTDB_3D}/filename.ext
            # Matches: (model "any/path/to/model.step"
            model_pattern = r'\(model\s+"[^"]*[/\\]([^"/\\]+\.[^"]+)"'
            model_replacement = r'(model "${DMTDB_3D}/\1"'
            content = re.sub(model_pattern, model_replacement, content, flags=re.IGNORECASE)
        
        # Save text file
        dest_path.write_text(content, encoding="utf-8")
    else:
        # Save binary files (3D models) directly
        dest_path = dest_dir / filename
        
        # For 3D models: if file already exists, just reuse it (no duplication)
        if dest_path.exists():
            result = {
                "success": True,
                "type": file_type,
                "filename": filename,
                "name": Path(filename).stem,
                "url": f"/kicad_libs/{file_type}/{filename}",
                "size": dest_path.stat().st_size,
                "reused": True,
                "message": f"File already exists, using existing {filename}",
            }
            
            # Still update part record with reference to existing file
            dmtuid = request.form.get("dmtuid", "").strip()
            if dmtuid:
                from db import get_session
                from db.models import Part
                session = get_session()
                try:
                    part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
                    if part:
                        part.kicad_3dmodel = filename
                        result["linked_field"] = "kicad_3dmodel"
                        result["linked_value"] = filename
                        session.commit()
                finally:
                    session.close()
            
            return jsonify(result), 200
        
        file.save(dest_path)
    
    result = {
        "success": True,
        "type": file_type,
        "filename": filename,
        "name": Path(filename).stem,
        "url": f"/kicad_libs/{file_type}/{filename}",
        "size": dest_path.stat().st_size,
    }
    
    # If dmtuid provided, update the part's KiCad fields
    dmtuid = request.form.get("dmtuid", "").strip()
    
    if dmtuid:
        from db import get_session
        from db.models import Part
        
        session = get_session()
        try:
            part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
            if part:
                name = Path(filename).stem
                if file_type == "symbols":
                    part.kicad_symbol = f"DMTDB:{name}"
                    result["linked_field"] = "kicad_symbol"
                    result["linked_value"] = part.kicad_symbol
                    # Also save LCSC_PART if provided
                    lcsc_part = custom_props.get("LCSC_PART", "").strip() if custom_props else ""
                    if lcsc_part:
                        part.kicad_libref = lcsc_part
                        result["lcsc_part"] = lcsc_part
                elif file_type == "footprints":
                    part.kicad_footprint = f"DMTDB:{name}"
                    result["linked_field"] = "kicad_footprint"
                    result["linked_value"] = part.kicad_footprint
                elif file_type == "3dmodels":
                    part.kicad_3dmodel = filename  # Store full filename with extension
                    result["linked_field"] = "kicad_3dmodel"
                    result["linked_value"] = part.kicad_3dmodel
                session.commit()
        finally:
            session.close()
    
    return jsonify(result), 201


@api_bp.route("/libs/<file_type>/<filename>", methods=["DELETE"])
def delete_lib_file(file_type: str, filename: str):
    """
    DELETE /api/v1/libs/{type}/{filename}
    
    Delete a library file.
    """
    type_dirs = {
        "symbols": SYMBOLS_DIR,
        "footprints": FOOTPRINTS_DIR,
        "3dmodels": MODELS_DIR,
    }
    
    if file_type not in type_dirs:
        return jsonify({"error": f"Invalid type: {file_type}"}), 400
    
    filepath = type_dirs[file_type] / secure_filename(filename)
    
    if not filepath.exists():
        return jsonify({"error": "File not found"}), 404
    
    filepath.unlink()
    return jsonify({"success": True, "deleted": filename})


@api_bp.route("/libs/symbols/<filename>/sync", methods=["POST"])
def sync_symbol_with_part(filename: str):
    """
    POST /api/v1/libs/symbols/{filename}/sync
    
    Re-process a symbol file with data from a linked part.
    
    JSON body:
      - dmtuid: The part to pull data from
    """
    from db import get_session
    from db.models import Part
    from services.kicad_symbol_processor import process_uploaded_symbol
    
    data = request.get_json(force=True) if request.is_json else {}
    dmtuid = data.get("dmtuid", "").strip()
    
    if not dmtuid:
        return jsonify({"error": "dmtuid required"}), 400
    
    filepath = SYMBOLS_DIR / secure_filename(filename)
    if not filepath.exists():
        return jsonify({"error": "Symbol file not found"}), 404
    
    session = get_session()
    try:
        part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
        if not part:
            return jsonify({"error": "Part not found"}), 404
        
        result = process_uploaded_symbol(filepath, part)
        
        return jsonify({
            "success": True,
            "filename": filename,
            "symbol_name": result["symbol_name"],
            "filled_properties": {
                k: v for k, v in result["updated_properties"].items()
                if v and k in ["Value", "Footprint", "Datasheet", "Description", "MFR", "MPN", "ROHS"]
            },
        })
    finally:
        session.close()


@api_bp.route("/libs/link", methods=["POST"])
def link_existing_lib():
    """
    POST /api/v1/libs/link
    
    Link an existing library file to a part without re-uploading.
    
    Form data:
      - dmtuid: The part to link to
      - filename: The existing library filename
      - type: 'symbols', 'footprints', or '3dmodels'
    """
    from db import get_session
    from db.models import Part
    
    dmtuid = request.form.get("dmtuid", "").strip()
    filename = request.form.get("filename", "").strip()
    file_type = request.form.get("type", "").strip()
    
    if not dmtuid or not filename or not file_type:
        return jsonify({"error": "dmtuid, filename, and type required"}), 400
    
    if file_type not in ("symbols", "footprints", "3dmodels"):
        return jsonify({"error": "Invalid type"}), 400
    
    # Verify file exists
    type_dirs = {
        "symbols": SYMBOLS_DIR,
        "footprints": FOOTPRINTS_DIR,
        "3dmodels": MODELS_DIR,
    }
    filepath = type_dirs[file_type] / filename
    if not filepath.exists():
        return jsonify({"error": "File not found"}), 404
    
    session = get_session()
    try:
        part = session.query(Part).filter(Part.dmtuid == dmtuid).first()
        if not part:
            return jsonify({"error": "Part not found"}), 404
        
        name = Path(filename).stem
        
        if file_type == "symbols":
            part.kicad_symbol = f"DMTDB:{name}"
        elif file_type == "footprints":
            part.kicad_footprint = f"DMTDB:{name}"
        elif file_type == "3dmodels":
            part.kicad_3dmodel = filename
        
        session.commit()
        
        return jsonify({
            "success": True,
            "type": file_type,
            "filename": filename,
            "name": name,
        })
    finally:
        session.close()
