import io
import json
import re
from datetime import timedelta
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from tests.test_designs import app, sample, publish, post
from tests.test_library_catalog import git_snapshot
from db import get_session
from db.models import (PhysicalUnit, AssemblyDefinition, BuildPosting, BackgroundJob, LibrarySource)
from services.parts_service import PartsService
from services import build_service as build, inventory_service as stock, jobs


def assembly(db, count=100):
    p = PartsService.create(db, {'tt':'01','ff':'02','cc':'01','ss':'01','Quantity':str(count),'Location':'A','_inventory_key':'components'})
    _, board, release = sample(db)
    raw=f'Reference,Quantity,DMTUID,Value,DNP,Source\n"C1,C2,C3,C4,C5,C6,C7,C8",8,{p.dmtuid},100nF,no,personal\nR1,1,,10k,yes,personal\n'.encode()
    build.import_bom(db,release.id,raw,'bom.csv')
    publish(db,release)
    batch=build.create_build(db,release.id,5)
    db.commit()
    return p.dmtuid,batch.id


def test_five_boards_eight_capacitors_replay_serials_and_frozen_bom(app):
    with get_session() as db:
        uid,batch_id=assembly(db)
        review=build.plan(db,batch_id,5)
        assert review['materials'][0]['required']==40
        first=build.apply(db,batch_id,review,'post-one')
        db.commit()
        assert stock.summary(db,uid)['on_hand']==60
        assert db.query(PhysicalUnit).filter_by(build_id=batch_id).count()==5
        assert build.apply(db,batch_id,review,'post-one').id==first.id
        assert stock.summary(db,uid)['on_hand']==60
        with pytest.raises(ValueError,match='different input'):
            build.apply(db,batch_id,{**review,'fingerprint':'changed'},'post-one')
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE assembly_definitions SET lines_json='[]'"))
        db.rollback()
        assert stock.reconcile(db)==[]


def test_partial_reserved_build_cancel_does_not_return_consumed_stock(app):
    with get_session() as db:
        uid,batch_id=assembly(db)
        build.apply(db,batch_id,build.plan(db,batch_id,5),'reserve','reserve')
        assert stock.summary(db,uid)['reserved']==40
        build.apply(db,batch_id,build.plan(db,batch_id,2),'partial')
        assert stock.summary(db,uid)['on_hand']==84
        assert stock.summary(db,uid)['reserved']==24
        build.cancel(db,batch_id,'Remaining units abandoned; two assembled units retained','cancel')
        assert stock.summary(db,uid)['on_hand']==84
        assert stock.summary(db,uid)['reserved']==0
        assert db.query(PhysicalUnit).count()==2
        assert stock.reconcile(db)==[]


def test_shortage_and_stale_review_cannot_deduct(app):
    with get_session() as db:
        uid,batch_id=assembly(db,10)
        assert build.plan(db,batch_id,5)['shortages']
        review=build.plan(db,batch_id,1)
        stock.stocktake(db,uid,'9','A',key='count',actor='test',reason='Count changed')
        with pytest.raises(ValueError,match='changed'):
            build.apply(db,batch_id,review,'stale')
        assert db.query(PhysicalUnit).count()==0


def test_build_html_review_and_signed_posting(app):
    with get_session() as db:
        uid,batch_id=assembly(db)
    client=app.test_client()
    url=f'/builds/{batch_id}'
    assert client.get('/builds').status_code==200
    assert client.get(url).status_code==200
    response=post(client,url,{'action':'preview','quantity':'5'})
    assert response.status_code==200
    token=re.search(rb'name="review" value="([^"]+)"',response.data)[1].decode()
    assert post(client,url,{'action':'assemble','review':token+'x'}).status_code==400
    assert post(client,url,{'action':'assemble','review':token}).status_code==303
    assert post(client,url,{'action':'assemble','review':token}).status_code==303
    assert b'completed' in client.get(url).data


def test_bom_duplicate_references_and_quantity_mismatch_rejected():
    for raw in [b'Reference,Quantity\nC1,2\n',b'Reference,Quantity\nC1,1\nC1,1\n']:
        with pytest.raises(ValueError):
            build.parse_bom(raw)


