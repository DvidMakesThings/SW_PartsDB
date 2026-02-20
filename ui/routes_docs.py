"""
ui.routes_docs - API documentation page.
"""

from flask import render_template

from ui import ui_bp


@ui_bp.route("/api/docs")
def api_docs():
    return render_template("api_docs.html")
