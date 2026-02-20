"""
services.kicad_service - Queries tailored for KiCad integration.

Returns lightweight dicts instead of full Part objects to keep
the response payload minimal.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Part
from schema.loader import domain_name, family_name


class KiCadService:

    @staticmethod
    def search(
        session: Session,
        *,
        q: str = "",
        mpn: str = "",
        value: str = "",
        manufacturer: str = "",
        limit: int = 200,
    ) -> list[dict]:
        """Multi-criteria search returning KiCad-friendly records."""
        query = session.query(Part)

        if mpn:
            query = query.filter(Part.mpn == mpn)
        if value:
            query = query.filter(Part.value == value)
        if manufacturer:
            query = query.filter(Part.manufacturer == manufacturer)
        if q:
            like = f"%{q}%"
            query = query.filter(
                Part.dmtuid.ilike(like)
                | Part.mpn.ilike(like)
                | Part.value.ilike(like)
                | Part.description.ilike(like)
            )

        return [KiCadService._to_kicad_dict(p) for p in query.limit(limit).all()]

    @staticmethod
    def in_stock(session: Session) -> list[dict]:
        """Return all parts with a non-zero Quantity."""
        parts = session.query(Part).filter(
            Part.quantity != "",
            Part.quantity != "0",
            Part.quantity.isnot(None),
        ).all()

        results = []
        for p in parts:
            try:
                if int(p.quantity) <= 0:
                    continue
            except (ValueError, TypeError):
                pass  # non-numeric → include anyway
            results.append(KiCadService._to_kicad_dict(p))
        return results

    # ── Serialisation ──────────────────────────────────────────────────

    @staticmethod
    def _to_kicad_dict(p: Part) -> dict:
        return {
            "dmtuid": p.dmtuid,
            "mpn": p.mpn,
            "value": p.value,
            "manufacturer": p.manufacturer,
            "description": p.description,
            "quantity": p.quantity,
            "datasheet": p.datasheet,
            "kicad_symbol": p.kicad_symbol,
            "kicad_footprint": p.kicad_footprint,
            "kicad_libref": p.kicad_libref,
            "domain": domain_name(p.tt),
            "family": family_name(p.tt, p.ff),
        }
