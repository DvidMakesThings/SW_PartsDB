# Local configuration and versioned migrations

The current code includes machine-local configuration, migration auditing, inventory foundations, design archives, serial-unit histories, and library indexing/review. It also includes product-domain SN management, scheduled jobs, BOM/build stock posting and portable backups. See [access and deployment](access-and-deployment.md) for the writable PC deployment, feature workflows and later Raspberry Pi rollout.

## Per-machine settings

Copy `config.local.example.ini` to `config.local.ini` beside `config.py`. The local file is gitignored; keep one different file per machine. Never copy the Windows local file onto Linux.

Configuration precedence is environment variables, local INI settings, then existing application defaults. Use `DMTDB_CONFIG` to select another INI file. A missing explicitly selected file or malformed file fails clearly rather than silently using the wrong database. Relative INI paths resolve beside the INI file; relative path environment overrides resolve beside `config.py`. Do not surround paths with quotes. `~` expands to the current account's home directory. A Windows drive path on Linux is rejected.

An example for the rack server:

```ini
[paths]
database = /home/masterpi/_GitHub/SW_PartsDB/dmtdb.sqlite
library_repo = /home/masterpi/_GitHub/LIB_KiCad-Libraries
library_cache = instance/library-cache
artifacts = instance/artifacts
backups = instance/backups
datasheets = datasheets
part_images = part_images
kicad_libs = kicad_libs
staging = _staging

[server]
host = 0.0.0.0
port = 5000
debug = false
public_url = http://192.168.0.25:5000
```

`library_repo` identifies the external Git library; it is separate from app-managed `kicad_libs`. Merely configuring it does not fetch, index, or modify the repository. Library Sync reads its committed HEAD. GitHub fetches use the separate `library_cache`. `artifacts` holds original uploaded design/history files under SHA-256-addressed filenames. Back up that directory together with the database. These paths also support `DMTDB_LIBRARY_CACHE_DIR` and `DMTDB_ARTIFACTS_DIR` overrides.

Optional individual path settings: `schema`, `templates`, `csv_seed`, `kicad_symbols`, `kicad_footprints`, and `kicad_3dmodels`. Setting `csv_seed` to an empty value disables automatic seed import. Existing `DMTDB_*` environment overrides remain supported, with additional `DMTDB_DATABASE_PATH`, `DMTDB_LIBRARY_REPO_DIR`, `DMTDB_ARTIFACTS_DIR`, `DMTDB_BACKUPS_DIR`, `DMTDB_DATASHEETS_DIR`, `DMTDB_PART_IMAGES_DIR`, `DMTDB_KICAD_LIBS_DIR`, and `DMTDB_STAGING_DIR` overrides.

For a database connection URL, use `DMTDB_DB` or `[database] url`; it takes precedence over `[paths] database`. Use absolute filesystem paths in SQLite connection URLs. The new audit/upgrade commands currently support file-backed SQLite. Do not assume a PostgreSQL deployment has been validated.

Set the Flask secret through `DMTDB_SECRET` or `[server] secret`, keeping it out of Git. The loader does not print INI values when reporting syntax errors. Protect the local INI with mode `0600` on Linux if it contains secrets. Neither INI settings nor SSH credentials are sent to browser clients.

## Read-only deployment audit

