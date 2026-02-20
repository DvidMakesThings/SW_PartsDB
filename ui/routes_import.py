"""
ui.routes_import - CSV import upload page.
"""

from flask import request, render_template, flash

from ui import ui_bp
from import_engine import run_import


@ui_bp.route("/import", methods=["GET", "POST"])
def import_page():
    if request.method == "GET":
        return render_template("import.html", report=None)

    f = request.files.get("csv_file")
    if not f:
        flash("No file selected", "danger")
        return render_template("import.html", report=None)

    replace = request.form.get("replace") == "1"
    content = f.read()
    report = run_import(content, replace_existing=replace)
    return render_template("import.html", report=report.to_dict())
