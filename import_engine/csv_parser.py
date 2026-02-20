"""
import_engine.csv_parser - Low-level CSV reading and cleaning.

Responsibilities:
  • BOM removal (UTF-8 / UTF-8-SIG)
  • Header whitespace stripping
  • Returns a csv.DictReader ready for iteration
"""

from __future__ import annotations

import csv
import io
from typing import Optional


def prepare_reader(raw: str | bytes) -> Optional[csv.DictReader]:
    """
    Accept raw file content (bytes or str), clean it,
    and return a DictReader.  Returns None if content is empty.
    """
    text = _decode(raw)
    if not text or not text.strip():
        return None

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return None

    # Strip whitespace from every header
    reader.fieldnames = [h.strip() for h in reader.fieldnames]
    return reader


def _decode(raw: str | bytes) -> str:
    if isinstance(raw, bytes):
        # Strip UTF-8 BOM
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        return raw.decode("utf-8", errors="replace")
    if raw.startswith("\ufeff"):
        return raw[1:]
    return raw
