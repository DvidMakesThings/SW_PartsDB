"""
schema.loader - Parse dmt_schema.json at startup and expose lookup helpers.

This module owns the in-memory copies of domain/family/guideline data.
Template field lists live in schema.templates (separate concern).
"""

from __future__ import annotations

import json
from pathlib import Path

# ── Module-level state (populated by load()) ──────────────────────────
_schema: dict = {}
_domain_map: dict[str, str] = {}          # tt  → domain name
_family_map: dict[str, str] = {}          # ttff → family name
_cc_guidelines: dict = {}
_cross_cutting: dict = {}


def load(schema_path: str | Path, template_path: str | Path) -> dict:
    """
    Read dmt_schema.json (and forward template_path to schema.templates).

    Returns a stats dict for logging.
    """
    global _schema, _domain_map, _family_map, _cc_guidelines, _cross_cutting

    with open(schema_path, encoding="utf-8") as fh:
        _schema = json.load(fh)

    # Build fast-lookup maps
    _domain_map.clear()
    _family_map.clear()
    for dom in _schema.get("domains", []):
        tt = dom["tt"]
        _domain_map[tt] = dom["name"]
        for fam in dom.get("families", []):
            _family_map[f"{tt}{fam['ff']}"] = fam["name"]

    _cc_guidelines = _schema.get("family_cc_ss_guidelines", {})
    _cross_cutting = _schema.get("cross_cutting_class_codes", {})

    # Delegate template loading
    from schema.templates import _load_templates
    tpl_count = _load_templates(template_path)

    return {
        "domains": len(_domain_map),
        "families": len(_family_map),
        "templates": tpl_count,
    }


# ── Public helpers ────────────────────────────────────────────────────

def get_domains() -> list[dict]:
    """Return the full domain list with nested families."""
    return _schema.get("domains", [])


def list_domain_codes() -> list[str]:
    """Return list of all domain TT codes."""
    return list(_domain_map.keys())


def list_family_codes(tt: str) -> list[str]:
    """Return list of all FF codes for a given domain TT."""
    prefix = tt
    return [key[2:] for key in _family_map.keys() if key.startswith(prefix)]


def domain_name(tt: str) -> str:
    return _domain_map.get(tt, "Unknown")


def family_name(tt: str, ff: str) -> str:
    return _family_map.get(f"{tt}{ff}", "Unknown")


def valid_tt(tt: str) -> bool:
    return tt in _domain_map


def valid_ttff(tt: str, ff: str) -> bool:
    return f"{tt}{ff}" in _family_map


def get_cc_ss_guidelines(tt: str, ff: str) -> dict:
    """Return the CC/SS guideline block for a family (if any)."""
    key = f"{tt}{ff}"
    for gk, gv in _cc_guidelines.items():
        if gk.startswith(key):
            return gv
    return {}


def get_cross_cutting() -> dict:
    return _cross_cutting
