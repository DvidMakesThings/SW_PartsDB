"""Read-only Git catalogue indexing and explicit part-identity review.

Never writes KiCad files or the user's library checkout. GitHub fetches use a
separate bare cache; metadata is read from immutable Git blobs at one commit.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
import config
from db import get_session
from db.models import LibrarySource, LibraryEntry, LibrarySyncRun, LibraryReviewEvent, Part
from services.parts_service import PartsService
from services.inventory_service import lock_inventory
from schema.loader import valid_ttff
from schema.numbering import validate_segments, parse_dmtuid

DEFAULT_URL = "https://github.com/DvidMakesThings/LIB_KiCad-Libraries.git"
ALIASES = {
    "manufacturer": ("manufacturer", "mfr", "manuf", "manufacturername"),
    "mpn": ("mpn", "manufacturerpartnumber", "manufacturerpart", "partnumber"),
    "dmtuid": ("dmtuid", "dmtid"), "value": ("value",),
    "footprint": ("footprint", "kicadfootprint"),
    "datasheet": ("datasheet", "datasheeturl"), "description": ("description", "kidescription"),
    "lcsc": ("lcscpart", "lcsc", "lcscpartnumber", "lcscnumber", "kicadlibref"),
    "digikey": ("digikeypartnumber", "digikeypart", "digikey"),
    "mouser": ("mouserpartnumber", "mouserpart", "mouser"),
}
MANUFACTURER_ALIASES = {"ti": "texas instruments", "texas instruments incorporated": "texas instruments",
                        "st": "stmicroelectronics", "st microelectronics": "stmicroelectronics"}
IDENTIFIERS = ("dmtuid", "manufacturer", "mpn", "lcsc", "digikey", "mouser", "footprint")


def normalized(value):
    return str(value or "").strip().casefold()


def normalize_properties(properties):
    keyed = {}
    for key, value in properties.items():
        k = re.sub(r"[^a-z0-9]", "", key.casefold())
        keyed.setdefault(k, []).append(str(value or "").strip())
    result, conflicts = {}, []
    for field, names in ALIASES.items():
        values = {v for name in names for v in keyed.get(name, []) if v}
        norm = {normalized(v) for v in values}
        if field == "manufacturer":
            norm = {MANUFACTURER_ALIASES.get(v, v) for v in norm}
        if len(norm) > 1:
            conflicts.append(field)
        result[field] = sorted(norm)[0] if norm else ""
        result[field + "_display"] = sorted(values)[0] if values else ""
    result["alias_conflicts"] = conflicts
    return result


def parse_symbols(raw):
    """Bounded structural S-expression parser, reading only library properties.

    Ignores graphical children, resolves inheritance within the file, and counts
    only top-level symbols (not units). No source serialization or editing.
    """
    source = raw.decode("utf-8-sig")
    stack, roots, index, tokens = [], [], 0, 0
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        tokens += 1
        if tokens > 4000000:
            raise ValueError("Symbol library exceeds parser token limit")
        if char == "(":
            node = []
            (stack[-1] if stack else roots).append(node)
            stack.append(node)
            if len(stack) > 100:
                raise ValueError("Symbol nesting exceeds limit")
            index += 1
        elif char == ")":
            if not stack:
                raise ValueError("Unbalanced library expression")
            stack.pop()
            index += 1
        else:
            if not stack:
                raise ValueError("Unexpected text outside library expression")
            if char == '"':
                index += 1
                value = []
                while index < len(source) and source[index] != '"':
                    if source[index] == "\\":
                        index += 1
                        if index >= len(source):
                            raise ValueError("Unterminated escape")
                        value.append({"n": "\n", "r": "\r", "t": "\t"}.get(source[index], source[index]))
                    else:
                        value.append(source[index])
                    index += 1
                if index >= len(source):
                    raise ValueError("Unterminated property string")
                index += 1
                value = "".join(value)
            else:
                end = index
                while index < len(source) and not source[index].isspace() and source[index] not in '()':
                    index += 1
                value = source[end:index]
            stack[-1].append(value)
    if stack or len(roots) != 1 or not roots[0] or roots[0][0] != "kicad_symbol_lib":
        raise ValueError("Invalid KiCad symbol library")
    definitions = {}
    for node in roots[0][1:]:
        if not isinstance(node, list) or not node or node[0] != "symbol":
            continue
        if len(node) < 2 or not isinstance(node[1], str) or node[1] in definitions:
            raise ValueError("Missing or duplicate top-level symbol name")
        properties, parent = {}, None
        for item in node[2:]:
            if isinstance(item, list) and item:
                if item[0] == "property":
                    if len(item) < 3 or not all(isinstance(v, str) for v in item[1:3]):
                        raise ValueError("Invalid symbol property")
                    if item[1] in properties:
                        raise ValueError("Duplicate symbol property")
                    properties[item[1]] = item[2]
                elif item[0] == "extends":
                    if len(item) != 2 or not isinstance(item[1], str):
                        raise ValueError("Invalid inheritance declaration")
                    parent = item[1]
        definitions[node[1]] = (parent, properties)
    resolved = {}
    def resolve(name, trail=()):
        if name in trail or len(trail) > 50:
            raise ValueError("Cyclic or excessive symbol inheritance")
        if name not in definitions:
            raise ValueError("Inherited symbol definition is missing")
        if name not in resolved:
            parent, own = definitions[name]
            resolved[name] = {**(resolve(parent, (*trail, name)) if parent else {}), **own}
        return resolved[name]
    return [(name, resolve(name)) for name in definitions]


def git(repo, *args, timeout=60):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    env.setdefault("GCM_INTERACTIVE", "never")
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Git is unavailable or the operation timed out. The last catalogue is retained.") from None
    if result.returncode:
        # Git errors can contain credential-bearing URLs; never reflect stderr.
        raise ValueError("Git could not read/fetch the repository. Check the configured path, access and network. The last catalogue is retained.")
    return result.stdout


def validate_repository_url(url):
    if re.fullmatch(r"git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", url.strip()):
        return url.strip()
    parsed = urlsplit(url.strip())
    if (parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password
            or parsed.port or parsed.query or parsed.fragment or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?", parsed.path)):
        raise ValueError("Use an HTTPS github.com owner/repository URL or git@github.com:owner/repository.git, without embedded credentials")
    return url.strip().rstrip("/")


def repository_identity(url):
    value = validate_repository_url(url)
    path = value.split(":", 1)[1] if value.startswith("git@github.com:") else urlsplit(value).path.lstrip("/")
    return path.removesuffix(".git").casefold()


def read_snapshot(repo, revision="HEAD"):
    commit = git(repo, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        raise ValueError("Git returned an invalid commit identifier")
    tree = git(repo, "ls-tree", "-r", "-z", commit)
    entries, errors, total_bytes = [], [], 0
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        path = raw_path.decode("utf-8")
        if not path.endswith(".kicad_sym"):
            continue
        mode, kind, oid = metadata.decode().split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            errors.append({"path": path, "error": "Linked library files are not indexed"})
            continue
        try:
            size = int(git(repo, "cat-file", "-s", oid))
            total_bytes += size
            if total_bytes > 256 * 1024 * 1024:
                raise RuntimeError("Total symbol library size exceeds 256 MiB")
            if size > 30 * 1024 * 1024:
                raise ValueError("Library file exceeds 30 MiB parser limit")
            raw = git(repo, "cat-file", "blob", oid)
            symbols = parse_symbols(raw)
            for symbol, properties in symbols:
                payload = json.dumps(properties, sort_keys=True, ensure_ascii=False)
                entries.append({"path": path, "symbol": symbol, "properties_json": payload,
                    "normalized_json": json.dumps(normalize_properties(properties), sort_keys=True),
                    "content_hash": hashlib.sha256(payload.encode()).hexdigest(), "seen_commit": commit})
            if len(entries) > 100000:
                raise RuntimeError("Catalogue exceeds 100,000 entries")
        except (ValueError, UnicodeError) as error:
            errors.append({"path": path, "error": str(error)})
    if not entries:
        raise ValueError("No readable KiCad symbols were found; previous catalogue retained")
    return commit, entries, errors


def sync_library(source_id, fetch=False, *, lease=None):
    # Commit job state before I/O; no long-lived database write transaction during Git fetch/parse.
    with get_session() as db:
        source = db.get(LibrarySource, source_id)
        if not source:
            raise ValueError("Configure the source first")
        result = db.execute(update(LibrarySource).where(LibrarySource.id == source.id, LibrarySource.state != "running")
            .values(state="running", last_attempt_at=datetime.now(timezone.utc), last_error=""))
        if result.rowcount != 1:
            raise ValueError("A sync is already running. Wait for it to finish.")
        url = source.repository_url
        run = LibrarySyncRun(source_id=source.id)
        db.add(run)
        db.flush()
        run_id = run.id
        db.commit()
    try:
        repo, revision = config.LIBRARY_REPO_DIR, "HEAD"
        if fetch:
            url = validate_repository_url(url)
            repo = config.LIBRARY_CACHE_DIR / str(source_id)
            repo.mkdir(parents=True, exist_ok=True)
            if not (repo / "HEAD").exists():
                git(repo, "init", "--bare")
            git(repo, "-c", "protocol.file.allow=never", "fetch", "--depth=1", "--no-tags", url, "HEAD", timeout=120)
            revision = "FETCH_HEAD"
        commit, entries, errors = read_snapshot(repo, revision)
        with get_session() as db:
            from services.jobs import assert_lease
            lock_inventory(db)
            assert_lease(db, lease)
            source = db.get(LibrarySource, source_id)
            existing = {(e.path, e.symbol): e for e in db.scalars(select(LibraryEntry).where(LibraryEntry.source_id == source_id))}
            seen = set()
            counts = Counter()
            for values in entries:
                key = values["path"], values["symbol"]
                seen.add(key)
                entry = existing.get(key)
                if entry is None:
                    entry = LibraryEntry(source_id=source_id, **values)
                    db.add(entry)
                    counts["new_entries"] += 1
                else:
                    counts["unchanged" if entry.content_hash == values["content_hash"] else "changed"] += 1
                    for k, v in values.items():
                        setattr(entry, k, v)
                    entry.missing = False
            failed_paths = {item["path"] for item in errors}
            for key, entry in existing.items():
                if key not in seen and entry.path not in failed_paths:
                    entry.missing = True
                    counts["missing"] += 1
            source.indexed_commit, source.last_success_at = commit, datetime.now(timezone.utc)
            source.state = "idle"
            source.last_error = f"{len(errors)} library files need review" if errors else ""
            report = {"counts": dict(counts), "symbols": len(entries), "errors": errors,
                      "mode": "GitHub fetch" if fetch else "Configured local clone"}
            run = db.get(LibrarySyncRun, run_id)
            run.status, run.commit_hash, run.report_json = "completed", commit, json.dumps(report)
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            return report
    except Exception as error:
        message = str(error) if isinstance(error, ValueError) else "Sync failed; the last committed catalogue remains available"
        with get_session() as db:
            from services.jobs import assert_lease
            lock_inventory(db)
            assert_lease(db, lease)
            source, run = db.get(LibrarySource, source_id), db.get(LibrarySyncRun, run_id)
            source.state, source.last_error = "failed", message
            run.status, run.report_json, run.finished_at = "failed", json.dumps({"error": message}), datetime.now(timezone.utc)
            db.commit()
        raise ValueError(message) from None


class Matcher:
    def __init__(self, db):
        self.parts = {p.dmtuid: p for p in db.scalars(select(Part).options(selectinload(Part.fields)))}
        self.normalized = {}
        for uid, part in self.parts.items():
            data = part.to_dict()
            extra = data.pop("extra", {})
            self.normalized[uid] = normalize_properties({**extra, **data})
        self.identities = {}
        for uid, properties in self.normalized.items():
            for identity in self.keys(properties):
                self.identities.setdefault(identity, set()).add(uid)

    @staticmethod
    def keys(properties):
        result = []
        if properties.get("mpn") and properties.get("manufacturer"):
            result.append(("mpn", properties["manufacturer"], properties["mpn"]))
        for supplier in ("lcsc", "digikey", "mouser"):
            if properties.get(supplier):
                result.append((supplier, properties[supplier]))
        return result

    @staticmethod
    def conflicts(source, target):
        return [key for key in IDENTIFIERS if source.get(key) and target.get(key) and source[key] != target[key]]

    def evaluate(self, entry):
        props = json.loads(entry.normalized_json)
        prior = json.loads(entry.reviewed_identity_json)
        base = {"candidates": [], "part_id": None}
        if entry.missing:
            return {**base, "state": "missing", "reason": "Symbol is absent from the indexed commit; existing links and stock are retained"}
        if entry.source.indexed_commit and entry.seen_commit != entry.source.indexed_commit:
            return {**base, "state": "parse_error", "reason": "This file failed in the latest index. Showing its last good metadata; review is blocked until parsing succeeds"}
        if props.get("alias_conflicts"):
            return {**base, "state": "conflict", "reason": "Conflicting property aliases: " + ", ".join(props["alias_conflicts"])}
        if entry.decision == "ignore" and entry.reviewed_hash == entry.content_hash:
            return {**base, "state": "ignored", "reason": entry.review_note or "Ignored by review"}
        if entry.part_id:
            changes = [k for k in IDENTIFIERS if prior.get(k) != props.get(k)]
            conflicts = self.conflicts(props, self.normalized[entry.part_id])
            if changes or conflicts:
                return {**base, "state": "conflict", "candidates": [entry.part_id],
                        "reason": "Reviewed identifiers changed or disagree: " + ", ".join(sorted(set(changes + conflicts)))}
            return {**base, "state": "linked", "part_id": entry.part_id, "reason": "Reviewed source binding"}
        sets = [self.identities[key] for key in self.keys(props) if key in self.identities]
        uid = props.get("dmtuid", "").upper()
        if uid:
            if not parse_dmtuid(uid):
                return {**base, "state": "conflict", "reason": "Invalid DMTUID in source"}
            if uid in self.parts:
                sets.insert(0, {uid})
        candidates = sorted(set().union(*sets)) if sets else []
        if len(candidates) > 1:
            return {**base, "state": "conflict", "candidates": candidates, "reason": "Strong identifiers point to multiple parts"}
        if candidates:
            candidate = candidates[0]
            conflicts = self.conflicts(props, self.normalized[candidate])
            if conflicts:
                return {**base, "state": "conflict", "candidates": candidates, "reason": "Identifiers disagree: " + ", ".join(conflicts)}
            return {**base, "state": "match", "part_id": candidate, "candidates": candidates, "reason": "Unique strong identifier match; ready to link"}
        if self.keys(props):
            return {**base, "state": "create", "reason": "Identified component; classification and confirmation required"}
        suggestions = [uid for uid, p in self.normalized.items() if props.get("value") and props.get("footprint")
                       and props["value"] == p.get("value") and props["footprint"] == p.get("footprint")]
        return {**base, "state": "unresolved", "candidates": suggestions[:20],
                "reason": "No strong orderable identity. Value/package suggestions require review; no automatic merge"}


def review_entry(db, entry_id, decision, expected_hash, part_id="", classification=None, note=""):
    lock_inventory(db)  # Serializes DMTUID allocation and duplicate checks with ordinary part creation.
    entry = db.get(LibraryEntry, entry_id, populate_existing=True)
    if not entry or entry.missing or entry.content_hash != expected_hash:
        raise ValueError("Catalogue entry changed or disappeared; reload the review")
    if entry.source.indexed_commit and entry.seen_commit != entry.source.indexed_commit:
        raise ValueError("The latest version could not be parsed; fix the source before reviewing this entry")
    matcher = Matcher(db)
    result = matcher.evaluate(entry)
    props = json.loads(entry.normalized_json)
    if decision == "ignore":
        uid = None
    elif decision == "unresolved":
        uid = None
    elif decision == "link":
        uid = part_id.strip().upper()
        if uid not in matcher.parts:
            raise ValueError("Select an existing DMTUID")
        conflicts = matcher.conflicts(props, matcher.normalized[uid])
        if conflicts or props.get("alias_conflicts"):
            raise ValueError("Strong identifiers conflict. Correct the source or part metadata before linking")
        if not note.strip() and (result["state"] != "match" or result["part_id"] != uid):
            raise ValueError("Explain the evidence for this manual identity link")
    elif decision == "create":
        if result["state"] != "create":
            raise ValueError("Resolve existing matches/conflicts or missing orderable identity before creating a part")
        classification = {k: str((classification or {}).get(k, "")).strip() for k in ("tt", "ff", "cc", "ss")}
        error = validate_segments(**classification)
        if error:
            raise ValueError(error)
        classification = {k: v.zfill(2) for k, v in classification.items()}
        if not valid_ttff(classification["tt"], classification["ff"]):
            raise ValueError("Choose a valid domain and family from the classification guide")
        part = PartsService.create(db, {**classification,
            **{field: props.get(field + "_display", "") for field in ("manufacturer", "mpn", "value", "description", "datasheet")},
            **{supplier: props[supplier + "_display"] for supplier in ("lcsc", "digikey", "mouser") if props.get(supplier)},
            "kicad_symbol": f"{Path(entry.path).stem}:{entry.symbol}", "kicad_libref": props.get("lcsc_display", ""),
            "kicad_footprint": props.get("footprint_display", ""),
            "notes": "Catalogue part created from a reviewed library entry; no stock recorded."})
        uid = part.dmtuid
    else:
        raise ValueError("Choose link, create, ignore or leave unresolved")
    entry.part_id, entry.decision = uid, "linked" if uid else decision
    # A supplied source DMTUID cannot silently be allocated a different identity.
    if decision == "create" and props.get("dmtuid") and props["dmtuid"].upper() != uid:
        raise ValueError("Source contains an unrecognized DMTUID. Reconcile that identifier before allocating a new part")
    entry.reviewed_hash, entry.reviewed_identity_json = entry.content_hash, entry.normalized_json
    entry.review_note, entry.reviewed_at = note.strip(), datetime.now(timezone.utc)
    db.add(LibraryReviewEvent(entry_id=entry.id, decision=decision, part_id=uid,
                             content_hash=entry.content_hash, note=note.strip()))
    db.flush()
    return entry
