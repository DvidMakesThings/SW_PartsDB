#!/usr/bin/env python3
"""
DMTDB - Parts Database Web Application
=======================================

Single-command run:  python main.py

See config.py for all environment-variable tunables.
"""

import sys
import uuid
from flask import Flask, render_template, send_from_directory, request, abort

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
    app.config["MAX_CONTENT_LENGTH"] = config.ARTIFACT_MAX_BYTES + 1024 * 1024
    app.jinja_env.globals["new_operation_key"] = lambda: uuid.uuid4().hex
    app.jinja_env.globals["read_only_preview"] = config.READ_ONLY_PREVIEW
    app.jinja_env.globals["preview_production_url"] = config.PREVIEW_PRODUCTION_URL
    if config.READ_ONLY_PREVIEW:
        # Explicit allowlist: old GET endpoints can also have side effects.
        @app.before_request
        def protect_preview():
            allowed = {"ui.index", "ui.part_detail", "ui.stock_history",
                       "ui.inventory_migration_preview", "api.list_parts", "api.get_part",
                       "ui.ui_search", "ui.ui_template_fields", "ui.ui_facets",
                       "ui.designs_index", "ui.design_project", "ui.design_board", "ui.design_release",
                       "ui.design_artifact", "ui.release_manifest", "ui.prototypes_index",
                       "ui.prototype_detail", "ui.prototype_history",
                       "ui.product_serials", "ui.serial_settings",
                       "ui.library_catalog", "ui.library_entry",
                       "ui.jobs_page",
                       "ui.builds_index", "ui.build_detail", "ui.bom_example",
                       "static", "serve_part_image", "serve_kicad_lib", "ui.serve_datasheet"}
            if request.method not in {"GET", "HEAD", "OPTIONS"} or request.endpoint not in allowed:
                abort(403, description="This is a read-only preview using a separate database snapshot.")

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
    
    # KiCad HTTP Library blueprint (separate from /api/v1 for cleaner URLs)
    from api import kicad_httplib_bp
    app.register_blueprint(kicad_httplib_bp)

    # ── KiCad library file server ───────────────────────────────────
    @app.route("/kicad_libs/<path:filepath>")
    def serve_kicad_lib(filepath):
        """Serve KiCad library files (symbols, footprints, 3D models)."""
        kind, separator, relative = filepath.partition("/")
        directories = {"symbols": config.KICAD_SYMBOLS_DIR,
                       "footprints": config.KICAD_FOOTPRINT_DIR,
                       "3dmodels": config.KICAD_3DMODELS_DIR}
        if separator and kind in directories:
            return send_from_directory(directories[kind], relative)
        # Preserve existing root-file URLs, including HTTP library configuration.
        return send_from_directory(config.KICAD_LIBS_DIR, filepath)

    # ── Part image file server ──────────────────────────────────────
    @app.route("/part_images/<path:filepath>")
    def serve_part_image(filepath):
        """Serve part images from part_images directory."""
        safe = (config.PART_IMAGES_DIR / filepath).resolve()
        if not str(safe).startswith(str(config.PART_IMAGES_DIR)):
            from flask import abort
            abort(403)
        return send_from_directory(config.PART_IMAGES_DIR, filepath)

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
    if config.READ_ONLY_PREVIEW:
        return
    session = get_session()
    count = session.query(Part).count()
    session.close()

    if count > 0:
        print(f"\n  Database has {count} parts.")
        return

    if config.CSV_SEED_PATH is None or not config.CSV_SEED_PATH.is_file():
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
    if not config.READ_ONLY_PREVIEW:
        from services.jobs import start_worker
        start_worker()

    print(f"\n  http://{config.HOST}:{config.PORT}")
    print(f"  API docs: http://{config.HOST}:{config.PORT}/api/docs")
    print("=" * 56)

    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)


if __name__ == "__main__":
    main()
