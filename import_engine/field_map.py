"""
import_engine.field_map - Column-name ↔ model-attribute mapping.

Columns listed here are stored directly on the Part row for fast
indexing/search.  Everything else goes into the EAV table or extra_json.
"""

# CSV column name  →  Part model attribute
DIRECT_FIELDS: dict[str, str] = {
    "MPN":          "mpn",
    "Manufacturer": "manufacturer",
    "Value":        "value",
    "Description":  "description",
    "Quantity":     "quantity",
    "Location":     "location",
    "Datasheet":    "datasheet",
    "KiCadSymbol":  "kicad_symbol",
    "KiCadFootprint": "kicad_footprint",
    "KiCadLibRef":  "kicad_libref",
}

# Columns that form the UID structure - never stored as EAV
UID_COLUMNS = frozenset({"TT", "FF", "CC", "SS", "XXX", "DMTUID"})

# Combined skip set for EAV processing
SKIP_FOR_EAV = UID_COLUMNS | frozenset(DIRECT_FIELDS.keys())
