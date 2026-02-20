"""
import_engine.row_processor - Validate and transform one CSV row into a Part.

Single-responsibility: given a dict-row and a session, either return
a Part object ready to be added, or raise RowError.
"""

from __future__ import annotations

import json
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import Part, PartField
from schema.numbering import build_dmtuid, parse_dmtuid, validate_segments
from schema.loader import valid_tt
from schema.templates import get_fields
from import_engine.field_map import DIRECT_FIELDS, SKIP_FOR_EAV


class RowError(Exception):
    """Raised when a row cannot be imported."""
    pass


class RowProcessor:
    """
    Stateful processor that tracks XXX allocation within an import run
    to avoid collisions between rows in the same batch.
    """

    def __init__(self):
        self._xxx_cache: dict[str, int] = {}   # "TTFFCCSS" → last assigned int

    def process(
        self,
        session: Session,
        row: dict,
        replace: bool,
    ) -> Part:
        """
        Validate one row, resolve its DMTUID, build a Part.
        Raises RowError on any problem.
        """
        tt, ff, cc, ss, xxx, dmtuid = self._resolve_uid(session, row)

        # Duplicate check
        existing = session.get(Part, dmtuid)
        if existing and not replace:
            raise RowError(f"Duplicate DMTUID {dmtuid} (enable replace to overwrite)")
        if existing:
            session.delete(existing)
            session.flush()

        part = Part(dmtuid=dmtuid, tt=tt, ff=ff, cc=cc, ss=ss, xxx=xxx)

        # Direct (indexed) fields
        for csv_col, attr in DIRECT_FIELDS.items():
            val = (row.get(csv_col) or "").strip()
            if val:
                setattr(part, attr, val)

        # Template-driven EAV fields
        self._apply_template_fields(part, row)

        return part

    # ── Private helpers ────────────────────────────────────────────────

    def _resolve_uid(self, session: Session, row: dict):
        """Return (tt, ff, cc, ss, xxx, dmtuid) or raise RowError."""
        dmtuid_raw = (row.get("DMTUID") or "").strip()
        parsed = parse_dmtuid(dmtuid_raw) if dmtuid_raw else None

        if parsed:
            tt, ff, cc, ss, xxx = (
                parsed["tt"], parsed["ff"], parsed["cc"],
                parsed["ss"], parsed["xxx"],
            )
            return tt, ff, cc, ss, xxx, dmtuid_raw.upper()

        # Fall back to explicit TT/FF/CC/SS columns
        tt = (row.get("TT") or "").strip().zfill(2) if row.get("TT") else ""
        ff = (row.get("FF") or "").strip().zfill(2) if row.get("FF") else ""
        cc = (row.get("CC") or "").strip().zfill(2) if row.get("CC") else ""
        ss = (row.get("SS") or "").strip().zfill(2) if row.get("SS") else ""

        if not (tt and ff and cc and ss):
            raise RowError("Missing DMTUID and insufficient TT/FF/CC/SS columns")

        err = validate_segments(tt, ff, cc, ss)
        if err:
            raise RowError(err)

        if not valid_tt(tt):
            raise RowError(f"Unknown domain TT={tt}")

        xxx = self._next_xxx(session, tt, ff, cc, ss)
        return tt, ff, cc, ss, xxx, build_dmtuid(tt, ff, cc, ss, xxx)

    def _next_xxx(self, session: Session, tt: str, ff: str, cc: str, ss: str) -> str:
        """Allocate the next XXX for a TTFFCCSS group."""
        group = f"{tt}{ff}{cc}{ss}"
        if group in self._xxx_cache:
            self._xxx_cache[group] += 1
        else:
            db_max = session.query(func.max(Part.xxx)).filter(
                Part.tt == tt, Part.ff == ff,
                Part.cc == cc, Part.ss == ss,
            ).scalar()
            self._xxx_cache[group] = (int(db_max) if db_max else 0) + 1

        val = self._xxx_cache[group]
        if val > 999:
            raise RowError(f"XXX overflow for group {group}")
        return f"{val:03d}"

    @staticmethod
    def _apply_template_fields(part: Part, row: dict):
        """Add EAV fields allowed by the template, or dump to extra_json."""
        template = get_fields(part.tt, part.ff)

        if template:
            allowed = set(template) - SKIP_FOR_EAV
            for col in allowed:
                val = (row.get(col) or "").strip()
                if val:
                    part.fields.append(PartField(field_name=col, field_value=val))
        else:
            # No template → store everything non-empty as JSON
            extra: dict[str, str] = {}
            for k, v in row.items():
                if k in SKIP_FOR_EAV:
                    continue
                v = (v or "").strip()
                if v:
                    extra[k] = v
            if extra:
                part.extra_json = json.dumps(extra, ensure_ascii=False)
