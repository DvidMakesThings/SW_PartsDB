"""
import_engine.importer - Top-level orchestrator.

Coordinates csv_parser → row_processor → DB commit and produces
a structured ImportReport.
"""

from __future__ import annotations

from db.engine import get_session
from import_engine.csv_parser import prepare_reader
from import_engine.row_processor import RowProcessor, RowError
from import_engine.report import ImportReport


def run_import(
    file_content: str | bytes,
    *,
    replace_existing: bool = False,
) -> ImportReport:
    """
    Import a CSV blob into the database.

    Parameters
    ----------
    file_content : raw CSV (bytes or str)
    replace_existing : if True, overwrite rows with duplicate DMTUIDs

    Returns
    -------
    ImportReport with per-row error details
    """
    report = ImportReport()
    reader = prepare_reader(file_content)
    if reader is None:
        report.add_error(0, "CSV has no header row or is empty")
        return report

    session = get_session()
    processor = RowProcessor()

    try:
        for row_idx, row in enumerate(reader, start=2):   # row 1 = header
            report.total_rows += 1
            try:
                part = processor.process(session, row, replace_existing)
                session.add(part)
                session.flush()
                report.imported += 1
            except RowError as exc:
                report.add_error(row_idx, str(exc))
            except Exception as exc:
                report.add_error(row_idx, f"Unexpected: {exc}")

        session.commit()
    except Exception as exc:
        session.rollback()
        report.add_error(0, f"Fatal import error: {exc}")
    finally:
        session.close()

    return report
