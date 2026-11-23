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
    Boolean, Column, String, Integer, BigInteger, DateTime, Text, ForeignKey, Index,
    CheckConstraint, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class DesignProject(Base):
    __tablename__ = "design_projects"
    id = Column(Integer, primary_key=True)
    code = Column(String(6), nullable=False, unique=True)
    document_id = Column(String(100), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    repository_url = Column(Text, nullable=False, default="")
    archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    boards = relationship("BoardDesign", back_populates="project", order_by="BoardDesign.code")


class LibrarySource(Base):
    __tablename__ = "library_sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    repository_url = Column(Text, nullable=False)
    indexed_commit = Column(String(64), nullable=False, default="")
    state = Column(String(30), nullable=False, default="idle")
    last_attempt_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=False, default="")
    interval_minutes = Column(Integer, nullable=False, default=0)
    sync_mode = Column(String(20), nullable=False, default="local")


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    id = Column(Integer, primary_key=True)
    kind = Column(String(30), nullable=False)
    dedupe_key = Column(String(200), nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="queued", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    lease_token = Column(String(40), nullable=False, default="")
    lease_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    result_json = Column(Text, nullable=False, default="{}")
    error = Column(Text, nullable=False, default="")


class LibraryEntry(Base):
    __tablename__ = "library_entries"
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("library_sources.id", ondelete="RESTRICT"), nullable=False, index=True)
    path = Column(Text, nullable=False)
    symbol = Column(String(500), nullable=False)
    properties_json = Column(Text, nullable=False, default="{}")
    normalized_json = Column(Text, nullable=False, default="{}")
    content_hash = Column(String(64), nullable=False)
    seen_commit = Column(String(64), nullable=False)
    missing = Column(Boolean, nullable=False, default=False)
    part_id = Column(String(20), ForeignKey("parts.dmtuid", ondelete="RESTRICT"), nullable=True, index=True)
    decision = Column(String(20), nullable=False, default="unresolved")
    reviewed_hash = Column(String(64), nullable=False, default="")
    reviewed_identity_json = Column(Text, nullable=False, default="{}")
    review_note = Column(Text, nullable=False, default="")
    reviewed_at = Column(DateTime, nullable=True)
    source = relationship("LibrarySource")
    part = relationship("Part")
    __table_args__ = (UniqueConstraint("source_id", "path", "symbol", name="uq_library_symbol"),)


class LibrarySyncRun(Base):
    __tablename__ = "library_sync_runs"
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("library_sources.id", ondelete="RESTRICT"), nullable=False)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    commit_hash = Column(String(64), nullable=False, default="")
    status = Column(String(30), nullable=False, default="running")
    report_json = Column(Text, nullable=False, default="{}")


