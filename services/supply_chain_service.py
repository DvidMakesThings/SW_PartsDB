"""
services.supply_chain_service - Fetch pricing, stock, and lifecycle data
from external distributor APIs.

Currently supported:
  - JLCPCB  (scraped from partdetail page, no API key required)

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

# ── JLCPCB ─────────────────────────────────────────────────────────────

_JLCPCB_DETAIL_URL = "https://jlcpcb.com/partdetail/{code}"

# Reusable SSL context (system default CAs)
_ssl_ctx = ssl.create_default_context()


def _http_get_html(url: str, timeout: int = 20) -> str | None:
    """Simple GET → HTML string using only stdlib. Returns None on error."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
            if resp.status != 200:
                log.warning("HTTP %s from %s", resp.status, url)
                return None
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError,
            OSError, TimeoutError) as exc:
        log.warning("JLCPCB fetch error for %s: %s", url, exc)
        return None


def _normalise_lcsc_code(raw: str) -> str | None:
    """Extract a bare LCSC/JLCPCB part code like C6467859 from various inputs."""
    raw = raw.strip()
    m = re.search(r"(C\d{4,})", raw, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _parse_jlcpcb_page(html: str) -> dict:
    """
    Parse the JLCPCB SSR partdetail page for stock and pricing data.

    The page is a Nuxt.js SSR page with data in both the rendered HTML
    and the window.__NUXT__ closure.
    """
    result = {"stock": None, "prices": [], "lifecycle": ""}

    # ── Stock from rendered HTML: "In Stock: 1,366" or "In Stock: 1366"
    m = re.search(r"In Stock[:\s]*([\d,]+)", html)
    if m:
        try:
            result["stock"] = int(m.group(1).replace(",", ""))
        except ValueError:
            pass

    # If stock is 0 or not found, check for "out of stock" text
    if result["stock"] is None:
        if re.search(r"out of stock|discontinued|obsolete", html, re.IGNORECASE):
            result["stock"] = 0

    # ── Price breaks from rendered "In-stock Item Pricing" section
    #    Format: <span>QTY+</span> <span>$PRICE</span>
    pricing_section = re.search(
        r"In-stock Item Pricing.*?</div>\s*</div>", html, re.DOTALL
    )
    if pricing_section:
        section = pricing_section.group(0)
        # Find all qty+ / $price pairs
        breaks = re.findall(
            r"(\d+)\+</span>\s*<span[^>]*>\s*\$?([\d.]+)\s*</span>",
            section,
        )
        for qty_str, price_str in breaks:
            try:
                result["prices"].append({
                    "qty": int(qty_str),
                    "price": price_str,
                })
            except ValueError:
                continue

    # ── Lifecycle: JLCPCB doesn't show lifecycle status prominently.
    #    If part exists on the page and has stock, it's Active.
    if result["stock"] is not None and result["stock"] > 0:
        result["lifecycle"] = "Active"
    elif result["stock"] == 0:
        # Check for specific status text
        if re.search(r"discontinued", html, re.IGNORECASE):
            result["lifecycle"] = "Discontinued"
        else:
            result["lifecycle"] = "Out of Stock"

    return result


def fetch_jlcpcb(lcsc_code: str) -> dict:
    """
    Scrape the JLCPCB partdetail page for stock and pricing.

    Uses the same C-codes as LCSC (shared catalog between LCSC and JLCPCB).

    Returns a normalised dict:
        {source, part_code, url, stock, lifecycle, currency, prices: [...], error}
    """
    code = _normalise_lcsc_code(lcsc_code)
    if not code:
        return {"source": "JLCPCB", "error": f"Invalid part code: {lcsc_code!r}"}

    sanitized_code = quote(code, safe="")
    page_url = _JLCPCB_DETAIL_URL.format(code=sanitized_code)
    html = _http_get_html(page_url)

    if not html:
        return {"source": "JLCPCB", "part_code": code, "url": page_url,
                "error": "Failed to fetch JLCPCB page"}

    # Check if part actually exists (page might be a generic 404/empty)
    if code not in html:
        return {"source": "JLCPCB", "part_code": code, "url": page_url,
                "error": "Part not found on JLCPCB"}

    parsed = _parse_jlcpcb_page(html)
    prices = parsed["prices"]

    # Map to standard price columns using closest available break
    price_map = {p["qty"]: p["price"] for p in prices}

    # price_1: exact match or first/lowest break
    price_1 = price_map.get(1, "")
    if not price_1 and prices:
        price_1 = prices[0]["price"]

    # price_10: exact or closest ≤10
    price_10 = price_map.get(10, "")
    if not price_10:
        for p in prices:
            if p["qty"] <= 10:
                price_10 = p["price"]

    # price_100: exact or closest ≤100
    price_100 = price_map.get(100, "")
    if not price_100:
        for p in prices:
            if p["qty"] <= 100:
                price_100 = p["price"]

    # price_1000: exact or closest ≤1000
    price_1000 = price_map.get(1000, "")
    if not price_1000:
        for p in prices:
            if p["qty"] <= 1000:
                price_1000 = p["price"]

    return {
        "source": "JLCPCB",
        "part_code": code,
        "url": page_url,
        "stock": parsed["stock"],
        "lifecycle": parsed["lifecycle"],
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

    # JLCPCB: use kicad_libref (LCSC/JLCPCB Part code, shared catalog)
    lcsc_code = (part.kicad_libref or "").strip()
    if lcsc_code:
        info = fetch_jlcpcb(lcsc_code)
        _upsert_pricing(session, dmtuid, info)
        results.append(info)

        # Clean up legacy LCSC rows (source was renamed LCSC → JLCPCB)
        session.query(PartPricing).filter_by(
            dmtuid=dmtuid, source="LCSC"
        ).delete()

    session.flush()
    return results


def refresh_all(session: Session, *, limit: int = 0) -> dict:
    """
    Refresh pricing for all parts that have a JLCPCB/LCSC code.
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
