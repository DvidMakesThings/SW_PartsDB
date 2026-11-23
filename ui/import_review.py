"""Persist a CSV preview on the server until its signed confirmation is submitted."""
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from flask import current_app
from itsdangerous import URLSafeTimedSerializer
import config


def stage_import(content, replace, report):
    identifier = uuid.uuid4().hex
    folder = config.STAGING_DIR / "csv-reviews" / identifier
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "input.csv").write_bytes(content)
    (folder / "review.json").write_text(json.dumps({"replace": replace, "report": report,
                  "created_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
    return URLSafeTimedSerializer(current_app.secret_key, salt="csv-review").dumps(identifier)


def load_import(token):
    identifier = URLSafeTimedSerializer(current_app.secret_key, salt="csv-review").loads(token, max_age=1800)
    if not isinstance(identifier, str) or len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
        raise ValueError("Invalid import review")
    folder = config.STAGING_DIR / "csv-reviews" / identifier
    return identifier, (folder / "input.csv").read_bytes(), json.loads((folder / "review.json").read_text(encoding="utf-8"))
