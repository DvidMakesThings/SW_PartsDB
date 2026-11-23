import hashlib
import json
import os
import subprocess

import pytest
from sqlalchemy import select, func
from db import get_session
from db.models import LibrarySource, LibraryEntry, LibrarySyncRun, Part, StockHolding, StockMovement
from services import library_catalog as library
from services.inventory_service import summary
from services.parts_service import PartsService
from tests.test_designs import app, post


def entry(db, name, props):
    if not db.get(LibrarySource, 1):
        db.add(LibrarySource(id=1, name="Test library", repository_url=library.DEFAULT_URL))
        db.flush()
    raw = json.dumps(props, sort_keys=True)
    item = LibraryEntry(source_id=1, path="Test.kicad_sym", symbol=name, properties_json=raw,
        normalized_json=json.dumps(library.normalize_properties(props)), content_hash=hashlib.sha256(raw.encode()).hexdigest(), seen_commit="a" * 40)
    db.add(item)
    db.flush()
    return item


def part(db, mpn="TPS-test", manufacturer="Texas Instruments", **kwargs):
    return PartsService.create(db, {"tt": "01", "ff": "02", "cc": "01", "ss": "01",
                                   "mpn": mpn, "manufacturer": manufacturer, **kwargs})


def test_parser_inheritance_units_empty_fields_and_escapes():
    raw = br'''(kicad_symbol_lib (version 20251024)
      (symbol "BASE" (property "Manufacturer" "TI") (property "MPN" "ABC-TR")
        (property "Description" "Quoted \"label\" and \\ path")
        (symbol "BASE_1_1" (pin input line (name "A"))))
      (symbol "CHILD" (extends "BASE") (property "MPN" "") (property "Value" "10k")))'''
    symbols = dict(library.parse_symbols(raw))
    assert len(symbols) == 2
    assert symbols["CHILD"]["Manufacturer"] == "TI"
    assert symbols["CHILD"]["MPN"] == ""
    assert symbols["BASE"]["Description"] == 'Quoted "label" and \\ path'


@pytest.mark.parametrize("raw", [b"(kicad_symbol_lib", b"(kicad_symbol_lib) trailing",
    b'(kicad_symbol_lib (symbol "A" (extends "B")) (symbol "B" (extends "A")))',
    b'(kicad_symbol_lib (symbol "A") (symbol "A"))', b'(kicad_symbol_lib (symbol "A" (extends "missing")))'])
def test_malformed_libraries_fail_closed(raw):
    with pytest.raises(ValueError):
        library.parse_symbols(raw)


def test_exact_match_conflict_and_generic_not_merged(app):
    with get_session() as db:
        existing = part(db, Quantity="12", Location="A")
        first = entry(db, "Exact", {"MPN": " TPS-test ", "Manufacturer": "TI"})
        assert library.Matcher(db).evaluate(first)["part_id"] == existing.dmtuid
        library.review_entry(db, first.id, "link", first.content_hash, existing.dmtuid)
        assert summary(db, existing.dmtuid)["on_hand"] == 12
        changed = library.normalize_properties({"MPN": "TPS-test-X", "Manufacturer": "TI"})
        first.normalized_json = json.dumps(changed)
        first.content_hash = "b" * 64
        db.flush()
        assert library.Matcher(db).evaluate(first)["state"] == "conflict"
        generic = entry(db, "Generic", {"Value": "10k", "Footprint": "R_0603"})
        assert library.Matcher(db).evaluate(generic)["state"] == "unresolved"
        with pytest.raises(ValueError, match="orderable"):
            library.review_entry(db, generic.id, "create", generic.content_hash)
        conflicting = entry(db, "Conflict", {"DMTUID": existing.dmtuid, "Manufacturer": "TI", "MPN": "OTHER"})
        assert library.Matcher(db).evaluate(conflicting)["state"] == "conflict"


