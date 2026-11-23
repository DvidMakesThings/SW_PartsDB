"""Deployment helpers. Run `python -m manage --help`; previews never initialize the app."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

import config
from db.migrations import status, upgrade
from services.inventory_preview import preview_inventory
from services.inventory_service import reconcile
from sqlalchemy.orm import Session


def read_only_engine(url):
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
        raise ValueError("This audit currently supports existing file-backed SQLite databases")
    path = Path(parsed.database).resolve()
    if not path.is_file():
        raise ValueError("Database does not exist; audit will not create it")
    uri = path.as_uri() + "?mode=ro"
    return create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))


def inventory_report(engine):
    with engine.connect() as connection:
        # Audit should work before the legacy baseline is stamped.
        state = status(connection)
        rows = connection.exec_driver_sql(
            "SELECT dmtuid, mpn, quantity, location FROM parts ORDER BY dmtuid").mappings().all()
        report = preview_inventory(rows)
        report["schema_status"] = state
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["db-status", "db-upgrade", "inventory-preview", "inventory-check", "backup-all", "restore-backup"])
    parser.add_argument("--archive", help="Backup ZIP to restore")
    parser.add_argument("--destination", help="New/empty restore directory (never an active database folder)")
    parser.add_argument("--writers-stopped", action="store_true",
                        help="Required for upgrade: confirm application writers are paused")
    args = parser.parse_args(argv)
    engine = None
    try:
        if args.action == "backup-all":
            from services.backup_service import create_bundle
            engine = create_engine(config.DB_URL)
            result = {"archive":str(create_bundle(engine))}
        elif args.action == "restore-backup":
            from services.backup_service import restore_bundle
            if not args.archive or not args.destination:
                parser.error("restore-backup requires --archive and --destination")
            result = restore_bundle(args.archive,args.destination)
        elif args.action == "db-upgrade":
            if not args.writers_stopped:
                parser.error("db-upgrade requires --writers-stopped after pausing writers")
            engine = create_engine(config.DB_URL)
            result = upgrade(engine, config.BACKUPS_DIR)
        else:
            engine = read_only_engine(config.DB_URL)
            if args.action == "inventory-preview":
                result = inventory_report(engine)
            elif args.action == "inventory-check":
                with Session(engine) as session:
                    result = {"problems": reconcile(session)}
                print(json.dumps(result, indent=2))
                return 1 if result["problems"] else 0
            else:
                with engine.connect() as connection:
                    result = {"status": status(connection)}
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
