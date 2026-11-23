"""Explicit, validated schema upgrades. Never stamp an unrecognized database."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "0001_legacy"
HEAD = "0009_part_deletion"
MANIFESTS = {BASELINE: "legacy_schema.json", "0002_inventory": "inventory_schema.json",
             "0003_designs": "design_schema.json", "0004_library": "library_schema.json",
             "0005_serials": "serial_schema.json", "0006_jobs": "jobs_schema.json",
             "0007_builds": "builds_schema.json", "0008_document_id": "document_id_schema.json",
             HEAD: "part_deletion_schema.json"}


def alembic_config(connection):
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "migrations").replace("%", "%%"))
    cfg.attributes["connection"] = connection
    return cfg


def schema_signature(connection):
    inspector = inspect(connection)
    result = {}
    for name in sorted(set(inspector.get_table_names()) - {"alembic_version"}):
        result[name] = {
            "columns": {c["name"]: {"type": str(c["type"]), "nullable": c["nullable"]}
                        for c in inspector.get_columns(name)},
            "primary_key": inspector.get_pk_constraint(name)["constrained_columns"],
            "foreign_keys": sorted([
                {"columns": f["constrained_columns"], "table": f["referred_table"],
                 "references": f["referred_columns"], "ondelete": f.get("options", {}).get("ondelete")}
                for f in inspector.get_foreign_keys(name)], key=lambda f: f["columns"]),
            "unique_indexes": sorted([i["column_names"] for i in inspector.get_indexes(name) if i["unique"]]),
            "unique_constraints": sorted([i["column_names"] for i in inspector.get_unique_constraints(name)]),
            "check_constraints": sorted(i["sqltext"] for i in inspector.get_check_constraints(name)),
        }
    return result


def validate_legacy(connection, manifest="legacy_schema.json"):
    expected = json.loads((ROOT / "migrations" / manifest).read_text(encoding="utf-8"))
    actual = schema_signature(connection)
    if actual != expected:
        differences = sorted(name for name in set(actual) | set(expected)
                             if actual.get(name) != expected.get(name))
        raise RuntimeError("Unrecognized legacy schema in tables: " + ", ".join(differences)
                           + ". No baseline applied; inspect the schema before upgrading.")


def status(connection):
    tables = inspect(connection).get_table_names()
    heads = MigrationContext.configure(connection).get_current_heads()
    if heads:
        if len(heads) != 1 or heads[0] not in MANIFESTS:
            raise RuntimeError("Database schema version is incompatible with this application")
        validate_legacy(connection, MANIFESTS[heads[0]])
        return "current" if heads[0] == HEAD else "upgrade_required"
    if not tables:
        return "empty"
    if tables == ["alembic_version"]:
        raise RuntimeError("Incomplete migration state; restore or inspect before continuing")
    if "alembic_version" in tables:
        raise RuntimeError("Empty migration version marker; inspect before continuing")
    validate_legacy(connection)
    return "legacy"


def ensure_schema(engine):
    """Bootstrap only an empty database; existing schemas require explicit upgrade."""
    with engine.connect() as connection:
        state = status(connection)
    if state == "empty":
        with engine.connect() as connection:
            try:
                if engine.dialect.name == "sqlite":
                    connection.exec_driver_sql("BEGIN IMMEDIATE")
                command.upgrade(alembic_config(connection), HEAD)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    elif state != "current":
        raise RuntimeError("Existing database needs a versioned baseline. Stop the service, "
                           "then run python -m manage db-upgrade. A SQLite backup is made first.")


def backup_sqlite(engine, directory):
    """SQLite backup API includes committed WAL data; never copy only the main file."""
    if engine.dialect.name != "sqlite":
        raise RuntimeError("This upgrade command currently requires SQLite; no changes made")
    source = engine.url.database
    if not source or source == ":memory:" or not Path(source).is_file():
        return None
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    destination = directory / f"dmtdb-{name}.sqlite"
    destination.touch(mode=0o600, exist_ok=False)
    with sqlite3.connect(Path(source).resolve().as_uri() + "?mode=ro", uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed; migration was not started")
    return destination


def upgrade(engine, backups_dir):
    # Operator must pause writers; the backup and migration cannot span one SQLite lock.
    with engine.connect() as connection:
        state = status(connection)
    if state == "current":
        return {"status": "current", "backup": None, "revision": HEAD}
    backup = backup_sqlite(engine, backups_dir)
    with engine.connect() as connection:
        try:
            if engine.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            if state == "legacy":
                validate_legacy(connection)
                command.stamp(alembic_config(connection), BASELINE)
            command.upgrade(alembic_config(connection), HEAD)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"status": "upgraded", "backup": str(backup) if backup else None, "revision": HEAD}
