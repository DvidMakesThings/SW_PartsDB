"""Frozen BOMs and transactional, replay-safe assembly postings."""
import csv
import io
import json
import re
from sqlalchemy import select
from db.models import (AssemblyDefinition, BuildBatch, BuildPosting, DesignRelease, Part,
                       StockReservation, PhysicalUnit)
from services import inventory_service as stock
from services import design_service as designs


def positive(value, label, maximum=1000000):
    if not re.fullmatch(r"[0-9]+", str(value or "")) or not 1 <= int(value) <= maximum:
        raise ValueError(f"{label} must be a whole number from 1 to {maximum}")
    return int(value)


def parse_bom(raw):
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("BOM exceeds 10 MiB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("Export the BOM as UTF-8 CSV") from None
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV header is required")
    aliases = {"reference":"refs", "references":"refs", "refs":"refs", "designator":"refs", "designators":"refs",
               "quantity":"quantity", "qty":"quantity", "dmtuid":"part_id", "value":"value", "footprint":"footprint",
               "mpn":"mpn", "manufacturer":"manufacturer", "mfr":"manufacturer", "dnp":"dnp", "source":"source"}
    mapped = {name: aliases.get(name.strip().casefold()) for name in reader.fieldnames}
    if "refs" not in mapped.values():
        raise ValueError("BOM needs Reference/Refs/Designator, Quantity and DMTUID columns; see the example")
    rows, seen = [], set()
    for line, original in enumerate(reader, 2):
        if line > 5002:
            raise ValueError("BOM exceeds 5000 lines")
        if None in original:
            raise ValueError(f"Line {line}: invalid CSV columns; quote grouped references")
        data = {mapped[k]: (v or "").strip() for k,v in original.items() if mapped.get(k)}
        refs = [r.upper() for r in re.split(r"[,;\s]+", data.get("refs", "")) if r]
        if not refs or any(not re.fullmatch(r"[A-Z][A-Z0-9_.-]*[0-9][A-Z0-9_.-]*", r) for r in refs):
            raise ValueError(f"Line {line}: invalid or missing reference designators (expand ranges)")
        if len(refs) != len(set(refs)) or seen.intersection(refs):
            raise ValueError(f"Line {line}: repeated reference designator")
        seen.update(refs)
        qty = positive(data.get("quantity") or len(refs), "Quantity")
        if qty != len(refs):
            raise ValueError(f"Line {line}: quantity does not equal the number of references")
        dnp = data.get("dnp", "").casefold()
        if dnp not in {"", "0", "no", "false", "1", "yes", "true", "dnp"}:
            raise ValueError(f"Line {line}: DNP must be yes/no")
        source = data.get("source", "personal").casefold() or "personal"
        if source not in {"personal", "external"}:
            raise ValueError(f"Line {line}: Source must be personal or external")
        rows.append({**data, "refs": refs, "quantity": qty, "part_id": data.get("part_id", "").upper(),
                     "dnp": dnp in {"1", "yes", "true", "dnp"}, "source": source})
    if not rows:
        raise ValueError("BOM is empty")
    return rows


def bom_errors(db, lines):
    return [", ".join(line["refs"]) + ": select a concrete DMTUID" for line in lines
            if not line["dnp"] and (not line.get("part_id") or not db.get(Part, line["part_id"]))]


def import_bom(db, release_id, raw, filename):
    stock.lock_inventory(db)
    release = db.get(DesignRelease, release_id, populate_existing=True)
    if not release or release.status != "draft":
        raise ValueError("Import or edit the BOM on a draft release; published assembly definitions are frozen")
    lines = parse_bom(raw)
    from services.library_catalog import Matcher, normalize_properties
    from types import SimpleNamespace
    matcher = Matcher(db)
    for line in lines:
        if not line.get("part_id") and not line["dnp"]:
            candidate = SimpleNamespace(normalized_json=json.dumps(normalize_properties(line)),
                reviewed_identity_json="{}", part_id=None, missing=False, decision="unresolved",
                reviewed_hash="", content_hash="", seen_commit="", source=SimpleNamespace(indexed_commit=""))
            match = matcher.evaluate(candidate)
            if match["state"] == "match":
                line["part_id"] = match["part_id"]
    artifact = designs.add_artifact(db, io.BytesIO(raw), filename, "bom", release_id=release_id,
                                  provenance="Original assembly BOM CSV")
    definition = db.scalar(select(AssemblyDefinition).where(AssemblyDefinition.release_id == release_id))
    if not definition:
        definition = AssemblyDefinition(release_id=release_id)
        db.add(definition)
    definition.source_artifact_id, definition.lines_json = artifact.id, json.dumps(lines)
    db.flush()
    return definition


def map_bom(db, release_id, mappings):
    stock.lock_inventory(db)
    definition = db.scalar(select(AssemblyDefinition).where(AssemblyDefinition.release_id == release_id))
    if not definition or definition.release.status != "draft":
        raise ValueError("Only draft BOM mappings can be edited")
    lines = json.loads(definition.lines_json)
    for i, line in enumerate(lines):
        line["part_id"] = mappings.get(f"part_{i}", "").strip().upper()
        line["source"] = mappings.get(f"source_{i}", "personal")
        line["dnp"] = mappings.get(f"dnp_{i}") == "yes"
        if line["source"] not in {"personal", "external"}:
            raise ValueError("Choose personal stock or external/factory supply")
        if line["part_id"] and not db.get(Part, line["part_id"]):
            raise ValueError("Unknown DMTUID: " + line["part_id"])
    definition.lines_json = json.dumps(lines)
    db.flush()
    return definition


def create_build(db, release_id, quantity, notes=""):
    stock.lock_inventory(db)
    release = db.get(DesignRelease, release_id)
    definition = db.scalar(select(AssemblyDefinition).where(AssemblyDefinition.release_id == release_id))
    if not release or release.status not in {"released", "superseded"} or not definition:
        raise ValueError("Choose a published revision with a mapped assembly BOM")
    errors = bom_errors(db, json.loads(definition.lines_json))
    if errors:
        raise ValueError("Unresolved BOM: " + "; ".join(errors[:5]))
    build = BuildBatch(release_id=release.id, quantity=positive(quantity, "Board count", 1000), notes=notes.strip())
    db.add(build)
    db.flush()
    return build


def plan(db, build_id, quantity, substitutions=None, serials=None):
    build = db.get(BuildBatch, build_id, populate_existing=True)
    if not build or build.status in {"cancelled", "completed"}:
        raise ValueError("Choose an open build")
    quantity = positive(quantity, "Assembly count", 1000)
    if quantity > build.quantity - build.completed_quantity:
        raise ValueError("Assembly count exceeds the remaining planned quantity")
    definition = db.scalar(select(AssemblyDefinition).where(AssemblyDefinition.release_id == build.release_id))
    lines = json.loads(definition.lines_json)
    substitutions = substitutions or {}
    serials = [s.strip() for s in (serials or []) if s.strip()]
    if serials and (len(serials) != quantity or len({s.casefold() for s in serials}) != quantity):
        raise ValueError("Enter one distinct serial per unit, or leave all serials blank for generation")
    required, actual = {}, []
    for i, line in enumerate(lines):
        replacement = substitutions.get(str(i), {})
        uid = replacement.get("part_id", "").strip().upper() or line.get("part_id", "")
        reason = replacement.get("reason", "").strip()
        if not line["dnp"] and not db.get(Part, uid):
            raise ValueError("Unresolved BOM part: " + ", ".join(line["refs"]))
        if uid != line.get("part_id", "") and not reason:
            raise ValueError("A substitution requires a reason")
        actual.append({**line, "actual_part_id": uid, "substitution_reason": reason})
        if not line["dnp"] and line["source"] == "personal":
            required[uid] = required.get(uid, 0) + line["quantity"] * quantity
    reference = f"build:{build.id}"
    own = {r.holding_id: r.quantity for r in db.scalars(select(StockReservation).where(StockReservation.reference == reference))}
    allocations, shortages, states, materials = [], [], [], []
    for uid, amount in sorted(required.items()):
        left, available = amount, 0
        for h in stock.holdings(db, uid):
            states.append([h.id, h.version, h.on_hand, h.reserved, h.count_known, own.get(h.id, 0)])
            if not h.count_known:
                continue
            capacity = h.on_hand - h.reserved + own.get(h.id, 0)
            available += capacity
            take = min(left, capacity)
            if take:
                allocations.append({"holding_id": h.id, "quantity": take})
                left -= take
        materials.append({"part_id": uid, "required": amount, "available": available, "shortage": left})
        if left:
            shortages.append(f"{uid}: missing {left} (unknown counts cannot be consumed)")
    request = {"build_id": build.id, "quantity": quantity, "substitutions": substitutions, "serials": serials}
    return {"request": request, "allocations": allocations, "materials": materials, "shortages": shortages,
            "actual_bom": actual, "fingerprint": stock.digest([build.completed_quantity, build.status, states])}


def apply(db, build_id, reviewed, key, action="assemble"):
    stock.lock_inventory(db)
    payload = {"build_id": build_id, "reviewed": reviewed, "action": action}
    fingerprint = stock.digest(payload)
    existing = db.scalar(select(BuildPosting).where(BuildPosting.operation_key == key))
    if existing:
        if existing.payload_hash != fingerprint:
            raise ValueError("Operation key was already used with different input")
        return existing
    if not key or len(key) > 150 or action not in {"assemble", "reserve"}:
        raise ValueError("Invalid assembly operation")
    request = reviewed["request"]
    if request["build_id"] != build_id:
        raise ValueError("Review belongs to a different build")
    current = plan(db, build_id, request["quantity"], request["substitutions"], request["serials"])
    if current["fingerprint"] != reviewed["fingerprint"] or current["shortages"]:
        raise ValueError("Stock or build state changed, or parts are missing. Review the build again; nothing was deducted")
    build = db.get(BuildBatch, build_id)
    ref = f"build:{build.id}"
    result = {"actual_bom": current["actual_bom"], "unit_ids": [], "movement_ids": []}
    if action == "reserve":
        allocations = list(current["allocations"])
        selected = {a["holding_id"] for a in allocations}
        allocations += [{"holding_id": r.holding_id, "quantity": 0} for r in db.scalars(select(StockReservation).where(StockReservation.reference == ref)) if r.holding_id not in selected]
        stock.reserve(db, ref, allocations, key="build-reserve:"+key, actor="web-interface", reason="Reserve build materials")
        build.status = "reserved"
    else:
        if current["allocations"]:
            result.update(stock.consume(db, ref, current["allocations"], key="build-assemble:"+key,
                                         actor="web-interface", reason="Assemble reviewed prototype batch"))
        for index in range(request["quantity"]):
            unit = designs.register_unit(db, build.release.board_id,
                request["serials"][index] if request["serials"] else "", historical=False,
                release_id=build.release_id, generate_serial=not request["serials"], notes=f"Assembled in build #{build.id}")
            unit.build_id = build.id
            result["unit_ids"].append(unit.id)
        build.completed_quantity += request["quantity"]
        build.status = "completed" if build.completed_quantity == build.quantity else "in-progress"
        if build.status == "completed":
            release_reservations(db, ref, "build-complete:"+key)
    result["allocations"] = current["allocations"]
    posting = BuildPosting(build_id=build.id, operation_key=key, payload_hash=fingerprint, kind=action,
        quantity=request["quantity"] if action == "assemble" else 0, details_json=json.dumps(result))
    db.add(posting)
    db.flush()
    return posting


def release_reservations(db, reference, key):
    rows = [{"holding_id": r.holding_id, "quantity": 0} for r in db.scalars(select(StockReservation).where(
        StockReservation.reference == reference, StockReservation.quantity > 0))]
    if rows:
        stock.reserve(db, reference, rows, key=key, actor="web-interface", reason="Release unused build reservations")


def cancel(db, build_id, reason, key):
    stock.lock_inventory(db)
    reason = designs.required(reason, "Cancellation reason / treatment of consumed material", 10000)
    build = db.get(BuildBatch, build_id, populate_existing=True)
    if not build or build.status == "completed":
        raise ValueError("Completed builds cannot be cancelled; record a unit repair/return instead")
    if build.status == "cancelled":
        return build
    release_reservations(db, f"build:{build.id}", "build-cancel:"+key)
    build.status = "cancelled"
    db.add(BuildPosting(build_id=build.id, operation_key=key, payload_hash=stock.digest([build.id, reason]),
        kind="cancel", quantity=0, details_json=json.dumps({"reason":reason,"consumed_stock_returned":False})))
    db.flush()
    return build


def return_material(db, build_id, movement_id, quantity, reason, key):
    from db.models import StockMovement
    stock.lock_inventory(db)
    amount = positive(quantity, "Recovered quantity")
    reason = designs.required(reason, "Return reason", 10000)
    payload_hash = stock.digest([build_id, movement_id, amount, reason])
    existing = db.scalar(select(BuildPosting).where(BuildPosting.operation_key == key))
    if existing:
        if existing.payload_hash != payload_hash:
            raise ValueError("Operation key was reused with different input")
        return existing
    movement = db.get(StockMovement, movement_id)
    if not movement or movement.reference != f"build:{build_id}":
        raise ValueError("Choose a consumption movement from this build")
    result = stock.return_stock(db, movement_id, amount, key="build-return:"+key, actor="web-interface", reason=reason)
    posting = BuildPosting(build_id=build_id, operation_key=key, payload_hash=payload_hash, kind="return", quantity=0,
        details_json=json.dumps({**result, "original_movement_id":movement_id, "returned_components":amount, "reason":reason}))
    db.add(posting)
    db.flush()
    return posting
