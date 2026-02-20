"""
api.routes_import - /api/v1/import endpoint.

Accepts CSV via multipart file upload or raw request body.
"""

from flask import request, jsonify

from api import api_bp
from import_engine import run_import


@api_bp.route("/import", methods=["POST"])
def api_import_csv():
    """
    POST /api/v1/import?replace=0|1

    Multipart: field name 'csv_file'
    Or: raw CSV as request body (Content-Type: text/csv).
    """
    replace = request.args.get("replace", "0") == "1"

    if request.content_type and "multipart" in request.content_type:
        f = request.files.get("csv_file")
        if not f:
            return jsonify({"error": "no csv_file in upload"}), 400
        content = f.read()
    else:
        content = request.get_data()

    if not content:
        return jsonify({"error": "empty body"}), 400

    report = run_import(content, replace_existing=replace)
    return jsonify(report.to_dict())