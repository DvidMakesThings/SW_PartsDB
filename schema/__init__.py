"""
schema - DMT classification schema and template resolution.

Public API:
    loader.load(schema_path, template_path)
    numbering.build_dmtuid / parse_dmtuid
    templates.get_fields / get_all_keys
    loader.get_domains / domain_name / family_name / …
"""

from schema.loader import (                         # noqa: F401
    load,
    get_domains,
    domain_name,
    family_name,
    valid_tt,
    valid_ttff,
    get_cc_ss_guidelines,
    get_cross_cutting,
)
from schema.numbering import build_dmtuid, parse_dmtuid   # noqa: F401
from schema.templates import get_fields, get_all_keys     # noqa: F401
