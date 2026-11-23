import pytest
from db import get_session
from db.models import DesignProject
from services.document_ids import pbom_document_id
from tests.test_designs import app, post


@pytest.mark.parametrize('source,expected,code', [
    ('DMT-HW-VCTR-SCH-V100', 'DMT-HW-VCTR-PBOM-V100', 'VCTR'),
    ('DMT-HW-VCTR-PCB-V100', 'DMT-HW-VCTR-PBOM-V100', 'VCTR'),
    ('DMT-HW-USBSW-02-SCH-V110', 'DMT-HW-USBSW-02-PBOM-V110', 'USBSW'),
    (' dmt-hw-enrg-01-pbom-v101 ', 'DMT-HW-ENRG-01-PBOM-V101', 'ENRG'),
    ('DMT-HW-SCHX-01-PCB-V100', 'DMT-HW-SCHX-01-PBOM-V100', 'SCHX'),
])
def test_document_type_conversion_preserves_identity(source, expected, code):
    assert pbom_document_id(source) == (expected, code)


@pytest.mark.parametrize('value', ['', 'ENRG', 'DMT-HW-ENRG-00-PCB-V100',
                                 'DMT-HW-ENRG-01-PCB-V1.0.0', 'DMT-HW-ENRG-01-PCB-V1000'])
def test_invalid_document_id_is_rejected(value):
    with pytest.raises(ValueError, match='DOCUMENT_ID'):
        pbom_document_id(value)


def test_create_project_from_document_id_without_separate_code(app):
    client = app.test_client()
    page = client.get('/designs').data
    assert b'name="document_id"' in page and b'name="code"' not in page
    assert b'Project code' not in page
    result = post(client, '/designs', {'document_id': 'DMT-HW-VCTR-SCH-V100', 'name': 'VECTRA-10P40'})
    assert result.status_code == 303
    url = result.location
    assert b'DMT-HW-VCTR-PBOM-V100' in client.get(url).data
    assert b'VECTRA-10P40' in client.get('/designs?q=VCTR-PBOM').data
    with get_session() as db:
        project = db.query(DesignProject).one()
        assert project.code == 'VCTR'
        assert project.document_id == 'DMT-HW-VCTR-PBOM-V100'
    # Other revisions belong under this project rather than duplicating it.
    duplicate = post(client, '/designs', {'document_id': 'DMT-HW-VCTR-PCB-V110', 'name': 'Duplicate'})
    assert duplicate.status_code == 400
    assert b'existing project' in duplicate.data
    wrong_project = post(client, url, {'action':'edit', 'document_id':'DMT-HW-ENRG-PCB-V100', 'name':'VECTRA-10P40'})
    assert wrong_project.status_code == 400
    assert post(client, url, {'action':'edit', 'document_id':'DMT-HW-VCTR-PCB-V100', 'name':'VECTRA-10P40'}).status_code == 303
    assert b'DMT-HW-VCTR-PBOM-V100' in client.get(url).data
