"""HTML design archives and serial-unit tracking."""
import csv
from functools import wraps
import io
import json
import secrets
from flask import (abort, flash, jsonify, redirect, render_template, request,
                   session as browser_session, send_file, Response)
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from ui import ui_bp
from db import get_session
from db.models import (DesignProject, BoardDesign, DesignRelease, DesignArtifact,
                       PhysicalUnit, UnitEvent, EngineeringIssue, Part, DomainSerialPolicy, AssemblyDefinition, BuildBatch)
from services import design_service as designs


def csrf_token():
    if "engineering_csrf" not in browser_session:
        browser_session["engineering_csrf"] = secrets.token_urlsafe(32)
    return browser_session["engineering_csrf"]


@ui_bp.app_context_processor
def engineering_context():
    return {"engineering_csrf": csrf_token, "artifact_roles": designs.ARTIFACT_ROLES,
            "event_kinds": sorted(designs.EVENT_KINDS), "decode_json": json.loads,
            "unit_statuses": designs.UNIT_STATUSES}


def engineering_route(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        expected_token = browser_session.get("engineering_csrf")
        if request.method == "POST" and (not expected_token or not secrets.compare_digest(
                expected_token.encode(), request.form.get("csrf", "").encode())):
            abort(400, description="Form expired. Reload the page and try again.")
        with get_session() as db:
            try:
                result = function(db, *args, **kwargs)
                if request.method == "POST":
                    db.commit()
                return result
            except (ValueError, IntegrityError, OperationalError) as error:
                db.rollback()
                if isinstance(error, ValueError):
                    message = str(error)
                elif isinstance(error, IntegrityError):
                    message = "This identifier already exists or the change conflicts with a protected record. Reload and check your entries."
                else:
                    message = "The database is busy. Reload and try again. No changes were saved."
                return render_template("engineering_error.html", message=message, back=request.path), 400
    return wrapped


def get_or_404(db, model, identifier):
    item = db.get(model, identifier)
    if item is None:
        abort(404)
    return item


def integer(name, optional=False):
    value = request.form.get(name, "").strip()
    if not value and optional:
        return None
    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"Choose a valid {name.replace('_', ' ')}") from None
    if number < 1:
        raise ValueError("Identifiers must be positive")
    return number


