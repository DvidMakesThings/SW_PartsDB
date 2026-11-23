# DMTDB access, local deployment and Raspberry Pi rollout

Updated: 2026-11-23. The user selected **this Windows PC** as the writable development/deployment target. No further Raspberry Pi changes are being made.

## Open the working application

**http://192.168.0.100:5000/** from this PC or a reachable LAN client. On this PC, **http://localhost:5000/** also works.

This is a **writable local deployment**, not the old read-only preview. It uses the application's existing trusted-LAN access model. The header is Browse, + Add Part, Designs, Prototypes, Builds, Library Sync, followed by the existing destinations.

| Function | URL / navigation |
|---|---|
| Existing ENERGIS product and individual SNs | http://192.168.0.100:5000/part/DMT-29140201001#serials |
| Project and release archive | http://192.168.0.100:5000/designs |
| All prototype/product serial records | http://192.168.0.100:5000/prototypes |
| Serial-enabled domains and prefixes | http://192.168.0.100:5000/settings/serials |
| BOM-based assembly and stock deductions | http://192.168.0.100:5000/builds |
| Library catalogue and matching review | http://192.168.0.100:5000/library-sync |
| Background imports, schedules and retries | http://192.168.0.100:5000/jobs |
| Full data backup download | http://192.168.0.100:5000/settings/backup |
| Optional KiCad HTTP inventory overlay | http://192.168.0.100:5000/kicad/v1/ |

The IP above is this PC's current Ethernet address. If DHCP changes it, use the new address and update `[server] public_url` in `config.local.ini`. The app binds to `0.0.0.0:5000`; access from another machine also depends on that machine's route and Windows firewall configuration.

## Serial numbers directly on products

Domains **19 (Development and Programming), 20 (Computing and Embedded), and 29 (Project PCBs and Assemblies)** initially show individual serial management. Enable other product/equipment domains in Serial tracking settings. Disabling a domain preserves existing histories.

1. Browse to ENERGIS, an SBC, or another enabled product. Open **Add serial number** on its detail page.
2. Enter the actual SN, location and notes. Purchased products do not require a project/design archive. Link a known design revision when appropriate.
3. Open an SN to edit its label, stage, location or notes, or append firmware, modification, test, fault or repair records.
4. Mark a destroyed unit **WASTE** and record the reason. WASTE is excluded from the available serial count and retains its history. A modification to SN002 belongs only to SN002.
5. **Remove from active serial list** archives a unit; **Restore** brings it back. Removal does not erase its files or timeline. Use the archived filter to find it again.

SNs are unique within their inventory product, or within their standalone board design. Different products can both have SN001. Comparison trims whitespace and ignores case. New units can receive a collision-safe generated serial; prefixes are configurable per domain. Existing units require their actual serials.

Historical registration does not deduct stock or fabricate past assembly events. Serial status counts and legacy aggregate product inventory counts are displayed separately; entering a serial or marking it WASTE does not silently post another component deduction. New build assembly posts material consumption explicitly.

## Designs, firmware and assembly

**Designs:** create a project using its existing `DOCUMENT_ID` (for example, `DMT-HW-VCTR-SCH-V100` is saved as `DMT-HW-VCTR-PBOM-V100`). The standard board segment is retained when present, as in `DMT-HW-USBSW-01-PBOM-V100`; no separate project code is requested. Then add boards, link the inventory product, and create a draft revision. Archive a complete source ZIP and individually classified manufacturing, schematic/PCB, PDF/image, BOM, placement, mechanical, firmware or report files. Originals retain their exact bytes and SHA-256 checksums. ZIP contents are listed without extraction; PDF/PNG/JPEG previews are available.

A source snapshot can also be queued from a GitHub branch, tag or commit. The importer resolves and records the exact commit in its independent cache. Existing Git/SSH credentials on this machine handle private repositories; credentials are never embedded in repository URLs or returned to the browser. LFS pointers and submodules are explicitly reported as unresolved, and external dependencies must be archived separately.

Publishing freezes the release metadata, archived core contents and manifest. Missing artifacts or unresolved dependencies must be acknowledged. Corrections require another revision. Later factory responses and test reports can be appended without replacing the released package. The unit page says **Last recorded firmware**, not live device telemetry; version-only events are labeled when no binary is attached.

**Builds:** import a UTF-8 CSV BOM on a draft revision, review canonical DMTUID mappings, DNP flags and personal/external supply, then publish. The supported column names and downloadable example are available on each release. Reference lists and quantities are validated; ranges must be expanded. Unique strong identifier matches may prefill mappings, while uncertain identities remain unresolved.

Create a build for a published mapped BOM. Preview a whole or partial assembly, shortages, any documented substitutions and serials before posting. Reservation holds materials without reducing on-hand. Confirming assembly consumes the reviewed components atomically and creates linked serial units. Replaying a confirmed request does not deduct twice. Stale stock/build reviews are rejected. DNP and external/factory-supplied lines do not consume personal inventory. Cancelling releases unused reservations and preserves existing consumption and units. Physically recovered usable components can be explicitly returned, capped by their original consumption.

## Library catalogue and Git independence

