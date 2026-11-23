"""Transactional inventory. Caller commits/rolls back; no network or filesystem work.

All operations acquire a database write lock before reading balances. An operation
and its movements share a transaction and persistent idempotency key. Nested
transactions ensure a rejected batch cannot leave partially applied deductions.
"""
from contextlib import contextmanager
import hashlib
import json
import uuid

from sqlalchemy import select, text, func
from db.models import Part, StockHolding, StockMovement, StockReservation, InventoryOperation
from services.inventory_preview import classify_quantity, MAX_QUANTITY


def lock_inventory(session):
    session.execute(text("UPDATE inventory_lock SET version = version WHERE id = 1"))


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


@contextmanager
def operation(session, key, payload, actor, reason):
    if not key or len(key) > 200 or not actor or not reason:
        raise ValueError("Inventory changes require an operation key, actor, and reason")
    lock_inventory(session)
    fingerprint = digest({"payload": payload, "actor": actor, "reason": reason})
    existing = session.get(InventoryOperation, key)
    if existing:
        if existing.payload_hash != fingerprint:
            raise ValueError("Idempotency key was already used with different input")
        yield None, json.loads(existing.result_json)
        return
    with session.begin_nested():
        record = InventoryOperation(key=key, payload_hash=fingerprint, actor=actor, reason=reason)
        session.add(record)
        session.flush()
        result = {}
        yield record, result
        record.result_json = json.dumps(result, sort_keys=True)
        session.flush()


def holdings(session, dmtuid):
    return list(session.scalars(select(StockHolding).where(StockHolding.dmtuid == dmtuid)
                .order_by(StockHolding.id).execution_options(populate_existing=True)))


def summary(session, dmtuid):
    return summarize_holdings(holdings(session, dmtuid))


def summarize_holdings(rows):
    known = sum(h.on_hand for h in rows)
    reserved = sum(h.reserved for h in rows)
    unknown = sum(not h.count_known for h in rows)
    state = "Not stocked" if not rows else "In stock" if known else "Unknown quantity" if unknown else "Out of stock"
    return {"status": state, "on_hand": known, "reserved": reserved,
            "available": known - reserved, "unknown_holdings": unknown,
            "locations": sorted({h.location for h in rows if h.location})}


def summaries(session, dmtuids):
    grouped = {uid: [] for uid in dmtuids}
    if grouped:
        for h in session.scalars(select(StockHolding).where(StockHolding.dmtuid.in_(grouped))):
            grouped[h.dmtuid].append(h)
    return {uid: summarize_holdings(rows) for uid, rows in grouped.items()}


def sync_cache(session, dmtuid):
    rows = holdings(session, dmtuid)
    part = session.get(Part, dmtuid)
    # Compatibility fields are derived, never an independent inventory balance.
    part.quantity = str(sum(h.on_hand for h in rows)) if rows and all(h.count_known for h in rows) else ""
    part.location = "; ".join(sorted({h.location for h in rows if h.location}))
    session.flush()


def _holding(session, holding_id):
    row = session.get(StockHolding, holding_id, populate_existing=True)
    if row is None:
        raise ValueError("Unknown stock holding")
    return row


def _amount(value, positive=True):
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0) or value > MAX_QUANTITY:
        raise ValueError("Quantity must be a nonnegative whole number in the supported range" if not positive else "Quantity must be a positive whole number in the supported range")
    return value


def _move(session, holding, key, kind, delta, reference="", reverses_id=None, details=None):
    balance = holding.on_hand + delta
    if balance < holding.reserved or balance < 0 or balance > MAX_QUANTITY:
        raise ValueError("Insufficient unreserved stock or quantity outside supported range")
    holding.on_hand = balance
    holding.version += 1
    move = StockMovement(holding_id=holding.id, operation_key=key, kind=kind,
                         delta=delta, balance_after=balance, count_known_after=holding.count_known,
                         reference=reference, reverses_id=reverses_id, details_json=json.dumps(details or {}))
    session.add(move)
    session.flush()
    return move.id


