"""
services.supply_chain_service - Fetch pricing, stock, and lifecycle data
from external distributor APIs.

Currently supported:
  - LCSC / JLCPCB  (no API key required)

Future:
  - DigiKey  (requires API key)
  - Mouser   (requires API key)
  - Octopart / Nexar  (aggregator, requires API key)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote

import urllib.request
import urllib.error
import ssl

from sqlalchemy.orm import Session

from db.models import Part, PartPricing

log = logging.getLogger(__name__)

# ── LCSC / JLCPCB ─────────────────────────────────────────────────────

_LCSC_DETAIL_API = "https://wmsc.lcsc.com/ftps/wm/product/detail"
_LCSC_PRODUCT_URL = "https://www.lcsc.com/product-detail/{code}.html"
_JLCPCB_URL = "https://jlcpcb.com/parts/componentSearch?searchTxt={code}"

# Reusable SSL context (system default CAs)
_ssl_ctx = ssl.create_default_context()


def _http_get_json(url: str, timeout: int = 15) -> dict | None:
    """Simple GET → JSON using only stdlib. Returns None on error."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "DMTDB-PartsDB/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
            if resp.status != 200:
                log.warning("HTTP %s from %s", resp.status, url)
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            OSError, TimeoutError) as exc:
        log.warning("LCSC fetch error for %s: %s", url, exc)
        return None


def _normalise_lcsc_code(raw: str) -> str | None:
    """Extract a bare LCSC part code like C6467859 from various inputs."""
    raw = raw.strip()
    m = re.search(r"(C\d{4,})", raw, re.IGNORECASE)
    return m.group(1).upper() if m else None


def fetch_lcsc(lcsc_code: str) -> dict:
    """
    Query the LCSC product-detail API for a single part code.

    Returns a normalised dict or an error dict:
        {source, part_code, url, stock, lifecycle, currency, prices: [...], error}
    """
    code = _normalise_lcsc_code(lcsc_code)
    if not code:
        return {"source": "LCSC", "error": f"Invalid LCSC code: {lcsc_code!r}"}

    sanitized_code = quote(code, safe="")
    url = f"{_LCSC_DETAIL_API}?productCode={sanitized_code}"
    data = _http_get_json(url)

    if not data or data.get("code") != 200:
        msg = "No data returned"
        if data:
            msg = data.get("msg", str(data.get("code", "unknown error")))
        return {"source": "LCSC", "part_code": code, "error": msg}

    result = data.get("result")
    if not result:
        return {"source": "LCSC", "part_code": code, "error": "Part not found in LCSC"}

    # Price breaks
    prices = []
    for tier in result.get("productPriceList", []) or []:
        qty = tier.get("ladder")
        price = tier.get("productPrice")
        if qty is not None and price is not None:
            prices.append({"qty": int(qty), "price": str(price)})

    # Map to standard price columns
    price_map = {p["qty"]: p["price"] for p in prices}
    price_1 = price_map.get(1, "")
    price_10 = price_map.get(10, "")
    price_100 = price_map.get(100, "")
    price_1000 = price_map.get(1000, "")
    # Fall back to nearest break
    if not price_1 and prices:
        price_1 = prices[0]["price"]
    if not price_10:
        for p in prices:
            if p["qty"] <= 10:
                price_10 = p["price"]

    stock_val = result.get("stockNumber")
    if stock_val is not None:
        try:
            stock_val = int(stock_val)
        except (ValueError, TypeError):
            stock_val = None

    lifecycle = result.get("productCycle", "")
    # LCSC uses "normal" = Active, "nrfnd" = NRND, "discontinued" or "eol" etc.
    lifecycle_map = {
        "normal": "Active",
        "nrfnd": "NRND",
        "discontinued": "Discontinued",
        "eol": "EOL",
    }
    if isinstance(lifecycle, str):
        lifecycle = lifecycle_map.get(lifecycle.lower(), lifecycle.title() if lifecycle else "")

    product_url = _LCSC_PRODUCT_URL.format(code=quote(code, safe=""))

    return {
        "source": "LCSC",
        "part_code": code,
        "url": product_url,
        "stock": stock_val,
        "lifecycle": lifecycle,
        "currency": "USD",
        "price_1": price_1,
        "price_10": price_10,
        "price_100": price_100,
        "price_1000": price_1000,
        "prices": prices,
        "error": "",
    }


# ── Database persistence ───────────────────────────────────────────────

def _upsert_pricing(session: Session, dmtuid: str, info: dict) -> PartPricing:
    """Insert or update a PartPricing row for (dmtuid, source)."""
    source = info["source"]
    row = (
        session.query(PartPricing)
        .filter_by(dmtuid=dmtuid, source=source)
        .first()
    )
    if not row:
        row = PartPricing(dmtuid=dmtuid, source=source)
        session.add(row)

    row.part_code = info.get("part_code", "")
    row.url = info.get("url", "")
    row.stock = info.get("stock")
    row.lifecycle = info.get("lifecycle", "")
    row.currency = info.get("currency", "USD")
    row.price_1 = info.get("price_1", "")
    row.price_10 = info.get("price_10", "")
    row.price_100 = info.get("price_100", "")
    row.price_1000 = info.get("price_1000", "")
    row.price_json = json.dumps(info.get("prices", []))
    row.error = info.get("error", "")
    row.last_fetched = datetime.now(timezone.utc)
    return row


def refresh_part(session: Session, dmtuid: str) -> list[dict]:
    """
    Fetch pricing from all available sources for a single part.
    Returns a list of result dicts (one per source).
    """
    part = session.query(Part).filter_by(dmtuid=dmtuid).first()
    if not part:
        return [{"error": f"Part {dmtuid} not found"}]

    results = []

    # LCSC: use kicad_libref (LCSC Part code)
    lcsc_code = (part.kicad_libref or "").strip()
    if lcsc_code:
        info = fetch_lcsc(lcsc_code)
        _upsert_pricing(session, dmtuid, info)
        results.append(info)

    session.flush()
    return results


def refresh_all(session: Session, *, limit: int = 0) -> dict:
    """
    Refresh pricing for all parts that have an LCSC code.
    Returns summary stats.
    """
    query = session.query(Part).filter(Part.kicad_libref != "", Part.kicad_libref.isnot(None))
    if limit > 0:
        query = query.limit(limit)

    parts = query.all()
    ok = 0
    errors = 0
    for part in parts:
        try:
            results = refresh_part(session, part.dmtuid)
            if any(r.get("error") for r in results):
                errors += 1
            else:
                ok += 1
        except Exception as exc:
            log.error("Refresh failed for %s: %s", part.dmtuid, exc)
            errors += 1

    session.commit()
    return {"total": len(parts), "ok": ok, "errors": errors}


def get_pricing(session: Session, dmtuid: str) -> list[dict]:
    """Return all cached pricing rows for a part."""
    rows = (
        session.query(PartPricing)
        .filter_by(dmtuid=dmtuid)
        .all()
    )
    return [r.to_dict() for r in rows]
