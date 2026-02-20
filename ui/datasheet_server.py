"""
ui.datasheet_server - Serve local datasheet PDFs securely.

Only files under config.DATASHEETS_DIR are served.
Path-traversal (../) is blocked by resolving to absolute path
and checking the prefix.
"""

from flask import send_from_directory, abort

from ui import ui_bp
import config


@ui_bp.route("/datasheets/<path:filename>")
def serve_datasheet(filename: str):
    safe_path = (config.DATASHEETS_DIR / filename).resolve()

    # Must stay inside DATASHEETS_DIR
    if not str(safe_path).startswith(str(config.DATASHEETS_DIR)):
        abort(403)
    if not safe_path.is_file():
        abort(404)

    return send_from_directory(config.DATASHEETS_DIR, filename)
