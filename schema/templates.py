"""
schema.templates - Template field lists keyed by TT+FF.

Each template defines the ordered set of field names that a part in
that family may carry.  Used by the importer, the add/edit form, and
the detail page to decide which fields to show / store.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_templates: dict[str, list[str]] = {}


def _load_templates(path: str | Path) -> int:
    """Called once by schema.loader.load().  Returns template count."""
    global _templates
    with open(path, encoding="utf-8") as fh:
        _templates = json.load(fh)
    return len(_templates)


# ── Public helpers ────────────────────────────────────────────────────

def get_fields(tt: str, ff: str) -> Optional[list[str]]:
    """Return the ordered field list for TT+FF, or None if no template."""
    return _templates.get(f"{tt}{ff}")


def get_all_keys() -> list[str]:
    """Return all registered template keys, sorted."""
    return sorted(_templates.keys())


def has_template(tt: str, ff: str) -> bool:
    return f"{tt}{ff}" in _templates
