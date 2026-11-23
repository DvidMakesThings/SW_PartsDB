# DMTDB engineering archive and inventory change plan

Version: 1.2  
Date: 2026-11-22  
Status: Main design/prototype and library-review workflows implemented; isolated Linux preview available; production cutover pending  
Scope: Design archives, serial-numbered prototypes, Git library indexing, and build-based inventory consumption.

Priority correction (2026-11-22): the user clarified that stock deduction is optional polish, not the main request. Continue P3 (design archives and serial-unit tracking) now, followed by P2 (library catalogue/matching). Pause further inventory polish and P4 build automation until these primary workflows are delivered. The existing migration infrastructure can support P3 without completing P1's additional inventory screens. Final navigation order and data-integrity requirements remain unchanged.

Product-serial extension (2026-11-22): individual serial tracking belongs directly on product-part detail pages, including purchased SBCs without a design archive. Initially enable domains 19 (development boards), 20 (computing/embedded) and 29 (project PCBs); provide HTML settings to enable other product/equipment domains and configure serial prefixes. Serial uniqueness is per product (or per standalone design), replacing the previous global-uniqueness default. Users can add/edit/archive/restore units, mark a destroyed unit WASTE, and record modifications against one SN. All changes retain history. Removing a unit means archival; component inventory counts are not silently consumed or reconstructed from serial registration.

## 1. Purpose and implementation contract

Extend DMTDB so that one browser application answers these questions:

- Where are the exact design and manufacturing files for this board revision?
- Which physical boards were made from that revision, and what are their serial numbers?
- What firmware, modifications, faults, and test history belong to each board?
- Which components exist in the KiCad library, and which are available in personal inventory?
- Which parts were consumed when a particular batch or prototype was assembled?

This document is the implementation baseline. Requirement IDs below must be referenced by implementation tasks and acceptance checks. Implement phases in dependency order. Update phase status and record validation evidence as work is completed. Do not silently omit a requirement or mark a phase complete while its acceptance criteria remain unmet.

Routine implementation details may be refined without changing the intended behavior. Material changes to scope, data ownership, navigation, stock accounting, or compatibility must first be recorded in the decision log with the reason and impact. Changes to user-facing requirements must be discussed with the user; this is not a requirement to seek approval for routine implementation work already authorized.

Implementation began on 2026-11-22. The first increment adds machine-local configuration, a versioned legacy database baseline, and a read-only stock migration preview. The broader features below remain planned unless explicitly recorded as delivered in the evidence log. Production application cutover has not been performed.

## 2. Observed starting point

These observations describe the local checkout inspected on 2026-11-22, not a verified snapshot of the rack server:

- Flask application, SQLAlchemy models, SQLite database, and server-rendered Jinja HTML.
- `db/models.py` contains parts, extensible part fields, client configuration, pricing, and images. There are no dedicated design, release, build, or serial-unit models.
- `Part.quantity` is a string and `Part.location` is free text. Stock movements and reservations are not modeled.
- The local database contains 345 parts, including `DMT-29140201001`, an ENERGIS prototype entry. This entry represents existing inventory and must be preserved.
- Existing KiCad services, HTTP library endpoints, library uploads/downloads, and client setup provide integration foundations.
- Database startup uses `Base.metadata.create_all`; a versioned migration mechanism is required for upgrades.
- The current header is Browse, + Add Part, KiCad Libs, Labels, Import CSV, Client Setup, API Docs.
- The library exists locally at `G:\_GitHub\LIB_KiCad-Libraries` and remotely at `https://github.com/DvidMakesThings/LIB_KiCad-Libraries.git`. The remote is private, with `master` observed as its default branch.
- Sample library properties include MPN, MFR, LCSC_PART, Value, Footprint, Datasheet, and Description. Some identifiers contain trailing spaces; some symbols lack manufacturer and MPN.
- The library's hardware numbering standard uses `DMT-HW-XXXX-YY-TYPE-VMmp`.

Relevant existing files: `db/models.py`, `db/engine.py`, `services/parts_service.py`, `services/kicad_service.py`, `services/kicad_symbol_processor.py`, `api/routes_kicad.py`, `import_engine/`, `templates/base.html`, and `main.py`.

## 3. Architecture and ownership

| Information | Authoritative owner | Other representations |
|---|---|---|
| KiCad symbols, footprints, models | Existing Git library repository | Server checkout and indexed metadata |
| Inventory quantities, locations, reservations | DMTDB inventory records and movement ledger | HTML/API availability views |
| Canonical component identity | DMTDB part identity and reviewed external identifiers | Library bindings and BOM mappings |
| Released design files and BOM | Immutable DMTDB release snapshot | Source repository links and downloads |
| Physical-unit history | DMTDB serial-unit events | Current-state summary |
| Firmware source | Firmware Git repository | Archived binary, checksum, and commit reference |

ARC-01: Retain Flask, SQLAlchemy, and server-rendered HTML. Add service modules and blueprints within the existing architecture. A frontend rewrite is not required.

ARC-02: Store uploaded file bytes in a configured server data directory, outside the source checkout where practical. Store ownership, original filename, media type, size, storage key, and SHA-256 in SQL. Do not store large archives as database blobs.

ARC-03: The rack server owns its own checkout and storage paths. Browser clients must not need a shared drive, local Python, a mapped `G:` drive, or shell commands for application workflows.

ARC-04: Git fetching, archive processing, and library indexing run as persistent background jobs. Job state survives application restarts; retries cannot duplicate applied changes. Avoid introducing a distributed queue unless deployment needs justify it.

ARC-05: Preserve SQLite initially, with explicit atomic transaction and contention handling. Do not assume row-level locks work on SQLite. PostgreSQL migration is optional and requires its own verified migration and deployment work.

ARC-06: Git library synchronization is read-only. Do not rewrite or commit CAD source files as part of importing metadata. Existing app-managed library files and repository-managed assets must have distinct provenance and storage ownership.

## 4. Header navigation and browser experience

NAV-01: Insert the new primary entries immediately after Browse and + Add Part, in this order:

`Browse | + Add Part | Designs | Prototypes | Builds | Library Sync | KiCad Libs | Labels | Import CSV | Client Setup | API Docs`

NAV-02: Keep the existing header actions and destinations functional. Add active-section styling for nested pages. On narrow screens, use a keyboard-accessible collapsed or overflow navigation that preserves this order and makes every entry reachable without overlapping controls.

| Entry | Proposed route | Main functions |
|---|---|---|
| Designs | `/designs` | Projects, board designs, releases, archived files, BOMs, linked units |
| Prototypes | `/prototypes` | Serial-number search, physical-unit records, history, issues, firmware |
| Builds | `/builds` | Batch planning, shortages, reservations, assembly consumption, completion |
| Library Sync | `/library-sync` | Repository configuration, synchronization status, matching review, import results |

NAV-03: Prototypes is the user-facing label; its records may also represent pre-production and production units. Provide lifecycle filters instead of creating another unit database later.

NAV-04: Extend Browse with In stock, Out of stock, Not stocked, Unknown quantity, and All parts filters. Preserve existing links and filters, and make the selected availability scope visible. The initial default remains All parts to preserve current browse behavior.

