"""
api - REST API layer.

All route modules register on a single Flask Blueprint
with url_prefix /api/v1.
"""

from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# Import route modules so their @api_bp decorators execute
from api import routes_parts      # noqa: F401, E402
from api import routes_schema     # noqa: F401, E402
from api import routes_kicad      # noqa: F401, E402
from api import routes_import     # noqa: F401, E402
from api import errors            # noqa: F401, E402
