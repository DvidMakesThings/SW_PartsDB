"""Read-only inventory migration report; never posts opening balances."""
from flask import jsonify, render_template, request, abort
from sqlalchemy import select

from db import get_session
from db.models import Part, StockMovement, StockHolding, InventoryOperation, StockReservation
from services.inventory_preview import preview_inventory
from services import inventory_service as inventory
from ui import ui_bp


@ui_bp.route("/inventory/migration-preview")
def inventory_migration_preview():
    with get_session() as session:
        rows = session.execute(select(Part.dmtuid, Part.mpn, Part.quantity, Part.location)
                               .order_by(Part.dmtuid)).mappings().all()
        report = preview_inventory(rows)
    if request.args.get("format") == "json":
        response = jsonify(report)
        response.headers["Content-Disposition"] = 'attachment; filename="inventory-preview.json"'
    else:
        scope = request.args.get("status", "all")
        if scope not in {"all", "known", "unknown", "review"}:
            scope = "all"
        try:
            page = max(1, int(request.args.get("page", "1")))
        except ValueError:
            page = 1
        items = [item for item in report["items"] if scope == "all" or item["count_status"] == scope]
        pages = max(1, (len(items) + 99) // 100)
        page = min(page, pages)
        response = render_template("inventory_preview.html", report=report,
                                   items=items[(page - 1) * 100:page * 100],
                                   scope=scope, page=page, pages=pages)
    return response


@ui_bp.route("/part/<dmtuid>/stock")
def stock_history(dmtuid):
    with get_session() as session:
        part = session.get(Part, dmtuid.upper())
        if part is None:
            abort(404)
        try:
            page = max(1, int(request.args.get("page", "1")))
        except ValueError:
            page = 1
        rows = inventory.holdings(session, part.dmtuid)
        query = session.query(StockMovement, InventoryOperation).join(InventoryOperation).join(StockHolding)
        query = query.filter(StockHolding.dmtuid == part.dmtuid)
        pages = max(1, (query.count() + 49) // 50)
        page = min(page, pages)
        history = query.order_by(StockMovement.id.desc()).offset((page-1)*50).limit(50).all()
        reservations = session.scalars(select(StockReservation).join(StockHolding)
                           .where(StockHolding.dmtuid == part.dmtuid, StockReservation.quantity > 0)).all()
        return render_template("stock_history.html", part=part, holdings=rows, history=history,
                               reservations=reservations, stock=inventory.summary(session, part.dmtuid),
                               page=page, pages=pages)
