"""
ui.routes_import - CSV import upload page.
"""

from flask import request, render_template, flash

from ui import ui_bp
from import_engine import run_import
from ui.import_review import stage_import, load_import
from itsdangerous import BadSignature


@ui_bp.route("/import", methods=["GET", "POST"])
def import_page():
    if request.method == "GET":
        return render_template("import.html", report=None)

    token = request.form.get("review_token")
    if token:
        try:
            run_id, content, review = load_import(token)
            report = run_import(content, replace_existing=review["replace"], operation_key=run_id,
                                expected_inventory=review["report"]["inventory_fingerprint"])
            return render_template("import.html", report=report.to_dict())
        except (BadSignature, ValueError, OSError):
            flash("Import review expired or is unavailable. Upload the CSV again.", "danger")
            return render_template("import.html", report=None)

    f = request.files.get("csv_file")
    if not f:
        flash("No file selected", "danger")
        return render_template("import.html", report=None)

    replace = request.form.get("replace") == "1"
    content = f.read()
    report = run_import(content, replace_existing=replace, preview=True)
    token = stage_import(content, replace, report.to_dict()) if report.imported else None
    return render_template("import.html", report=report.to_dict(), review_token=token)
