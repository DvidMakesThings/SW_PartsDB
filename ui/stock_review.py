"""Signed confirmation payloads for HTML stocktake previews."""
from flask import current_app, render_template
from itsdangerous import URLSafeTimedSerializer, BadSignature

from services.inventory_service import digest
from services.stock_review import review_part_stock


def confirm_stock_form(session, part, data, token):
    review = review_part_stock(session, part, data)
    if review is None:
        return None
    data["_stock_version"] = str(review["version"])
    serializer = URLSafeTimedSerializer(current_app.secret_key, salt="stocktake-confirmation")
    payload = {"part": part.dmtuid if part else None, "data_hash": digest(data)}
    if token:
        try:
            if serializer.loads(token, max_age=1800) == payload:
                return None
        except BadSignature:
            pass
        raise ValueError("Stock confirmation expired or changed; reload and review the count")
    return render_template("stock_confirmation.html", review=review, data=data,
                           confirmation=serializer.dumps(payload), part=part)