NAV-05: Part detail gains Library references, Stock history, Used in designs, and Used in builds links. Stock operations are accessible from part detail; build operations also link back to the affected parts.

NAV-06: All management workflows must be usable through HTML forms, including repository setup, upload, matching review, release publication, historical-unit registration, firmware recording, and stock adjustments. Provide pagination, useful empty states, field validation, and actionable failure messages.

NAV-07: Do not add live navigation links to unimplemented destinations. Introduce each entry with its functional section while preserving the final order above.

## 5. Designs and immutable releases

DES-01: A project has a stable internal ID, unique project identifier derived from DOCUMENT_ID, name, description, lifecycle status, optional repository URL, and timestamps. A project can contain multiple board designs.

DES-02: A board design has a project, board identifier, name, purpose, and optional link to an existing inventory part representing that board or assembly. Project + board identifier must be unique. Component DMTUIDs and hardware document numbers remain separate concepts.

DES-03: A release belongs to a board design and has a unique revision within that design, draft/released/superseded status, release notes, source commit where applicable, tool-version metadata, and a frozen BOM/assembly definition. Preserve the user's numbering convention; do not silently renumber legacy records.

DES-04: Support browser upload of a project/release ZIP and server-side import of an explicitly selected Git commit. Resolve branch/tag selections to a full commit before import and record it. Local uploads may represent uncommitted work and must be labeled as such, without claiming Git reproducibility.

DES-05: Release artifacts support project files, all schematic sheets, PCB files, Gerbers, drills, BOM, CPL/pick-and-place, schematic PDF, board preview images, STEP exports, firmware binaries, test reports, and notes. The original upload is retained. Files have explicit roles; filenames alone do not establish authority.

DES-06: Allow drafts with incomplete files. Publishing requires a revision, source snapshot, release notes, and an explicit inventory of included/missing artifact roles. Missing manufacturing or dependency files must be visible and acknowledged with a reason, rather than silently presented as a complete manufacturing release. Build eligibility is separately gated by a validated BOM and part mappings.

DES-07: Publishing freezes source files, manufacturing files, BOM, and checksums. Corrections to these require a new release. Later supporting reports may be appended with timestamps and provenance, but cannot overwrite the released package. Superseding does not remove access to previous releases.

DES-08: Preserve dependencies needed to reopen a release, including project libraries and relevant external library versions/files. Record a dependency manifest and unresolved references. A Git URL or commit identifier alone is not a substitute for archived bytes. Resolve Git LFS/submodule content where applicable or mark the dependency unresolved.

DES-09: Distinguish original manufacturing exports, the exact package submitted to a factory, and any returned factory files. Never replace the original with factory-modified files. Allow a batch to reference the exact submitted package and its checksum.

DES-10: Provide file lists, downloads, and browser-safe PDF/image previews. Full interactive schematic/PCB editing or Gerber viewing is outside the first version. Uploaded previews are supported initially; automatic preview generation can be added without becoming a release dependency.

DES-11: Referenced projects, releases, and parts must be archived or superseded rather than hard-deleted. Explicit draft deletion is allowed only when it cannot break historical references.

## 6. Physical units, firmware, and issues

UNT-01: Each physical unit has an internal ID, serial number unique within its product (or standalone board design), optional exact design-release reference, optional build batch, lifecycle stage, current status, location, notes, and timestamps. Serial uniqueness uses trimmed, case-insensitive comparison while retaining entered display text. Purchased products can exist without a design archive.

UNT-02: Support entering existing serial numbers and generating new serials with a configurable prefix and collision-safe sequence. Do not invent historical serials or assume an existing aggregate part row identifies one specific board.

UNT-03: Register existing prototypes through a historical-registration workflow. Link the existing part and release, or mark the release unresolved pending reconciliation. Historical registration must not deduct components again. Unresolved historical units must remain visibly incomplete.

UNT-04: New builds require an exact released revision. Each unit links back to its board, project, release, batch, and inventory part where applicable. Design and part pages list associated units by serial number.

UNT-05: Keep an append-only unit timeline: registration, firmware installation, hardware modification, test, fault, repair, status change, location change, and retirement. Record event time, recording time, actor, notes, and attachments. Corrections reference previous events rather than erase them.

UNT-06: A firmware artifact records a human-readable version, optional source repository and commit, binary attachment and checksum where available. Installation events record which unit received which artifact and when. Manual entries without a binary are allowed but visibly identified as version-only records.

UNT-07: Display Last recorded firmware, not a claim about live running firmware. Hardware revision, firmware version, and physical modifications remain independent. Automatic device telemetry is outside the first version.

UNT-08: Hardware modifications record affected reference designators, before/after description, reason, date, and optional replacement parts. Material-consuming repairs can create linked stock transactions; notes alone never change stock.

UNT-09: Issues have title, description, severity, state, timestamps, and links to a release and/or one or more units. Scope must be explicit. Closing an issue records its resolution; a unit-specific repair does not automatically resolve a release-wide defect.

UNT-10: Record pass/fail/inconclusive test outcomes with procedure/version, notes, measurements or attachments, and test date. Support unit-history and serial-list export through HTML downloads.

UNT-11: Product detail pages in enabled domains list individual SNs with current availability/status and direct history links. Provide Add SN, audited edits (including serial corrections), archive/removal, restore and WASTE. WASTE requires a reason and excludes the unit from available serial counts. Archived and WASTE histories remain accessible. Domain settings and generation prefixes are editable through HTML; disabling a domain does not destroy existing units.

## 7. Library synchronization and identity matching

LIB-01: Configure the existing GitHub repository in the browser. Store credentials securely on the server using a read-only repository credential. Never send secrets back in page responses, log output, exported reports, or downloaded archives.

LIB-02: Offer Sync now and a configurable scheduled fetch. Show last attempted sync, last successful sync, indexed commit, job progress, and errors. An offline GitHub connection leaves the last successful catalogue usable.

LIB-03: Index a consistent checked-out commit using a structured parser. Support multiple symbols per file, inherited properties, multi-unit symbols, escaped text, and empty custom fields. Do not count symbol units as separate orderable components. Unsupported or malformed definitions are reported without replacing good existing records.

LIB-04: Extract library identity, symbol name, value, description, footprint reference, datasheet, manufacturer, MPN, supplier identifiers, and useful electrical/package properties. Retain original values and source provenance alongside normalized matching values.

LIB-05: Normalize property aliases such as MFR/Manufacturer, trim whitespace, and use explicit manufacturer aliases. Preserve meaningful MPN suffixes and package differences. Do not remove punctuation or suffixes indiscriminately to manufacture a match.

LIB-06: Apply matching in this priority order:

1. Existing reviewed source binding or valid DMTUID, provided identifiers do not conflict.
2. Unique manufacturer + exact normalized MPN with consistent metadata.
3. Unique supplier + supplier part number with consistent metadata.
4. Candidate suggestions based on electrical specifications and package, requiring review.
5. Unresolved identity if the evidence is insufficient or contradictory.

