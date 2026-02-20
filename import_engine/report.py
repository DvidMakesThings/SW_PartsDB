"""
import_engine.report - Structured result of a CSV import run.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImportReport:
    total_rows: int = 0
    imported: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)   # [{row, reason}]

    def add_error(self, row: int, reason: str):
        self.errors.append({"row": row, "reason": reason})
        self.skipped += 1

    def to_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "imported": self.imported,
            "skipped": self.skipped,
            "errors": self.errors,
        }
