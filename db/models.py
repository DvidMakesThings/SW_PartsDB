"""
db.models - SQLAlchemy ORM declarations.

Tables
------
parts        - one row per unique DMTUID.  Frequently-queried columns
               (MPN, value, manufacturer …) are stored directly for speed.
part_fields  - EAV store for template-driven parameters that vary per
               TT+FF family.  Keeps the schema migration-friendly and
               avoids ALTER TABLE for every new field set.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, DateTime, Text, ForeignKey, Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Part(Base):
    __tablename__ = "parts"

    # ── Primary key ────────────────────────────────────────────────────
    dmtuid = Column(String(20), primary_key=True)               # DMT-TTFFCCSSXXX

    # ── Classification segments ────────────────────────────────────────
    tt  = Column(String(2), nullable=False, index=True)
    ff  = Column(String(2), nullable=False, index=True)
    cc  = Column(String(2), nullable=False, index=True)
    ss  = Column(String(2), nullable=False, index=True)
    xxx = Column(String(3), nullable=False)

    # ── Frequently-queried direct columns ──────────────────────────────
    mpn          = Column(String(200), index=True, default="")
    manufacturer = Column(String(200), index=True, default="")
    value        = Column(String(200), index=True, default="")
    description  = Column(Text, default="")
    quantity     = Column(String(50), default="")
    location     = Column(String(200), default="")
    datasheet    = Column(Text, default="")
    distributor  = Column(Text, default="")

    # ── KiCad integration (future use) ─────────────────────────────────
    kicad_symbol    = Column(String(300), default="")
    kicad_footprint = Column(String(300), default="")
    kicad_libref    = Column(String(300), default="")
    kicad_3dmodel   = Column(String(300), default="")

    # ── Fallback for parts with no matching template ───────────────────
    extra_json = Column(Text, default="{}")
    notes      = Column(Text, default="")

    # ── Timestamps ─────────────────────────────────────────────────────
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # ── EAV relationship ───────────────────────────────────────────────
    fields = relationship(
        "PartField", back_populates="part",
        cascade="all, delete-orphan", lazy="selectin",
    )

    __table_args__ = (
        Index("ix_ttffccss", "tt", "ff", "cc", "ss"),
    )

    # ── Serialisation ──────────────────────────────────────────────────
    def to_dict(self) -> dict:
        d = {
            "dmtuid": self.dmtuid,
            "tt": self.tt, "ff": self.ff, "cc": self.cc,
            "ss": self.ss, "xxx": self.xxx,
            "mpn": self.mpn or "",
            "manufacturer": self.manufacturer or "",
            "value": self.value or "",
            "description": self.description or "",
            "quantity": self.quantity or "",
            "location": self.location or "",
            "datasheet": self.datasheet or "",
            "distributor": self.distributor or "",
            "kicad_symbol": self.kicad_symbol or "",
            "kicad_footprint": self.kicad_footprint or "",
            "kicad_libref": self.kicad_libref or "",
            "kicad_3dmodel": self.kicad_3dmodel or "",
            "notes": self.notes or "",            "created_at": self.created_at.isoformat() if self.created_at else "",        }
        for f in self.fields:
            d[f.field_name] = f.field_value
        if self.extra_json:
            try:
                d["extra"] = json.loads(self.extra_json)
            except Exception:
                d["extra"] = {}
        return d


class PartField(Base):
    __tablename__ = "part_fields"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    dmtuid     = Column(String(20),
                        ForeignKey("parts.dmtuid", ondelete="CASCADE"),
                        nullable=False, index=True)
    field_name = Column(String(200), nullable=False)
    field_value = Column(Text, nullable=False, default="")

    part = relationship("Part", back_populates="fields")

    __table_args__ = (
        Index("ix_field_lookup", "dmtuid", "field_name"),
    )


class ClientConfig(Base):
    """
    Stores KiCad library path configurations for each client PC.
    
    Clients register themselves with a unique identifier (hostname or custom name).
    The server remembers their local paths so they can sync updates.
    """
    __tablename__ = "client_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String(200), unique=True, nullable=False, index=True)  # Hostname or custom name
    client_name = Column(String(200), default="")  # Friendly display name
    
    # Local paths on the client machine
    path_symbols = Column(String(500), default="")
    path_footprints = Column(String(500), default="")
    path_3dmodels = Column(String(500), default="")
    
    # Server URL as seen from the client
    server_url = Column(String(500), default="")
    
    # Sync tracking
    last_sync = Column(DateTime, nullable=True)
    last_sync_hash = Column(String(64), default="")  # SHA256 of library state at last sync
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "client_id": self.client_id,
            "client_name": self.client_name or self.client_id,
            "path_symbols": self.path_symbols or "",
            "path_footprints": self.path_footprints or "",
            "path_3dmodels": self.path_3dmodels or "",
            "server_url": self.server_url or "",
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "last_sync_hash": self.last_sync_hash or "",
        }