LIB-07: A conflict between strong identifiers always enters review, including a previously mapped symbol whose MPN changes. Value/package alone must never cause an automatic identity merge. Suggested substitutes are not identical parts.

LIB-08: Show a preview with counts and per-item explanations for link existing, create catalogue part, update owned metadata, unchanged, conflict, missing source, and parse error. Allow review decisions of link, create, leave unresolved, or ignore. Review choices persist across retries and subsequent imports.

LIB-09: Several library representations can map to one part. Generic symbols may remain library entries without a canonical orderable part, with candidate/approved-part relationships when useful. Only identified orderable parts become stock-bearing catalogue records; selecting a generic symbol for a build requires a concrete component mapping.

LIB-10: New catalogue parts require valid DMT classification and an allocated DMTUID. Propose classification from library/category evidence; unresolved classification remains staged. Do not guess fine-grained classification or exceed the existing three-digit sequence limit. Allocation must be concurrency-safe and report exhaustion.

LIB-11: New confirmed parts start with no inventory holdings and display Not stocked. Synchronization must never infer purchased quantity, set a location from a symbol, or change existing stock/reservations/history.

LIB-12: Maintain field ownership. Repository-derived properties may refresh when unmodified locally; local overrides must be retained and conflicts shown. Do not replace a useful local value with an empty source property by default. Supplier stock is separate from personal stock.

LIB-13: Persist repository, path, library nickname, symbol name, commit, metadata hash, and match decision. Renames require explicit remapping or strong identity evidence; symbol disappearance marks a binding unavailable without deleting the part or historical BOM references.

LIB-14: Reapplying the same commit and decisions must have no additional effect. Use a staged import and validated apply operation, with uniqueness constraints and an audit report. Changes since preview require revalidation before apply. Initial import requires preview review; subsequent scheduled runs may apply only unchanged bindings and unambiguous, nonconflicting metadata updates. New identities and conflicts remain queued for review.

LIB-15: Existing local library upload/download behavior remains available. Repository-owned files cannot be overwritten by those paths. Indexing does not change the external repository or require clients to adopt a new library layout.

## 8. Stock representation and transactions

STK-01: Separate the catalogue part from its inventory holdings. A holding identifies a part, physical location, optional lot/reel identifier, and count status. Multiple locations for the same part must be supported.

STK-02: Use nonnegative integer quantities for countable components in this first version. Fractional materials require a later unit-of-measure extension; do not silently round them. Unknown counts are represented explicitly, not converted to zero.

STK-03: Derive the following display states:

| State | Meaning |
|---|---|
| Not stocked | Catalogue part has no inventory holdings |
| Out of stock | Holdings exist, all counts are known, total on-hand is zero |
| In stock | A known positive quantity is on hand; display any additional unknown holdings separately |
| Unknown quantity | No known positive quantity and at least one uncounted holding |

STK-04: Display Not stocked in the location column when there is no holding. Retain bin assignments when a holding reaches zero. Physical stock status and available-to-build quantity are different: a fully reserved part is still physically in stock but has zero available.

STK-05: Record immutable movements for opening balance, receipt, build consumption, return, scrap, transfer, and correction. Include quantity/direction, part, holding, actor, timestamps, reason, correlation/operation ID, and relevant build/unit reference. Transfer posts a balanced pair atomically.

STK-06: Compute on-hand from posted movements, optionally maintaining a transactionally updated balance cache that can be reconciled against the ledger. Compute available as known on-hand minus active reservations. Unknown holdings cannot be allocated automatically.

STK-07: After migration, all stock changes, including part forms, CSV import, API updates, repairs, and administrative adjustments, go through the same inventory service. No legacy path may overwrite an authoritative quantity directly. Counts entered in edit/import workflows become explicit stocktake corrections with a preview of the delta.

STK-08: Post multi-part consumption in one database transaction. Revalidate current balances at commit, reject shortages without partial deductions, and handle competing writes with bounded retries or a clear conflict response. Do not allow negative stock.

STK-09: Every stock-changing submission uses a persistent idempotency key. Retrying the same operation returns its original result; reusing the key with a different payload is rejected. Browser double clicks and network retries cannot deduct twice.

STK-10: Corrections and returns create linked compensating entries, not edits to old movements. Prevent repeated returns exceeding the eligible consumed amount. Cancellation does not assert that physical components were recovered.

## 9. BOMs and build workflow

BLD-01: Import an exported KiCad BOM through HTML. Support a documented CSV format with header mapping and a reusable mapping preset; use exported BOM/netlist data for design analysis. Preserve the original input and parsed snapshot.

BLD-02: Each BOM line records reference designators, quantity per assembly, value/specification, footprint, DNP/exclusion state, optional supplier/MPN identifiers, canonical part mapping, and procurement source. Validate repeated/missing reference designators and inconsistent quantities; do not count multi-unit schematic symbols multiple times.

BLD-03: A released assembly definition freezes its BOM and population variant. A changed variant must be a separately versioned definition. Builds reference one exact definition. Line-level substitutions retain planned and actual parts and their reasons without mutating the released BOM.

BLD-04: Creating a build requires a release, assembly definition, positive board count, and planned date/notes. Show required quantity, available quantity, existing reservation, shortage, selected holding, and external/factory-supplied quantity per line. Exclude DNP items.

BLD-05: Match imported lines using the library identity rules. Unresolved required lines prevent stock posting. External/factory-supplied lines must be explicitly marked and mapped for traceability but do not consume personal stock.

BLD-06: Use explicit states: Draft -> Planned -> Reserved (optional) -> In progress -> Completed; Cancelled is available with reconciliation rules. Store reservation and material-posting state separately so partial work is representable without ambiguous status transitions.

BLD-07: Plan and reserve do not reduce on-hand. Reservations reduce available-to-other-builds and can be released. Consumption converts the relevant reservation into a stock deduction in the same transaction. A build may consume its own reserved stock but cannot consume another build's allocation.

BLD-08: Present an explicit consumption preview for the selected assembly quantity. Default to BOM quantity multiplied by that quantity, then permit documented actual consumption and substitutions. Record waste separately. Component source and holding allocations must sum to the requested actual quantity.

BLD-09: Support partial batches through separate material/assembly postings with cumulative totals. Prevent accidental overproduction beyond the planned count unless the plan is explicitly revised. Do not use one irreversible Consume all flag for the entire batch.

BLD-10: Create or assign serial units to the assembled quantity and associate them with the applicable posting and actual component selections. If units within a batch differ, record per-unit exceptions or separate postings. The unit view must distinguish a shared batch BOM from a verified per-unit exception.

BLD-11: Completion requires reconciled material postings, unit assignments for serialized assemblies, and explicit handling of unused reservations. Registering a unit from an existing build must not consume components again.

BLD-12: Cancelling before consumption releases reservations. Cancelling after consumption preserves movements and unit history, and asks for explicit treatment of unused stock, assembled units, and scrap. Never automatically return all consumed parts.

BLD-13: Repairs and modifications use the same ledger with unit references. Return-to-stock requires a usable recovered part and an explicit return operation.

