"""Archive a fixed Git commit without changing any CAD source file."""
import io
import json
import re
import uuid
from pathlib import Path
import config
from db import get_session
from db.models import DesignRelease, DesignArtifact
from services.library_catalog import git, validate_repository_url
from services.inventory_service import lock_inventory
from services.jobs import assert_lease
from services.design_service import add_artifact


def import_release(release_id, revision, *, lease=None):
    revision = str(revision).strip()
    if not revision or revision.startswith("-") or len(revision) > 200 or not re.fullmatch(r"[A-Za-z0-9_./-]+", revision):
        raise ValueError("Enter a branch, tag or full commit hash")
    with get_session() as db:
        release = db.get(DesignRelease, release_id)
        if not release or release.status != "draft":
            raise ValueError("Choose a draft release")
        url = validate_repository_url(release.board.project.repository_url)
        project_id = release.board.project_id
    repo = config.LIBRARY_CACHE_DIR / f"design-{project_id}"
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / "HEAD").exists():
        git(repo, "init", "--bare")
    snapshot_ref = "refs/partsdb/" + uuid.uuid4().hex
    git(repo, "-c", "protocol.file.allow=never", "fetch", "--depth=1", "--no-tags", url, revision + ":" + snapshot_ref, timeout=120)
    commit = git(repo, "rev-parse", "--verify", snapshot_ref + "^{commit}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        raise ValueError("Git returned an invalid commit")
    tree = git(repo, "ls-tree", "-r", "-l", "-z", commit)
    total, members, unresolved = 0, 0, []
    for record in tree.split(b"\0"):
        if not record:
            continue
        info, path = record.split(b"\t", 1)
        mode, kind, oid, size = info.decode().split()
        name = path.decode("utf-8")
        members += 1
        if kind == "commit":
            unresolved.append("Submodule content not included: " + name)
            continue
        if mode == "120000":
            raise ValueError("Repository contains symbolic links; upload a resolved project ZIP instead")
        size = int(size)
        total += size
        if total > config.ARTIFACT_MAX_BYTES or members > 5000:
            raise ValueError("Repository snapshot exceeds archive limits")
        if size < 2048 and git(repo, "cat-file", "blob", oid).startswith(b"version https://git-lfs.github.com/spec/v1"):
            unresolved.append("Git LFS object not included (pointer only): " + name)
    raw = git(repo, "archive", "--format=zip", commit, timeout=120)
    provenance = f"Git source snapshot {url} at {commit}"
    with get_session() as db:
        lock_inventory(db)
        assert_lease(db, lease)
        release = db.get(DesignRelease, release_id, populate_existing=True)
        if release.status != "draft":
            raise ValueError("Release was published while the import was running")
        existing = db.query(DesignArtifact).filter_by(release_id=release_id, role="source_snapshot", provenance=provenance).first()
        if existing:
            return {"artifact_id": existing.id, "commit": commit, "replayed": True}
        artifact = add_artifact(db, io.BytesIO(raw), f"project-{commit[:12]}.zip", "source_snapshot", release_id=release_id, provenance=provenance)
        release.source_commit = commit
        notes = "Git snapshot retains tracked bytes; external library dependencies must be archived separately."
        if unresolved:
            notes += "\nUNRESOLVED:\n" + "\n".join(unresolved)
        release.dependency_notes = (release.dependency_notes + "\n" + notes).strip()
        db.commit()
        return {"artifact_id": artifact.id, "commit": commit, "unresolved_dependencies": unresolved}
