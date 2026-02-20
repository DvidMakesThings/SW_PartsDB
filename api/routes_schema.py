"""
api.routes_schema - /api/v1/schema/* endpoints.

Expose the classification schema so external tools (KiCad plugins,
CLI scripts) can enumerate valid codes without parsing the JSON themselves.
"""

from flask import jsonify

from api import api_bp
from schema.loader import get_domains, get_cc_ss_guidelines, get_cross_cutting
from schema.templates import get_fields


@api_bp.route("/schema/domains")
def schema_domains():
    """List all domains and their families."""
    return jsonify(get_domains())


@api_bp.route("/schema/template/<ttff>")
def schema_template(ttff: str):
    """Get the field template for a TT+FF key (4-digit string)."""
    if len(ttff) != 4:
        return jsonify({"error": "key must be 4 digits"}), 400
    fields = get_fields(ttff[:2], ttff[2:])
    if fields is None:
        return jsonify({"error": "no template for this key"}), 404
    return jsonify({"key": ttff, "fields": fields})


@api_bp.route("/schema/guidelines/<ttff>")
def schema_guidelines(ttff: str):
    """Get CC/SS code guidelines for a family."""
    if len(ttff) != 4:
        return jsonify({"error": "key must be 4 digits"}), 400
    return jsonify(get_cc_ss_guidelines(ttff[:2], ttff[2:]))


@api_bp.route("/schema/cross_cutting")
def schema_cross_cutting():
    """List cross-cutting class codes (90-99 meanings)."""
    return jsonify(get_cross_cutting())