BLD-14: The first version tracks finished prototypes through serial-unit records. It must not also increment a separate finished-goods stock total automatically. Existing board inventory links remain available; a later finished-goods accounting feature would require explicit reconciliation rules to avoid double counting.

## 10. Git independence and connected KiCad usage

INT-01: Machines outside the rack network continue cloning/pulling the same repository with their normal GitHub credentials. Library operation must not depend on the database server being available.

INT-02: Extend the existing optional HTTP library with DMTUID, known on-hand, reserved, available, stock status, locations, part-detail URL, and availability timestamp. Ensure referenced symbol/footprint library nicknames resolve in client clones. Preserve the current HTTP library protocol.

INT-03: Live availability is server information and may be cached by KiCad. Treat chooser fields as advisory; always revalidate stock during build operations. Do not write changing stock counts into Git symbols or treat schematic fields as authoritative inventory.

INT-04: A dated offline inventory export may be provided later; it is outside the required first version. Never label a cached/exported snapshot as live stock.

INT-05: Document that HTML handles management, downloads, and previews. Native KiCad remains the editing tool for downloaded/cloned design files. No browser-to-local-filesystem access is assumed.

Reference: https://dev-docs.kicad.org/en/apis-and-binding/http-libraries/

## 11. Logical data model and invariants

The following entities describe required responsibilities; exact table names may be refined during implementation without losing these relationships.

| Entity | Core relationships and constraints |
|---|---|
| Project | Unique embedded project identifier; entered as a full DOCUMENT_ID, normalized to PBOM; contains board designs |
| BoardDesign | Project + board code unique; optional existing Part link |
| DesignRelease | Board + revision unique; frozen source/artifact manifest after release |
| Artifact | Server storage key, checksum, size, role, provenance, explicit owner link |
| AssemblyDefinition / BomLine | Release + variant/version; frozen requirements and references |
| BuildBatch / BuildPosting | Exact assembly definition; cumulative assembly/material activity |
| PhysicalUnit | Unique serial; release/build; optional legacy Part link |
| UnitEvent / FirmwareArtifact | Append-only unit history; version/binary identity |
| Issue / IssueLink | Explicit affected releases and/or units; status history |
| LibraryRepository / SyncRun / ReviewItem | Commit-specific staged work, decisions, errors, and results |
| LibraryEntry / PartLibraryBinding | Source identity independent of canonical part; reviewed mappings |
| PartIdentifier | Manufacturer or supplier scope + identifier; conflict-aware canonical mapping |
| StockLocation / StockHolding | Part + location + optional lot; known/unknown count status |
| StockMovement / Reservation | Immutable movement ledger; explicit reservation lifecycle |
| Operation / AuditEvent | Unique idempotency key; actor and change provenance |

DAT-01: Use foreign keys for business links and database constraints for uniqueness, nonnegative balances/reservations, and valid quantities. Avoid replacing these with arbitrary JSON-only relationships. Validate cross-row invariants within transactions.

DAT-02: Preserve DMTUIDs. Introduce stable internal surrogate IDs where needed rather than renaming existing parts. Link duplicate candidates through reviewed identity resolution; do not perform destructive bulk merges as part of the first import.

DAT-03: Every meaningful mutation records actor and UTC timestamps. Display dates consistently in the configured user/server application timezone, initially Europe/Vienna. Record actual event time separately from entry time where historical entries are supported.

DAT-04: Prevent hard deletion of records referenced by released BOMs, stock movements, builds, or units. Maintain historical labels/snapshots so later part-description changes do not rewrite an old release.

## 12. Service, API, and operational requirements

OPS-01: Add focused services for designs/artifacts, unit history, library synchronization/matching, inventory transactions, and builds. HTML and REST handlers call the same services; routes do not duplicate stock rules.

OPS-02: Proposed REST resource groups are `/api/v1/designs`, `/api/v1/releases`, `/api/v1/units`, `/api/v1/builds`, `/api/v1/inventory`, and `/api/v1/library-sync`. Existing routes stay compatible where safe. Stock writes using old quantity fields must route through audited adjustment semantics, with compatibility behavior documented.

OPS-03: Persistent jobs expose queued/running/succeeded/failed state and a result report. Use per-repository serialization and restart recovery to avoid concurrent sync corruption. Parsing/fetch failures cannot erase a previously successful index.

OPS-04: Define the rack deployment's authenticated user identity before enabling mutations. Use the existing trusted authentication layer if present; otherwise add an appropriate application/reverse-proxy login integration. At minimum distinguish read access from write/admin operations. Protect browser mutations against CSRF and authorize downloads as well as page views.

OPS-05: Restrict server Git imports to configured trusted repository hosts and protocols, with no arbitrary shell execution or Git hooks. Do not expose credential-bearing URLs. Validate redirects and network destinations to prevent using imports to access unrelated internal services.

OPS-06: Enforce upload/archive limits, reject path traversal, absolute paths and unsafe links, and limit extracted size/file count. Uploaded HTML/SVG and other active content must not execute in the application origin. Treat filenames and metadata as untrusted display text.

OPS-07: Stage file bytes, validate/checksum them, and publish an artifact only when storage and metadata are durable. Handle interrupted uploads and orphan cleanup without deleting referenced release data. Content-addressed storage is acceptable but must retain separate ownership metadata.

OPS-08: Back up the database with a database-aware method and include artifact storage, configuration, and relevant manifests. Protect credentials separately. Verify a restore to a separate instance and confirm artifact hashes and record links. Copying only the main SQLite file while WAL writes are active is insufficient.

OPS-09: Add indexes and pagination for serial, project/revision, canonical identifiers, part availability, movements, and library review queues. Measure list/search performance against the complete imported library on representative rack hardware; record dataset size and measured timings rather than promise an unmeasured latency.

## 13. Migration and compatibility plan

MIG-01: Introduce versioned schema migrations and a documented baseline for existing databases. Test against a backup copy. Application startup must detect incompatible schema versions and never silently recreate the database.

MIG-02: Inventory the actual rack database before cutover: schema version, row counts, quantity values, locations, identifier duplicates, existing prototype rows, library paths, and deployed app revision. Local observations in section 2 are not a migration input substitute.

MIG-03: Produce a quantity migration preview. Nonnegative integer strings become opening balances; blank/invalid/negative values enter a reconciliation report. Preserve original values. Unknown quantities remain unknown until counted.

MIG-04: Preserve existing physical-location text and propose normalized location records with a preview. Do not erase locations for zero-count parts. Create explicit unlocated holdings for known stock without a location. Legacy unknown-stock rows remain holdings requiring reconciliation, not newly imported catalogue-only records.

MIG-05: Each opening balance must be posted exactly once and linked to the migration run. Reconcile per-part quantities and totals against the preview. Keep legacy quantity fields as a derived compatibility view/cache during transition, then remove them only after all readers/writers have migrated.

MIG-06: Preserve existing prototype catalogue entries. Offer explicit linkage to design releases and serial units. Do not fabricate build history, firmware history, serials, or past component consumption.

MIG-07: First library synchronization runs in preview mode against migrated data. No stock values change. Resolve ambiguous matches progressively; the rest of the system remains usable while review is pending.

