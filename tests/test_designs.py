import io
import json
import re
import zipfile
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import text, select, func
from sqlalchemy.exc import IntegrityError
from db import get_session
from db.models import PhysicalUnit, UnitEvent, StockMovement, DesignArtifact, DesignRelease
from services import design_service as service


@pytest.fixture
def app(tmp_path, monkeypatch):
    import config
    from main import create_app
    monkeypatch.setattr(config, "DB_URL", f"sqlite:///{(tmp_path / 'designs.sqlite').as_posix()}")
    monkeypatch.setattr(config, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(config, "READ_ONLY_PREVIEW", False)
    result = create_app()
    result.config.update(TESTING=True)
    yield result
    import db.engine
    db.engine._engine.dispose()


def sample(db):
    project = service.create_project(db, "DMT-HW-TEST-01-SCH-V100", "Test project")
    board = service.create_board(db, project.id, "1", "Main board")
    release = service.create_release(db, board.id, "A1", "Initial hardware")
    return project, board, release


def zip_bytes(name="project/main.kicad_pcb", content=b"preserve these exact bytes"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(name, content)
    return output.getvalue()


def publish(db, release):
    service.add_artifact(db, io.BytesIO(zip_bytes()), "source.zip", "source_snapshot", release_id=release.id)
    service.publish_release(db, release.id, "Historical source only; manufacturing and dependencies unavailable")


def post(client, url, values):
    with client.session_transaction() as browser:
        token = browser["engineering_csrf"]
    return client.post(url, data={"csrf": token, **values}, follow_redirects=False)


def test_complete_html_archive_unit_flow(app):
    client = app.test_client()
    assert client.get("/designs").status_code == 200
    assert client.post("/designs", data={"document_id": "DMT-HW-FAIL-SCH-V100", "name": "Missing CSRF"}).status_code == 400
    response = post(client, "/designs", {"document_id": "DMT-HW-DEMO-01-PCB-V100", "name": "Board archive"})
    project_url = response.location
    assert response.status_code == 303
    assert client.get(project_url).status_code == 200
    board = post(client, project_url, {"code": "1", "name": "Controller"}).location
    assert client.get(board).status_code == 200
    release = post(client, board, {"revision": "A1", "notes": "First revision"}).location
    assert client.get(release).status_code == 200
    raw = zip_bytes()
    assert post(client, release, {"action": "upload", "role": "source_snapshot", "file": (io.BytesIO(raw), "board.zip")}).status_code == 303
    page = client.get(release)
    assert b"project/main.kicad_pcb" in page.data
    download = re.search(rb'href="(/designs/artifacts/\d+/download)"', page.data)[1].decode()
    assert client.get(download).data == raw
    assert post(client, release, {"action": "publish"}).status_code == 400
    assert post(client, release, {"action": "publish", "missing_reason": "Archive lacks historical manufacturing exports"}).status_code == 303
    assert client.get(release + "/manifest").json["artifacts"][0]["filename"] == "board.zip"
    assert client.get("/prototypes").status_code == 200
    unit = post(client, "/prototypes", {"board_id": "1", "release_id": "1", "serial": "XY-001"}).location
    assert client.get(unit).status_code == 200
    assert post(client, unit, {"action": "event", "kind": "firmware", "title": "Flash v2", "version": "2.0"}).status_code == 303
    assert b"Version-only record" in client.get(unit).data
    assert client.get(unit + "/history.json").json["last_recorded_firmware"] == "2.0"
    assert post(client, unit, {"action": "issue", "title": "Unstable USB", "description": "Fails during reset"}).status_code == 303
    assert post(client, unit, {"action": "resolve", "issue_id": "1", "resolution": "Replaced connector"}).status_code == 303
    assert b"Replaced connector" in client.get(unit).data
    assert b"XY-001" in client.get("/prototypes?format=csv").data
    assert b"XY-001" in client.get(board).data


def test_frozen_release_and_append_only_history(app):
    with get_session() as db:
        _, board, release = sample(db)
        publish(db, release)
        unit = service.register_unit(db, board.id, "001", release_id=release.id)
        db.commit()
        for statement in ["UPDATE design_releases SET notes='replacement'", "DELETE FROM design_releases",
                          "UPDATE design_artifacts SET filename='replacement'", "DELETE FROM design_artifacts",
                          "UPDATE unit_events SET notes='replacement'", "DELETE FROM unit_events",
                          "UPDATE physical_units SET serial='002'"]:
            with pytest.raises(IntegrityError):
                db.execute(text(statement))
            db.rollback()
        with pytest.raises(ValueError, match="immutable"):
            service.add_artifact(db, io.BytesIO(b"new"), "new.kicad_pcb", "pcb", release_id=release.id)
        db.rollback()
        service.add_artifact(db, io.BytesIO(b"factory response"), "factory.txt", "factory_return", release_id=release.id)
        db.commit()
        assert len(json.loads(release.manifest_json)["artifacts"]) == 1
        assert db.scalar(select(func.count()).select_from(DesignArtifact)) == 2


def test_historical_units_do_not_consume_and_serials_ignore_case(app):
    with get_session() as db:
        _, board, release = sample(db)
        unit = service.register_unit(db, board.id, " AbC-001 ")
        assert unit.release_id is None and unit.serial == "AbC-001"
        assert db.scalar(select(func.count()).select_from(StockMovement)) == 0
        with pytest.raises(ValueError, match="already exists"):
            service.register_unit(db, board.id, "abc-001")
        with pytest.raises(ValueError, match="released"):
            service.register_unit(db, board.id, "new", historical=False, release_id=release.id)
        with pytest.raises(ValueError, match="historical"):
            service.register_unit(db, board.id, "", generate_serial=True)


def test_new_units_require_exact_release_and_allocate_unique_serials(app):
    with get_session() as db:
        project, board, release = sample(db)
        other = service.create_board(db, project.id, "2", "Other board")
        publish(db, release)
        with pytest.raises(ValueError, match="belong"):
            service.register_unit(db, other.id, "bad", release_id=release.id)
        a = service.register_unit(db, board.id, "", historical=False, generate_serial=True, release_id=release.id)
        b = service.register_unit(db, board.id, "", historical=False, generate_serial=True, release_id=release.id)
        assert (a.serial, b.serial) == ("TEST-01-00001", "TEST-01-00002")


def test_backdated_firmware_and_issue_scopes(app):
    with get_session() as db:
        _, board, release = sample(db)
        unit = service.register_unit(db, board.id, "unit", release_id=release.id)
        service.record_event(db, unit.id, "firmware", "Current", details={"version": "2"})
        old = service.record_event(db, unit.id, "firmware", "Previous", details={"version": "1"},
                                  event_at=datetime.now(timezone.utc) - timedelta(days=10))
        assert unit.firmware_version == "2"
        service.record_event(db, unit.id, "correction", "Correction", "Old event uncertain", corrects_id=old.id)
        release_issue = service.create_issue(db, "Design error", "Affects all boards", release_id=release.id)
        unit_issue = service.create_issue(db, "Bad solder", "Unit-specific", unit_id=unit.id)
        service.resolve_issue(db, unit_issue.id, "Reworked joint")
        assert release_issue.status == "open"
        with pytest.raises(ValueError, match="already resolved"):
            service.resolve_issue(db, unit_issue.id, "Changed history")


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:/absolute", "a/../../outside"])
def test_unsafe_zip_rejected(app, name):
    with pytest.raises(ValueError, match="unsafe path"):
        service.store_upload(io.BytesIO(zip_bytes(name)), "bad.zip")


def test_artifact_damage_detected_and_upload_limit(app, monkeypatch):
    import config
    with get_session() as db:
        _, _, release = sample(db)
        a = service.add_artifact(db, io.BytesIO(b"original"), "board.kicad_pcb", "pcb", release_id=release.id)
        service.blob_path(a.sha256).write_bytes(b"tampered")
        with pytest.raises(ValueError, match="checksum"):
            service.verify_artifact(a)
        monkeypatch.setattr(config, "ARTIFACT_MAX_BYTES", 2)
        with pytest.raises(ValueError, match="limit"):
            service.store_upload(io.BytesIO(b"too long"), "file.txt")


def test_preview_allows_engineering_reads_and_blocks_writes(app, monkeypatch):
    import config
    from main import create_app
    with get_session() as db:
        _, board, release = sample(db)
        service.register_unit(db, board.id, "preview")
        db.commit()
    monkeypatch.setattr(config, "READ_ONLY_PREVIEW", True)
    client = create_app().test_client()
    for path in ["/designs", "/designs/1", "/designs/boards/1", "/designs/releases/1", "/prototypes", "/prototypes/1", "/prototypes/1/history.json"]:
        assert client.get(path).status_code == 200, path
        assert client.post(path).status_code == 403


def test_two_revisions_keep_distinct_files_serials_and_part_links(app):
    from services.parts_service import PartsService
    with get_session() as db:
        part = PartsService.create(db, {"tt": "29", "ff": "14", "cc": "02", "ss": "01",
                                      "Quantity": "2", "Location": "Prototype shelf", "_inventory_key": "prototype-count"})
        _, board, first = sample(db)
        board.part_id = part.dmtuid
        second = service.create_release(db, board.id, "B1", "Second hardware revision")
        for release in (first, second):
            service.add_artifact(db, io.BytesIO(zip_bytes(content=release.revision.encode())),
                                 "project.zip", "source_snapshot", release_id=release.id)
            service.publish_release(db, release.id, "Historical prototype source; other artifacts not available")
        a = service.register_unit(db, board.id, "OLD-A1", release_id=first.id)
        b = service.register_unit(db, board.id, "OLD-B1", release_id=second.id)
        assert a.part_id == b.part_id == part.dmtuid
        assert db.scalar(select(func.count()).select_from(StockMovement)) == 1
        assert first.artifacts[0].sha256 != second.artifacts[0].sha256
        db.commit()
        uid, a_id, b_id = part.dmtuid, a.id, b.id
    client = app.test_client()
    assert b"OLD-A1" in client.get(f"/part/{uid}").data
    assert b"OLD-B1" in client.get(f"/part/{uid}").data
    assert client.get(f"/prototypes/{a_id}/history.json").json["revision"] == "A1"
    assert client.get(f"/prototypes/{b_id}/history.json").json["revision"] == "B1"


def test_serial_allocation_serializes_concurrent_registrations(app):
    from concurrent.futures import ThreadPoolExecutor
    with get_session() as db:
        _, board, release = sample(db)
        publish(db, release)
        db.commit()
        board_id, release_id = board.id, release.id
    def register(_):
        with get_session() as db:
            unit = service.register_unit(db, board_id, "", release_id=release_id, historical=False, generate_serial=True)
            db.commit()
            return unit.serial
    with ThreadPoolExecutor(max_workers=3) as executor:
        serials = list(executor.map(register, range(3)))
    assert len(set(serials)) == 3
    assert sorted(serials) == ["TEST-01-00001", "TEST-01-00002", "TEST-01-00003"]