def paginate(query):
    page = max(1, request.args.get("page", 1, type=int))
    pages = max(1, (query.count() + 49) // 50)
    page = min(page, pages)
    return query.offset((page - 1) * 50).limit(50).all(), page, pages


@ui_bp.route("/designs", methods=["GET", "POST"])
@engineering_route
def designs_index(db):
    if request.method == "POST":
        item = designs.create_project(db, request.form.get("document_id"), request.form.get("name"),
            request.form.get("description", ""), request.form.get("repository_url", ""))
        return redirect(f"/designs/{item.id}", 303)
    q = request.args.get("q", "").strip()
    query = db.query(DesignProject)
    if q:
        query = query.filter(or_(DesignProject.document_id.icontains(q, autoescape=True),
                                 DesignProject.code.icontains(q, autoescape=True),
                                 DesignProject.name.icontains(q, autoescape=True)))
    items, page, pages = paginate(query.order_by(DesignProject.code))
    return render_template("designs.html", items=items, q=q, page=page, pages=pages)


@ui_bp.route("/designs/<int:project_id>", methods=["GET", "POST"])
@engineering_route
def design_project(db, project_id):
    project = get_or_404(db, DesignProject, project_id)
    if request.method == "POST":
        if request.form.get("action") == "archive":
            project.archived = True
            return redirect(request.path, 303)
        if request.form.get("action") == "edit":
            document_id = request.form.get("document_id", "").strip()
            if document_id:
                document_id, code = designs.pbom_document_id(document_id)
                if code != project.code:
                    raise ValueError("DOCUMENT_ID must identify this project's existing identifier")
                project.document_id = document_id
            project.name = designs.required(request.form.get("name"), "Project name")
            project.description = request.form.get("description", "").strip()
            url = request.form.get("repository_url", "").strip()
            if url and not url.startswith(("https://", "http://", "git@github.com:")):
                raise ValueError("Repository must use HTTP(S) or GitHub SSH")
            project.repository_url = url
            return redirect(request.path, 303)
        board = designs.create_board(db, project.id, request.form.get("code"), request.form.get("name"),
            request.form.get("description", ""), request.form.get("part_id", ""))
        return redirect(f"/designs/boards/{board.id}", 303)
    return render_template("design_project.html", project=project)


@ui_bp.route("/designs/boards/<int:board_id>", methods=["GET", "POST"])
@engineering_route
def design_board(db, board_id):
    board = get_or_404(db, BoardDesign, board_id)
    if request.method == "POST":
        if request.form.get("action") == "edit_board":
            from services.inventory_service import lock_inventory
            lock_inventory(db)
            part_id = designs._part(db, request.form.get("part_id", ""))
            if part_id != board.part_id and db.query(PhysicalUnit).filter_by(board_id=board.id).count():
                raise ValueError("A board's inventory ownership cannot change after serial units have been registered")
            board.name = designs.required(request.form.get("name"), "Board name")
            board.description, board.part_id = request.form.get("description", "").strip(), part_id
            return redirect(request.path, 303)
        release = designs.create_release(db, board.id, request.form.get("revision"),
            *[request.form.get(k, "") for k in ("notes", "source_commit", "tool_versions", "dependency_notes")])
        return redirect(f"/designs/releases/{release.id}", 303)
    units = db.query(PhysicalUnit).filter_by(board_id=board.id).order_by(PhysicalUnit.serial_key).limit(50).all()
    return render_template("design_board.html", board=board, units=units)


@ui_bp.route("/designs/releases/<int:release_id>", methods=["GET", "POST"])
@engineering_route
def design_release(db, release_id):
    release = get_or_404(db, DesignRelease, release_id)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "upload":
            upload = request.files.get("file")
            if not upload or not upload.filename:
                raise ValueError("Choose a file to archive")
            designs.add_artifact(db, upload.stream, upload.filename, request.form.get("role"),
                                  release_id=release.id, provenance=request.form.get("provenance", ""))
        elif action == "publish":
            designs.publish_release(db, release.id, request.form.get("missing_reason", ""))
        elif action == "git_import":
            from services.jobs import enqueue
            if release.status != "draft":
                raise ValueError("Only draft releases can import source snapshots")
            job = enqueue(db, "design_git", {"release_id": release.id, "revision": request.form.get("git_revision", "").strip()}, f"design:{release.id}")
            flash(f"Git snapshot queued as job #{job.id}. See Background jobs for its result.", "success")
        elif action == "edit":
            designs.edit_release(db, release.id, *[request.form.get(k, "") for k in
                ("notes", "source_commit", "tool_versions", "dependency_notes")])
        elif action == "bom_import":
            from services.build_service import import_bom
            upload = request.files.get("file")
            if not upload or not upload.filename:
                raise ValueError("Choose the exported BOM CSV")
            import_bom(db, release.id, upload.stream.read(10 * 1024 * 1024 + 1), upload.filename)
        elif action == "bom_map":
            from services.build_service import map_bom
            map_bom(db, release.id, request.form)
        elif action == "supersede":
            if release.status != "released":
                raise ValueError("Only a published release can be superseded")
            release.status = "superseded"
        elif action == "issue":
            designs.create_issue(db, request.form.get("title"), request.form.get("description", ""),
                                 release_id=release.id, severity=request.form.get("severity", "normal"))
        elif action == "resolve":
            issue = get_or_404(db, EngineeringIssue, integer("issue_id"))
            if issue.release_id != release.id or issue.unit_id:
                abort(404)
            designs.resolve_issue(db, issue.id, request.form.get("resolution"))
        else:
            raise ValueError("Unknown release action")
        return redirect(request.path, 303)
    units = db.query(PhysicalUnit).filter_by(release_id=release.id).order_by(PhysicalUnit.serial_key).limit(50).all()
    issues = db.query(EngineeringIssue).filter_by(release_id=release.id, unit_id=None).order_by(EngineeringIssue.id.desc()).all()
    missing = sorted(designs.RELEASE_REQUIRED_ROLES - {a.role for a in release.artifacts})
    return render_template("design_release.html", release=release, units=units, issues=issues, missing=missing,
                           supporting_roles=designs.SUPPORTING_ROLES,
                           assembly=db.query(AssemblyDefinition).filter_by(release_id=release.id).first(),
                           builds=db.query(BuildBatch).filter_by(release_id=release.id).all())


@ui_bp.route("/designs/artifacts/<int:artifact_id>/download")
@engineering_route
def design_artifact(db, artifact_id):
    artifact = get_or_404(db, DesignArtifact, artifact_id)
    path = designs.verify_artifact(artifact)
    # Downloads never execute uploaded HTML/SVG. Only PDF and raster images may be previewed.
    inline = request.args.get("preview") == "1" and artifact.media_type in {"application/pdf", "image/png", "image/jpeg"}
    response = send_file(path, mimetype=artifact.media_type if inline else "application/octet-stream",
                         as_attachment=not inline, download_name=artifact.filename,
                         etag=artifact.sha256, conditional=True)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


@ui_bp.route("/designs/releases/<int:release_id>/manifest")
@engineering_route
def release_manifest(db, release_id):
    release = get_or_404(db, DesignRelease, release_id)
    if release.status == "draft":
        raise ValueError("Publish the draft to freeze its manifest")
    response = jsonify(json.loads(release.manifest_json))
    response.headers["Content-Disposition"] = f'attachment; filename="release-{release.id}-manifest.json"'
    return response


@ui_bp.route("/prototypes", methods=["GET", "POST"])
@engineering_route
def prototypes_index(db):
    if request.method == "POST":
        unit = designs.register_unit(db, integer("board_id"), request.form.get("serial"),
            release_id=integer("release_id", True), part_id=request.form.get("part_id", ""),
            historical=request.form.get("registration", "historical") == "historical",
            stage=request.form.get("stage", "prototype"), location=request.form.get("location", ""),
            notes=request.form.get("notes", ""), generate_serial=request.form.get("generate_serial") == "yes")
        return redirect(f"/prototypes/{unit.id}", 303)
    q = request.args.get("q", "").strip()
    query = db.query(PhysicalUnit)
    if request.args.get("archived") != "1":
        query = query.filter(PhysicalUnit.archived.is_(False))
    if q:
        query = query.filter(PhysicalUnit.serial_key.contains(q.casefold(), autoescape=True))
    for field in ("board_id", "release_id", "part_id", "stage", "status"):
        if request.args.get(field):
            query = query.filter(getattr(PhysicalUnit, field) == request.args[field])
    if request.args.get("unresolved") == "1":
        query = query.filter(PhysicalUnit.release_id.is_(None))
    query = query.order_by(PhysicalUnit.serial_key)
    if request.args.get("format") == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Serial", "Project", "Board", "Revision", "Stage", "Status", "Location", "Last recorded firmware"])
        def safe(value):
            value = str(value or "")
            return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
        for unit in query.yield_per(100):
            writer.writerow([safe(v) for v in [unit.serial, unit.board.project.code if unit.board else unit.part_id,
                unit.board.code if unit.board else "Product",
                unit.release.revision if unit.release else "Unresolved", unit.stage, unit.status, unit.location, unit.firmware_version]])
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": 'attachment; filename="serial-units.csv"'})
    units, page, pages = paginate(query)
    boards = db.query(BoardDesign).join(DesignProject).filter(DesignProject.archived.is_(False), BoardDesign.archived.is_(False)).order_by(DesignProject.code, BoardDesign.code).all()
    releases = db.query(DesignRelease).order_by(DesignRelease.id.desc()).all()
    return render_template("prototypes.html", units=units, boards=boards, releases=releases, q=q, page=page, pages=pages)


@ui_bp.route("/prototypes/<int:unit_id>", methods=["GET", "POST"])
@engineering_route
def prototype_detail(db, unit_id):
    unit = get_or_404(db, PhysicalUnit, unit_id)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "edit":
            designs.edit_unit(db, unit.id, **{k: request.form.get(k, "") for k in ("serial", "stage", "location", "notes", "reason")})
        elif action in {"archive", "restore"}:
            designs.archive_unit(db, unit.id, archive=action == "archive", reason=request.form.get("reason", ""))
        elif action == "status":
            status = request.form.get("status", "")
            designs.record_event(db, unit.id, "status", "Status changed to " + status.upper(),
                                 request.form.get("reason", ""), {"status": status})
        elif action == "event":
            details = {k: request.form.get(k, "").strip() for k in
                ("version", "repository", "commit", "references", "before", "after", "reason", "outcome", "procedure", "status", "location")}
            event = designs.record_event(db, unit.id, request.form.get("kind"), request.form.get("title"),
                request.form.get("notes", ""), {k: v for k, v in details.items() if v},
                event_at=request.form.get("event_at") or None, corrects_id=integer("corrects_id", True))
            upload = request.files.get("file")
            if upload and upload.filename:
                designs.add_artifact(db, upload.stream, upload.filename, request.form.get("role", "test_report"),
                                      event_id=event.id, provenance="Attached when recording event")
        elif action == "issue":
            issue = designs.create_issue(db, request.form.get("title"), request.form.get("description", ""),
                unit_id=unit.id, severity=request.form.get("severity", "normal"))
            designs.record_event(db, unit.id, "fault", f"Issue #{issue.id}: {issue.title}", issue.description, {"issue_id": issue.id})
        elif action == "resolve":
            issue = get_or_404(db, EngineeringIssue, integer("issue_id"))
            if issue.unit_id != unit.id:
                abort(404)
            designs.resolve_issue(db, issue.id, request.form.get("resolution"))
        elif action == "reconcile":
            release = get_or_404(db, DesignRelease, integer("release_id"))
            if unit.release_id or (unit.board_id and release.board_id != unit.board_id) or (
                    not unit.board_id and release.board.part_id != unit.part_id):
                raise ValueError("Only unresolved units can be linked to a revision of their own board")
            designs.record_event(db, unit.id, "note", "Historical release identified", request.form.get("notes", ""), {"release_id": release.id})
            unit.release_id = release.id
            unit.board_id = release.board_id
        else:
            raise ValueError("Unknown prototype action")
        return redirect(request.path, 303)
    events, page, pages = paginate(db.query(UnitEvent).filter_by(unit_id=unit.id).order_by(UnitEvent.event_at.desc(), UnitEvent.id.desc()))
    issues = db.query(EngineeringIssue).filter_by(unit_id=unit.id).order_by(EngineeringIssue.id.desc()).all()
    release_issues = db.query(EngineeringIssue).filter_by(release_id=unit.release_id, unit_id=None).all() if unit.release_id else []
    return render_template("prototype_detail.html", unit=unit, events=events, issues=issues,
                           release_issues=release_issues, page=page, pages=pages,
                           available_releases=db.query(DesignRelease).join(BoardDesign).filter(
                               BoardDesign.id == unit.board_id if unit.board_id else BoardDesign.part_id == unit.part_id).all())


@ui_bp.route("/prototypes/<int:unit_id>/history.json")
@engineering_route
def prototype_history(db, unit_id):
    unit = get_or_404(db, PhysicalUnit, unit_id)
    response = jsonify({"serial": unit.serial, "part_id": unit.part_id, "status": unit.status, "archived": unit.archived,
        "project": unit.board.project.code if unit.board else None, "board": unit.board.code if unit.board else None,
        "revision": unit.release.revision if unit.release else None, "last_recorded_firmware": unit.firmware_version,
        "events": [{"id": e.id, "kind": e.kind, "title": e.title, "notes": e.notes, "actor": e.actor,
            "event_at": e.event_at.isoformat() + "Z", "recorded_at": e.recorded_at.isoformat() + "Z",
            "corrects_id": e.corrects_id, "details": json.loads(e.details_json),
            "attachments": [{"filename": a.filename, "sha256": a.sha256, "role": a.role,
                "download": f"/designs/artifacts/{a.id}/download"} for a in e.artifacts]} for e in unit.events]})
    response.headers["Content-Disposition"] = f'attachment; filename="unit-{unit.id}-history.json"'
    return response


@ui_bp.route("/part/<dmtuid>/serials", methods=["GET", "POST"])
@engineering_route
def product_serials(db, dmtuid):
    product = get_or_404(db, Part, dmtuid.upper())
    if request.method == "GET":
        return redirect(f"/part/{product.dmtuid}#serials")
    unit = designs.register_unit(db, integer("board_id", True), request.form.get("serial"), part_id=product.dmtuid,
        release_id=integer("release_id", True), historical=request.form.get("registration", "historical") == "historical",
        stage=request.form.get("stage", "production"), location=request.form.get("location", ""),
        notes=request.form.get("notes", ""), generate_serial=request.form.get("generate_serial") == "yes")
    return redirect(f"/prototypes/{unit.id}", 303)


@ui_bp.route("/settings/serials", methods=["GET", "POST"])
@engineering_route
def serial_settings(db):
    from schema.loader import get_domains
    domains = get_domains()
    if request.method == "POST":
        from services.inventory_service import lock_inventory
        lock_inventory(db)
        enabled = set(request.form.getlist("enabled"))
        if not enabled <= {d["tt"] for d in domains}:
            raise ValueError("Unknown domain")
        for domain in domains:
            policy = db.get(DomainSerialPolicy, domain["tt"])
            if not policy:
                policy = DomainSerialPolicy(tt=domain["tt"])
                db.add(policy)
            policy.enabled = domain["tt"] in enabled
            policy.serial_prefix = request.form.get("prefix_" + domain["tt"], "").strip()
            if len(policy.serial_prefix) > 80 or any(ord(c) < 32 for c in policy.serial_prefix):
                raise ValueError("Serial prefix must be at most 80 printable characters")
        flash("Serial-tracking domains saved. Existing unit records remain accessible.", "success")
        return redirect(request.path, 303)
    return render_template("serial_settings.html", domains=domains,
                           policies={p.tt: p for p in db.query(DomainSerialPolicy)})


@ui_bp.route("/settings/backup", methods=["GET", "POST"])
@engineering_route
def backup_settings(db):
    if request.method == "POST":
        from services.backup_service import create_bundle
        from db.engine import _engine
        path = create_bundle(_engine)
        return send_file(path, as_attachment=True, download_name=path.name, mimetype="application/zip")
    return render_template("backup_settings.html")