MIG-08: Perform cutover during a controlled write pause after backup and migration rehearsal. Verify counts, files, representative pages, and stock reconciliation before resuming writes. A failed cutover restores the matching application/database/artifact backup; once new writes have occurred, prefer a forward fix or explicitly preserve/reconcile those writes before rollback.

## 14. Acceptance scenarios

| ID | Scenario and required result |
|---|---|
| AC-01 | Header order matches NAV-01; all destinations and keyboard/mobile navigation work; existing actions remain usable. |
| AC-02 | Create a project, two board revisions, and units for both. Each serial opens the correct frozen release, and both revisions remain downloadable. |
| AC-03 | Attempt to overwrite a released BOM/source file. The operation is rejected; a new release can be created. |
| AC-04 | Register an existing ENERGIS prototype. Existing part remains linked; stock ledger does not acquire historical consumption. |
| AC-05 | Record two firmware installations and a repair. Current summary reflects the latest applicable event; all previous events and attachment hashes remain accessible. |
| AC-06 | Link an issue to a release and to one unit. Unit repair does not silently resolve the release-wide issue. |
| AC-07 | Import a symbol whose manufacturer/MPN matches a stocked part. It links without duplicate part creation or quantity/location changes. |
| AC-08 | Import two equal-value/package symbols with different MPNs, and a symbol with contradictory strong identifiers. Distinct identities are retained and conflicts enter review. |
| AC-09 | Import a concrete new part and a generic symbol. The part shows Not stocked; the generic remains an unresolved/selectable library entry without fabricated stock identity. |
| AC-10 | Repeat a sync, rename/delete a source symbol, and interrupt a job. No duplicate applied changes, missing historical references, or lost successful catalogue results occur. |
| AC-11 | Build five boards requiring eight capacitors each. Preview proposes 40, posting consumes 40 once, and the build and serial records link to the movement. |
| AC-12 | Repeat the same consumption request and submit a changed payload with the same key. The first is a replay; the second is rejected. |
| AC-13 | Two builds compete for insufficient remaining stock. Only a valid allocation succeeds; the other has no partial deduction and gets a shortage/conflict response. |
| AC-14 | Reserve, partially assemble, release unused reservations, and cancel. Stock, availability, unit count, and return/scrap history reconcile at every step. |
| AC-15 | DNP and factory-supplied items consume no personal stock. An explicit substitute consumes the selected real part and remains visible in the build/unit history. |
| AC-16 | Attempt consumption from an unknown holding or with unresolved required BOM mappings. Posting is blocked with an actionable explanation. |
| AC-17 | Existing part-edit, CSV, and API quantity writes create audited corrections; no legacy path bypasses the ledger. |
| AC-18 | Take the rack server offline. A separate machine can still use its Git clone; reconnecting restores optional HTTP stock access without rewriting library files. |
| AC-19 | Restore a backup on a separate instance. Releases, checksums, serial histories, mappings, stock balances, and reservations reconcile. |
| AC-20 | Reject malicious/oversized archive paths and unauthorized mutations/downloads; credentials do not appear in UI, logs, or exports. |
| AC-21 | Rehearse migration twice safely: existing IDs and original values remain recoverable; opening balances cannot be duplicated; unknown quantities do not become zero. |

Use unit/service tests for identity matching, BOM arithmetic, state transitions, and transaction invariants; integration tests for migrations, concurrency, retry behavior, imports, and storage failure paths; and browser checks for navigation and end-to-end workflows. Add focused fixtures from representative library metadata, avoiding dependence on a live private repository in routine tests. Record the tested KiCad/library format versions.

## 15. Implementation phases and estimates

Estimates are planning ranges for one experienced developer, including focused validation. They exclude major source-data cleanup, a full CAD viewer, telemetry, and unexpected deployment constraints. Re-estimate after the initial rack-data audit and importer prototype.

| Phase | Deliverables | Dependency | Estimate | Status |
|---|---|---|---|---|
| P0 | Confirm deployment inputs, migration baseline, stock migration preview, API compatibility inventory | None | Included in P1 | Local inputs recorded and migration/restore rehearsed; rack cutover deferred by user |
| P1 | Numeric holdings, ledger, reservations foundation, migrated legacy stock writes | P0 | 4-6 days | Ledger and legacy write adapters tested; authenticated attribution and dedicated holding forms remain |
| P2 | Read-only Git indexing, identity mapping/review, catalogue availability, Library Sync navigation | P1 foundations | 4-7 days | Core catalogue, scheduled jobs/recovery and HTTP stock overlay implemented; real private-remote credentials not verified |
| P3 | Projects, releases/artifacts, serial units, firmware/issues/history, Designs and Prototypes navigation | P1 foundations | 5-8 days | Core archive, fixed-commit Git import and product-domain serial workflows implemented; advanced issue/dependency features remain |
| P4 | BOM mapping, builds, material posting, substitutions, unit assignment, Builds navigation | P2 and P3 | 5-8 days | BOM mapping, substitutions, reservation, partial assembly, serial creation and returns implemented; advanced BOM presets/waste accounting remain |
| P5 | Complete integration checks, deployment configuration, restore rehearsal, docs, cutover validation | P1-P4 | 3-5 days | Local Windows checks, restore rehearsal, rendered UI review and writable deployment completed; rack rollout deferred |
| Total | Reliable integrated first version | All phases | 21-34 developer days | Core workflows deployed on PC; full-plan refinements remain; Pi production unchanged |

Security, migration safety, and transaction tests are implemented within the relevant phase; P5 verifies the complete deployment and is not a reason to defer correctness work.

### Phase completion checklist

- [ ] P0: Actual deployment inputs recorded; schema baseline and migration preview reviewed for data-loss risks.
- [ ] P1: AC-12/13/16/17/21 applicable inventory cases pass; ledger reconciles with migrated data.
- [ ] P2: AC-07 through AC-10 pass; imported catalogue does not alter holdings; library setup compatibility checked.
- [ ] P3: AC-02 through AC-06 pass; released files and unit history persist correctly.
- [ ] P4: AC-11 through AC-16 pass with real workflow fixtures and retry/concurrency integration coverage.
- [ ] P5: AC-01 and AC-18 through AC-20 pass; complete acceptance set and rack cutover checks recorded.

### Evidence record template

For each completed phase, append: implementation commit(s), requirement IDs delivered, migration versions, commands/checks run, relevant results, known limitations, and remaining follow-up work. A checked phase means delivered and verified, not merely coded.

### 2026-11-22: configuration and migration foundation