def test_create_catalogue_without_stock_and_second_representation_matches(app):
    with get_session() as db:
        item = entry(db, "Supplier identified", {"LCSC_PART": "C123456", "Value": "100nF"})
        library.review_entry(db, item.id, "create", item.content_hash,
                             classification={"tt": "01", "ff": "02", "cc": "01", "ss": "01"})
        assert summary(db, item.part_id)["status"] == "Not stocked"
        created = db.get(Part, item.part_id)
        assert created.kicad_symbol == "Test:Supplier identified"
        assert created.kicad_libref == "C123456"
        assert db.scalar(select(func.count()).select_from(StockHolding)) == 0
        assert db.scalar(select(func.count()).select_from(StockMovement)) == 0
        duplicate = entry(db, "Another representation", {"LCSC": "C123456"})
        match = library.Matcher(db).evaluate(duplicate)
        assert match["state"] == "match" and match["part_id"] == item.part_id
        with pytest.raises(ValueError, match="matches"):
            library.review_entry(db, duplicate.id, "create", duplicate.content_hash)


def test_existing_lcsc_field_and_http_availability_overlay(app):
    with get_session() as db:
        p = part(db, kicad_libref="C100", kicad_symbol="Test:Existing")
        item = entry(db, "Supplier match", {"LCSC_PART":"C100"})
        assert library.Matcher(db).evaluate(item)["part_id"] == p.dmtuid
        db.commit()
        uid=p.dmtuid
    data=app.test_client().get(f"/kicad/v1/parts/{uid}.json").json
    assert data["symbolIdStr"] == "Test:Existing"
    assert data["fields"]["LCSC_PART"]["value"] == "C100"
    assert data["fields"]["Stock status"]["value"] == "Not stocked"
    assert data["fields"]["Location"]["value"] == "Not stocked"


def test_duplicate_mpn_and_supplier_contradiction_require_review(app):
    with get_session() as db:
        first = part(db, lcsc="C100")
        second = part(db, mpn="other", lcsc="C200")
        item = entry(db, "Contradiction", {"MPN": first.mpn, "Manufacturer": first.manufacturer, "LCSC": "C200"})
        assert library.Matcher(db).evaluate(item)["state"] == "conflict"
        part(db)
        item = entry(db, "Ambiguous", {"MPN": first.mpn, "Manufacturer": first.manufacturer})
        assert library.Matcher(db).evaluate(item)["state"] == "conflict"


def test_review_staleness_alias_conflicts_and_suffix_preservation(app):
    with get_session() as db:
        item = entry(db, "Aliases", {"MPN": "ABC", "Manufacturer Part Number": "ABC-TR", "Manufacturer": "TI"})
        assert library.Matcher(db).evaluate(item)["state"] == "conflict"
        with pytest.raises(ValueError, match="changed"):
            library.review_entry(db, item.id, "ignore", "old hash")
        assert library.normalize_properties({"MPN": "ABC-TR"})["mpn"] == "abc-tr"


def git_snapshot(repo, files):
    env = dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
               GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid")
    def git(*args, data=None):
        return subprocess.run(["git", "-C", str(repo), *args], input=data, capture_output=True, check=True, env=env).stdout.strip()
    repo.mkdir(exist_ok=True)
    git("init", "--bare")
    git("read-tree", "--empty")
    for path, data in files.items():
        oid = git("hash-object", "-w", "--stdin", data=data).decode()
        git("update-index", "--add", "--cacheinfo", f"100644,{oid},{path}")
    tree = git("write-tree").decode()
    commit = git("commit-tree", tree, "-m", "Synthetic metadata fixture").decode()
    git("update-ref", "HEAD", commit)
    return commit


