"""Design archives and physical-unit history, independent of stock deduction."""
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

from sqlalchemy import select, text
from db.models import (DesignProject, BoardDesign, DesignRelease, PhysicalUnit,
                       UnitEvent, DesignArtifact, EngineeringIssue, Part, DomainSerialPolicy)
from services.inventory_service import lock_inventory
from services.document_ids import pbom_document_id
import config

ARTIFACT_ROLES = {
    "source_snapshot": "Source / complete project ZIP", "schematic": "Schematic source",
    "pcb": "Board source", "manufacturing": "Manufacturing exports",
    "submitted_manufacturing": "Exact package submitted to factory",
    "factory_return": "Factory-returned files", "bom": "Bill of materials",
    "placement": "Placement / CPL", "schematic_pdf": "Schematic PDF",
    "board_preview": "Board image", "mechanical": "Mechanical / STEP",
    "dependency": "Library dependencies", "firmware_binary": "Firmware binary",
    "test_report": "Test report", "notes": "Supporting document",
}
RELEASE_REQUIRED_ROLES = {"source_snapshot", "schematic_pdf", "manufacturing", "bom", "placement", "dependency"}
SUPPORTING_ROLES = {"factory_return", "test_report", "notes"}
EVENT_KINDS = {"note", "firmware", "modification", "test", "fault", "repair", "status", "location", "correction"}
UNIT_STATUSES = ("active", "in-test", "faulty", "repaired", "retired", "waste")


def serial_enabled(session, part):
    policy = session.get(DomainSerialPolicy, part.tt)
    return bool(policy and policy.enabled)


def unit_scope(board_id, part_id):
    return f"part:{part_id}" if part_id else f"board:{board_id}"


def required(value, label, limit=200):
    value = str(value or "").strip()
    if not value or len(value) > limit:
        raise ValueError(f"{label} is required (maximum {limit} characters)")
    return value


def _part(session, uid):
    uid = (uid or "").strip().upper()
    if uid and not session.get(Part, uid):
        raise ValueError("Linked inventory part does not exist")
    return uid or None


def _project_lock(session, project_id):
    session.execute(text("UPDATE design_projects SET id=id WHERE id=:id"), {"id": project_id})


def create_project(session, document_id, name, description="", repository_url=""):
    document_id, code = pbom_document_id(document_id)
    lock_inventory(session)
    if session.scalar(select(DesignProject.id).where(DesignProject.code == code)):
        raise ValueError("This document belongs to an existing project. Add its board or revision there.")
    repository_url = repository_url.strip()
    if repository_url and not repository_url.startswith(("https://", "http://", "git@github.com:")):
        raise ValueError("Repository URL must be an HTTP(S) link")
    project = DesignProject(code=code, document_id=document_id, name=required(name, "Name"), description=description.strip(),
                            repository_url=repository_url)
    session.add(project)
    session.flush()
    return project


def create_board(session, project_id, code, name, description="", part_id=""):
    project = session.get(DesignProject, project_id)
    if not project or project.archived:
        raise ValueError("Choose an active project")
    code = str(code).strip().zfill(2)
    if not re.fullmatch(r"[0-9]{2}", code) or code == "00":
        raise ValueError("Board code must be 01–99")
    board = BoardDesign(project_id=project.id, code=code, name=required(name, "Board name"),
                        description=description.strip(), part_id=_part(session, part_id))
    session.add(board)
    session.flush()
    return board


def create_release(session, board_id, revision, notes="", source_commit="", tool_versions="", dependency_notes=""):
    board = session.get(BoardDesign, board_id)
    if not board or board.archived or board.project.archived:
        raise ValueError("Choose an active board design")
    revision = required(revision, "Revision", 40)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}", revision):
        raise ValueError("Revision can contain letters, digits, dots, underscores and hyphens")
    source_commit = source_commit.strip()
    if source_commit and not re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", source_commit):
        raise ValueError("Use a full source commit hash, or leave it empty for an uploaded working copy")
    release = DesignRelease(board_id=board_id, revision=revision, notes=notes.strip(),
                            source_commit=source_commit.lower(), tool_versions=tool_versions.strip(),
                            dependency_notes=dependency_notes.strip())
    session.add(release)
    session.flush()
    return release