- Added `config.local.ini` (gitignored) on Windows and the Linux rack server, with a tracked example and documented environment precedence. The Windows file includes the server's SSH/path information as reference-only metadata. Linux settings use native Linux paths and mode 0600.
- Wired existing app-managed library upload/download/serving and staging paths to central configuration. Kept external library repository storage separate. No CAD files were modified.
- Added frozen Alembic revision `0001_legacy`, schema recognition, explicit upgrade with SQLite backup/integrity checking, future/unknown-schema rejection, and repeat-upgrade no-op behavior. Existing application startup now requires this baseline before running the new code.
- Added `python -m manage db-status` and `inventory-preview`, using read-only SQLite connections. Added an HTML preview at `/inventory/migration-preview` with filtering, pagination, and JSON export, accessible from Browse in the new code.
- Rack audit: `/home/masterpi/_GitHub/SW_PartsDB`; Python 3.11.2; deployed Git revision `86f55d8`; active `dmtdb` service; application environment `venv`; SQLite at the repository root. External library path confirmed, revision `aaccfa0` at audit time.
- Actual rack inventory: 345 parts, 279 known counts, 66 unknown counts, zero invalid nonblank counts, 307090 known components, and nine distinct trimmed location values. Unknown counts are preserved. ENERGIS prototype entry remains unchanged.
- Windows validation: `.venv/Scripts/python.exe -m pytest -q` -> 23 passed, 1 POSIX-only test skipped. Linux validation: isolated test environment using deployed dependency versions -> 24 passed. `git diff --check` passed.
- Rehearsed the upgrade against a SQLite backup of the rack database in `/tmp/dmtdb-foundations-20261122-b7c9`. Compared all rows of all five original tables before/after; all unchanged. A repeated upgrade returned current without another backup or mutation.
- Requirements progressed: ARC-01/02/03/06 configuration foundations, MIG-01/02/03 baseline and preview portions, OPS-08 SQLite backup portion. This does not complete the artifact backup workflow or later stock migration requirements.
- Production changes are limited to the requested local config file and its `.gitignore` rule. No service restart, production schema migration, source deployment, or stock modification occurred. Test dependencies were installed only in the isolated temporary environment.
- Next work: settle mutation authentication for the rack deployment, implement P1 holdings/ledger/reservations, route all legacy quantity writes through the inventory service, and add stock reconciliation/migration before enabling any build deductions. The current CSV replacement code deletes/recreates parts and must be changed before historical links exist.
- Navigation sections remain scheduled with their functional features, per NAV-07. No placeholder Designs/Prototypes/Builds/Library Sync destinations have been added.
- Deployment and configuration instructions: [local-configuration-and-migrations.md](local-configuration-and-migrations.md). Work is in the working tree, not committed.

### 2026-11-22: inventory ledger and browser preview

- Added revision `0002_inventory`: numeric holdings with known/unknown counts, persistent operation keys, immutable SQLite stock movements, reservations, and an inventory writer lock. Migration posts one opening record per legacy part and preserves original quantity/location metadata. Invalid counts roll back the complete migration.
- Added transactional stocktake, receipt, scrap/correction, reserve/release, consume, return, and balanced transfer services. Stock changes validate available counts under the writer lock; failed multi-holding operations roll back together. Duplicate operation requests replay stored results and conflicting payloads are rejected. Returns cannot exceed their original consumption.
- Existing HTML/API part edits and CSV imports use the ledger. CSV updates no longer delete/recreate existing parts. Row-level savepoints isolate invalid rows; import runs have persistent replay results. Known stock cannot be silently cleared to unknown. A part with stock history cannot be hard-deleted.
- HTML count edits show an expiring, signed review before saving. CSV uploads perform a rolled-back preview, show proposed counts, and require confirmation; inventory changes between preview/apply cause rejection. REST stock edits require `Idempotency-Key`; CSV supports run keys, preview mode, and inventory-fingerprint checks.
- Added `/part/<DMTUID>/stock`, with holdings, active reservations and paginated movement history; part-detail and browse quantities link to it. Browse filters distinguish In stock, Out of stock, Not stocked and Unknown quantity, and quantity sorting is numeric. Part JSON includes on-hand/reserved/available/unknown inventory data.
- Added `python -m manage inventory-check` to compare ledger totals, reservation totals, and compatibility fields. Snapshot rehearsal created 345 holdings and 345 movements, preserved 66 unknown holdings, and reconciled without errors. Every row in the original five tables remained unchanged.
- Final increment validation: Windows `python -m pytest -q` -> 37 passed, 1 POSIX-only skip; Linux against deployed dependency versions -> 38 passed. Tests cover partial-operation rollback, simultaneous competing consumption, request replay/conflicts, capped returns, reservations, immutable history, CSV relationship preservation, reviewed/stale imports, signed stocktake confirmations, numeric sorting, and read-only preview enforcement. This verifies the implemented inventory portions of AC-12/13/16/17/21; the full build acceptance scenarios still await P4.
- HTTP checks verified Browse/availability, stock history, migration report, search, JSON inventory and CSS on port 5001, plus unchanged production availability on port 5000. A preview POST returned HTTP 403. Browser-control host was unavailable, so visual inspection was not completed.
- Preview code and data are isolated under `/home/masterpi/_GitHub/SW_PartsDB/.local/inventory-preview`. A read-only process serves `http://192.168.0.25:5001/`; mutation requests return HTTP 403. Production remains at `http://192.168.0.25:5000/`, with original source/schema and its service still running.
- Access instructions and future-update reporting requirements are recorded in [access-and-deployment.md](access-and-deployment.md). New pages are not deployed on port 5000.
- Remaining P1/cutover work: authenticated write attribution, CSRF protection, dedicated holding management/stock-count UI, and broader compatibility review before production migration. P1 is not marked complete. Build and library-sync workflows have not yet been exposed.

### 2026-11-22: primary design/prototype and library catalogue implementation

