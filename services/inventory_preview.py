"""Read-only stock migration classification; no models or write sessions required."""
from collections import Counter
import re

MAX_QUANTITY = 2**63 - 1


def classify_quantity(raw):
    value = "" if raw is None else str(raw).strip()
    if not value:
        return "unknown", None, "No recorded count; retain an uncounted holding"
    if not re.fullmatch(r"[0-9]+", value):
        return "review", None, "Expected a nonnegative whole number; preserve original value"
    # Bound the input before conversion (also handles very long legacy strings).
    digits = value.lstrip("0") or "0"
    if len(digits) > 19 or int(digits) > MAX_QUANTITY:
        return "review", None, "Count exceeds the supported signed 64-bit range"
    return "known", int(digits), "Opening balance proposed; no movement has been posted"


def preview_inventory(rows):
    results = []
    counts = Counter()
    known_total = 0
    locations = Counter()
    for row in rows:
        raw = row["quantity"]
        state, quantity, reason = classify_quantity(raw)
        location_raw = row["location"]
        location = (location_raw or "").strip()
        counts[state] += 1
        locations[location] += 1
        if quantity is not None:
            known_total += quantity
        results.append({"dmtuid": row["dmtuid"], "mpn": row["mpn"],
                        "original_quantity": raw, "original_location": location_raw,
                        "proposed_quantity": quantity, "count_status": state,
                        "proposed_location": location or None, "reason": reason})
    return {"read_only": True, "parts": len(results),
            "known_counts": counts["known"], "unknown_counts": counts["unknown"],
            "review_counts": counts["review"], "known_quantity_total": known_total,
            "locations": [{"name": k or None, "parts": v} for k, v in sorted(locations.items())],
            "items": results}