def _inspect_zip(path):
    entries, expanded = [], 0
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 5000:
                raise ValueError("Archive has too many files (maximum 5000)")
            for info in infos:
                name = info.filename.replace("\\", "/")
                parts = PurePosixPath(name)
                if parts.is_absolute() or ".." in parts.parts or ":" in name or "\x00" in name:
                    raise ValueError("Archive contains an unsafe path")
                if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                    raise ValueError("Archive links and encrypted entries are not supported")
                expanded += info.file_size
                if expanded > 500 * 1024 * 1024 or info.file_size > 100 * 1024 * 1024:
                    raise ValueError("Expanded archive exceeds the size limit")
                if info.file_size > max(info.compress_size, 1) * 500:
                    raise ValueError("Archive compression ratio exceeds the limit")
                entries.append({"name": name, "size": info.file_size, "directory": info.is_dir()})
    except zipfile.BadZipFile:
        raise ValueError("Invalid ZIP archive") from None
    return entries


def blob_path(sha):
    if not re.fullmatch(r"[a-f0-9]{64}", sha):
        raise ValueError("Invalid artifact checksum")
    return config.ARTIFACTS_DIR / sha[:2] / (sha + ".blob")


def store_upload(stream, filename):
    """Keep original bytes under an immutable content hash; never edit CAD files."""
    filename = required(str(filename).replace("\\", "/").split("/")[-1], "Filename", 255)
    if filename in {".", ".."} or any(ord(c) < 32 for c in filename):
        raise ValueError("Invalid filename")
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    digest, size = hashlib.sha256(), 0
    with tempfile.NamedTemporaryFile(dir=config.ARTIFACTS_DIR, delete=False) as staged:
        temporary = Path(staged.name)
        try:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > config.ARTIFACT_MAX_BYTES:
                    raise ValueError("File exceeds the configured upload limit")
                digest.update(chunk)
                staged.write(chunk)
            staged.flush()
            os.fsync(staged.fileno())
        except Exception:
            staged.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        if size == 0:
            raise ValueError("Empty files cannot be archived")
        archive_manifest = _inspect_zip(temporary) if filename.lower().endswith(".zip") else []
        sha = digest.hexdigest()
        destination = blob_path(sha)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(temporary, destination)  # Atomic publication; never overwrite an existing blob.
        except FileExistsError:
            if destination.stat().st_size != size or hashlib.sha256(destination.read_bytes()).hexdigest() != sha:
                raise ValueError("Existing artifact storage failed checksum validation")
        return {"filename": filename, "size": size, "sha256": sha,
                "media_type": mimetypes.guess_type(filename)[0] or "application/octet-stream",
                "archive_manifest": json.dumps(archive_manifest)}
    finally:
        temporary.unlink(missing_ok=True)


def add_artifact(session, stream, filename, role, *, release_id=None, event_id=None, provenance=""):
    if role not in ARTIFACT_ROLES or bool(release_id) == bool(event_id):
        raise ValueError("Choose a valid artifact role and one owner")
    if role == "source_snapshot" and not filename.lower().endswith(".zip"):
        raise ValueError("A source snapshot must be a complete project ZIP")
    if release_id:
        release = session.get(DesignRelease, release_id)
        if not release:
            raise ValueError("Release does not exist")
        _project_lock(session, release.board.project_id)
        session.refresh(release)
        if release.status != "draft" and role not in SUPPORTING_ROLES:
            raise ValueError("Released source/manufacturing files are immutable; create a new release")
    elif not session.get(UnitEvent, event_id):
        raise ValueError("History event does not exist")
    artifact = DesignArtifact(**store_upload(stream, filename), role=role, release_id=release_id,
                              event_id=event_id, provenance=provenance.strip())
    session.add(artifact)
    session.flush()
    return artifact


