"""Repository indexing and library-to-part matching review in HTML."""
import json
from flask import abort, flash, redirect, render_template, request
from sqlalchemy import or_
from ui import ui_bp
from ui.routes_designs import engineering_route, get_or_404, paginate
from db.models import LibrarySource, LibraryEntry, LibrarySyncRun, LibraryReviewEvent
from services import library_catalog as catalog
from services.inventory_service import summaries, lock_inventory
from schema.loader import get_domains, get_cc_ss_guidelines


@ui_bp.route("/library-sync", methods=["GET", "POST"])
@engineering_route
def library_catalog(db):
    source = db.get(LibrarySource, 1)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "configure":
            url = catalog.validate_repository_url(request.form.get("repository_url", ""))
            if source and source.state == "running":
                raise ValueError("Wait for the current sync to finish before changing configuration")
            if source and source.indexed_commit and catalog.repository_identity(source.repository_url) != catalog.repository_identity(url):
                raise ValueError("This source already has an indexed history. A different repository needs a separate source; do not replace its identity")
            if not source:
                source = LibrarySource(id=1, name="KiCad component library", repository_url=url)
                db.add(source)
            else:
                source.repository_url = url
        elif action in {"index", "fetch"}:
            if not source:
                raise ValueError("Save the source configuration first")
            from services.jobs import enqueue
            job = enqueue(db, "library", {"source_id": source.id, "fetch": action == "fetch"}, f"library:{source.id}")
            flash(f"Sync queued as job #{job.id}. This page will refresh while it runs.", "success")
        elif action == "schedule":
            if not source:
                raise ValueError("Configure the source first")
            try:
                interval = int(request.form.get("interval", "0"))
            except ValueError:
                raise ValueError("Enter a schedule interval in minutes") from None
            if interval != 0 and not 15 <= interval <= 10080:
                raise ValueError("Use 0 to disable scheduling, or 15–10080 minutes")
            mode = request.form.get("mode", "local")
            if mode not in {"local", "fetch"}:
                raise ValueError("Choose local indexing or GitHub fetch")
            source.interval_minutes, source.sync_mode = interval, mode
        elif action == "link_matches":
            if not source:
                raise ValueError("Index the library first")
            lock_inventory(db)
            db.refresh(source)
            if source.indexed_commit != request.form.get("commit"):
                raise ValueError("A new commit was indexed. Reload before confirming matches")
            matcher = catalog.Matcher(db)
            count = 0
            for entry in db.query(LibraryEntry).filter_by(source_id=1, missing=False, part_id=None).order_by(LibraryEntry.id):
                match = matcher.evaluate(entry)
                if match["state"] == "match":
                    # Reuse the evidence already checked under the allocation lock.
                    entry.part_id, entry.decision = match["part_id"], "linked"
                    entry.reviewed_hash, entry.reviewed_identity_json = entry.content_hash, entry.normalized_json
                    entry.review_note = "Confirmed unique strong-identifier matches in browser"
                    entry.reviewed_at = catalog.datetime.now(catalog.timezone.utc)
                    db.add(LibraryReviewEvent(entry_id=entry.id, decision="link", part_id=entry.part_id,
                        content_hash=entry.content_hash, note=entry.review_note))
                    count += 1
            flash(f"Linked {count} library representations to existing parts. Stock was unchanged.", "success")
        elif action == "create_selected":
            lock_inventory(db)
            if not source:
                raise ValueError("Index the library first")
            db.refresh(source)
            if source.indexed_commit != request.form.get("commit"):
                raise ValueError("A new commit was indexed. Reload the catalogue before importing")
            selected = request.form.getlist("entry_id")
            if not selected or len(selected) > 50:
                raise ValueError("Select between 1 and 50 entries on this page")
            if len(selected) != len(set(selected)):
                raise ValueError("Duplicate selection")
            family = request.form.get("family", "")
            classification = {"tt": family[:2], "ff": family[2:], "cc": request.form.get("cc", ""), "ss": request.form.get("ss", "")}
            counts = catalog.Counter()
            for selected_id in selected:
                try:
                    entry_id = int(selected_id)
                except ValueError:
                    raise ValueError("Invalid catalogue selection") from None
                entry = get_or_404(db, LibraryEntry, entry_id)
                result = catalog.Matcher(db).evaluate(entry)
                decision = "link" if result["state"] == "match" else "create"
                if result["state"] not in {"match", "create"}:
                    raise ValueError(f"{entry.symbol}: identity changed or needs review; no selected parts were imported")
                catalog.review_entry(db, entry.id, decision, request.form.get(f"hash_{entry.id}"),
                    result["part_id"] or "", classification,
                    "Batch catalogue classification confirmed in browser")
                counts[decision] += 1
            flash(f"Created {counts['create']} Not stocked parts; linked {counts['link']} existing representations. No stock changed.", "success")
        else:
            raise ValueError("Unknown library action")
        return redirect("/library-sync", 303)
    q, scope = request.args.get("q", "").strip(), request.args.get("state", "all")
    selected_path = request.args.get("path", "")
    matcher = catalog.Matcher(db)
    entries = db.query(LibraryEntry).order_by(LibraryEntry.path, LibraryEntry.symbol).all()
    evaluated = [(entry, matcher.evaluate(entry)) for entry in entries]
    counts = catalog.Counter(result["state"] for _, result in evaluated)
    filtered = [(entry, result) for entry, result in evaluated if (scope == "all" or result["state"] == scope)
                and (not selected_path or entry.path == selected_path)
                and (not q or q.casefold() in (entry.symbol + " " + entry.path + " " + entry.properties_json).casefold())]
    pages = max(1, (len(filtered) + 49) // 50)
    page = min(max(1, request.args.get("page", 1, type=int)), pages)
    rows = filtered[(page - 1) * 50:page * 50]
    stock = summaries(db, [entry.part_id for entry, _ in rows if entry.part_id])
    runs = db.query(LibrarySyncRun).order_by(LibrarySyncRun.id.desc()).limit(10).all()
    return render_template("library_catalog.html", source=source, default_url=catalog.DEFAULT_URL,
                           rows=rows, counts=counts, q=q, scope=scope, stock=stock, runs=runs, page=page, pages=pages,
                           paths=sorted({e.path for e in entries}), selected_path=selected_path, domains=get_domains())


@ui_bp.route("/library-sync/entries/<int:entry_id>", methods=["GET", "POST"])
@engineering_route
def library_entry(db, entry_id):
    entry = get_or_404(db, LibraryEntry, entry_id)
    if request.method == "POST":
        family = request.form.get("family", "")
        classification = {"tt": family[:2], "ff": family[2:], "cc": request.form.get("cc", ""), "ss": request.form.get("ss", "")}
        catalog.review_entry(db, entry.id, request.form.get("decision"), request.form.get("expected_hash"),
            request.form.get("part_id", ""), classification, request.form.get("note", ""))
        return redirect(request.path, 303)
    matcher = catalog.Matcher(db)
    result = matcher.evaluate(entry)
    reviews = db.query(LibraryReviewEvent).filter_by(entry_id=entry.id).order_by(LibraryReviewEvent.id.desc()).all()
    return render_template("library_entry.html", entry=entry, result=result,
        properties=json.loads(entry.properties_json), normalized=json.loads(entry.normalized_json),
        candidates=[matcher.parts[uid] for uid in result["candidates"] if uid in matcher.parts],
        domains=get_domains(), guidelines=get_cc_ss_guidelines, reviews=reviews,
        stock=summaries(db, [entry.part_id]) if entry.part_id else {})


@ui_bp.route("/jobs", methods=["GET", "POST"])
@engineering_route
def jobs_page(db):
    from db.models import BackgroundJob
    from services.jobs import enqueue
    if request.method == "POST":
        try:
            identifier = int(request.form.get("job_id", ""))
        except ValueError:
            raise ValueError("Choose a job") from None
        job = get_or_404(db, BackgroundJob, identifier)
        if job.status != "failed":
            raise ValueError("Only failed jobs can be retried manually")
        enqueue(db, job.kind, json.loads(job.payload_json), job.dedupe_key)
        return redirect("/jobs", 303)
    items = db.query(BackgroundJob).order_by(BackgroundJob.id.desc()).limit(100).all()
    return render_template("jobs.html", jobs=items, running=any(j.status in {"queued", "running"} for j in items))
