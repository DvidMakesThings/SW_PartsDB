import io
import json
import sqlite3
import zipfile
import pytest
from tests.test_designs import app, sample, publish
from db import get_session
from db.models import DesignArtifact
from services import backup_service, design_service


def test_backup_restores_database_and_exact_archive_bytes(app,tmp_path,monkeypatch):
    import config
    import db.engine as database_engine
    for key in ['BACKUPS_DIR','PART_IMAGES_DIR','DATASHEETS_DIR','KICAD_LIBS_DIR']:
        monkeypatch.setattr(config,key,tmp_path/key)
    with get_session() as db:
        _,board,release=sample(db)
        publish(db,release)
        design_service.register_unit(db,board.id,'BACKUP-001',release_id=release.id)
        artifact=db.query(DesignArtifact).one()
        digest=artifact.sha256
        original=design_service.blob_path(digest).read_bytes()
        db.commit()
    archive=backup_service.create_bundle(database_engine._engine)
    destination=tmp_path/'restored'
    result=backup_service.restore_bundle(archive,destination)
    assert result['files']==2
    assert (destination/'artifacts'/digest[:2]/(digest+'.blob')).read_bytes()==original
    with sqlite3.connect(destination/'database.sqlite') as restored:
        assert restored.execute('select serial from physical_units').fetchone()[0]=='BACKUP-001'
        assert restored.execute('pragma foreign_key_check').fetchall()==[]
    with pytest.raises(ValueError,match='empty'):
        backup_service.restore_bundle(archive,destination)


def test_restore_rejects_traversal_before_writing(tmp_path):
    archive=tmp_path/'unsafe.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('../outside','bad')
    target=tmp_path/'restore'
    with pytest.raises(ValueError,match='Unsafe'):
        backup_service.restore_bundle(archive,target)
    assert not target.exists()
