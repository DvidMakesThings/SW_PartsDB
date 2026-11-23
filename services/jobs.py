"""Small durable SQLite job queue with leases and restart recovery."""
from datetime import datetime, timezone, timedelta
import json
import threading
import time
import uuid
from sqlalchemy import or_, select
from db import get_session
from db.models import BackgroundJob, LibrarySource
from services.inventory_service import lock_inventory


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enqueue(db, kind, payload, dedupe_key):
    lock_inventory(db)
    existing = db.scalar(select(BackgroundJob).where(BackgroundJob.dedupe_key == dedupe_key,
                         BackgroundJob.status.in_(["queued", "running"])))
    if existing:
        return existing
    job = BackgroundJob(kind=kind, payload_json=json.dumps(payload), dedupe_key=dedupe_key)
    db.add(job)
    if kind == "library":
        source = db.get(LibrarySource, payload["source_id"])
        if not source:
            raise ValueError("Library source does not exist")
        source.state = "queued"
    db.flush()
    return job


def assert_lease(db, lease):
    if not lease:
        return
    job = db.get(BackgroundJob, lease[0], populate_existing=True)
    if not job or job.status != "running" or job.lease_token != lease[1] or job.lease_until < now():
        raise ValueError("Job lease expired; a recovered worker owns this operation")


def schedule_due():
    with get_session() as db:
        lock_inventory(db)
        for source in db.scalars(select(LibrarySource).where(LibrarySource.interval_minutes > 0)):
            if not source.last_attempt_at or source.last_attempt_at + timedelta(minutes=source.interval_minutes) <= now():
                enqueue(db, "library", {"source_id": source.id, "fetch": source.sync_mode == "fetch"}, f"library:{source.id}")
        db.commit()


def run_next():
    with get_session() as db:
        lock_inventory(db)
        job = db.scalar(select(BackgroundJob).where(or_(BackgroundJob.status == "queued",
            (BackgroundJob.status == "running") & (BackgroundJob.lease_until < now())))
            .order_by(BackgroundJob.id))
        if not job:
            db.rollback()
            return False
        if job.attempts >= 3:
            job.status, job.error = "failed", "Job interrupted repeatedly; inspect the source and retry explicitly"
            db.commit()
            return True
        job.status, job.attempts = "running", job.attempts + 1
        job.lease_token, job.lease_until = uuid.uuid4().hex, now() + timedelta(minutes=15)
        job.updated_at = now()
        payload, kind, lease = json.loads(job.payload_json), job.kind, (job.id, job.lease_token)
        if kind == "library" and job.attempts > 1:
            source = db.get(LibrarySource, payload["source_id"])
            source.state = "queued"
        db.commit()
    try:
        if kind == "library":
            from services.library_catalog import sync_library
            result = sync_library(payload["source_id"], payload.get("fetch", False), lease=lease)
        elif kind == "design_git":
            from services.git_archive import import_release
            result = import_release(payload["release_id"], payload["revision"], lease=lease)
        else:
            raise ValueError("Unknown background job kind")
        error = ""
    except Exception as exc:
        result = {}
        error = str(exc) if isinstance(exc, ValueError) else "Job failed; inspect local server logs and retry"
    with get_session() as db:
        lock_inventory(db)
        job = db.get(BackgroundJob, lease[0], populate_existing=True)
        if job.lease_token == lease[1] and job.status == "running":
            job.status, job.error, job.result_json = "failed" if error else "completed", error, json.dumps(result)
            job.updated_at, job.lease_until = now(), None
            db.commit()
    return True


def start_worker():
    def loop():
        while True:
            try:
                schedule_due()
                if run_next():
                    continue
            except Exception:
                # Lease recovery preserves ownership after transient connection failures.
                pass
            time.sleep(2)
    worker = threading.Thread(target=loop, name="partsdb-jobs", daemon=True)
    worker.start()
    return worker
