from concurrent.futures import ThreadPoolExecutor
import threading
import uuid

import pytest
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import Session

from db.engine import init_db, get_session
from db.models import Part, StockHolding, StockMovement, StockReservation, PartImage
from db.migrations import upgrade
from services import inventory_service as stock
from services.parts_service import PartsService
from import_engine import run_import


@pytest.fixture
def inventory(tmp_path):
    import schema, config
    schema.load(config.SCHEMA_PATH, config.TEMPLATES_PATH)
    init_db(f"sqlite:///{(tmp_path / 'inventory.sqlite').as_posix()}")
    with get_session() as s:
        part = PartsService.create(s, {"tt":"01", "ff":"02", "cc":"01", "ss":"01",
                                      "Quantity":"10", "Location":"A", "_inventory_key":"initial"})
        uid = part.dmtuid
        h = stock.holdings(s, uid)[0].id
        s.commit()
    yield uid, h
    import db.engine
    db.engine._engine.dispose()


def args(key):
    return {"key":key, "actor":"test-operator", "reason":"Test assembly"}


def test_stocktake_history_retry_and_changed_payload(inventory):
    uid, h = inventory
    with get_session() as s:
        first = stock.stocktake(s, uid, "8", "A", **args("count"))
        s.commit()
    with get_session() as s:
        replay = stock.stocktake(s, uid, "8", "A", **args("count"))
        assert first == replay
        assert s.scalar(select(func.count()).select_from(StockMovement)) == 2
        with pytest.raises(ValueError, match="different input"):
            stock.stocktake(s, uid, "7", "A", **args("count"))
        assert stock.reconcile(s) == []


def test_reserve_consume_return_and_limits(inventory):
    uid, h = inventory
    with get_session() as s:
        stock.reserve(s, "build-A", [{"holding_id":h,"quantity":7}], **args("reserve"))
        assert stock.summary(s,uid)["available"] == 3
        with pytest.raises(ValueError, match="Insufficient"):
            stock.consume(s,"build-B",[{"holding_id":h,"quantity":4}],**args("wrong-build"))
        result = stock.consume(s,"build-A",[{"holding_id":h,"quantity":5}],**args("consume"))
        assert stock.summary(s,uid)["on_hand"] == 5
        assert stock.summary(s,uid)["reserved"] == 2
        stock.reserve(s,"build-A",[{"holding_id":h,"quantity":0}],**args("release"))
        stock.return_stock(s,result["movement_ids"][0],3,**args("return"))
        with pytest.raises(ValueError, match="exceeds"):
            stock.return_stock(s,result["movement_ids"][0],3,**args("over-return"))
        assert stock.summary(s,uid)["available"] == 8
        assert stock.reconcile(s) == []
        s.commit()


def test_failed_multi_holding_consumption_is_atomic(inventory):
    uid,h = inventory
    with get_session() as s:
        second = stock.receive(s,uid,2,"B",**args("receive"))["holding_id"]
        before = s.scalar(select(func.count()).select_from(StockMovement))
        with pytest.raises(ValueError, match="Insufficient"):
            stock.consume(s,"build",[{"holding_id":h,"quantity":5},
                                      {"holding_id":second,"quantity":3}],**args("failed"))
        s.commit()  # Even caller commit after the rejection must not post half a batch.
    with get_session() as s:
        assert stock.summary(s,uid)["on_hand"] == 12
        assert s.scalar(select(func.count()).select_from(StockMovement)) == before
        assert stock.reconcile(s) == []


def test_transfer_balances_and_history_is_immutable(inventory):
    uid,h=inventory
    with get_session() as s:
        second = stock.receive(s,uid,1,"B",**args("receive"))["holding_id"]
        stock.transfer(s,h,second,4,**args("transfer"))
        assert stock.summary(s,uid)["on_hand"] == 11
        assert s.get(StockHolding,second).on_hand == 5
        assert stock.reconcile(s) == []
        with pytest.raises(Exception, match="immutable"):
            with s.begin_nested():
                s.execute(text("DELETE FROM stock_movements"))
        PartsService.delete(s,s.get(Part,uid))
        assert s.get(Part,uid) is None
        assert stock.holdings(s,uid) == []
        assert s.get(StockHolding,h).deleted_dmtuid == uid
        assert stock.reconcile(s) == []


