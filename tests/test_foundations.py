import json
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from db.models import Base, Part
from db.migrations import ensure_schema, status, upgrade, alembic_config
from alembic import command
from local_config import LocalConfig
from manage import inventory_report, read_only_engine
from services.inventory_preview import classify_quantity


def legacy_database(tmp_path):
    path = tmp_path / "legacy.sqlite"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.begin() as c:
        command.upgrade(alembic_config(c), "0001_legacy")
        c.exec_driver_sql("DROP TABLE alembic_version")
    with Session(engine) as session:
        session.add_all([Part(dmtuid=f"DMT-0102010100{i}", tt="01", ff="02", cc="01", ss="01", xxx=f"00{i}",
                              quantity=count, location=location)
                         for i, count, location in [(1, "5", "Bin A"), (2, "", "Bin B"), (3, "0", "Bin C")]])
        session.commit()
    return path, engine


def test_config_precedence_and_relative_paths(tmp_path, monkeypatch):
    (tmp_path / "config.local.ini").write_text("[paths]\nlibrary_repo = ../library with spaces\n[server]\nport = 5010\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path.parent)
    cfg = LocalConfig(tmp_path, {"DMTDB_PORT": "5020"})
    assert cfg.get("server", "port", 5000, "DMTDB_PORT") == "5020"
    assert cfg.path("library_repo", "unused") == (tmp_path.parent / "library with spaces").resolve()
    assert cfg.path("database", "default.sqlite") == tmp_path / "default.sqlite"


def test_explicit_config_and_disabled_seed(tmp_path):
    folder = tmp_path / "settings"
    folder.mkdir()
    (folder / "local.ini").write_text("[paths]\ncsv_seed =\ndatabase = data.sqlite\n[server]\nsecret = literal%secret\n", encoding="utf-8")
    cfg = LocalConfig(tmp_path, {"DMTDB_CONFIG": "settings/local.ini"})
    assert cfg.path("database", "default") == folder / "data.sqlite"
    assert cfg.path("csv_seed", "default", optional=True) is None
    assert cfg.get("server", "secret") == "literal%secret"
    with pytest.raises(ValueError, match="existing file"):
        LocalConfig(tmp_path, {"DMTDB_CONFIG": "missing.ini"})


def test_malformed_config_does_not_echo_secret(tmp_path):
    (tmp_path / "config.local.ini").write_text("[server]\nsecret = TOPSECRET\nsecret = SECONDSECRET\n")
    with pytest.raises(ValueError) as error:
        LocalConfig(tmp_path, {})
    assert "SECRET" not in str(error.value)


def test_empty_required_path_and_bad_bool(tmp_path):
    cfg = LocalConfig(tmp_path, {"DIR": "", "FLAG": "perhaps"})
    with pytest.raises(ValueError, match="empty"):
        cfg.path("database", "db", "DIR")
    with pytest.raises(ValueError, match="boolean"):
        cfg.boolean("server", "debug", env="FLAG")


@pytest.mark.skipif(__import__('os').name == 'nt', reason="POSIX-only path rejection")
def test_windows_path_rejected_on_linux(tmp_path):
    cfg = LocalConfig(tmp_path, {"DIR": "G:/_GitHub/database.sqlite"})
    with pytest.raises(ValueError, match="Windows path"):
        cfg.path("database", "db", "DIR")


@pytest.mark.parametrize("raw,state,quantity", [
    (None, "unknown", None), ("", "unknown", None), ("  ", "unknown", None),
    ("0", "known", 0), (" 0012 ", "known", 12), ("-1", "review", None),
    ("1.5", "review", None), ("1e3", "review", None), ("1,000", "review", None),
    ("many", "review", None), ("１２", "review", None), (str(2**63), "review", None),
    ("9" * 5000, "review", None),
])
def test_quantity_classification(raw, state, quantity):
    assert classify_quantity(raw)[:2] == (state, quantity)


def test_fresh_schema_and_repeat_upgrade(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'fresh.sqlite').as_posix()}")
    ensure_schema(engine)
    with engine.connect() as connection:
        assert status(connection) == "current"
        assert len(inspect(connection).get_table_names()) == 27
    assert upgrade(engine, tmp_path / "backups")["status"] == "current"
    assert not (tmp_path / "backups").exists()
    engine.dispose()