- Added frozen migrations `0003_designs` and `0004_library`. The upgrade creates design/archive/unit/history/issue and library-index/review tables; it does not alter existing inventory rows. Migration status recognizes each earlier revision and validates its matching frozen schema before advancing.
- Added functional **Designs**, **Prototypes**, **Library Sync** header entries after Browse and + Add Part, with nested-section active styling and horizontal keyboard-accessible overflow navigation. No Builds placeholder was introduced. This delivers the implemented portion of NAV-01/02/03/05/06/07; final mobile visual acceptance is still pending.
- DES-01/02/05/06/07/09/10/11: project → board → revision hierarchy, existing-part links, explicit artifact roles, original-byte upload/download, SHA-256 content storage, safe ZIP manifests, PDF/raster previews, draft metadata editing, publication with acknowledged omissions, frozen release manifests, appended supporting reports, and project archival/release supersession. SQLite guards prevent changes/deletion of released contents and archived metadata. No KiCad source files are edited.
- UNT-01/03/04/05/06/07/08/09/10 implemented portions: globally case-insensitive serials, historical registrations with explicit unresolved revisions, later revision reconciliation, released-revision requirement for new units, collision-safe generated serials, part/design/release crosslinks, append-only firmware/modification/test/fault/repair/status/location/correction history, attachments, last-recorded-firmware summaries, backdated-event handling, separately scoped issues/resolutions, serial CSV and history JSON exports. New registrations never consume stock. Generated prefix currently follows project + board; configurable overrides remain pending. Multi-unit issue associations remain pending.
- LIB-03/04/05/06/07/08/09/10/11/12 implemented portions: read immutable blobs at one Git commit, structural S-expression property parsing, inherited/empty/escaped properties, top-level symbol identities, normalized manufacturer aliases and suffix-preserving identifiers, reviewed bindings, exact manufacturer/MPN and supplier matches, contradictory/ambiguous identity review, metadata provenance and immutable review history, source disappearance retention, and staged generic symbols. Failed files retain last-good data and are visibly blocked from review until parsing succeeds.
- HTML supports configuring a public HTTPS GitHub repository, indexing the separately configured local clone, fetching into an independent bare cache, reviewing one entry, confirming all unique matches, and classifying up to 50 selected entries together. Batch creation rechecks identity under the inventory writer lock, links duplicate representations, creates no holdings, and rolls back the entire batch on a conflict. New catalogue parts display **Not stocked** in Browse, part detail and library review. Source metadata never overwrites existing part metadata or stock.
- Each new mutation form checks a session CSRF token. Preview still blocks every mutation. `web-interface` is a recording-source label, not authenticated human attribution; production write access remains gated by the outstanding access-control work.
- The real Linux library indexed 1,428 symbols at commit `aaccfa0df726d0fefffa29c02013a933ccbb972b`, with zero parse errors. Before review: 26 unique matches, 37 conflicts, 1,252 identified entries needing classification, 113 unresolved entries. No actual catalogue creations or matching decisions were applied. All five original production tables still equal the preview snapshot, including all 345 parts.
- Validation covers HTML project/archive/publication/serial/history/issue flows; exact archive byte round-trips; frozen releases and append-only history; two revisions with distinct serials and part links; concurrent serial allocation; historical registration without stock deduction; backdated firmware; issue scope isolation; unsafe ZIP paths and corruption/size detection; parser inheritance/units/escaping/malformed definitions; exact/supplier/contradictory matches; generic entries; no-stock creation; duplicate representations; repeated Git indexing; parse/network failures; deleted sources; stale review rejection; and batch rollback. Tests use disposable databases and Git objects, not production data.
- Outstanding P2/P3 requirements remain explicit: design import from a selected Git commit (DES-04), automated dependency completeness/reproducibility checks (DES-08), configurable serial prefixes (UNT-02), multi-unit issue associations (UNT-09), private-repository credentials, scheduled fetch/job-crash recovery (LIB-01/02), classification proposals beyond the user-reviewed guide, broader compatibility/optional HTTP overlay checks, and complete authorization/backup-restore/cutover acceptance. These phases are not marked complete. BOM/build consumption remains deferred by the user's priority correction.
- Access: **http://192.168.0.25:5001/designs**, **/prototypes**, **/library-sync**. This is a read-only isolated snapshot. Production remains **http://192.168.0.25:5000/** with its original application/schema and active `dmtdb` service. New forms are exercised in isolated integration tests; no fictional design or serial data was added to the real snapshot. See [access-and-deployment.md](access-and-deployment.md) for workflow and storage details.
- Final verification: Windows `python -m pytest -q` → **68 passed, 1 POSIX-only skip**; Linux Python 3.11 with deployed dependencies → **69 passed**. Preview schema reports current at `0004_library`; `inventory-check` reports no problems. HTTP checks return 200 for all three sections and catalogue filters, verify header order, and confirm POST requests return 403 on each new preview section. Production `dmtdb` remains active. Browser automation was unavailable, so no rendered visual/mobile inspection is claimed. Work remains uncommitted in the working tree.

### 2026-11-22: writable PC deployment, product serials, builds and durable jobs

This evidence supersedes the earlier preview-only URLs and deferred-work descriptions above. Earlier entries are historical evidence, not the current deployment status. The user explicitly selected local PC deployment and will push/pull the code onto the Raspberry Pi later.

- Current writable URL: **http://192.168.0.100:5000/**; localhost:5000 on this PC. Active data is in ignored `instance/partsdb-local.sqlite`, created from a consistent copy of the existing database. Original `dmtdb.sqlite` remains untouched. Machine-local settings and secrets stay in ignored `config.local.ini`. No later SSH deployment was made.
- Migrations `0005_serials`, `0006_jobs`, `0007_builds` add scoped serial identity, per-domain policy, persistent jobs, library schedules, frozen BOMs/build postings and unit/build links. Current schema head is `0007_builds`.
- UNT-02/11 and product workflows: domains 19/20/29 enabled initially, browser-configurable prefixes and domain selection, independent SN registration on product detail pages, audited edit, WASTE with reason, archive/remove and restore. Purchased products do not need a design. Availability counts exclude waste/retired/faulty units. Serial registration/status never silently changes aggregate stock. Same SN on different products is permitted. Backdated history does not overwrite newer recorded state.
- DES-04 and LIB-01/02 implemented portions: fixed-commit Git source ZIP imports; public HTTPS or GitHub SSH repository URLs; machine Git/SSH credential reuse without interactive prompts; isolated Git caches; queued/scheduled sync; persistent leases, deduplication, retries and restart recovery visible at `/jobs`. LFS pointers/submodules are flagged unresolved; publication requires an explicit omission acknowledgement. Private-remote credentials have not been exercised end to end on this PC.
- P4 core: original BOM CSV/TSV archival, recognized column aliases, manufacturer/MPN matching and editable canonical mappings, DNP/external supply, frozen released BOMs, build quantities, reviewed signed posting, reservations, partial assembly, substitutions with reasons, automatic/manual unit serials, cancellation of unconsumed reservations and capped recovered-component returns. Material posting is atomic and replay-safe. Test fixture: five boards with eight capacitors consumes exactly 40 once.
- Header order is Browse, + Add Part, Designs, Prototypes, Builds, Library Sync, then existing destinations. Product details link serial records and BOM design usage. Unit pages link their build and revision. Project/board descriptions and repository settings are editable with ownership restrictions.
- Fixed legacy KiCad field semantics: `kicad_libref` remains the LCSC supplier ID; symbol identity is stored separately with its library prefix. Optional HTTP fields expose stock status, known on-hand, available, reserved, unknown holdings, location and lookup timestamp. These are lookup snapshots; ordinary Git library use remains independent and unchanged.
- Real local index: 1,428 entries, zero parse errors; after supplier-alias correction, 21 unique matches, 61 conflicts, 1,233 identified entries needing classification, and 113 unresolved. No actual catalogue creation/matching decisions or fictional user serials/designs were inserted. Existing parts remain 345.
- Backup browser download and CLI bundle include consistent SQLite, referenced immutable artifacts and app assets, excluding secrets/external Git clones. Restore verifies manifest/checksums, paths, database integrity and foreign keys into an empty directory. Real rehearsal restored 303 files; inventory reconciliation returned no discrepancies.
- Final Windows suite: **85 passed, 1 POSIX-only skip**. `git diff --check` passed; active schema is current and `inventory-check` returned no problems. A populated 0004 database upgraded to 0007 with serials, issue links and firmware history preserved; audited edits still work and unaudited serial changes are rejected. SQLAlchemy reflection reports an apparent inline build-FK delete-action difference; SQLite PRAGMA confirms the actual constraint is RESTRICT, matching the model. Previous Linux results apply only to the earlier increment; this latest version was not deployed/tested on the Pi after the user's local-only instruction. Headless Chrome rendered the product serial section at desktop and narrow widths; responsive navigation overflow was corrected.
- Full-plan refinements remain explicit: authenticated human attribution and legacy-endpoint CSRF hardening for production; dedicated holding management UI; arbitrary BOM column mapping presets and actual waste quantities beyond reviewed substitutions/returns; multi-unit issue associations; automated external dependency resolution/reproducibility; real private-remote and current Linux cutover validation; operational backup retention. These do not prevent using the implemented core workflows on the authorized local LAN deployment. The phase checkboxes remain unchecked until their complete acceptance sets pass.
- Final local restart succeeded. HTTP 200 verified for Browse, Designs, Prototypes, Builds, Library Sync, Jobs, serial settings, backup settings, ENERGIS detail and the KiCad stock JSON. Header order and writable mode verified. Final Chrome mobile emulation at 390 x 844 confirms readable serial controls and horizontally scrollable tables/navigation.
- Work is uncommitted. [Access and deployment](access-and-deployment.md) documents local start/restart, every feature URL, backups, code-versus-data transfer and user-controlled Pi migration. No Windows autostart service is installed.