def stocktake(session, dmtuid, quantity, location, *, key, actor, reason, expected_version=None):
    """Compatibility edit for a single holding; blank does not erase known stock."""
    state, count, explanation = classify_quantity(quantity)
    if state == "review":
        raise ValueError(explanation)
    location = (location or "").strip()
    if len(location) > 200:
        raise ValueError("Location is too long")
    payload = {"action": "stocktake", "part": dmtuid, "quantity": count, "location": location,
               "expected_version": expected_version}
    with operation(session, key, payload, actor, reason) as (op, result):
        if op is None:
            return result
        if session.get(Part, dmtuid) is None:
            raise ValueError("Part does not exist")
        rows = holdings(session, dmtuid)
        if len(rows) > 1:
            # A legacy form's unchanged aggregate fields are harmless.
            current = summary(session, dmtuid)
            aggregate = sum(h.on_hand for h in rows) if all(h.count_known for h in rows) else None
            if count == aggregate and location == "; ".join(current["locations"]):
                result.update(current)
                return result
            raise ValueError("This part has multiple holdings; adjust a specific holding instead")
        if not rows and count is None and not location:
            result.update(summary(session, dmtuid))
            return result
        if rows:
            h = rows[0]
            if expected_version is not None and h.version != int(expected_version):
                raise ValueError("Stock changed since this form was opened; reload before saving")
            if h.count_known and count is None:
                raise ValueError("A known stock count cannot be cleared; enter the actual count")
        else:
            if expected_version not in (None, -1, "-1"):
                raise ValueError("Stock holding changed; reload before saving")
            h = StockHolding(dmtuid=dmtuid, location=location, lot="", count_known=False, on_hand=0, reserved=0, version=0)
            session.add(h)
            session.flush()
        old_location = h.location
        if old_location != location and h.reserved:
            raise ValueError("Release reservations before moving a holding")
        old_known = h.count_known
        old_count = h.on_hand
        h.location = location
        h.count_known = count is not None
        if count != (old_count if old_known else None) or old_location != location or h.version == 0:
            _move(session, h, key, "stocktake", (count or 0) - old_count,
                  details={"previous_location": old_location, "location": location,
                           "previous_count_known": old_known})
        sync_cache(session, dmtuid)
        result.update(summary(session, dmtuid))
    return result


def adjust(session, holding_id, delta, *, key, actor, reason, kind="receipt", reference=""):
    if kind not in {"receipt", "scrap", "correction"}:
        raise ValueError("Unsupported adjustment kind")
    if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0 or abs(delta) > MAX_QUANTITY:
        raise ValueError("Adjustment must be a nonzero whole number")
    if (kind == "receipt" and delta < 0) or (kind == "scrap" and delta > 0):
        raise ValueError("Adjustment direction does not match its kind")
    with operation(session, key, {"action": kind, "holding": holding_id, "delta": delta, "reference": reference}, actor, reason) as (op, result):
        if op is None:
            return result
        h = _holding(session, holding_id)
        if not h.count_known:
            raise ValueError("Count this unknown holding before adjusting it")
        result["movement_id"] = _move(session, h, key, kind, delta, reference)
        sync_cache(session, h.dmtuid)
    return result


def reserve(session, reference, allocations, *, key, actor, reason):
    """Set reservation amounts for specified holdings (zero releases a holding)."""
    if not reference or len(reference) > 200:
        raise ValueError("A reservation reference is required")
    with operation(session, key, {"action": "reserve", "reference": reference, "allocations": allocations}, actor, reason) as (op, result):
        if op is None:
            return result
        seen = set()
        for item in allocations:
            h = _holding(session, item["holding_id"])
            if h.id in seen:
                raise ValueError("Duplicate holding in allocation")
            seen.add(h.id)
            amount = _amount(item["quantity"], positive=False)
            if not h.count_known:
                raise ValueError("Cannot reserve an unknown count")
            r = session.scalar(select(StockReservation).where(StockReservation.holding_id == h.id,
                                StockReservation.reference == reference).execution_options(populate_existing=True))
            old = r.quantity if r else 0
            if h.reserved - old + amount > h.on_hand:
                raise ValueError("Insufficient available stock to reserve")
            if r is None:
                r = StockReservation(holding_id=h.id, reference=reference, quantity=0)
                session.add(r)
            r.quantity = amount
            h.reserved += amount - old
            h.version += 1
            session.flush()
        result.update({"reference": reference, "allocations": allocations})
    return result


def consume(session, reference, allocations, *, key, actor, reason):
    if not reference or len(reference) > 200 or not allocations:
        raise ValueError("Consumption requires a reference and allocations")
    with operation(session, key, {"action": "consume", "reference": reference, "allocations": allocations}, actor, reason) as (op, result):
        if op is None:
            return result
        result["movement_ids"] = []
        seen = set()
        for item in allocations:
            h = _holding(session, item["holding_id"])
            if h.id in seen:
                raise ValueError("Duplicate holding in allocation")
            seen.add(h.id)
            amount = _amount(item["quantity"])
            if not h.count_known:
                raise ValueError("Cannot consume an unknown count")
            own = session.scalar(select(StockReservation).where(StockReservation.holding_id == h.id,
                                  StockReservation.reference == reference).execution_options(populate_existing=True))
            reserved = own.quantity if own else 0
            if amount > h.on_hand - h.reserved + reserved:
                raise ValueError("Insufficient available stock to consume")
            released = min(reserved, amount)
            if own:
                own.quantity -= released
            h.reserved -= released
            result["movement_ids"].append(_move(session, h, key, "consumption", -amount, reference))
            sync_cache(session, h.dmtuid)
    return result