def test_git_snapshot_repeat_index_parse_failure_and_missing(app, tmp_path, monkeypatch):
    import config
    repo = tmp_path / "library.git"
    one = b'(kicad_symbol_lib (symbol "ONE" (property "MPN" "ABC") (property "Manufacturer" "TI")))'
    two = b'(kicad_symbol_lib (symbol "TWO" (property "Value" "100nF")))'
    commit = git_snapshot(repo, {"one.kicad_sym": one, "two.kicad_sym": two})
    monkeypatch.setattr(config, "LIBRARY_REPO_DIR", repo)
    with get_session() as db:
        db.add(LibrarySource(id=1, name="Test", repository_url=library.DEFAULT_URL))
        db.commit()
    assert library.sync_library(1)["symbols"] == 2
    assert library.sync_library(1)["counts"]["unchanged"] == 2
    git_snapshot(repo, {"one.kicad_sym": b"broken", "new.kicad_sym": two})
    report = library.sync_library(1)
    assert len(report["errors"]) == 1
    with get_session() as db:
        old = db.query(LibraryEntry).filter_by(path="one.kicad_sym").one()
        missing = db.query(LibraryEntry).filter_by(path="two.kicad_sym").one()
        assert not old.missing and old.seen_commit == commit
        assert library.Matcher(db).evaluate(old)["state"] == "parse_error"
        assert missing.missing
    monkeypatch.setattr(config, "LIBRARY_REPO_DIR", tmp_path / "nonexistent")
    with pytest.raises(ValueError, match="Git"):
        library.sync_library(1)
    with get_session() as db:
        assert db.query(LibraryEntry).count() == 3
        assert db.get(LibrarySource, 1).state == "failed"


def test_browser_review_and_source_configuration(app):
    with get_session() as db:
        p = part(db)
        item = entry(db, "Match", {"MPN": p.mpn, "MFR": p.manufacturer})
        db.commit()
        item_id = item.id
    client = app.test_client()
    assert client.get("/library-sync").status_code == 200
    response = client.get(f"/library-sync/entries/{item_id}")
    assert response.status_code == 200
    assert b"Unique strong identifier" in response.data
    assert post(client, f"/library-sync/entries/{item_id}", {"expected_hash": item.content_hash,
                "decision": "link", "part_id": p.dmtuid}).status_code == 303
    assert b"Library references" in client.get(f"/part/{p.dmtuid}").data
    assert post(client, "/library-sync", {"action": "configure", "repository_url": "https://secret:password@github.com/a/b"}).status_code == 400


def test_batch_creation_deduplicates_and_rolls_back_conflicts(app):
    with get_session() as db:
        one = entry(db, "First", {"MPN": "NEW-TR", "Manufacturer": "TI"})
        two = entry(db, "Second", {"MPN": "NEW-TR", "Manufacturer": "TI"})
        db.commit()
    client = app.test_client()
    client.get("/library-sync")
    response = post(client, "/library-sync", {"action": "create_selected", "commit": "",
        "entry_id": [str(one.id), str(two.id)], f"hash_{one.id}": one.content_hash, f"hash_{two.id}": two.content_hash,
        "family": "0102", "cc": "01", "ss": "01"})
    assert response.status_code == 303
    with get_session() as db:
        assert db.query(Part).count() == 1
        assert db.get(LibraryEntry, one.id).part_id == db.get(LibraryEntry, two.id).part_id
        three = entry(db, "Third", {"MPN": "OTHER", "Manufacturer": "TI"})
        generic = entry(db, "Generic", {"Value": "10k"})
        db.commit()
    response = post(client, "/library-sync", {"action": "create_selected", "commit": "",
        "entry_id": [str(three.id), str(generic.id)], f"hash_{three.id}": three.content_hash, f"hash_{generic.id}": generic.content_hash,
        "family": "0102", "cc": "01", "ss": "01"})
    assert response.status_code == 400
    with get_session() as db:
        assert db.query(Part).count() == 1
        assert db.query(StockHolding).count() == 0


@pytest.mark.parametrize("url", ["file:///etc", "http://github.com/a/b", "https://github.com.evil/a/b", "https://github.com/a/b?token=secret", "https://github.com/a/b#x"])
def test_repository_urls_cannot_embed_credentials_or_change_protocol(url):
    with pytest.raises(ValueError):
        library.validate_repository_url(url)