class LibraryReviewEvent(Base):
    __tablename__ = "library_review_events"
    id = Column(Integer, primary_key=True)
    entry_id = Column(Integer, ForeignKey("library_entries.id", ondelete="RESTRICT"), nullable=False, index=True)
    decision = Column(String(30), nullable=False)
    part_id = Column(String(20), ForeignKey("parts.dmtuid", ondelete="RESTRICT"), nullable=True)
    content_hash = Column(String(64), nullable=False)
    note = Column(Text, nullable=False, default="")
    recorded_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class BoardDesign(Base):
    __tablename__ = "board_designs"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("design_projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    code = Column(String(2), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    part_id = Column(String(20), ForeignKey("parts.dmtuid", ondelete="RESTRICT"), nullable=True, index=True)
    archived = Column(Boolean, nullable=False, default=False)
    project = relationship("DesignProject", back_populates="boards")
    releases = relationship("DesignRelease", back_populates="board", order_by="DesignRelease.id.desc()")
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_project_board"),)


class DesignRelease(Base):
    __tablename__ = "design_releases"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("board_designs.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision = Column(String(40), nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    notes = Column(Text, nullable=False, default="")
    source_commit = Column(String(64), nullable=False, default="")
    tool_versions = Column(Text, nullable=False, default="")
    dependency_notes = Column(Text, nullable=False, default="")
    missing_artifacts_reason = Column(Text, nullable=False, default="")
    manifest_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    released_at = Column(DateTime, nullable=True)
    board = relationship("BoardDesign", back_populates="releases")
    artifacts = relationship("DesignArtifact", back_populates="release", order_by="DesignArtifact.id")
    __table_args__ = (UniqueConstraint("board_id", "revision", name="uq_board_release"),
                     CheckConstraint("status IN ('draft','released','superseded')", name="ck_release_status"))


class PhysicalUnit(Base):
    __tablename__ = "physical_units"
    id = Column(Integer, primary_key=True)
    serial = Column(String(120), nullable=False)
    serial_key = Column(String(120), nullable=False)
    serial_scope = Column(String(50), nullable=False)
    archived = Column(Boolean, nullable=False, default=False)
    build_id = Column(Integer, ForeignKey("build_batches.id", ondelete="RESTRICT"), nullable=True, index=True)
    board_id = Column(Integer, ForeignKey("board_designs.id", ondelete="RESTRICT"), nullable=True, index=True)
    release_id = Column(Integer, ForeignKey("design_releases.id", ondelete="RESTRICT"), nullable=True, index=True)
    part_id = Column(String(20), ForeignKey("parts.dmtuid", ondelete="RESTRICT"), nullable=True, index=True)
    historical = Column(Boolean, nullable=False, default=True)
    stage = Column(String(30), nullable=False, default="prototype")
    status = Column(String(30), nullable=False, default="active")
    location = Column(String(200), nullable=False, default="")
    notes = Column(Text, nullable=False, default="")
    firmware_version = Column(String(200), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    board = relationship("BoardDesign")
    part = relationship("Part")
    release = relationship("DesignRelease")
    events = relationship("UnitEvent", back_populates="unit", order_by="UnitEvent.recorded_at.desc()")
    __table_args__ = (
        UniqueConstraint("serial_scope", "serial_key", name="uq_unit_scope_serial"),
        CheckConstraint("board_id IS NOT NULL OR part_id IS NOT NULL", name="ck_unit_owner"),
        CheckConstraint("historical OR release_id IS NOT NULL OR board_id IS NULL", name="ck_unit_release_required"),
        CheckConstraint("status IN ('active','in-test','faulty','repaired','retired','waste')", name="ck_unit_status"))


class DomainSerialPolicy(Base):
    __tablename__ = "domain_serial_policies"
    tt = Column(String(2), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False)
    serial_prefix = Column(String(80), nullable=False, default="")


class AssemblyDefinition(Base):
    __tablename__ = "assembly_definitions"
    id = Column(Integer, primary_key=True)
    release_id = Column(Integer, ForeignKey("design_releases.id", ondelete="RESTRICT"), nullable=False, unique=True)
    source_artifact_id = Column(Integer, ForeignKey("design_artifacts.id", ondelete="RESTRICT"), nullable=False)
    lines_json = Column(Text, nullable=False)
    release = relationship("DesignRelease")


class BuildBatch(Base):
    __tablename__ = "build_batches"
    id = Column(Integer, primary_key=True)
    release_id = Column(Integer, ForeignKey("design_releases.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    completed_quantity = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="planned")
    notes = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    release = relationship("DesignRelease")
    __table_args__ = (CheckConstraint("quantity > 0 AND completed_quantity >= 0 AND completed_quantity <= quantity", name="ck_build_quantity"),)


class BuildPosting(Base):
    __tablename__ = "build_postings"
    id = Column(Integer, primary_key=True)
    build_id = Column(Integer, ForeignKey("build_batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    operation_key = Column(String(150), nullable=False, unique=True)
    payload_hash = Column(String(64), nullable=False)
    kind = Column(String(30), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    details_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class UnitEvent(Base):
    __tablename__ = "unit_events"
    id = Column(Integer, primary_key=True)
    unit_id = Column(Integer, ForeignKey("physical_units.id", ondelete="RESTRICT"), nullable=False, index=True)
    kind = Column(String(30), nullable=False)
    title = Column(String(200), nullable=False)
    notes = Column(Text, nullable=False, default="")
    details_json = Column(Text, nullable=False, default="{}")
    actor = Column(String(200), nullable=False)
    event_at = Column(DateTime, nullable=False)
    recorded_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    corrects_id = Column(Integer, ForeignKey("unit_events.id", ondelete="RESTRICT"), nullable=True)
    unit = relationship("PhysicalUnit", back_populates="events")
    artifacts = relationship("DesignArtifact", back_populates="event", order_by="DesignArtifact.id")


class EngineeringIssue(Base):
    __tablename__ = "engineering_issues"
    id = Column(Integer, primary_key=True)
    release_id = Column(Integer, ForeignKey("design_releases.id", ondelete="RESTRICT"), nullable=True, index=True)
    unit_id = Column(Integer, ForeignKey("physical_units.id", ondelete="RESTRICT"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    severity = Column(String(20), nullable=False, default="normal")
    status = Column(String(20), nullable=False, default="open")
    resolution = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)
    __table_args__ = (CheckConstraint("release_id IS NOT NULL OR unit_id IS NOT NULL", name="ck_issue_scope"),)


class DesignArtifact(Base):
    __tablename__ = "design_artifacts"
    id = Column(Integer, primary_key=True)
    release_id = Column(Integer, ForeignKey("design_releases.id", ondelete="RESTRICT"), nullable=True, index=True)
    event_id = Column(Integer, ForeignKey("unit_events.id", ondelete="RESTRICT"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    role = Column(String(40), nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    size = Column(BigInteger, nullable=False)
    media_type = Column(String(100), nullable=False)
    provenance = Column(Text, nullable=False, default="")
    archive_manifest = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    release = relationship("DesignRelease", back_populates="artifacts")
    event = relationship("UnitEvent", back_populates="artifacts")
    __table_args__ = (CheckConstraint("(release_id IS NOT NULL AND event_id IS NULL) OR (event_id IS NOT NULL AND release_id IS NULL)", name="ck_artifact_owner"),)


class InventoryLock(Base):
    """One row serializes stock writers, including SQLite deployments."""
    __tablename__ = "inventory_lock"
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False, default=0)


class StockHolding(Base):
    __tablename__ = "stock_holdings"
    id = Column(Integer, primary_key=True)
    dmtuid = Column(String(20), ForeignKey("parts.dmtuid", ondelete="RESTRICT"), nullable=False, index=True)
    location = Column(String(200), nullable=False, default="")
    lot = Column(String(200), nullable=False, default="")
    count_known = Column(Boolean, nullable=False, default=False)
    on_hand = Column(BigInteger, nullable=False, default=0)
    reserved = Column(BigInteger, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("dmtuid", "location", "lot", name="uq_holding_location_lot"),
        CheckConstraint("on_hand >= 0 AND reserved >= 0 AND reserved <= on_hand", name="ck_holding_balance"),
        CheckConstraint("count_known OR (on_hand = 0 AND reserved = 0)", name="ck_unknown_holding"),
    )


class InventoryOperation(Base):
    __tablename__ = "inventory_operations"
    key = Column(String(200), primary_key=True)
    payload_hash = Column(String(64), nullable=False)
    actor = Column(String(200), nullable=False)
    reason = Column(Text, nullable=False)
    result_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id = Column(Integer, primary_key=True)
    holding_id = Column(Integer, ForeignKey("stock_holdings.id", ondelete="RESTRICT"), nullable=False, index=True)
    operation_key = Column(String(200), ForeignKey("inventory_operations.key", ondelete="RESTRICT"), nullable=False, index=True)
    kind = Column(String(40), nullable=False)
    delta = Column(BigInteger, nullable=False)
    balance_after = Column(BigInteger, nullable=False)
    count_known_after = Column(Boolean, nullable=False)
    reference = Column(String(200), nullable=False, default="")
    reverses_id = Column(Integer, ForeignKey("stock_movements.id", ondelete="RESTRICT"), nullable=True)
    details_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (CheckConstraint("balance_after >= 0", name="ck_movement_balance"),)


class StockReservation(Base):
    __tablename__ = "stock_reservations"
    id = Column(Integer, primary_key=True)
    holding_id = Column(Integer, ForeignKey("stock_holdings.id", ondelete="RESTRICT"), nullable=False, index=True)
    reference = Column(String(200), nullable=False)
    quantity = Column(BigInteger, nullable=False)
    __table_args__ = (
        UniqueConstraint("holding_id", "reference", name="uq_reservation_reference"),
        CheckConstraint("quantity >= 0", name="ck_reservation_quantity"),
    )


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

    # ── Status flags ──────────────────────────────────────────────────
    eol = Column(Boolean, default=False)

    # ── Fallback for parts with no matching template ───────────────────
    extra_json = Column(Text, default="{}")
    notes      = Column(Text, default="")

    # ── Timestamps ─────────────────────────────────────────────────────
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # ── Supply chain relationship ──────────────────────────────────────
    pricing = relationship(
        "PartPricing", back_populates="part",
        cascade="all, delete-orphan", lazy="selectin",
    )

    # ── Image relationship ─────────────────────────────────────────────
    images = relationship(
        "PartImage", back_populates="part",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="PartImage.position",
    )

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
            "notes": self.notes or "",
            "eol": bool(self.eol),            "created_at": self.created_at.isoformat() if self.created_at else "",        }
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


class PartPricing(Base):
    """
    Supply-chain snapshot for a part from a specific source.

    Each row captures price breaks, stock, lifecycle status, and the URL
    from a single distributor or aggregator query (LCSC, DigiKey, Mouser, …).
    Rows are replaced on each refresh so the table stays compact.
    """
    __tablename__ = "part_pricing"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    dmtuid     = Column(String(20),
                        ForeignKey("parts.dmtuid", ondelete="CASCADE"),
                        nullable=False, index=True)
    source     = Column(String(50), nullable=False)          # "LCSC", "DigiKey", …
    part_code  = Column(String(200), default="")             # e.g. C6467859
    url        = Column(Text, default="")                    # product page link
    stock      = Column(Integer, nullable=True)              # units in stock
    lifecycle  = Column(String(50), default="")              # Active, NRND, EOL, …
    currency   = Column(String(10), default="USD")
    price_1    = Column(String(30), default="")              # price for qty 1
    price_10   = Column(String(30), default="")
    price_100  = Column(String(30), default="")
    price_1000 = Column(String(30), default="")
    price_json = Column(Text, default="[]")                  # full break list
    last_fetched = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    error      = Column(Text, default="")                    # last error message if any

    part = relationship("Part", back_populates="pricing")

    __table_args__ = (
        Index("ix_pricing_lookup", "dmtuid", "source"),
    )

    def to_dict(self) -> dict:
        import json as _json
        breaks = []
        if self.price_json:
            try:
                breaks = _json.loads(self.price_json)
            except Exception:
                pass
        return {
            "source": self.source,
            "part_code": self.part_code or "",
            "url": self.url or "",
            "stock": self.stock,
            "lifecycle": self.lifecycle or "",
            "currency": self.currency or "USD",
            "price_1": self.price_1 or "",
            "price_10": self.price_10 or "",
            "price_100": self.price_100 or "",
            "price_1000": self.price_1000 or "",
            "price_breaks": breaks,
            "last_fetched": self.last_fetched.isoformat() if self.last_fetched else "",
            "error": self.error or "",
        }


class PartImage(Base):
    """
    Images attached to a part. Max 5 per part.
    Files stored under part_images/<dmtuid>/.
    """
    __tablename__ = "part_images"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    dmtuid   = Column(String(20),
                      ForeignKey("parts.dmtuid", ondelete="CASCADE"),
                      nullable=False, index=True)
    filename = Column(String(300), nullable=False)
    position = Column(Integer, nullable=False, default=0)  # 0-4
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    part = relationship("Part", back_populates="images")