The local clone at `G:/_GitHub/LIB_KiCad-Libraries` was indexed successfully: **1,428 symbols, no parse errors**. Catalogue entries are staged separately from canonical inventory parts. Matching uses reviewed bindings, DMTUIDs, exact manufacturer/MPN, and supplier identifiers; it preserves suffixes and detects conflicting evidence. Value/package similarity alone does not merge parts.

Confirm unique matches or review individual entries. For identified new parts, filter by library file, select up to 50 entries and choose their common TT/FF/CC/SS classification. Duplicate representations link to the same part. Batch errors roll back the batch. Confirmed new catalogue parts have no holdings and display **Not stocked**. Generic or contradictory entries stay in review. Synchronization never overwrites existing quantities or locations.

**Index configured local clone** reads committed HEAD, not uncommitted working-tree edits. **Fetch GitHub and index** uses a separate bare cache. Both are persistent background jobs. Configure a schedule from 15 to 10080 minutes, or 0 to disable it. Interrupted work is eligible for recovery after a 15-minute lease; failed jobs can be retried from Jobs. The main application starts its worker automatically.

Your original library checkout and GitHub repository are never modified by these workflows. Normal `git clone` and `git pull` remain independent of DMTDB, including on off-network machines. The optional KiCad HTTP connector returns stock status, available/reserved counts, locations and a lookup timestamp. Those fields are a snapshot at lookup/placement time, not a claim that an offline schematic continuously refreshes stock.

## Local files and process

- Source: `G:/_GitHub/SW_PartsDB`
- Local settings: `config.local.ini` (gitignored; includes a generated Flask signing secret)
- Active database: `instance/partsdb-local.sqlite` (gitignored)
- Original local `dmtdb.sqlite`: preserved, not migrated in place
- Archived bytes: `instance/artifacts`
- Git download cache: `instance/library-cache`
- Backups: `instance/backups`
- Logs: `instance/server.log`, `instance/server-error.log`
- Launcher PID: `instance/server.pid`

From the repository in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-server.ps1 -Action Start
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-server.ps1 -Action Restart
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-server.ps1 -Action Stop
```

The script checks the recorded process and Windows Python launcher children before stopping anything. It starts a hidden local server. This is not configured as a Windows startup service; run Start after a reboot. For a foreground console, use `.venv/Scripts/python.exe main.py` after stopping the background instance.

## Backups and data transfer

**Git transfers code, not the live data created here.** Do not commit `config.local.ini`, `instance`, backup archives or live SQLite WAL files. If you need local SNs/design archives on the Pi, transfer a data bundle deliberately; a plain pull will not transfer them or merge newer Pi inventory changes.

Use the browser backup page, or:

```powershell
.venv/Scripts/python.exe -m manage backup-all
.venv/Scripts/python.exe -m manage restore-backup --archive instance/backups/partsdb-TIMESTAMP.zip --destination .local/restore-check
```

A bundle contains a consistent SQLite snapshot, referenced immutable artifacts and app-managed assets, with checksums. Secrets and the external Git checkout are excluded. Restore refuses a nonempty destination and verifies every checksum, SQLite integrity and foreign keys. It never overwrites an active database. Configure a restored instance to use `database.sqlite`, `artifacts`, and the appropriate `assets` subdirectories. Preserve newer records on either machine before deciding which database becomes authoritative; automatic cross-machine data merging is not implemented.

A full local restore rehearsal recovered **303 files** into `.local/restore-rehearsal-20261122`; inventory reconciliation reported no discrepancies. Additional automated tests verify restored serial histories and exact artifact bytes.

## Later Raspberry Pi rollout (user-controlled)

The Pi remains at **http://192.168.0.25:5000/** with its original production application/database. The older read-only preview on port 5001 is not the current development deployment. No SSH deployment was made after the user's instruction to work on this PC.

After reviewing and pushing the code yourself, use the Pi's own `config.local.ini`; never copy the Windows paths or signing secret onto it. Keep the Pi database authoritative unless intentionally transferring a reviewed data bundle.

```bash
cd /home/masterpi/_GitHub/SW_PartsDB
sudo systemctl stop dmtdb
# Record the current revision and preserve a consistent database/assets backup first.
git rev-parse HEAD
git pull --ff-only
venv/bin/python -m pip install -r requirements.txt
venv/bin/python -m manage backup-all
venv/bin/python -m manage db-upgrade --writers-stopped
venv/bin/python -m manage db-status
venv/bin/python -m manage inventory-check
sudo systemctl start dmtdb
sudo systemctl status dmtdb --no-pager
```

`db-upgrade` makes its own consistent SQLite backup before applying migrations. Current schema head is **0008_document_id**. It recognizes the original legacy schema and previous numbered revisions; unknown schemas are rejected. Do not start the new application against an unmigrated database. Ensure the service user can write the artifact, backup and Git-cache directories and read the configured library clone. Scheduled work runs with that service user's Git credentials.

After startup, verify the same feature pages on port 5000, a representative product, archive download/checksum and inventory reconciliation. Restore matching code/database/assets if a cutover fails before accepting new writes; preserve/reconcile new writes before any later rollback. Production authentication/human attribution remains a separate deployment-hardening decision; the writable PC uses the existing application's LAN model.
