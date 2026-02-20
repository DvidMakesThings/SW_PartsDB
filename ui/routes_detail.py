"""
ui.routes_detail - Part detail view.
"""

from flask import render_template, abort

from ui import ui_bp
from db import get_session
from services.parts_service import PartsService
from schema.loader import domain_name, family_name
from schema.templates import get_fields


@ui_bp.route("/part/<dmtuid>")
def part_detail(dmtuid: str):
    session = get_session()
    try:
        part = PartsService.get(session, dmtuid)
        if not part:
            abort(404)
        template = get_fields(part.tt, part.ff)
        return render_template(
            "detail.html",
            part=part,
            template=template,
            domain_name=domain_name,
            family_name=family_name,
        )
    finally:
        session.close()