## 16. Defaults, deployment inputs, and exclusions

Defaults established by this plan:

- Navigation labels and order are specified in section 4.
- Existing library repository remains authoritative and unchanged by synchronization.
- SQLite remains the initial database backend.
- Product/design-scoped serial numbers; configurable domain generation prefix.
- Manual firmware recording and browser PDF/image previews.
- Integer component counts, no automatic finished-goods stock posting.
- First sync reviewed; subsequent scheduled sync does not auto-create ambiguous/new identities.

Deployment inputs to determine during P0, without blocking independent implementation:

- Rack deployment revision, Python version, database path, and service status have been audited (see evidence above). The user selected a writable PC deployment under the existing LAN access model; rack authentication/hardening remains a later rollout decision.
- Durable storage path, capacity/quotas, backup destination, and backup/retention schedule.
- Server-side read-only Git credential and desired sync frequency; scheduling remains disabled until configured.
- Existing serial conventions and data needing historical import.
- KiCad versions and representative exported BOM formats used by the company.

Outside the first version: in-browser CAD editing, automatic electrical design review, automatic flashing/device telemetry, two-way Git library authoring, a purchasing/accounting system, fractional stock units, and automated factory ordering. These must not be introduced as dependencies of the required workflows.

## 17. Decision and change log

| Date | Decision | Reason / impact |
|---|---|---|
| 2026-11-22 | Adopt this file as the implementation baseline | User requested a detailed Markdown plan to guide implementation. |
| 2026-11-22 | Place Designs, Prototypes, Builds, and Library Sync after Browse and + Add Part | Makes the new workflows first-class header destinations while retaining existing functions. |
| 2026-11-22 | Separate catalogue identity, inventory holdings, releases, and serial units | Supports trustworthy matching, reproducible archives, and physical-unit history. |
| 2026-11-22 | Use read-only Git indexing and an optional HTTP inventory overlay | Preserves independent Git clone/pull usage outside the rack network. |
| 2026-11-22 | Use ledger-based consumption with reservations and idempotent posting | Prevents duplicate deductions and preserves an auditable explanation of stock changes. |
| 2026-11-22 | Add gitignored INI configuration per machine, with environment overrides | User supplied Linux app/library paths and requested a small local-path configuration file; avoids Windows paths on Linux. |
| 2026-11-22 | Baseline existing databases explicitly; rehearse on a backup before cutover | Introduces migrations without silently altering production inventory or treating unknown counts as zero. |
| 2026-11-22 | State environment, URL and navigation in future implementation updates | User requested clear instructions for accessing the database after changes. A read-only snapshot on port 5001 enables review while production remains on port 5000. |
| 2026-11-22 | Prioritize P3, then P2, ahead of optional stock/build refinements | User explicitly corrected the implementation priority: design storage, prototype traceability, and library catalogue integration are the main features. |
| 2026-11-22 | Add product-domain serial management, audited editing/removal and WASTE | User explicitly requested individual SNs on SBC/prototype/product detail pages, without requiring a design archive. SN uniqueness now follows the owning product/design. |
| 2026-11-22 | Deploy on this PC; user pushes/pulls to Raspberry Pi later | Supersedes the earlier rack preview rollout. Writable PC is 192.168.0.100:5000; Pi production remains unchanged. |


### 2026-11-23: use the existing DOCUMENT_ID

- User correction: remove the separate 4-6-character project-code input. Enter `DOCUMENT_ID` from existing SCH/PCB documentation instead; normalize its TYPE segment to `PBOM` and derive the embedded project identifier internally.
- Reference: `G:/_GitHub/LIB_KiCad-Libraries/Part_Numbering_Standard.md`, version 1.0.0. Standard form is `DMT-HW-XXXX-YY-TYPE-VMmp`. The explicit user-requested PBOM type extends that document's listed types. Existing VECTRA source/fabrication identifiers omit YY; accept and preserve this form too, without inventing a board number.
- Examples: `DMT-HW-VCTR-SCH-V100` and `DMT-HW-VCTR-PCB-V100` become `DMT-HW-VCTR-PBOM-V100`; `DMT-HW-USBSW-02-PCB-V110` becomes `DMT-HW-USBSW-02-PBOM-V110`. Already-PBOM values remain unchanged. Input is trimmed and uppercased; the project, optional board and three-digit revision segments are retained.
- Project creation, project display/edit and search use DOCUMENT_ID. The embedded project identifier remains unique and permanent. A different revision of an existing project belongs under that project, rather than creating another project record. Existing generated serial conventions continue using the derived identifier.
- Migration `0008_document_id` adds the nullable document field, preserving all existing projects, board/release links, serials and histories. Legacy records do not receive fabricated document IDs; their real ID can be entered through Edit project information. No KiCad source files or external numbering-standard files are changed.
- Validation: 96 Windows tests passed, 1 POSIX-only skip. Includes normalization for both ID formats, exact segment preservation, invalid IDs, browser creation without a separate code, search/edit, duplicate-project rejection and migration/history preservation.

- Local rollout verified: full bundle and migration backup created before upgrade; current schema is `0008_document_id`. All prior rows/columns in 26 application tables matched the pre-upgrade snapshot. Inventory reconciliation is clean. Restarted local app and verified the new DOCUMENT_ID form at http://192.168.0.100:5000/designs. Pi unchanged.

### 2026-11-23: complete transformer classification and properties

- Added missing 0706 CC/SS guidelines and property template to the tracked description JSONs. 749020111A is classified as 07/06/02/01 (Pulse / LAN / Ethernet, SMT). Includes Inductance, Turns Ratio - Primary:Secondary, Transformer Type and the shared core fields. Part-specific values are not family defaults.
- Verified the template/classification API and property save/edit/detail round-trip in an isolated database. Restarted the local app and confirmed the live definitions at http://192.168.0.100:5000/. No database migration is required for this JSON-only update. Details and datasheet reference: [transformer-classification.md](transformer-classification.md).
