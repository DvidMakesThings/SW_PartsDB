"""
services.kicad_staging - In-memory staging for KiCad file uploads.

Files are staged in a temp directory until the part form is submitted.
On form submission, staged files are processed and saved to the final location.
"""

import os
import json
import uuid
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

import config

# Staging directory - temp files stored here before final save
STAGING_DIR = config.BASE_DIR / "_staging"

# Auto-cleanup: remove staged files older than this
STAGING_MAX_AGE = timedelta(hours=2)


def _ensure_staging_dir():
    """Ensure staging directory exists."""
    STAGING_DIR.mkdir(parents=True, exist_ok=True)


def _get_session_dir(session_id: str) -> Path:
    """Get the staging directory for a session."""
    return STAGING_DIR / session_id


def _cleanup_old_sessions():
    """Remove staging directories older than STAGING_MAX_AGE."""
    if not STAGING_DIR.exists():
        return
    
    now = datetime.now()
    for item in STAGING_DIR.iterdir():
        if item.is_dir():
            # Check directory modification time
            mtime = datetime.fromtimestamp(item.stat().st_mtime)
            if now - mtime > STAGING_MAX_AGE:
                try:
                    shutil.rmtree(item)
                except Exception:
                    pass  # Ignore cleanup errors


def create_session() -> str:
    """Create a new staging session and return its ID."""
    _ensure_staging_dir()
    _cleanup_old_sessions()
    
    session_id = str(uuid.uuid4())
    session_dir = _get_session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Create metadata file
    meta_path = session_dir / "_metadata.json"
    meta_path.write_text(json.dumps({
        "created": datetime.now().isoformat(),
        "files": {}
    }))
    
    return session_id


