import re

import pytest
from sqlalchemy.exc import IntegrityError
from db import get_session
from db.models import Part, StockHolding
from services import inventory_service as stock
from services.parts_service import PartsService
from services.design_service import create_project, create_board
from tests.test_designs import app


def test_counted_part_saves_edits_and_deletes_without_stock_confirmation(app):
    client = app.test_client()
    result = client.post('/part/add', data={
        'tt':'03','ff':'06','cc':'02','ss':'05','MPN':'PART-ENTRY-TEST',
        'Quantity':'25','Location':'Drawer','_inventory_key':'new-count','_stock_version':'-1',
    })
    assert result.status_code == 302
    assert '/part/DMT-' in result.location and not result.location.endswith('/add')
    url = result.location
    uid = url.rsplit('/', 1)[-1]
    with get_session() as db:
        assert db.get(Part, uid).quantity == '25'
        holding_id = stock.holdings(db, uid)[0].id
    edit = client.get(url+'/edit').data
    version = re.search(rb'name="_stock_version" value="([^"]+)"', edit)[1].decode()
    result = client.post(url+'/edit', data={'Quantity':'12','Location':'Drawer',
                         '_inventory_key':'edit-count','_stock_version':version})
    assert result.status_code == 302 and result.location.endswith(uid)
    with get_session() as db:
        assert db.get(Part, uid).quantity == '12'
    result = client.post(url+'/delete')
    assert result.status_code == 302 and result.location == '/'
    assert client.get(url).status_code == 404
    with get_session() as db:
        assert db.get(Part, uid) is None
        assert stock.summary(db, uid)['on_hand'] == 0
        row = db.get(StockHolding, holding_id)
        assert row.dmtuid is None and row.deleted_dmtuid == uid
        with pytest.raises(ValueError, match='deleted part'):
            stock.adjust(db, holding_id, 1, key='stale-adjust', actor='test', reason='Stale request')
        assert stock.reconcile(db) == []


def test_deletion_failure_rolls_back_stock_detachment(app):
    with get_session() as db:
        part = PartsService.create(db, {'tt':'29','ff':'14','cc':'02','ss':'01','Quantity':'2'})
        project = create_project(db, 'DMT-HW-TEST-SCH-V100', 'Test')
        create_board(db, project.id, '01', 'Board', part_id=part.dmtuid)
        db.commit()
        uid = part.dmtuid
        with pytest.raises(IntegrityError):
            PartsService.delete(db, part)
        db.commit()
        assert db.get(Part, uid).quantity == '2'
        assert stock.summary(db, uid)['on_hand'] == 2
        assert stock.holdings(db, uid)[0].deleted_dmtuid is None
        assert stock.reconcile(db) == []
