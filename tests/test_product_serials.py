from tests.test_designs import app, post
from db import get_session
from db.models import PhysicalUnit, UnitEvent, StockMovement
from services.parts_service import PartsService
from services import design_service as design
import pytest
from datetime import datetime, timezone, timedelta


def products(db):
    a = PartsService.create(db, {"tt":"29", "ff":"14", "cc":"02", "ss":"01", "mpn":"ENERGIS", "Quantity":"2", "Location":"Shelf", "_inventory_key":"energis"})
    b = PartsService.create(db, {"tt":"20", "ff":"01", "cc":"01", "ss":"01", "mpn":"SBC"})
    return a,b


def test_product_detail_serials_waste_edit_modification_archive_restore(app):
    with get_session() as db:
        a,b = products(db)
        db.commit()
        uid=a.dmtuid
    client=app.test_client()
    assert b'Add serial number' in client.get('/part/'+uid).data
    response=post(client, '/part/'+uid+'/serials', {'serial':'SN001','notes':'Existing ENERGIS'})
    url=response.location
    assert response.status_code==303
    assert b'Product serial' in client.get(url).data
    assert post(client,url,{'action':'status','status':'waste','reason':'Destroyed by overvoltage'}).status_code==303
    assert b'WASTE' in client.get('/part/'+uid).data
    second=post(client,'/part/'+uid+'/serials',{'serial':'SN002'}).location
    assert post(client,second,{'action':'event','kind':'modification','title':'Protection added','notes':'Added TVS at J1'}).status_code==303
    assert post(client,second,{'action':'edit','serial':'SN002-C','stage':'prototype','location':'Bench','notes':'Modified board','reason':'Correct label after rework'}).status_code==303
    history=client.get(second+'/history.json').json
    assert history['serial']=='SN002-C'
    assert any(e['kind']=='edit' and e['details']['before']['serial']=='SN002' for e in history['events'])
    assert post(client,second,{'action':'archive','reason':'No longer in active use'}).status_code==303
    assert b'SN002-C' not in client.get('/part/'+uid).data
    assert b'SN002-C' in client.get('/prototypes?archived=1').data
    assert post(client,second,{'action':'restore','reason':'Returned to workbench'}).status_code==303
    assert b'SN002-C' in client.get('/part/'+uid).data
    with get_session() as db:
        assert db.query(StockMovement).count()==1


def test_serial_scope_allows_same_sn_on_different_products(app):
    with get_session() as db:
        a,b=products(db)
        design.register_unit(db,None,'SN001',part_id=a.dmtuid)
        design.register_unit(db,None,'SN001',part_id=b.dmtuid)
        with pytest.raises(ValueError,match='already exists'):
            design.register_unit(db,None,' sn001 ',part_id=a.dmtuid)


def test_component_domains_disabled_and_settings_can_enable(app):
    with get_session() as db:
        part=PartsService.create(db,{'tt':'01','ff':'02','cc':'01','ss':'01'})
        uid=part.dmtuid
        with pytest.raises(ValueError,match='enabled'):
            design.register_unit(db,None,'ABC',part_id=uid)
        db.commit()
    client=app.test_client()
    assert client.get('/settings/serials').status_code==200
    assert post(client,'/settings/serials',{'enabled':['01','19','20','29'],'prefix_01':'C-'}).status_code==303
    result=post(client,'/part/'+uid+'/serials',{'registration':'new','generate_serial':'yes'})
    assert result.status_code==303
    assert client.get(result.location+'/history.json').json['serial']=='C-00001'


def test_backdated_location_preserves_later_serial_edit(app):
    with get_session() as db:
        part, _ = products(db)
        unit = design.register_unit(db, None, 'SN001', part_id=part.dmtuid)
        design.edit_unit(db, unit.id, serial='SN001', stage='prototype', location='Bench',
                         notes='', reason='Moved during inspection')
        design.record_event(db, unit.id, 'location', 'Earlier storage', details={'location': 'Shelf'},
                            event_at=datetime.now(timezone.utc) - timedelta(days=1))
        assert unit.location == 'Bench'
        design.record_event(db, unit.id, 'location', 'Returned to storage', details={'location': 'Rack'})
        assert unit.location == 'Rack'
