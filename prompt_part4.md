Proceed with §13 (tests) from prompt.md. Do NOT change project layout or app names.

GOAL
Create a runnable pytest suite under backend/tests that validates importer, datasheet fetcher, API filters, and basic admin. All tests must pass locally with SQLite.

FILES TO ADD (exact paths)
- backend/tests/conftest.py
- backend/tests/factories.py
- backend/tests/test_health_and_schema.py
- backend/tests/importers/test_csv_importer.py
- backend/tests/files/test_datasheet_fetch.py
- backend/tests/api/test_components_api.py
- keep backend/tests/__snapshots__/ as-is

CONSTRAINTS
- Use pytest + pytest-django fixtures.
- Override MEDIA_ROOT to a tmp dir for tests.
- Use factory_boy for Component, InventoryItem.
- Mock outbound HTTP in datasheet tests (requests.get). No real network.
- Tests must not depend on Docker/Redis; Celery path must fall back to synchronous.
- Use backend/tests/sample_components.csv as the dataset.

IMPLEMENTATION DETAILS

A) conftest.py
- Configure Django settings for tests if needed.
- Autouse fixture to set MEDIA_ROOT to a temporary folder (cleanup after).
- client fixture: Django test client is fine.

B) factories.py
- factory_boy factories:
  - ComponentFactory (sets mpn/manufacturer; fills normalized fields if model expects them).
  - InventoryItemFactory (FK to Component, quantity default >0).

C) test_health_and_schema.py
- test_health_ok(): GET /api/health → 200 {"ok": true}
- test_openapi_ok(): GET /api/schema/ → 200 and contains "openapi" in body.

D) importers/test_csv_importer.py
- test_import_dry_run_counts(): call management command import_csv with --dry-run on backend/tests/sample_components.csv → assert created>0, updated>=0, errors==0.
- test_import_idempotent(): run without --dry-run twice → second run creates 0 and updates 0.
- test_package_size_parsed(): ensure a component with "Package (LxW)" parses numeric package_l_mm/package_w_mm.
- test_bad_row_logged(): feed a tiny temp CSV with a broken URL/row → ensure a file is written to apps/inventory/import_errors/<timestamp>.csv.

E) files/test_datasheet_fetch.py
- Mock requests.get to return:
  1) Valid PDF (Content-Type=application/pdf and bytes start with %PDF) → POST /api/components/{id}/fetch_datasheet/ returns 200; file saved under MEDIA_ROOT/Datasheets/...; Attachment created with sha256.
  2) Same PDF again → dedupe (no duplicate file/attachment).
  3) Non-PDF (e.g., text/html) → API returns 400; nothing saved.

F) api/test_components_api.py
- test_search_by_mpn_and_manufacturer(): create two components; GET /api/components/?search=<term> returns expected.
- test_in_stock_filter(): one component with InventoryItem(quantity>0), one without; GET /api/components/?in_stock_only=true returns only stocked.
- test_component_list_paginates(): check default pagination keys.

HELPERS/SNIPPETS TO USE (keep them minimal)

# conftest: temp MEDIA_ROOT
import shutil
import pytest
from django.conf import settings

@pytest.fixture(autouse=True, scope="session")
def _temp_media(tmp_path_factory):
    p = tmp_path_factory.mktemp("media")
    settings.MEDIA_ROOT = str(p)
    yield
    shutil.rmtree(p, ignore_errors=True)

# datasheet mock outline
from unittest.mock import patch, Mock
PDF = b"%PDF-1.7\n%..."

@patch("apps.files.services.requests.get")
def test_fetch_pdf_saves_attachment(mock_get, client, component_factory):
    resp = Mock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "application/pdf"}
    resp.iter_content = lambda chunk_size: [PDF]
    resp.content = PDF
    mock_get.return_value = resp
    # create component with url_datasheet set, then POST to action

SUCCESS CRITERIA (run these)
- cd backend && pytest -q  (no failures)
- python manage.py import_csv backend/tests/sample_components.csv --dry-run  (summary printed)
- python manage.py import_csv backend/tests/sample_components.csv  (idempotent on second run)

Report: list of files created/modified and pytest output summary.
Do not rename or move any existing files. Keep code concise and correct.
