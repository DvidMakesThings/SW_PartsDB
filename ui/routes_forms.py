"""
ui.routes_forms - Add / Edit / Delete part forms.
"""

import re
from pathlib import Path
from flask import request, render_template, redirect, url_for, flash, abort

import config
from ui import ui_bp
from db import get_session
from db.models import PartField
from services.parts_service import PartsService
from services.kicad_symbol_processor import KiCadSymbolProcessor
from services import kicad_staging
from schema.loader import get_domains, domain_name, family_name
from schema.templates import get_fields
from schema.numbering import build_dmtuid
from services.sequence_service import next_xxx
from import_engine.field_map import DIRECT_FIELDS, SKIP_FOR_EAV

# Mapping of passive families to library names
PASSIVE_LIBRARY_MAP = {
    ("01", "01"): "DMTDB_PassiveComponents_Capacitors",  # Capacitors
    ("01", "02"): "DMTDB_PassiveComponents_Resistors",   # Resistors
    ("01", "03"): "DMTDB_PassiveComponents_Inductors",   # Inductors
}

# Mapping package sizes to KiCad footprint names
PACKAGE_TO_FOOTPRINT = {
    # Metric (imperial) - supported sizes
    "0201": ("R_0201_0603Metric", "C_0201_0603Metric"),
    "0402": ("R_0402_1005Metric", "C_0402_1005Metric"),
    "0603": ("R_0603_1608Metric", "C_0603_1608Metric"),
    "0805": ("R_0805_2012Metric", "C_0805_2012Metric"),
    "1206": ("R_1206_3216Metric", "C_1206_3216Metric"),
    "1210": ("R_1210_3225Metric", "C_1210_3225Metric"),
    "2010": ("R_2010_5025Metric", "C_2010_5025Metric"),
    "2512": ("R_2512_6332Metric", "C_2512_6332Metric"),
}


def derive_footprint_from_package(package_case: str, family: str) -> tuple[str | None, str | None]:
    """
    Derive KiCad footprint and 3D model from 'Package / Case' field value.
    
    Args:
        package_case: Value like "0402 (1005 Metric)" or "0805"
        family: "01" for capacitors, "02" for resistors, "03" for inductors
    
    Returns:
        Tuple of (footprint reference, 3D model filename) or (None, None)
    """
    if not package_case:
        return None, None
    
    # Extract package size (4-digit number like 0402, 0805, 2512)
    match = re.search(r'\b(0201|0402|0603|0805|1206|1210|2010|2512)\b', package_case)
    if not match:
        return None, None
    
    size = match.group(1)
    if size not in PACKAGE_TO_FOOTPRINT:
        return None, None
    
    r_fp, c_fp = PACKAGE_TO_FOOTPRINT[size]
    
    # Choose footprint and 3D model based on family
    if family == "01":  # Capacitors
        return f"DMTDB:{c_fp}", f"{c_fp}.step"
    elif family == "02":  # Resistors
        return f"DMTDB:{r_fp}", f"{r_fp}.step"
    elif family == "03":  # Inductors (use resistor footprints for now)
        return f"DMTDB:{r_fp}", f"{r_fp}.step"
    
    return None, None


# ── Add ────────────────────────────────────────────────────────────────

@ui_bp.route("/part/add", methods=["GET", "POST"])
def part_add():
    domains = get_domains()

    if request.method == "GET":
        template_part = None
        template_dmtuid = request.args.get("template", "").strip()
        
        # Load template part if specified (for "Use as template" feature)
        if template_dmtuid:
            session = get_session()
            try:
                template_part = PartsService.get(session, template_dmtuid)
            finally:
                session.close()
        
        return render_template(
            "add_edit.html", part=None, domains=domains,
            template_fields=None, mode="add", template_part=template_part,
        )

    # POST: collect form data into a dict and delegate to PartsService
    data = dict(request.form)
    staging_session_id = data.pop('staging_session_id', None)
    
    session = get_session()
    try:
        part = PartsService.create(session, data)
        
        # Process staged KiCad files if any
        if staging_session_id:
            staged_result = kicad_staging.process_staged_files(
                staging_session_id, 
                dmtuid=part.dmtuid,
                tt=part.tt,
                ff=part.ff,
                value=part.value,
                mpn=part.mpn,
                kicad_footprint=part.kicad_footprint
            )
            # Update part with KiCad field references from staged files
            if staged_result.get('symbol_ref'):
                part.kicad_symbol = staged_result['symbol_ref']
            if staged_result.get('footprint_ref'):
                part.kicad_footprint = staged_result['footprint_ref']
            if staged_result.get('model3d_name'):
                part.kicad_3dmodel = staged_result['model3d_name']
        
        # Auto-populate kicad_footprint and kicad_3dmodel from "Package / Case" if not set
        if not part.kicad_footprint:
            package_case = data.get("Package / Case", "")
            derived_fp, derived_3d = derive_footprint_from_package(package_case, part.ff)
            if derived_fp:
                part.kicad_footprint = derived_fp
            if derived_3d and not part.kicad_3dmodel:
                part.kicad_3dmodel = derived_3d
        
        # Auto-generate symbol for passive components
        lib_key = (part.tt, part.ff)
        if lib_key in PASSIVE_LIBRARY_MAP:
            lib_name = PASSIVE_LIBRARY_MAP[lib_key]
            lib_path = config.KICAD_SYMBOLS_DIR / f"{lib_name}.kicad_sym"
            
            # Generate the symbol - returns "added", "exists", or "error"
            result = KiCadSymbolProcessor.generate_passive_symbol(part, lib_path)
            if result in ("added", "exists"):
                # Build symbol reference: "LibName:Value MPN"
                value = part.value or ""
                mpn = part.mpn or ""
                mpn_sanitized = re.sub(r'[<>:"/\\|?*]', '_', mpn)
                if value and mpn_sanitized:
                    symbol_name = f"{value} {mpn_sanitized}"
                elif mpn_sanitized:
                    symbol_name = mpn_sanitized
                else:
                    symbol_name = value
                
                # Set kicad_symbol on the part
                part.kicad_symbol = f"{lib_name}:{symbol_name}"
        
        session.commit()
        flash(f"Part {part.dmtuid} created.", "success")
        return redirect(url_for("ui.part_detail", dmtuid=part.dmtuid))
    except Exception as exc:
        session.rollback()
        flash(f"Error: {exc}", "danger")
        return redirect(url_for("ui.part_add"))
    finally:
        session.close()


