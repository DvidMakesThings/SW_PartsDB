"""
services.parts_service - CRUD operations on Part records.

All session management is the caller's responsibility (open before,
close/commit after).  This keeps the service testable and allows
the caller to batch multiple operations in one transaction.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Part, PartField
from schema.numbering import build_dmtuid
from schema.templates import get_fields
from import_engine.field_map import DIRECT_FIELDS, SKIP_FOR_EAV
from services.sequence_service import next_xxx


class PartsService:

    # ── Create ─────────────────────────────────────────────────────────

    @staticmethod
    def create(session: Session, data: dict) -> Part:
        """
        Create a new Part from a dict of field values.
        Required keys: tt, ff, cc, ss.  XXX is auto-assigned.
        """
        tt = str(data.get("tt", "")).zfill(2)
        ff = str(data.get("ff", "")).zfill(2)
        cc = str(data.get("cc", "")).zfill(2)
        ss = str(data.get("ss", "")).zfill(2)

        xxx = next_xxx(session, tt, ff, cc, ss)
        dmtuid = build_dmtuid(tt, ff, cc, ss, xxx)

        part = Part(dmtuid=dmtuid, tt=tt, ff=ff, cc=cc, ss=ss, xxx=xxx)

        # Direct fields
        for csv_col, attr in DIRECT_FIELDS.items():
            val = str(data.get(csv_col, data.get(attr, ""))).strip()
            if val:
                setattr(part, attr, val)

        # KiCad fields
        for kf in ("kicad_symbol", "kicad_footprint", "kicad_libref", "kicad_3dmodel"):
            val = str(data.get(kf, "")).strip()
            if val:
                setattr(part, kf, val)

        # Notes
        part.notes = str(data.get("notes", "")).strip()

        # Template EAV fields
        template = get_fields(tt, ff)
        if template:
            allowed = set(template) - SKIP_FOR_EAV
            for k, v in data.items():
                if k in allowed and str(v).strip():
                    part.fields.append(
                        PartField(field_name=k, field_value=str(v).strip())
                    )

        session.add(part)
        session.flush()
        return part

    # ── Read ───────────────────────────────────────────────────────────

    @staticmethod
    def get(session: Session, dmtuid: str) -> Part | None:
        return session.get(Part, dmtuid.upper())

    # ── Update ─────────────────────────────────────────────────────────

    @staticmethod
    def update(session: Session, part: Part, data: dict) -> Part:
        """
        Update direct, KiCad, notes, and EAV fields on an existing Part.
        """
        # Direct fields
        for csv_col, attr in DIRECT_FIELDS.items():
            if csv_col in data or attr in data:
                val = str(data.get(csv_col, data.get(attr, ""))).strip()
                setattr(part, attr, val)

        # KiCad
        for kf in ("kicad_symbol", "kicad_footprint", "kicad_libref", "kicad_3dmodel"):
            if kf in data:
                setattr(part, kf, str(data[kf]).strip())

        # Notes
        if "notes" in data:
            part.notes = str(data["notes"]).strip()

        # EAV fields
        template = get_fields(part.tt, part.ff)
        skip = SKIP_FOR_EAV | {"kicad_symbol", "kicad_footprint",
                                "kicad_libref", "kicad_3dmodel", "dmtuid", "notes"}
        if template:
            allowed = set(template) - skip
            existing_map = {f.field_name: f for f in part.fields}
            for k, v in data.items():
                if k not in allowed:
                    continue
                val = str(v).strip()
                if k in existing_map:
                    if val:
                        existing_map[k].field_value = val
                    else:
                        session.delete(existing_map[k])
                elif val:
                    part.fields.append(
                        PartField(field_name=k, field_value=val)
                    )

        session.flush()
        return part

    # ── Delete ─────────────────────────────────────────────────────────

    @staticmethod
    def delete(session: Session, part: Part) -> None:
        session.delete(part)
        session.flush()