def test_legacy_requires_explicit_upgrade_and_preserves_data(tmp_path):
    path, engine = legacy_database(tmp_path)
    with pytest.raises(RuntimeError, match="db-upgrade"):
        ensure_schema(engine)
    with engine.connect() as c:
        assert "alembic_version" not in inspect(c).get_table_names()
    report_before = inventory_report(read_only_engine(str(engine.url)))
    result = upgrade(engine, tmp_path / "backups")
    assert Path(result["backup"]).is_file()
    report_after = inventory_report(read_only_engine(str(engine.url)))
    assert report_before["items"] == report_after["items"]
    assert report_after["unknown_counts"] == 1
    assert report_after["known_quantity_total"] == 5
    with sqlite3.connect(result["backup"]) as backup:
        assert backup.execute("select count(*) from parts").fetchone()[0] == 3
    engine.dispose()


def test_populated_design_database_upgrades_with_serial_history(tmp_path):
    from db.models import PhysicalUnit, UnitEvent, EngineeringIssue
    from services.design_service import edit_unit
    engine = create_engine(f"sqlite:///{(tmp_path / 'design-v4.sqlite').as_posix()}")
    with engine.begin() as c:
        command.upgrade(alembic_config(c), "0004_library")
        c.exec_driver_sql("""INSERT INTO design_projects
            (id,code,name,description,repository_url,archived,created_at)
            VALUES (1,'ENER','ENERGIS','','',0,CURRENT_TIMESTAMP)""")
        c.exec_driver_sql("""INSERT INTO board_designs
            (id,project_id,code,name,description,archived)
            VALUES (1,1,'01','ENERGIS','','0')""")
        c.exec_driver_sql("""INSERT INTO physical_units
            (id,serial,serial_key,board_id,historical,stage,status,location,notes,firmware_version,created_at)
            VALUES (1,'SN001','sn001',1,1,'prototype','active','Shelf','','v1',CURRENT_TIMESTAMP)""")
        c.exec_driver_sql("""INSERT INTO unit_events
            (id,unit_id,kind,title,notes,details_json,actor,event_at,recorded_at)
            VALUES (1,1,'firmware','Initial firmware','','{"version":"v1"}','test',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""")
        c.exec_driver_sql("""INSERT INTO engineering_issues
            (id,unit_id,title,description,severity,status,resolution,created_at)
            VALUES (1,1,'Watchdog fault','Recorded before upgrade','minor','open','',CURRENT_TIMESTAMP)""")
    result = upgrade(engine, tmp_path / 'backups')
    assert result['revision'] == '0008_document_id'
    with engine.connect() as c:
        assert status(c) == 'current'
        assert c.exec_driver_sql('PRAGMA foreign_key_check').all() == []
        build_fk = next(row for row in c.exec_driver_sql('PRAGMA foreign_key_list(physical_units)').mappings()
                        if row['from'] == 'build_id')
        assert build_fk['on_delete'] == 'RESTRICT'
    with Session(engine) as db:
        unit = db.get(PhysicalUnit, 1)
        assert (unit.serial, unit.serial_scope, unit.archived, unit.build_id) == ('SN001', 'board:1', False, None)
        assert db.get(UnitEvent, 1).unit_id == unit.id
        assert db.get(EngineeringIssue, 1).unit_id == unit.id
        edit_unit(db, 1, serial='SN001-C', stage='prototype', location='Bench', notes='', reason='Label correction')
        db.commit()
        assert db.get(UnitEvent, 1).title == 'Initial firmware'
    with engine.begin() as c:
        with pytest.raises(Exception, match='history event'):
            c.exec_driver_sql("UPDATE physical_units SET serial='UNREVIEWED' WHERE id=1")
    engine.dispose()


