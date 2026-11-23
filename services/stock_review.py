"""Read-only review of changes submitted through the existing part form."""
from services.inventory_service import holdings, summarize_holdings
from services.inventory_preview import classify_quantity


def review_part_stock(session, part, data):
    rows = holdings(session, part.dmtuid) if part else []
    current = summarize_holdings(rows)
    raw = data.get("Quantity", data.get("quantity", part.quantity if part else ""))
    location = str(data.get("Location", data.get("location", part.location if part else ""))).strip()
    state, count, error = classify_quantity(raw)
    if state == "review":
        raise ValueError(error)
    previous = sum(h.on_hand for h in rows) if rows and all(h.count_known for h in rows) else None
    old_location = "; ".join(current["locations"])
    if count == previous and location == old_location:
        return None
    if len(rows) > 1:
        raise ValueError("This part has multiple holdings; use a holding-specific stock operation")
    if rows and rows[0].count_known and count is None:
        raise ValueError("A known count cannot be cleared; enter the actual count")
    expected = rows[0].version if rows else -1
    submitted_version = data.get("_stock_version")
    if submitted_version is not None and int(submitted_version) != expected:
        raise ValueError("Stock changed since this form was opened; reload before saving")
    return {"previous": previous, "proposed": count,
            "delta": count - (previous or 0) if count is not None else None,
            "old_location": old_location or "Unassigned", "location": location or "Unassigned",
            "version": expected, "new_part": part is None}