def publish_release(session, release_id, missing_reason=""):
    release = session.get(DesignRelease, release_id)
    if not release:
        raise ValueError("Release does not exist")
    _project_lock(session, release.board.project_id)
    session.refresh(release)
    if release.status != "draft":
        raise ValueError("This release is already frozen")
    artifacts = list(session.scalars(select(DesignArtifact).where(DesignArtifact.release_id == release.id)))
    roles = {a.role for a in artifacts}
    if "source_snapshot" not in roles or not release.notes:
        raise ValueError("Publishing requires a source snapshot and release notes")
    missing = sorted(RELEASE_REQUIRED_ROLES - roles)
    if (missing or not release.dependency_notes or "UNRESOLVED:" in release.dependency_notes) and not missing_reason.strip():
        raise ValueError("Record why missing artifacts/dependencies are absent before publishing")
    for artifact in artifacts:
        verify_artifact(artifact)
    from db.models import AssemblyDefinition
    from services.build_service import bom_errors
    definition = session.scalar(select(AssemblyDefinition).where(AssemblyDefinition.release_id == release.id))
    assembly = None
    if definition:
        lines = json.loads(definition.lines_json)
        errors = bom_errors(session, lines)
        if errors and not missing_reason.strip():
            raise ValueError("Map all required BOM parts or explicitly acknowledge the unresolved mappings")
        assembly = {"id": definition.id, "source_artifact_id": definition.source_artifact_id,
                    "lines": lines, "unresolved": errors}
    release.manifest_json = json.dumps({"artifacts": [{"id": a.id, "filename": a.filename,
        "role": a.role, "sha256": a.sha256, "size": a.size} for a in artifacts],
        "missing_roles": missing, "dependencies": release.dependency_notes,
        "source_commit": release.source_commit, "tool_versions": release.tool_versions,
        "assembly_definition": assembly}, sort_keys=True)
    release.missing_artifacts_reason = missing_reason.strip()
    release.status = "released"
    release.released_at = datetime.now(timezone.utc)
    session.flush()
    return release


def verify_artifact(artifact):
    path = blob_path(artifact.sha256)
    if not path.is_file() or path.stat().st_size != artifact.size:
        raise ValueError("Archived file is missing or damaged")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()
    if digest != artifact.sha256:
        raise ValueError("Archived file checksum does not match")
    return path


def register_unit(session, board_id, serial, *, release_id=None, part_id="", historical=True,
                  stage="prototype", location="", notes="", actor="web-interface", generate_serial=False):
    lock_inventory(session)
    board = session.get(BoardDesign, board_id) if board_id else None
    if board_id and not board:
        raise ValueError("Choose a valid board design")
    linked_part = _part(session, part_id) or (board.part_id if board else None)
    product = session.get(Part, linked_part) if linked_part else None
    if board and board.part_id and linked_part != board.part_id:
        raise ValueError("This design is linked to a different inventory product")
    if not board and (not product or not serial_enabled(session, product)):
        raise ValueError("Serial tracking must be enabled for this product's domain")
    if stage not in {"prototype", "pre-production", "production"}:
        raise ValueError("Invalid lifecycle stage")
    release = session.get(DesignRelease, release_id) if release_id else None
    if release_id and (not release or not board or release.board_id != board.id):
        raise ValueError("Release must belong to the selected board")
    if not historical and board and (not release or release.status not in {"released", "superseded"}):
        raise ValueError("A new designed unit must reference a released revision")
    scope = unit_scope(board.id if board else None, linked_part)
    if generate_serial:
        if historical:
            raise ValueError("Enter the actual serial for a historical unit; do not generate a historical identifier")
        policy = session.get(DomainSerialPolicy, product.tt) if product else None
        prefix = (policy.serial_prefix if policy and policy.serial_prefix else
                  f"{board.project.code}-{board.code}-" if board else f"{linked_part}-")
        number = 1
        while session.scalar(select(PhysicalUnit.id).where(PhysicalUnit.serial_scope == scope,
                PhysicalUnit.serial_key == f"{prefix}{number:05d}".casefold())):
            number += 1
        serial = f"{prefix}{number:05d}"
    serial = required(serial, "Serial number", 120)
    if session.scalar(select(PhysicalUnit.id).where(PhysicalUnit.serial_scope == scope,
                                                  PhysicalUnit.serial_key == serial.casefold())):
        raise ValueError("Serial number already exists for this product/design (comparison ignores case)")
    unit = PhysicalUnit(serial=serial, serial_key=serial.casefold(), serial_scope=scope,
                        board_id=board.id if board else None, release_id=release.id if release else None,
                        part_id=linked_part, historical=historical, stage=stage,
                        location=location.strip(), notes=notes.strip())
    session.add(unit)
    session.flush()
    event = UnitEvent(unit_id=unit.id, kind="registration", title="Historical unit registered" if historical else "Unit registered",
                     notes=notes.strip(), actor=actor, event_at=datetime.now(timezone.utc),
                     details_json=json.dumps({"release_id": unit.release_id, "historical": historical,
                                              "location": unit.location, "stage": stage}))
    session.add(event)
    session.flush()
    return unit