def test_unknown_stock_and_stale_form(inventory):
    uid,h=inventory
    with get_session() as s:
        version = s.get(StockHolding,h).version
        stock.adjust(s,h,1,**args("receipt"))
        with pytest.raises(ValueError, match="changed since"):
            stock.stocktake(s,uid,"5","A",expected_version=version,**args("stale"))
        with pytest.raises(ValueError, match="cannot be cleared"):
            stock.stocktake(s,uid,"","A",**args("clear"))
        unknown = PartsService.create(s,{"tt":"01","ff":"02","cc":"01","ss":"01",
                                         "Quantity":"","Location":"Unknown bin"})
        uh = stock.holdings(s,unknown.dmtuid)[0].id
        with pytest.raises(ValueError, match="unknown"):
            stock.consume(s,"build",[{"holding_id":uh,"quantity":1}],**args("unknown"))
        assert stock.summary(s,unknown.dmtuid)["status"] == "Unknown quantity"
        catalogue = PartsService.create(s,{"tt":"01","ff":"02","cc":"01","ss":"01"})
        assert stock.summary(s,catalogue.dmtuid)["status"] == "Not stocked"


def test_competing_builds_cannot_spend_same_stock(inventory):
    uid,h=inventory
    gate=threading.Barrier(2)
    def consume(name):
        with get_session() as s:
            gate.wait(timeout=5)
            try:
                stock.consume(s,name,[{"holding_id":h,"quantity":7}],**args(name))
                s.commit()
                return "ok"
            except ValueError:
                s.rollback()
                return "shortage"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(consume,["one","two"]))
    assert sorted(outcomes)==["ok","shortage"]
    with get_session() as s:
        assert stock.summary(s,uid)["on_hand"]==3
        assert stock.reconcile(s)==[]


def test_csv_updates_in_place_preserves_links_and_isolates_errors(inventory):
    uid,h=inventory
    with get_session() as s:
        s.add(PartImage(dmtuid=uid,filename="photo.png",position=0))
        s.commit()
    csv=f"DMTUID,MPN,Quantity,Location\n{uid},Updated,6,A\nDMT-01020101999,Invalid,-1,A\n"
    result=run_import(csv,replace_existing=True)
    assert result.imported==1
    assert result.skipped==1
    repeated=run_import(csv,replace_existing=True)
    assert repeated.imported==1
    with get_session() as s:
        assert s.get(Part,uid).mpn=="Updated"
        assert s.get(Part,uid).quantity=="6"
        assert s.scalar(select(func.count()).select_from(PartImage))==1
        assert s.scalar(select(func.count()).select_from(StockMovement))==2
        assert s.get(Part,"DMT-01020101999") is None
        assert stock.reconcile(s)==[]


def test_invalid_migration_rolls_back_entire_upgrade(tmp_path):
    from tests.test_foundations import legacy_database
    path,engine=legacy_database(tmp_path)
    with engine.begin() as c:
        c.execute(text("UPDATE parts SET quantity='bad' WHERE xxx='001'"))
    with pytest.raises(RuntimeError,match="invalid inventory"):
        upgrade(engine,tmp_path/'backups')
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM sqlite_master WHERE name='stock_holdings'")).scalar()==0
        assert c.execute(text("SELECT count(*) FROM sqlite_master WHERE name='alembic_version'")).scalar()==0
    engine.dispose()


def test_repeat_migration_does_not_duplicate_openings(tmp_path):
    from tests.test_foundations import legacy_database
    path,engine=legacy_database(tmp_path)
    upgrade(engine,tmp_path/'backups')
    upgrade(engine,tmp_path/'backups')
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(StockMovement))==3
        unknown=s.scalar(select(StockHolding).where(StockHolding.count_known==False))
        assert unknown.on_hand==0
        assert stock.reconcile(s)==[]
    engine.dispose()


def test_browser_history_api_retry_and_preview_write_block(inventory, monkeypatch):
    import config, db.engine
    from main import create_app
    uid,h=inventory
    url = str(db.engine._engine.url)
    monkeypatch.setattr(config,"DB_URL",url)
    monkeypatch.setattr(config,"READ_ONLY_PREVIEW",False)
    app=create_app()
    app.config["TESTING"]=True
    client=app.test_client()
    history=client.get(f"/part/{uid}/stock")
    assert history.status_code==200
    assert b"Recorded stock count" in history.data
    assert client.put(f"/api/v1/parts/{uid}",json={"quantity":"8"}).status_code==400
    response=client.put(f"/api/v1/parts/{uid}",json={"quantity":"8"},headers={"Idempotency-Key":"api-count"})
    assert response.status_code==200
    with get_session() as s:
        stock.consume(s,"batch",[{"holding_id":h,"quantity":3}],**args("consume"))
        s.commit()
    replay=client.put(f"/api/v1/parts/{uid}",json={"quantity":"8"},headers={"Idempotency-Key":"api-count"})
    assert replay.status_code==200
    assert replay.json["quantity"]=="5"
    assert client.get(f"/api/v1/parts/{uid}").json["inventory"]["available"]==5
    monkeypatch.setattr(config,"READ_ONLY_PREVIEW",True)
    preview=create_app().test_client()
    assert b"Read-only development preview" in preview.get("/").data
    assert preview.get(f"/part/{uid}/stock").status_code==200
    assert preview.post(f"/part/{uid}/delete").status_code==403
    assert preview.put(f"/api/v1/parts/{uid}",json={"quantity":"1"}).status_code==403
    assert preview.get("/part/add").status_code==403


