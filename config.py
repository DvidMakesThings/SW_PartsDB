"""Central configuration: environment > config.local.ini > portable defaults."""

from pathlib import Path
from local_config import LocalConfig

BASE_DIR = Path(__file__).resolve().parent
_local = LocalConfig(BASE_DIR)
LOCAL_CONFIG_PATH = _local.filename

SCHEMA_PATH = _local.path("schema", BASE_DIR / "dmt_schema.json", "DMTDB_SCHEMA")
TEMPLATES_PATH = _local.path("templates", BASE_DIR / "dmt_templates.json", "DMTDB_TEMPLATES")
CSV_SEED_PATH = _local.path("csv_seed", BASE_DIR / "DMT_Partslib.csv", "DMTDB_CSV_SEED", optional=True)
DATASHEETS_DIR = _local.path("datasheets", BASE_DIR / "datasheets", "DMTDB_DATASHEETS_DIR")
PART_IMAGES_DIR = _local.path("part_images", BASE_DIR / "part_images", "DMTDB_PART_IMAGES_DIR")
STAGING_DIR = _local.path("staging", BASE_DIR / "_staging", "DMTDB_STAGING_DIR")
KICAD_LIBS_DIR = _local.path("kicad_libs", BASE_DIR / "kicad_libs", "DMTDB_KICAD_LIBS_DIR")
KICAD_SYMBOLS_DIR = _local.path("kicad_symbols", KICAD_LIBS_DIR / "symbols", "DMTDB_KICAD_SYMBOLS_DIR")
KICAD_FOOTPRINT_DIR = _local.path("kicad_footprints", KICAD_LIBS_DIR / "footprints", "DMTDB_KICAD_FOOTPRINTS_DIR")
KICAD_3DMODELS_DIR = _local.path("kicad_3dmodels", KICAD_LIBS_DIR / "3dmodels", "DMTDB_KICAD_3DMODELS_DIR")

# Read-only repository source, separate from app-managed library assets.
LIBRARY_REPO_DIR = _local.path("library_repo", BASE_DIR.parent / "LIB_KiCad-Libraries", "DMTDB_LIBRARY_REPO_DIR")
LIBRARY_CACHE_DIR = _local.path("library_cache", BASE_DIR / "instance" / "library-cache", "DMTDB_LIBRARY_CACHE_DIR")
ARTIFACTS_DIR = _local.path("artifacts", BASE_DIR / "instance" / "artifacts", "DMTDB_ARTIFACTS_DIR")
ARTIFACT_MAX_BYTES = int(_local.get("server", "artifact_max_bytes", str(100 * 1024 * 1024), "DMTDB_ARTIFACT_MAX_BYTES"))
BACKUPS_DIR = _local.path("backups", BASE_DIR / "instance" / "backups", "DMTDB_BACKUPS_DIR")
DATABASE_PATH = _local.path("database", BASE_DIR / "dmtdb.sqlite", "DMTDB_DATABASE_PATH")
DB_URL = _local.get("database", "url", f"sqlite:///{DATABASE_PATH.as_posix()}", "DMTDB_DB")

HOST = _local.get("server", "host", "0.0.0.0", "DMTDB_HOST")
PORT = int(_local.get("server", "port", "5000", "DMTDB_PORT"))
if not 1 <= PORT <= 65535:
    raise ValueError("server.port must be between 1 and 65535")
DEBUG = _local.boolean("server", "debug", False, "DMTDB_DEBUG")
READ_ONLY_PREVIEW = _local.boolean("server", "read_only_preview", False, "DMTDB_READ_ONLY_PREVIEW")
PREVIEW_PRODUCTION_URL = _local.get("server", "preview_production_url", "", "DMTDB_PREVIEW_PRODUCTION_URL")
SECRET = _local.get("server", "secret", "dmtdb-dev-key-change-in-prod", "DMTDB_SECRET")
PUBLIC_URL = _local.get("server", "public_url", "", "DMTDB_PUBLIC_URL").rstrip("/")

DEFAULT_PAGE_SIZE = 50
API_MAX_LIMIT = 1000
API_DEFAULT_LIMIT = 100
SEARCH_DROPDOWN_LIMIT = 20
KICAD_SEARCH_LIMIT = 200
SUPPLY_CHAIN_CACHE_TTL = int(_local.get("supply", "cache_ttl", "86400", "DMTDB_SUPPLY_CACHE_TTL"))
USD_TO_EUR_RATE = float(_local.get("supply", "usd_to_eur", "0.92", "DMTDB_USD_TO_EUR"))