def return_stock(session, movement_id, amount, *, key, actor, reason):
    _amount(amount)
    with operation(session, key, {"action": "return", "movement": movement_id, "quantity": amount}, actor, reason) as (op, result):
        if op is None:
            return result
        original = session.get(StockMovement, movement_id)
        if not original or original.kind != "consumption":
            raise ValueError("Return must reference a consumption movement")
        returned = session.scalar(select(func.coalesce(func.sum(StockMovement.delta), 0))
                                  .where(StockMovement.reverses_id == movement_id))
        if amount + returned > -original.delta:
            raise ValueError("Return exceeds the original consumption")
        h = _holding(session, original.holding_id)
        if not h.count_known:
            raise ValueError("Count the destination holding before returning stock")
        result["movement_id"] = _move(session, h, key, "return", amount, original.reference, original.id)
        sync_cache(session, h.dmtuid)
    return result


def receive(session, dmtuid, amount, location, *, key, actor, reason, lot=""):
    _amount(amount)
    location, lot = location.strip(), lot.strip()
    if len(location) > 200 or len(lot) > 200:
        raise ValueError("Location or lot is too long")
    with operation(session, key, {"action": "receive", "part": dmtuid, "amount": amount,
                                 "location": location, "lot": lot}, actor, reason) as (op, result):
        if op is None:
            return result
        if session.get(Part, dmtuid) is None:
            raise ValueError("Part does not exist")
        h = session.scalar(select(StockHolding).where(StockHolding.dmtuid == dmtuid,
                           StockHolding.location == location, StockHolding.lot == lot)
                           .execution_options(populate_existing=True))
        if h is None:
            h = StockHolding(dmtuid=dmtuid, location=location, lot=lot, count_known=True,
                             on_hand=0, reserved=0, version=0)
            session.add(h)
            session.flush()
        if not h.count_known:
            raise ValueError("Count this unknown holding before receiving into it")
        result["holding_id"] = h.id
        result["movement_id"] = _move(session, h, key, "receipt", amount)
        sync_cache(session, dmtuid)
    return result


def transfer(session, source_id, destination_id, amount, *, key, actor, reason):
    _amount(amount)
    with operation(session, key, {"action": "transfer", "source": source_id,
                                 "destination": destination_id, "amount": amount}, actor, reason) as (op, result):
        if op is None:
            return result
        source, destination = _holding(session, source_id), _holding(session, destination_id)
        if source.id == destination.id or source.dmtuid != destination.dmtuid:
            raise ValueError("Transfer requires different holdings of the same part")
        if not source.count_known or not destination.count_known:
            raise ValueError("Count both holdings before transferring")
        result["movement_ids"] = [
            _move(session, source, key, "transfer_out", -amount, key),
            _move(session, destination, key, "transfer_in", amount, key)]
        sync_cache(session, source.dmtuid)
    return result


def legacy_edit(session, part, data, *, actor="legacy-interface", reason="Recorded stock count"):
    """Adapt existing part forms/API/CSV without allowing direct quantity writes."""
    if not any(k in data for k in ("Quantity", "quantity", "Location", "location")):
        return
    lock_inventory(session)
    session.refresh(part, ["quantity", "location"])
    value = data.get("Quantity", data.get("quantity", part.quantity))
    location = data.get("Location", data.get("location", part.location))
    return stocktake(session, part.dmtuid, value, location,
                     key=data.get("_inventory_key") or uuid.uuid4().hex,
                     actor=actor, reason=reason, expected_version=data.get("_stock_version"))


def reconcile(session):
    problems = []
    for h in session.scalars(select(StockHolding)):
        total = session.scalar(select(func.coalesce(func.sum(StockMovement.delta), 0)).where(StockMovement.holding_id == h.id))
        reserved = session.scalar(select(func.coalesce(func.sum(StockReservation.quantity), 0)).where(StockReservation.holding_id == h.id))
        if total != h.on_hand or reserved != h.reserved:
            problems.append({"holding_id": h.id, "ledger": total, "cached": h.on_hand,
                             "reserved": reserved, "cached_reserved": h.reserved})
    for part in session.scalars(select(Part)):
        rows = holdings(session, part.dmtuid)
        expected = sum(h.on_hand for h in rows) if rows and all(h.count_known for h in rows) else None
        state, count, _ = classify_quantity(part.quantity)
        locations = "; ".join(sorted({h.location for h in rows if h.location}))
        if state == "review" or count != expected or (part.location or "").strip() != locations:
            problems.append({"part": part.dmtuid, "error": "Legacy quantity/location cache disagrees with holdings"})
    return problems
