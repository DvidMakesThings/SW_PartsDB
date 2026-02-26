"""
services.parts_service - CRUD operations on Part records.

All session management is the caller's responsibility (open before,
close/commit after).  This keeps the service testable and allows
the caller to batch multiple operations in one transaction.
"""

from __future__ import annotations

import json
import re
from sqlalchemy.orm import Session

from db.models import Part, PartField
from schema.numbering import build_dmtuid
from schema.templates import get_fields
from import_engine.field_map import DIRECT_FIELDS, SKIP_FOR_EAV
from services.sequence_service import next_xxx


def collect_distributors_from_form(data: dict) -> str:
    """
    Collect distributor fields from form data.
    Form fields are named: dist_name_0, dist_url_0, dist_name_1, dist_url_1, etc.
    Returns JSON string or empty string if no distributors.
    """
    distributors = []
    # Find all dist_name_* and dist_url_* fields
    indices = set()
    for key in data.keys():
        match = re.match(r'dist_(name|url)_(\d+)', key)
        if match:
            indices.add(int(match.group(2)))
    
    for idx in sorted(indices):
        name = data.get(f'dist_name_{idx}', '').strip()
        url = data.get(f'dist_url_{idx}', '').strip()
        if url:  # URL is required, name is optional
            distributors.append({'name': name, 'url': url})
    
    if distributors:
        return json.dumps(distributors, ensure_ascii=False)
    return ""


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

        # Direct fields (excluding Distributor - handled separately)
        for csv_col, attr in DIRECT_FIELDS.items():
            if csv_col == "Distributor":
                continue  # Handled below
            val = str(data.get(csv_col, data.get(attr, ""))).strip()
            if val:
                setattr(part, attr, val)

        # Collect distributors from form fields (dist_name_*, dist_url_*)
        part.distributor = collect_distributors_from_form(data)

        # KiCad fields
        for kf in ("kicad_symbol", "kicad_footprint", "kicad_libref", "kicad_3dmodel"):
            val = str(data.get(kf, "")).strip()
            if val:
                setattr(part, kf, val)

        # Notes
        part.notes = str(data.get("notes", "")).strip()

        # Template EAV fields + extra_json for non-template fields
        template = get_fields(tt, ff)
        skip = SKIP_FOR_EAV | {"kicad_symbol", "kicad_footprint",
                                "kicad_libref", "kicad_3dmodel", "dmtuid", "notes",
                                "tt", "ff", "cc", "ss", "xxx", "distributor_count"}
        # Also skip distributor form fields
        skip_patterns = {'dist_name_', 'dist_url_'}
        
        extra: dict[str, str] = {}
        if template:
            allowed = set(template) - skip
            for k, v in data.items():
                # Skip distributor form fields
                if any(k.startswith(p) for p in skip_patterns):
                    continue
                val = str(v).strip()
                if not val:
                    continue
                if k in allowed:
                    part.fields.append(
                        PartField(field_name=k, field_value=val)
                    )
                elif k not in skip:
                    # Non-template field → extra_json
                    extra[k] = val
        else:
            # No template → all non-skip fields go to extra_json
            for k, v in data.items():
                # Skip distributor form fields
                if any(k.startswith(p) for p in skip_patterns):
                    continue
                val = str(v).strip()
                if val and k not in skip:
                    extra[k] = val

        if extra:
            part.extra_json = json.dumps(extra, ensure_ascii=False)

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
        # Direct fields (excluding Distributor - handled separately)
        for csv_col, attr in DIRECT_FIELDS.items():
            if csv_col == "Distributor":
                continue  # Handled below
            if csv_col in data or attr in data:
                val = str(data.get(csv_col, data.get(attr, ""))).strip()
                setattr(part, attr, val)

        # Collect distributors from form fields (dist_name_*, dist_url_*)
        # Only update if distributor form fields are present
        if any(k.startswith('dist_name_') or k.startswith('dist_url_') for k in data.keys()):
            part.distributor = collect_distributors_from_form(data)

        # KiCad
        for kf in ("kicad_symbol", "kicad_footprint", "kicad_libref", "kicad_3dmodel"):
            if kf in data:
                setattr(part, kf, str(data[kf]).strip())

        # Notes
        if "notes" in data:
            part.notes = str(data["notes"]).strip()

        # EAV fields + extra_json for non-template fields
        template = get_fields(part.tt, part.ff)
        skip = SKIP_FOR_EAV | {"kicad_symbol", "kicad_footprint",
                                "kicad_libref", "kicad_3dmodel", "dmtuid", "notes",
                                "tt", "ff", "cc", "ss", "xxx", "distributor_count"}
        # Also skip distributor form fields
        skip_patterns = {'dist_name_', 'dist_url_'}

        # Load existing extra_json
        existing_extra: dict[str, str] = {}
        if part.extra_json:
            try:
                existing_extra = json.loads(part.extra_json)
            except (json.JSONDecodeError, TypeError):
                pass

        if template:
            allowed = set(template) - skip
            existing_map = {f.field_name: f for f in part.fields}
            for k, v in data.items():
                # Skip distributor form fields
                if any(k.startswith(p) for p in skip_patterns):
                    continue
                val = str(v).strip()
                if k in allowed:
                    # Template field → EAV
                    if k in existing_map:
                        if val:
                            existing_map[k].field_value = val
                        else:
                            session.delete(existing_map[k])
                    elif val:
                        part.fields.append(
                            PartField(field_name=k, field_value=val)
                        )
                elif k not in skip:
                    # Non-template field → extra_json
                    if val:
                        existing_extra[k] = val
                    elif k in existing_extra:
                        del existing_extra[k]
        else:
            # No template → all non-skip fields go to extra_json
            for k, v in data.items():
                # Skip distributor form fields
                if any(k.startswith(p) for p in skip_patterns):
                    continue
                val = str(v).strip()
                if k in skip:
                    continue
                if val:
                    existing_extra[k] = val
                elif k in existing_extra:
                    del existing_extra[k]

        # Update extra_json
        part.extra_json = json.dumps(existing_extra, ensure_ascii=False) if existing_extra else None

        session.flush()
        return part

    # ── Delete ─────────────────────────────────────────────────────────

    @staticmethod
    def delete(session: Session, part: Part) -> None:
        session.delete(part)
        session.flush()
