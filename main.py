#!/usr/bin/env python3
"""
DMTDB - Parts Database Web Application
=======================================

Single-command run:  python main.py

See config.py for all environment-variable tunables.
"""

import sys
from flask import Flask, render_template, send_from_directory

import config
import schema
from db import init_db, get_session, Part
from api import api_bp
from ui import ui_bp


def create_app() -> Flask:
    """Flask application factory."""

    app = Flask(
        __name__,
        template_folder=str(config.BASE_DIR / "templates"),
        static_folder=str(config.BASE_DIR / "static"),
    )
    app.secret_key = config.SECRET

    # ── Load classification schema + templates ──────────────────────
    if not config.SCHEMA_PATH.exists():
        print(f"FATAL: schema not found: {config.SCHEMA_PATH}")
        sys.exit(1)
    if not config.TEMPLATES_PATH.exists():
        print(f"FATAL: templates not found: {config.TEMPLATES_PATH}")
        sys.exit(1)

    stats = schema.load(config.SCHEMA_PATH, config.TEMPLATES_PATH)
    print(f"  Schema: {stats['domains']} domains, "
          f"{stats['families']} families, {stats['templates']} templates")

    # ── Initialise database ─────────────────────────────────────────
    init_db(config.DB_URL)
    print(f"  Database: {config.DB_URL}")

    # ── Register blueprints ─────────────────────────────────────────
    app.register_blueprint(api_bp)
    app.register_blueprint(ui_bp)

    # ── KiCad library file server ───────────────────────────────────
    kicad_libs_dir = config.BASE_DIR / "kicad_libs"

    @app.route("/kicad_libs/<path:filepath>")
    def serve_kicad_lib(filepath):
        """Serve KiCad library files (symbols, footprints, 3D models)."""
        return send_from_directory(kicad_libs_dir, filepath)

    # ── Error handlers ──────────────────────────────────────────────
    @app.errorhandler(404)
    def _404(e):
        return render_template("error.html", code=404,
                               message="Page not found"), 404

    @app.errorhandler(500)
    def _500(e):
        return render_template("error.html", code=500,
                               message="Internal server error"), 500

    return app


def _seed_if_empty():
    """Auto-import seed CSV when the database is empty."""
    session = get_session()
    count = session.query(Part).count()
    session.close()

    if count > 0:
        print(f"\n  Database has {count} parts.")
        return

    if not config.CSV_SEED_PATH.exists():
        print(f"\n  No seed CSV at {config.CSV_SEED_PATH} - starting empty.")
        return

    print(f"\n  Database empty → auto-importing {config.CSV_SEED_PATH.name} …")
    from import_engine import run_import

    with open(config.CSV_SEED_PATH, "rb") as fh:
        report = run_import(fh.read())

    print(f"  Done: {report.imported} imported, "
          f"{report.skipped} skipped / {report.total_rows} rows")
    if report.errors:
        print(f"  First errors (max 10):")
        for err in report.errors[:10]:
            print(f"    Row {err['row']}: {err['reason']}")


def main():
    print("=" * 56)
    print("  DMTDB - Parts Database")
    print("=" * 56)

    app = create_app()
    _seed_if_empty()

    print(f"\n  http://{config.HOST}:{config.PORT}")
    print(f"  API docs: http://{config.HOST}:{config.PORT}/api/docs")
    print("=" * 56)

    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)


if __name__ == "__main__":
    main()
