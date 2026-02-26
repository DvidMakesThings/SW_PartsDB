"""
ui.routes_detail - Part detail view.
"""

import json
from flask import render_template, abort

from ui import ui_bp
from db import get_session
from services.parts_service import PartsService
from schema.loader import domain_name, family_name
from schema.templates import get_fields


def parse_distributors(distributor_field: str) -> list:
    """
    Parse the distributor field which can be:
    - Empty/null → []
    - Single URL string (legacy) → []  (handled in template)
    - JSON array of {name, url} objects → list
    """
    if not distributor_field:
        return []
    try:
        data = json.loads(distributor_field)
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, TypeError):
        # Not JSON, it's a legacy single URL
        return []


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
            parse_distributors=parse_distributors,
        )
    finally:
        session.close()
