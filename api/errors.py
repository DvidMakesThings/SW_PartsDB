"""
api.errors - JSON error handlers for the API blueprint.
"""

from flask import jsonify
from api import api_bp


@api_bp.errorhandler(404)
def api_not_found(_e):
    return jsonify({"error": "not found"}), 404


@api_bp.errorhandler(400)
def api_bad_request(_e):
    return jsonify({"error": "bad request"}), 400


@api_bp.errorhandler(500)
def api_server_error(_e):
    return jsonify({"error": "internal server error"}), 500