# ── Edit ───────────────────────────────────────────────────────────────

@ui_bp.route("/part/<dmtuid>/edit", methods=["GET", "POST"])
def part_edit(dmtuid: str):
    session = get_session()
    try:
        part = PartsService.get(session, dmtuid)
        if not part:
            abort(404)
        template = get_fields(part.tt, part.ff)
        domains = get_domains()

        if request.method == "GET":
            return render_template(
                "add_edit.html", part=part, domains=domains,
                template_fields=template, mode="edit",
            )

        # POST
        data = dict(request.form)
        staging_session_id = data.pop('staging_session_id', None)
        
        PartsService.update(session, part, data)
        
        # Process staged KiCad files if any
        if staging_session_id:
            staged_result = kicad_staging.process_staged_files(
                staging_session_id, 
                dmtuid=part.dmtuid,
                tt=part.tt,
                ff=part.ff,
                value=part.value,
                mpn=part.mpn,
                kicad_footprint=part.kicad_footprint
            )
            # Update part with KiCad field references from staged files
            if staged_result.get('symbol_ref'):
                part.kicad_symbol = staged_result['symbol_ref']
            if staged_result.get('footprint_ref'):
                part.kicad_footprint = staged_result['footprint_ref']
            if staged_result.get('model3d_name'):
                part.kicad_3dmodel = staged_result['model3d_name']
        
        # Auto-populate kicad_footprint and kicad_3dmodel from "Package / Case" if not set
        if not part.kicad_footprint:
            package_case = data.get("Package / Case", "")
            derived_fp, derived_3d = derive_footprint_from_package(package_case, part.ff)
            if derived_fp:
                part.kicad_footprint = derived_fp
            if derived_3d and not part.kicad_3dmodel:
                part.kicad_3dmodel = derived_3d
        
        # Auto-generate/regenerate symbol for passive components
        lib_key = (part.tt, part.ff)
        if lib_key in PASSIVE_LIBRARY_MAP:
            lib_name = PASSIVE_LIBRARY_MAP[lib_key]
            lib_path = config.KICAD_SYMBOLS_DIR / f"{lib_name}.kicad_sym"
            
            # Generate symbol - returns "added", "exists", or "error"
            result = KiCadSymbolProcessor.generate_passive_symbol(part, lib_path)
            if result in ("added", "exists"):
                # Build symbol reference: "LibName:Value MPN"
                value = part.value or ""
                mpn = part.mpn or ""
                mpn_sanitized = re.sub(r'[<>:"/\\|?*]', '_', mpn)
                if value and mpn_sanitized:
                    symbol_name = f"{value} {mpn_sanitized}"
                elif mpn_sanitized:
                    symbol_name = mpn_sanitized
                else:
                    symbol_name = value
                
                # Update kicad_symbol reference
                part.kicad_symbol = f"{lib_name}:{symbol_name}"
        
        session.commit()
        flash(f"Part {dmtuid} updated.", "success")
        return redirect(url_for("ui.part_detail", dmtuid=dmtuid))
    except Exception as exc:
        session.rollback()
        flash(f"Error: {exc}", "danger")
        return redirect(url_for("ui.part_edit", dmtuid=dmtuid))
    finally:
        session.close()


# ── Delete ─────────────────────────────────────────────────────────────

@ui_bp.route("/part/<dmtuid>/delete", methods=["POST"])
def part_delete(dmtuid: str):
    session = get_session()
    try:
        part = PartsService.get(session, dmtuid)
        if not part:
            abort(404)
        PartsService.delete(session, part)
        session.commit()
        flash(f"Part {dmtuid} deleted.", "success")
        return redirect(url_for("ui.index"))
    except Exception as exc:
        session.rollback()
        flash(f"Error: {exc}", "danger")
        return redirect(url_for("ui.part_detail", dmtuid=dmtuid))
    finally:
        session.close()


# ── Client Setup ────────────────────────────────────────────────────────

@ui_bp.route("/client-setup")
def client_setup():
    """Render the client setup page for configuring local KiCad paths."""
    return render_template("client_setup.html")
