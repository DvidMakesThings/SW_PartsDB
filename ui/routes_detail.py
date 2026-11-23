"""
ui.routes_detail - Part detail view.
"""

import json
from flask import render_template, abort

from ui import ui_bp
from db import get_session
from db.models import Part, PartImage, BoardDesign, PhysicalUnit, LibraryEntry, AssemblyDefinition
from services.parts_service import PartsService
from services.inventory_service import summary as inventory_summary
from services.design_service import serial_enabled
from services.supply_chain_service import get_pricing
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
        pricing_data = get_pricing(session, dmtuid)
        images = session.query(PartImage).filter(
            PartImage.dmtuid == dmtuid
        ).order_by(PartImage.position).all()
        return render_template(
            "detail.html",
            part=part,
            template=template,
            domain_name=domain_name,
            family_name=family_name,
            parse_distributors=parse_distributors,
            pricing_data=pricing_data,
            images=images,
            design_boards=session.query(BoardDesign).filter_by(part_id=part.dmtuid).all(),
            serial_units=session.query(PhysicalUnit).filter_by(part_id=part.dmtuid).filter(
                PhysicalUnit.archived.is_(False)).order_by(PhysicalUnit.serial_key).limit(50).all(),
            serial_tracking=serial_enabled(session, part),
            serial_counts={state: session.query(PhysicalUnit).filter_by(part_id=part.dmtuid, status=state, archived=False).count()
                           for state in ("active", "in-test", "faulty", "repaired", "retired", "waste")},
            library_entries=session.query(LibraryEntry).filter_by(part_id=part.dmtuid).all(),
            inventory=inventory_summary(session, part.dmtuid),
            used_assemblies=[a for a in session.query(AssemblyDefinition).all()
                             if any(line.get("part_id") == part.dmtuid for line in json.loads(a.lines_json))],
        )
    finally:
        session.close()