def test_unknown_schema_and_version_are_not_modified(tmp_path):
    path, engine = legacy_database(tmp_path)
    with engine.begin() as c:
        c.exec_driver_sql("CREATE TABLE unexpected (id INTEGER)")
    with pytest.raises(RuntimeError, match="Unrecognized"):
        upgrade(engine, tmp_path / "backups")
    assert not (tmp_path / "backups").exists()
    with engine.begin() as c:
        c.exec_driver_sql("DROP TABLE unexpected")
        c.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        c.exec_driver_sql("INSERT INTO alembic_version VALUES ('9999_future')")
    with pytest.raises(RuntimeError, match="incompatible"):
        ensure_schema(engine)
    engine.dispose()


def test_preview_cannot_write_or_create_database(tmp_path):
    path, original = legacy_database(tmp_path)
    reader = read_only_engine(str(original.url))
    with reader.connect() as c:
        with pytest.raises(Exception, match="readonly"):
            c.exec_driver_sql("DELETE FROM parts")
    assert inventory_report(reader)["parts"] == 3
    with pytest.raises(ValueError, match="does not exist"):
        read_only_engine(f"sqlite:///{tmp_path / 'missing.sqlite'}")
    assert not (tmp_path / "missing.sqlite").exists()
    reader.dispose()
    original.dispose()


def test_backup_includes_committed_wal_data(tmp_path):
    path, engine = legacy_database(tmp_path)
    writer = sqlite3.connect(path)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("UPDATE parts SET quantity='17' WHERE xxx='001'")
    writer.commit()
    result = upgrade(engine, tmp_path / "backups")
    with sqlite3.connect(result["backup"]) as backup:
        assert backup.execute("SELECT quantity FROM parts WHERE xxx='001'").fetchone()[0] == "17"
    writer.close()
    engine.dispose()


def test_html_preview_download_and_configured_asset_path(tmp_path, monkeypatch):
    import config
    import db.engine as db_engine
    monkeypatch.setattr(config, "DB_URL", f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}")
    asset_dir = tmp_path / "external models"
    asset_dir.mkdir()
    (asset_dir / "sample.step").write_bytes(b"test asset")
    monkeypatch.setattr(config, "KICAD_3DMODELS_DIR", asset_dir)
    monkeypatch.setattr(config, "KICAD_LIBS_DIR", asset_dir)
    (asset_dir / "DMTDB.kicad_httplib").write_bytes(b"configuration")
    from main import create_app
    app = create_app()
    app.config["TESTING"] = True
    with db_engine.get_session() as session:
        session.add(Part(dmtuid="DMT-01020101001",tt="01",ff="02",cc="01",ss="01",xxx="001",quantity="",location="Rack"))
        session.commit()
        assert session.execute(__import__('sqlalchemy').text("PRAGMA foreign_keys")).scalar() == 1
    client = app.test_client()
    page = client.get("/inventory/migration-preview?status=unknown&page=nonsense")
    assert page.status_code == 200
    assert b"No quantities or locations are changed" in page.data
    assert b"DMT-01020101001" in page.data
    report = client.get("/inventory/migration-preview?format=json")
    assert report.json["unknown_counts"] == 1
    assert report.json["items"][0]["original_quantity"] == ""
    asset = client.get("/kicad_libs/3dmodels/sample.step")
    assert asset.data == b"test asset"
    asset.close()
    legacy_asset = client.get("/kicad_libs/DMTDB.kicad_httplib")
    assert legacy_asset.data == b"configuration"
    legacy_asset.close()
    assert client.get("/kicad_libs/unknown/sample.step").status_code == 404
    assert client.get("/").status_code == 200
    db_engine._engine.dispose()
