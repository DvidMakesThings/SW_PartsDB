"""CSV imports with stock review, row savepoints and durable run idempotency."""
import hashlib
import uuid

from sqlalchemy import select
from db.engine import get_session
from db.models import Part, StockHolding
from import_engine.csv_parser import prepare_reader
from import_engine.row_processor import RowProcessor, RowError
from import_engine.report import ImportReport


def run_import(file_content, *, replace_existing=False, operation_key=None,
               preview=False, expected_inventory=None):
    from services.inventory_service import lock_inventory, operation, digest
    report = ImportReport(preview=preview)
    reader = prepare_reader(file_content)
    if reader is None:
        report.add_error(0, "CSV has no header row or is empty")
        return report
    raw = file_content.encode() if isinstance(file_content, str) else file_content
    file_hash = hashlib.sha256(raw).hexdigest()
    run_key = operation_key or hashlib.sha256(raw + str(replace_existing).encode()).hexdigest()
    if preview:
        # Previews always simulate the latest state, even for a previously
        # imported file; all temporary operations roll back below.
        run_key = "preview-" + uuid.uuid4().hex
    session = get_session()
    processor = RowProcessor()
    try:
        lock_inventory(session)  # SQLite outer transaction before SAVEPOINTs.
        payload = {"file": file_hash, "replace": replace_existing}
        with operation(session, "csv-run:" + run_key, payload, "csv-import", "CSV import") as (op, result):
            if op is None:
                return ImportReport(**result)
            report.inventory_fingerprint = digest({
                "parts": [list(r) for r in session.execute(select(Part.dmtuid, Part.quantity, Part.location).order_by(Part.dmtuid))],
                "holdings": [list(r) for r in session.execute(select(StockHolding.id, StockHolding.version).order_by(StockHolding.id))]})
            if expected_inventory and report.inventory_fingerprint != expected_inventory:
                raise ValueError("Inventory changed since the preview; upload again to review current counts")
            for row_idx, row in enumerate(reader, start=2):
                report.total_rows += 1
                try:
                    with session.begin_nested():
                        existing = session.get(Part, (row.get("DMTUID") or "").strip().upper())
                        before = existing.quantity if existing else None
                        location = existing.location if existing else None
                        row["_inventory_key"] = "csv:" + run_key + ":" + str(row_idx)
                        part = processor.process(session, row, replace_existing)
                        session.flush()
                        if any(k in row for k in ("Quantity", "Location")):
                            report.changes.append({"row":row_idx, "dmtuid":part.dmtuid,
                                "before":before, "after":part.quantity,
                                "old_location":location, "location":part.location})
                    report.imported += 1
                except Exception as exc:
                    report.add_error(row_idx, str(exc) if isinstance(exc, (RowError, ValueError)) else "Row failed validation; no changes for this row")
            result.update(report.to_dict())
        if preview:
            session.rollback()
        else:
            session.commit()
    except Exception as exc:
        session.rollback()
        report.imported = 0
        report.changes = []
        report.add_error(0, str(exc) if isinstance(exc, ValueError) else "Import failed; all changes rolled back")
    finally:
        session.close()
    return report