def record_event(session, unit_id, kind, title, notes="", details=None, *, actor="web-interface", event_at=None, corrects_id=None):
    unit = session.get(PhysicalUnit, unit_id)
    if not unit or kind not in EVENT_KINDS:
        raise ValueError("Choose a unit and valid history event")
    lock_inventory(session)
    session.refresh(unit)
    details = dict(details or {})
    when = event_at or datetime.now(timezone.utc)
    if isinstance(when, str):
        when = datetime.fromisoformat(when.replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    when = when.astimezone(timezone.utc)
    if when > datetime.now(timezone.utc):
        raise ValueError("A recorded event cannot be in the future")
    if corrects_id:
        old = session.get(UnitEvent, corrects_id)
        if not old or old.unit_id != unit.id:
            raise ValueError("Correction must reference an event on this unit")
    if kind == "firmware":
        details["version"] = required(details.get("version"), "Firmware version")
        commit = details.get("commit", "").strip()
        if commit and not re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", commit):
            raise ValueError("Firmware commit must be a full hash")
    if kind == "modification" and not notes.strip():
        raise ValueError("Describe the hardware change and affected reference designators")
    if kind == "test" and details.get("outcome") not in {"pass", "fail", "inconclusive"}:
        raise ValueError("Choose a test outcome")
    if kind == "status" and details.get("status") not in UNIT_STATUSES:
        raise ValueError("Choose a valid unit status")
    if kind == "status" and details.get("status") == "waste" and not notes.strip():
        raise ValueError("Record why this unit is WASTE")
    if kind == "location":
        details["location"] = required(details.get("location"), "Location")
    event = UnitEvent(unit_id=unit.id, kind=kind, title=required(title, "Title"), notes=notes.strip(),
                      details_json=json.dumps(details), actor=actor, event_at=when, corrects_id=corrects_id)
    session.add(event)
    session.flush()
    # Backdated entries must not overwrite a newer recorded state.
    state_kinds = [kind, "edit"] if kind == "location" else [kind]
    latest = session.scalar(select(UnitEvent).where(UnitEvent.unit_id == unit.id, UnitEvent.kind.in_(state_kinds))
                            .order_by(UnitEvent.event_at.desc(), UnitEvent.id.desc()))
    if latest.id == event.id:
        if kind == "firmware": unit.firmware_version = details["version"]
        if kind == "status": unit.status = details["status"]
        if kind == "location": unit.location = details["location"]
    session.flush()
    return event


def create_issue(session, title, description, *, release_id=None, unit_id=None, severity="normal"):
    release = session.get(DesignRelease, release_id) if release_id else None
    unit = session.get(PhysicalUnit, unit_id) if unit_id else None
    if not release and not unit:
        raise ValueError("An issue must refer to a release or physical unit")
    if release and unit and unit.release_id != release.id:
        raise ValueError("The unit is not linked to this release")
    if severity not in {"low", "normal", "high", "critical"}:
        raise ValueError("Invalid severity")
    issue = EngineeringIssue(title=required(title, "Issue title"), description=description.strip(),
                              release_id=release_id, unit_id=unit_id, severity=severity)
    session.add(issue)
    session.flush()
    return issue


def resolve_issue(session, issue_id, resolution):
    issue = session.get(EngineeringIssue, issue_id)
    if not issue:
        raise ValueError("Issue does not exist")
    resolution = required(resolution, "Resolution", 10000)
    # Resolution is final for this report. A recurrence is a new issue, preserving history.
    result = session.execute(text("UPDATE engineering_issues SET status='resolved', resolution=:r, "
        "resolved_at=:at WHERE id=:id AND status='open'"),
        {"r": resolution, "at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(" "), "id": issue.id})
    if result.rowcount != 1:
        raise ValueError("This issue is already resolved; report a recurrence as a new issue")
    session.refresh(issue)
    if issue.unit_id:
        record_event(session, issue.unit_id, "note", f"Issue #{issue.id} resolved: {issue.title}", resolution,
                     {"issue_id": issue.id})
    return issue


def edit_release(session, release_id, notes, source_commit, tool_versions, dependency_notes):
    release = session.get(DesignRelease, release_id)
    if not release:
        raise ValueError("Release does not exist")
    _project_lock(session, release.board.project_id)
    session.refresh(release)
    if release.status != "draft":
        raise ValueError("Published release metadata is frozen")
    if source_commit and not re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", source_commit.strip()):
        raise ValueError("Use a full source commit hash")
    release.notes, release.source_commit = notes.strip(), source_commit.strip().lower()
    release.tool_versions, release.dependency_notes = tool_versions.strip(), dependency_notes.strip()
    session.flush()
    return release


def edit_unit(session, unit_id, *, serial, stage, location, notes, reason, actor="web-interface"):
    lock_inventory(session)
    unit = session.get(PhysicalUnit, unit_id, populate_existing=True)
    if not unit:
        raise ValueError("Unknown serial unit")
    serial = required(serial, "Serial number", 120)
    reason = required(reason, "Reason for editing", 10000)
    if stage not in {"prototype", "pre-production", "production"}:
        raise ValueError("Invalid lifecycle stage")
    duplicate = session.scalar(select(PhysicalUnit.id).where(PhysicalUnit.serial_scope == unit.serial_scope,
        PhysicalUnit.serial_key == serial.casefold(), PhysicalUnit.id != unit.id))
    if duplicate:
        raise ValueError("Serial number already exists for this product/design")
    before = {k: getattr(unit, k) for k in ("serial", "stage", "location", "notes")}
    after = {"serial": serial, "stage": stage, "location": location.strip(), "notes": notes.strip()}
    event = UnitEvent(unit_id=unit.id, kind="edit", title="Serial record edited", notes=reason, actor=actor,
                      event_at=datetime.now(timezone.utc), details_json=json.dumps({"before": before, "after": after}))
    session.add(event)
    session.flush()
    for key, value in after.items():
        setattr(unit, key, value)
    unit.serial_key = serial.casefold()
    session.flush()
    return unit


def archive_unit(session, unit_id, *, archive=True, reason, actor="web-interface"):
    lock_inventory(session)
    unit = session.get(PhysicalUnit, unit_id, populate_existing=True)
    if not unit:
        raise ValueError("Unknown serial unit")
    reason = required(reason, "Reason", 10000)
    if unit.archived == archive:
        return unit
    session.add(UnitEvent(unit_id=unit.id, kind="archive" if archive else "restore",
        title="Removed from active serial list" if archive else "Restored to active serial list", notes=reason,
        actor=actor, event_at=datetime.now(timezone.utc), details_json=json.dumps({"archived": archive})))
    unit.archived = archive
    session.flush()
    return unit