Install dependencies in a development/test environment first:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m manage db-status
python -m manage inventory-preview > inventory-preview.json
```

On Windows, use `.venv/Scripts/python.exe`; on the rack's current installation, use `venv/bin/python`. The commands run without starting Flask or importing seed data. Read-only commands refuse to create a missing database and use SQLite `mode=ro` connections. The report retains original quantities and locations, separates valid integer counts from blanks and invalid values, and proposes no deductions.

After application deployment, Browse links to `/inventory/migration-preview`. This paginated page can filter count status and download the JSON report. The report is read-only. New design/prototype/library mutation forms use CSRF tokens; the local deployment retains the existing trusted-LAN access model. Read-only preview mode, when explicitly configured, blocks mutations.

## Explicit baseline upgrade

The frozen Alembic revision `0001_legacy` represents the original five tables. Revision `0002_inventory` creates holdings, movements, reservations, operation records, and the stock writer lock. Each legacy part receives exactly one opening movement and holding, preserving unknown counts and original quantity/location values in the movement details. Invalid nonblank quantities block migration until reviewed. The explicit upgrade command applies these and all subsequent revisions up to the current head. Original part records are preserved.

Schemas are checked against frozen columns, types, primary/foreign keys, unique constraints/indexes, and checks. Unknown schemas and future revision markers are rejected. SQLite migration DDL and data run in an explicit transaction, so a rejected opening balance does not leave half-created ledger tables.

Before deploying this code to a running server:

1. Rehearse on a SQLite backup made with the SQLite backup API, including committed WAL data.
2. Install the new Alembic requirement in the application's virtual environment.
3. Pause all application writers, including the systemd service and external tools.
4. Deploy the tested source while retaining that machine's `config.local.ini`.
5. Run the explicit baseline command:

```bash
venv/bin/python -m manage db-upgrade --writers-stopped
venv/bin/python -m manage db-status
venv/bin/python -m manage inventory-check
```

6. Verify the backup path reported by the command, run the preview, and compare the original records. Restart the service only when the baseline and checks succeed.

`--writers-stopped` is an operator assertion; the command does not stop systemd itself. A uniquely named, integrity-checked SQLite backup is created in `backups` before the first upgrade. Repeating a completed baseline is a no-op. Destructive downgrades are disabled. Restore the matching previous code/database backup if cutover fails before accepting new writes.

Application startup initializes a genuinely empty database through the versioned migration. It refuses an existing unversioned database with instructions to run the explicit upgrade, instead of silently changing it. **Do not restart the production service on the new code before baselining its database.**

Revisions `0003_designs` and `0004_library` add the design/archive/serial/history/issue tables and library catalogue/review records. They preserve the inventory tables. Revision `0005_serials` adds domain policies, product/design-scoped serial uniqueness and archival status; `0006_jobs` adds durable background jobs and library schedules; `0007_builds` adds frozen BOM definitions, build batches, material postings and serial/build links. Revision `0008_document_id` adds the project DOCUMENT_ID field without changing existing identities or histories. Current schema head is `0008_document_id`; upgrades recognize and validate each prior revision before advancing. Frozen manifests also detect unexpected schema changes.

Archive/history and review records have SQLite immutability triggers. Restoring an earlier application requires the matching database **and artifact storage** snapshot; downgrades do not silently delete engineering history. Database upgrades create a consistent SQLite backup automatically. Use `python -m manage backup-all` or `/settings/backup` for a database/artifact/assets bundle, and `python -m manage restore-backup --archive FILE.zip --destination NEW_EMPTY_DIRECTORY` for checksum-verified restoration. A full local restore was rehearsed successfully; operators still need an external backup destination and retention schedule.

## Current validation scope

Automated coverage includes config precedence and path anchoring, disabled seeding, malformed-file secret redaction, POSIX rejection of Windows paths, quantity classification, legacy/fresh schema handling, unknown schema/version rejection, repeated baseline, WAL-aware backup, read-only audit connections, HTML/JSON preview, and configured asset serving with existing root-file URLs preserved.

Existing part forms, REST part writes, and CSV imports now route quantity/location changes through the ledger. The old part quantity/location fields remain derived compatibility fields. Direct SQL edits bypass application accounting and are not a supported stock workflow. `inventory-check` detects ledger/balance/reservation/cache disagreements and exits nonzero if it finds any.

HTML part edits show a signed, expiring confirmation of changed stock counts. CSV uploads simulate changes in a transaction that is rolled back, show a proposed-count report, and stage the original file for confirmation. Confirming checks whether inventory changed since the preview. Repeating a completed import run returns its original report; CSV replacement updates parts in place, preserving images and history.

REST part POST/PUT requests containing quantity or location now require an `Idempotency-Key` header. Reuse that key only to retry the same stock request. CSV REST requests accept the same header for the run ID; without one, identical file bytes and replace mode identify the same run. Use a new explicit key to intentionally import the same file again. `POST /api/v1/import?preview=1` returns a rolled-back preview; send its `inventory_fingerprint` in `If-Inventory-Match` when applying the import. A mismatched fingerprint rejects the import without applying rows. API automation can also submit an intentional stock count directly, without the HTML confirmation UI.

Authenticated human attribution, CSRF protection for legacy mutation endpoints, and dedicated holding-specific management forms are still pending before production cutover. Current legacy-interface records identify the source channel, not a verified human operator. The current PC deployment is writable using the existing LAN model; the older Pi preview is not the current implementation.
