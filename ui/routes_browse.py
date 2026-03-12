"""
ui.routes_browse - Main browse / search table page.
"""

import json
from flask import request, render_template

from ui import ui_bp
from db import get_session
from db.models import PartPricing
from services.search_service import SearchService
from schema.loader import get_domains, domain_name, family_name
import config


# Available page sizes
PAGE_SIZE_OPTIONS = [25, 50, 100, 200, 500]
DEFAULT_PER_PAGE = 100


@ui_bp.route("/")
def index():
    q     = request.args.get("q", "").strip()
    tt    = request.args.get("tt", "").strip()
    ff    = request.args.get("ff", "").strip()
    cc    = request.args.get("cc", "").strip()
    ss    = request.args.get("ss", "").strip()
    props = request.args.get("props", "").strip()
    page  = max(int(request.args.get("page", 1)), 1)
    sort_by = request.args.get("sort", "dmtuid").strip()
    sort_order = request.args.get("order", "asc").strip()
    
    # Get per_page with validation
    try:
        per_page = int(request.args.get("per_page", DEFAULT_PER_PAGE))
    except ValueError:
        per_page = DEFAULT_PER_PAGE
    if per_page not in PAGE_SIZE_OPTIONS:
        per_page = DEFAULT_PER_PAGE
    
    # Validate sort params
    if sort_by not in SearchService.SORTABLE_COLUMNS:
        sort_by = "dmtuid"
    if sort_order not in ("asc", "desc"):
        sort_order = "asc"

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
            sort_by=sort_by, sort_order=sort_order,
            limit=per_page,
            offset=(page - 1) * per_page,
        )
        total_pages = max((total + per_page - 1) // per_page, 1)

        # Build pricing lookup for displayed parts
        dmtuids = [p.dmtuid for p in parts]
        pricing_lookup = {}
        if dmtuids:
            rows = (
                session.query(PartPricing)
                .filter(PartPricing.dmtuid.in_(dmtuids), PartPricing.source == "LCSC")
                .all()
            )
            rate = config.USD_TO_EUR_RATE
            for r in rows:
                eur_price = ""
                if r.price_1:
                    try:
                        eur_price = f"{float(r.price_1) * rate:.4f}"
                    except (ValueError, TypeError):
                        pass
                pricing_lookup[r.dmtuid] = {
                    "lifecycle": r.lifecycle or "",
                    "price_eur": eur_price,
                }

        return render_template(
            "index.html",
            parts=parts, q=q, tt=tt, ff=ff, cc=cc, ss=ss,
            pricing_lookup=pricing_lookup,
            props=props, props_parsed=props_parsed,
            page=page, total_pages=total_pages, total=total,
            per_page=per_page, page_size_options=PAGE_SIZE_OPTIONS,
            sort_by=sort_by, sort_order=sort_order,
            domains=get_domains(),
            domain_name=domain_name,
            family_name=family_name,
        )
    finally:
        session.close()


@ui_bp.route("/libs")
def libs_page():
    """KiCad library file browser."""
    return render_template("libs.html")
