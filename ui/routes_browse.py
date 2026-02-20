"""
ui.routes_browse - Main browse / search table page.
"""

import json
from flask import request, render_template

from ui import ui_bp
from db import get_session
from services.search_service import SearchService
from schema.loader import get_domains, domain_name, family_name
import config


@ui_bp.route("/")
def index():
    q     = request.args.get("q", "").strip()
    tt    = request.args.get("tt", "").strip()
    ff    = request.args.get("ff", "").strip()
    cc    = request.args.get("cc", "").strip()
    ss    = request.args.get("ss", "").strip()
    props = request.args.get("props", "").strip()
    page  = max(int(request.args.get("page", 1)), 1)

    # Parse property filters from JSON
    props_parsed = {}
    if props:
        try:
            props_parsed = json.loads(props)
        except json.JSONDecodeError:
            props_parsed = {}

    session = get_session()
    try:
        parts, total = SearchService.search(
            session, q=q, tt=tt, ff=ff, cc=cc, ss=ss, props=props_parsed,
            limit=config.DEFAULT_PAGE_SIZE,
            offset=(page - 1) * config.DEFAULT_PAGE_SIZE,
        )
        total_pages = max((total + config.DEFAULT_PAGE_SIZE - 1) //
                          config.DEFAULT_PAGE_SIZE, 1)
        return render_template(
            "index.html",
            parts=parts, q=q, tt=tt, ff=ff, cc=cc, ss=ss,
            props=props, props_parsed=props_parsed,
            page=page, total_pages=total_pages, total=total,
            domains=get_domains(),
            domain_name=domain_name,
            family_name=family_name,
        )
    finally:
        session.close()
