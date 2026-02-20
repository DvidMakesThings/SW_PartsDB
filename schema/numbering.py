"""
schema.numbering - DMTUID construction and parsing.

Format:  DMT-TTFFCCSSXXX
         TT/FF/CC/SS = 2 digits each, XXX = 3 digits (001-999).
"""

from __future__ import annotations

from typing import Optional


def build_dmtuid(tt: str, ff: str, cc: str, ss: str, xxx: str) -> str:
    """Assemble a canonical DMTUID string."""
    return f"DMT-{tt.zfill(2)}{ff.zfill(2)}{cc.zfill(2)}{ss.zfill(2)}{xxx.zfill(3)}"


def parse_dmtuid(uid: str) -> Optional[dict]:
    """
    Parse 'DMT-TTFFCCSSXXX' → {tt, ff, cc, ss, xxx}.
    Returns None on any format violation.
    """
    uid = uid.strip().upper()
    if not uid.startswith("DMT-"):
        return None
    body = uid[4:]
    if len(body) != 11 or not body.isdigit():
        return None
    return {
        "tt":  body[0:2],
        "ff":  body[2:4],
        "cc":  body[4:6],
        "ss":  body[6:8],
        "xxx": body[8:11],
    }


def validate_segments(tt: str, ff: str, cc: str, ss: str) -> Optional[str]:
    """Return an error message if any segment is invalid, else None."""
    for label, val in [("TT", tt), ("FF", ff), ("CC", cc), ("SS", ss)]:
        v = val.strip()
        if not v:
            return f"{label} is empty"
        if not v.isdigit():
            return f"{label} is non-numeric: {v!r}"
        if len(v) > 2:
            return f"{label} exceeds 2 digits: {v!r}"
    return None