def stage_file(session_id: str, file_type: str, filename: str, content: bytes, 
               is_text: bool = False, metadata: Optional[dict] = None) -> dict:
    """
    Stage a file for later processing.
    
    Args:
        session_id: Staging session ID
        file_type: "symbol", "footprint", or "3dmodel"
        filename: Original filename
        content: File content (bytes)
        is_text: If True, content is text (decode as UTF-8)
        metadata: Additional metadata (e.g., extracted symbol properties)
    
    Returns:
        dict with staging info
    """
    session_dir = _get_session_dir(session_id)
    if not session_dir.exists():
        raise ValueError(f"Invalid session: {session_id}")
    
    # Save file content
    staged_path = session_dir / f"{file_type}_{filename}"
    if is_text:
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        # Normalize line endings
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        staged_path.write_text(content, encoding='utf-8')
    else:
        if isinstance(content, str):
            content = content.encode('utf-8')
        staged_path.write_bytes(content)
    
    # Update metadata
    meta_path = session_dir / "_metadata.json"
    meta = json.loads(meta_path.read_text())
    meta["files"][file_type] = {
        "filename": filename,
        "staged_path": str(staged_path),
        "is_text": is_text,
        "metadata": metadata or {}
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    
    return {
        "success": True,
        "session_id": session_id,
        "file_type": file_type,
        "filename": filename,
        "staged": True
    }


def get_staged_files(session_id: str) -> dict:
    """Get metadata about all staged files for a session."""
    session_dir = _get_session_dir(session_id)
    if not session_dir.exists():
        return {"files": {}}
    
    meta_path = session_dir / "_metadata.json"
    if not meta_path.exists():
        return {"files": {}}
    
    return json.loads(meta_path.read_text())


def get_staged_content(session_id: str, file_type: str) -> Optional[tuple[str, str, bool]]:
    """
    Get the content of a staged file.
    
    Returns:
        Tuple of (filename, content, is_text) or None if not found
    """
    meta = get_staged_files(session_id)
    file_info = meta.get("files", {}).get(file_type)
    if not file_info:
        return None
    
    staged_path = Path(file_info["staged_path"])
    if not staged_path.exists():
        return None
    
    is_text = file_info.get("is_text", False)
    if is_text:
        content = staged_path.read_text(encoding='utf-8')
    else:
        content = staged_path.read_bytes()
    
    return (file_info["filename"], content, is_text)


def update_staged_metadata(session_id: str, file_type: str, metadata: dict):
    """Update metadata for a staged file (e.g., symbol properties after editing)."""
    session_dir = _get_session_dir(session_id)
    meta_path = session_dir / "_metadata.json"
    
    if not meta_path.exists():
        return
    
    meta = json.loads(meta_path.read_text())
    if file_type in meta.get("files", {}):
        meta["files"][file_type]["metadata"].update(metadata)
        meta_path.write_text(json.dumps(meta, indent=2))


def clear_session(session_id: str):
    """Remove all staged files for a session."""
    session_dir = _get_session_dir(session_id)
    if session_dir.exists():
        try:
            shutil.rmtree(session_dir)
        except Exception:
            pass


def process_staged_files(session_id: str, dmtuid: str = None, tt: str = None, ff: str = None, 
                        value: str = None, mpn: str = None, kicad_footprint: str = None) -> dict:
    """
    Process all staged files and save them to the final locations.
    
    This is called when the part form is submitted.
    
    Args:
        session_id: Staging session ID
        dmtuid: Part DMTUID (optional - for reference)
        tt: Type/domain code (e.g., "01" for Passive Components)
        ff: Family code (e.g., "01" for Capacitors)
        value: Part value
        mpn: Manufacturer part number
        kicad_footprint: Existing footprint reference
    
    Returns:
        dict with results:
        - symbol_ref: KiCad symbol reference (LibName:SymbolName)
        - footprint_ref: KiCad footprint reference (DMTDB:FootprintName)
        - model3d_name: 3D model filename
    """
    from services.kicad_symbol_processor import KiCadSymbolProcessor
    from schema.loader import domain_name, family_name
    import re
    
    # Use paths from config (reads from env vars DMTDB_SYM, DMTDB_FOOTPRINT, DMTDB_3D)
    SYMBOLS_DIR = config.KICAD_SYMBOLS_DIR
    FOOTPRINTS_DIR = config.KICAD_FOOTPRINT_DIR
    MODELS_DIR = config.KICAD_3DMODELS_DIR
    
    meta = get_staged_files(session_id)
    result = {}
    
    tt = tt or ""
    ff = ff or ""
    
    # Process symbol
    symbol_info = meta.get("files", {}).get("symbol")
    if symbol_info:
        staged_content = get_staged_content(session_id, "symbol")
        if staged_content:
            filename, content, _ = staged_content
            symbol_props = symbol_info.get("metadata", {}).get("symbol_props", {})
            
            # Apply symbol properties
            for prop_name, prop_value in symbol_props.items():
                content = KiCadSymbolProcessor._set_property(content, prop_name, prop_value)
            
            # Determine library filename
            if tt and ff:
                dom_name = re.sub(r'[^a-zA-Z0-9]', '', domain_name(tt))
                fam_name = re.sub(r'[^a-zA-Z0-9]', '', family_name(tt, ff))
                lib_filename = f"DMTDB_{dom_name}_{fam_name}.kicad_sym"
            else:
                lib_filename = "DMTDB.kicad_sym"
            
            # Generate symbol name
            value_name = symbol_props.get("Value", "") or value or ""
            mpn_val = symbol_props.get("MPN", "") or mpn or ""
            mpn_sanitized = re.sub(r'[<>:"/\\|?*]', '_', mpn_val)
            
            if tt == "01" and ff in ("01", "02", "03") and value_name and mpn_sanitized:
                symbol_name = f"{value_name} {mpn_sanitized}"
            elif mpn_sanitized:
                symbol_name = mpn_sanitized
            elif value_name:
                symbol_name = value_name
            else:
                symbol_name = Path(filename).stem
            
            # Update symbol name in content
            content = KiCadSymbolProcessor.set_symbol_name(content, symbol_name)
            
            # Update Footprint property
            footprint = symbol_props.get("Footprint", "") or kicad_footprint or ""
            if footprint and not footprint.startswith("DMTDB:"):
                fp_name = footprint.split(":")[-1] if ":" in footprint else footprint
                footprint = f"DMTDB:{fp_name}"
            if footprint:
                content = KiCadSymbolProcessor._set_property(content, "Footprint", footprint)
            
            # Extract symbol block and add to library
            symbol_block = KiCadSymbolProcessor.extract_symbol_block(content)
            if symbol_block:
                SYMBOLS_DIR.mkdir(parents=True, exist_ok=True)
                library_path = SYMBOLS_DIR / lib_filename
                KiCadSymbolProcessor.add_symbol_to_library(library_path, symbol_block, symbol_name)
                
                lib_name = Path(lib_filename).stem
                result["symbol_ref"] = f"{lib_name}:{symbol_name}"
    
    # Process footprint
    footprint_info = meta.get("files", {}).get("footprint")
    if footprint_info:
        staged_content = get_staged_content(session_id, "footprint")
        if staged_content:
            filename, content, _ = staged_content
            
            FOOTPRINTS_DIR.mkdir(parents=True, exist_ok=True)
            dest_path = FOOTPRINTS_DIR / filename
            
            if dest_path.exists():
                result["footprint_ref"] = f"DMTDB:{Path(filename).stem}"
            else:
                # Update model path if 3D model was also staged
                model_info = meta.get("files", {}).get("3dmodel")
                if model_info:
                    model_filename = model_info["filename"]
                    model_pattern = r'\(model\s+"[^"]*"'
                    model_replacement = f'(model "${{DMTDB_3D}}/{model_filename}"'
                    content = re.sub(model_pattern, model_replacement, content, flags=re.IGNORECASE)
                else:
                    # Normalize existing model paths
                    model_pattern = r'\(model\s+"[^"]*[/\\]([^"/\\]+\.[^"]+)"'
                    model_replacement = r'(model "${DMTDB_3D}/\\1"'
                    content = re.sub(model_pattern, model_replacement, content, flags=re.IGNORECASE)
                
                dest_path.write_text(content, encoding='utf-8')
                result["footprint_ref"] = f"DMTDB:{Path(filename).stem}"
    
    # Process 3D model
    model_info = meta.get("files", {}).get("3dmodel")
    if model_info:
        staged_content = get_staged_content(session_id, "3dmodel")
        if staged_content:
            filename, content, is_text = staged_content
            
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            dest_path = MODELS_DIR / filename
            
            if not dest_path.exists():
                if is_text:
                    dest_path.write_text(content, encoding='utf-8')
                else:
                    dest_path.write_bytes(content)
            
            result["model3d_name"] = filename
    
    # Clean up staging directory
    clear_session(session_id)
    
    return result