def test_availability_filter_and_numeric_quantity_sort(inventory):
    from services.search_service import SearchService
    uid,h=inventory
    with get_session() as s:
        for qty,location in [("2","B"),("0","C"),("","D"),("","")]:
            PartsService.create(s,{"tt":"01","ff":"02","cc":"01","ss":"01","Quantity":qty,"Location":location})
        expected={"in_stock":2,"out_of_stock":1,"unknown":1,"not_stocked":1,"all":5}
        for state,count in expected.items():
            assert SearchService.search(s,availability=state)[1]==count
        parts,total=SearchService.search(s,availability="in_stock",sort_by="quantity")
        assert [p.quantity for p in parts]==["2","10"]


def test_stock_form_confirmation_is_read_only_and_tamper_resistant(inventory, monkeypatch):
    import config, db.engine, re
    from main import create_app
    from ui.stock_review import confirm_stock_form
    uid,h=inventory
    monkeypatch.setattr(config,"DB_URL",str(db.engine._engine.url))
    monkeypatch.setattr(config,"READ_ONLY_PREVIEW",False)
    app=create_app()
    with app.test_request_context(f"/part/{uid}/edit"), get_session() as s:
        part=s.get(Part,uid)
        data={"Quantity":"4","Location":"A","_inventory_key":"form", "staging_session_id":"preserve-me"}
        html=confirm_stock_form(s,part,data,None)
        assert "Review stock change" in html and "preserve-me" in html
        assert stock.summary(s,uid)["on_hand"]==10
        token=re.search(r'name="_stock_confirmation" value="([^"]+)"',html).group(1)
        assert confirm_stock_form(s,part,data,token) is None
        changed=dict(data,Quantity="3")
        with pytest.raises(ValueError,match="changed"):
            confirm_stock_form(s,part,changed,token)


def test_csv_preview_stale_inventory_and_exact_run_replay(inventory):
    uid,h=inventory
    csv=f"DMTUID,Quantity,Location\n{uid},3,A\n"
    preview=run_import(csv,replace_existing=True,preview=True)
    assert preview.preview and preview.imported==1
    assert preview.changes[0]["before"]=="10"
    assert preview.changes[0]["after"]=="3"
    with get_session() as s:
        assert s.get(Part,uid).quantity=="10"
        assert s.scalar(select(func.count()).select_from(StockMovement))==1
        stock.adjust(s,h,1,**args("received"))
        s.commit()
    rejected=run_import(csv,replace_existing=True,operation_key="stale-import",expected_inventory=preview.inventory_fingerprint)
    assert rejected.imported==0 and "changed since" in rejected.errors[0]["reason"]
    fresh=run_import(csv,replace_existing=True,preview=True)
    applied=run_import(csv,replace_existing=True,operation_key="confirmed-import",expected_inventory=fresh.inventory_fingerprint)
    assert applied.imported==1
    with get_session() as s:
        stock.adjust(s,h,1,**args("later-receipt"))
        s.commit()
    replay=run_import(csv,replace_existing=True,operation_key="confirmed-import",expected_inventory=fresh.inventory_fingerprint)
    assert replay.to_dict()==applied.to_dict()
    with get_session() as s:
        assert s.get(Part,uid).quantity=="4"
        assert stock.reconcile(s)==[]


def test_html_csv_upload_review_confirm_and_retry(inventory,monkeypatch,tmp_path):
    import config, db.engine, io, re
    from main import create_app
    uid,h=inventory
    monkeypatch.setattr(config,"DB_URL",str(db.engine._engine.url))
    monkeypatch.setattr(config,"READ_ONLY_PREVIEW",False)
    monkeypatch.setattr(config,"STAGING_DIR",tmp_path/'uploads')
    client=create_app().test_client()
    content=f"DMTUID,Quantity,Location\n{uid},9,A\n".encode()
    response=client.post('/import',data={'replace':'1','csv_file':(io.BytesIO(content),'stock.csv')})
    assert response.status_code==200
    assert b'no changes saved' in response.data
    token=re.search(rb'name="review_token" value="([^"]+)"',response.data).group(1).decode()
    with get_session() as s: assert s.get(Part,uid).quantity=='10'
    assert client.post('/import',data={'review_token':token}).status_code==200
    assert client.post('/import',data={'review_token':token}).status_code==200
    with get_session() as s:
        assert s.get(Part,uid).quantity=='9'
        assert s.scalar(select(func.count()).select_from(StockMovement))==2
