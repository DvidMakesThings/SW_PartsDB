"""
ui.routes_forms - Add / Edit / Delete part forms.
"""

from flask import request, render_template, redirect, url_for, flash, abort

from ui import ui_bp
from db import get_session
from db.models import PartField
from services.parts_service import PartsService
from schema.loader import get_domains, domain_name, family_name
from schema.templates import get_fields
from schema.numbering import build_dmtuid
from services.sequence_service import next_xxx
from import_engine.field_map import DIRECT_FIELDS, SKIP_FOR_EAV


# ── Add ────────────────────────────────────────────────────────────────

@ui_bp.route("/part/add", methods=["GET", "POST"])
def part_add():
    domains = get_domains()

    if request.method == "GET":
        return render_template(
            "add_edit.html", part=None, domains=domains,
            template_fields=None, mode="add",
        )

    # POST: collect form data into a dict and delegate to PartsService
    data = dict(request.form)
    session = get_session()
    try:
        part = PartsService.create(session, data)
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
