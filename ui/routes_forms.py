"""
ui.routes_forms - Add / Edit / Delete part forms.
"""

import re
from pathlib import Path
from flask import request, render_template, redirect, url_for, flash, abort

from ui import ui_bp
from db import get_session
from db.models import PartField
from services.parts_service import PartsService
from services.kicad_symbol_processor import KiCadSymbolProcessor
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
    session = get_session()
    try:
        part = PartsService.create(session, data)
        
        # Auto-generate symbol for passive components
        lib_key = (part.tt, part.ff)
        if lib_key in PASSIVE_LIBRARY_MAP:
            lib_name = PASSIVE_LIBRARY_MAP[lib_key]
            lib_path = Path(__file__).parent.parent / "kicad_libs" / "symbols" / f"{lib_name}.kicad_sym"
            
            # Generate the symbol
            if KiCadSymbolProcessor.generate_passive_symbol(part, lib_path):
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
        PartsService.update(session, part, data)
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
