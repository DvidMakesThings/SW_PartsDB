"""
DMTDB - Centralised configuration.

All tunables live here.  Every other module imports from config
instead of reading os.environ directly.
"""

from __future__ import annotations
import os
from pathlib import Path


# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent
SCHEMA_PATH     = Path(os.environ.get("DMTDB_SCHEMA",    BASE_DIR / "dmt_schema.json"))
TEMPLATES_PATH  = Path(os.environ.get("DMTDB_TEMPLATES",  BASE_DIR / "dmt_templates.json"))
CSV_SEED_PATH   = Path(os.environ.get("DMTDB_CSV_SEED",   BASE_DIR / "DMT_Partslib.csv"))
DATASHEETS_DIR  = (BASE_DIR / "datasheets").resolve()

# ── Database ───────────────────────────────────────────────────────────
DB_URL = os.environ.get("DMTDB_DB", f"sqlite:///{BASE_DIR / 'dmtdb.sqlite'}")

# ── Server ─────────────────────────────────────────────────────────────
HOST   = os.environ.get("DMTDB_HOST", "0.0.0.0")
PORT   = int(os.environ.get("DMTDB_PORT", "5000"))
DEBUG  = os.environ.get("DMTDB_DEBUG", "0") == "1"
SECRET = os.environ.get("DMTDB_SECRET", "dmtdb-dev-key-change-in-prod")

# ── Pagination ─────────────────────────────────────────────────────────
DEFAULT_PAGE_SIZE = 50
API_MAX_LIMIT     = 1000
API_DEFAULT_LIMIT = 100
SEARCH_DROPDOWN_LIMIT = 20
KICAD_SEARCH_LIMIT    = 200