def test_substitution_and_capped_material_return(app):
    with get_session() as db:
        uid,batch_id=assembly(db)
        replacement=PartsService.create(db,{'tt':'01','ff':'02','cc':'02','ss':'01','Quantity':'60','Location':'B','_inventory_key':'alternate'})
        review=build.plan(db,batch_id,5,{'0':{'part_id':replacement.dmtuid,'reason':'Approved higher voltage rating'}})
        posting=build.apply(db,batch_id,review,'substitution')
        assert stock.summary(db,uid)['on_hand']==100
        assert stock.summary(db,replacement.dmtuid)['on_hand']==20
        movement=json.loads(posting.details_json)['movement_ids'][0]
        build.return_material(db,batch_id,movement,10,'Recovered unused capacitors','return-one')
        build.return_material(db,batch_id,movement,10,'Recovered unused capacitors','return-one')
        assert stock.summary(db,replacement.dmtuid)['on_hand']==30
        with pytest.raises(ValueError,match='exceeds'):
            build.return_material(db,batch_id,movement,31,'Too many','return-two')
        assert stock.reconcile(db)==[]


def test_factory_supplied_components_do_not_consume_personal_stock(app):
    with get_session() as db:
        p=PartsService.create(db,{'tt':'01','ff':'02','cc':'01','ss':'01','Quantity':'10','Location':'A','_inventory_key':'external'})
        _,_,release=sample(db)
        build.import_bom(db,release.id,f'Reference,Quantity,DMTUID,Source\nC1,1,{p.dmtuid},external\n'.encode(),'external.csv')
        publish(db,release)
        batch=build.create_build(db,release.id,2)
        build.apply(db,batch.id,build.plan(db,batch.id,2),'external-assembly')
        assert stock.summary(db,p.dmtuid)['on_hand']==10
        assert db.query(PhysicalUnit).count()==2


def test_job_queue_deduplicates_recovers_expired_lease_and_indexes(app,tmp_path,monkeypatch):
    import config
    repo=tmp_path/'source.git'
    git_snapshot(repo,{'symbols.kicad_sym':b'(kicad_symbol_lib (symbol "ONE" (property "MPN" "ABC") (property "MFR" "TI")))'})
    monkeypatch.setattr(config,'LIBRARY_REPO_DIR',repo)
    with get_session() as db:
        db.add(LibrarySource(id=1,name='Test',repository_url='https://github.com/test/library.git',interval_minutes=30))
        db.flush()
        first=jobs.enqueue(db,'library',{'source_id':1,'fetch':False},'library:1')
        assert jobs.enqueue(db,'library',{'source_id':1,'fetch':False},'library:1').id==first.id
        first.status,first.lease_token,first.lease_until,first.attempts='running','lost-worker',jobs.now()-timedelta(minutes=1),1
        db.get(LibrarySource,1).state='running'
        db.commit()
        identifier=first.id
    assert jobs.run_next()
    with get_session() as db:
        job=db.get(BackgroundJob,identifier)
        assert job.status=='completed' and job.attempts==2
        assert db.get(LibrarySource,1).state=='idle'
    jobs.schedule_due()
    assert not jobs.run_next()


def test_git_release_job_records_exact_commit_and_bytes(app,tmp_path,monkeypatch):
    import config
    from services import git_archive
    monkeypatch.setattr(config,'LIBRARY_CACHE_DIR',tmp_path/'cache')
    (tmp_path/'cache').mkdir()
    with get_session() as db:
        project,board,release=sample(db)
        project.repository_url='git@github.com:example/design.git'
        db.commit()
    repo=tmp_path/'cache'/'design-1'
    commit=git_snapshot(repo,{'README.md':b'Exact archived design bytes','firmware.bin':b'version https://git-lfs.github.com/spec/v1\noid sha256:unresolved\n'})
    real_git=git_archive.git
    def local_git(path,*args,**kwargs):
        if 'fetch' in args:
            destination=args[-1].split(':',1)[1]
            return real_git(path,'update-ref',destination,commit)
        return real_git(path,*args,**kwargs)
    monkeypatch.setattr(git_archive,'git',local_git)
    result=git_archive.import_release(1,'HEAD')
    assert result['commit']==commit
    assert result['unresolved_dependencies']
    assert git_archive.import_release(1,'HEAD')['replayed']
