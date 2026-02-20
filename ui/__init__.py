"""
ui - Server-rendered HTML layer.

All route modules register on a single Flask Blueprint.
"""

from flask import Blueprint

ui_bp = Blueprint("ui", __name__)

# Import route modules so their @ui_bp decorators execute
from ui import routes_browse      # noqa: F401, E402
from ui import routes_detail      # noqa: F401, E402
from ui import routes_forms       # noqa: F401, E402
from ui import routes_import      # noqa: F401, E402
from ui import routes_docs        # noqa: F401, E402
from ui import datasheet_server   # noqa: F401, E402
from ui import live_search        # noqa: F401, E402
