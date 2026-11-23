"""Portable data bundles: consistent SQLite snapshot plus immutable archive bytes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import uuid
import zipfile
import config
from db.migrations import backup_sqlite


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def create_bundle(engine):
    snapshot = backup_sqlite(engine, config.BACKUPS_DIR)
    if not snapshot:
        raise ValueError("Backup requires a file-backed SQLite database")
    snapshot = Path(snapshot)
    name = datetime.now(timezone.utc).strftime('partsdb-%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8] + '.zip'
    output = config.BACKUPS_DIR / name
    files = {'database.sqlite': snapshot}
    with sqlite3.connect(snapshot) as database:
        if database.execute('pragma integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Snapshot integrity check failed')
        tables = {r[0] for r in database.execute("select name from sqlite_master where type='table'")}
        if 'design_artifacts' in tables:
            for digest, size in database.execute('select distinct sha256,size from design_artifacts'):
                from services.design_service import blob_path
                path = blob_path(digest)
                if not path.is_file() or path.stat().st_size != size or sha256(path) != digest:
                    raise ValueError('Referenced archive file is missing or damaged; backup was not completed')
                files['artifacts/' + digest[:2] + '/' + digest + '.blob'] = path
    for label, directory in [('part_images', config.PART_IMAGES_DIR), ('datasheets', config.DATASHEETS_DIR), ('kicad_libs', config.KICAD_LIBS_DIR)]:
        root = directory.resolve()
        if root.is_dir():
            for path in root.rglob('*'):
                if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root):
                    files['assets/' + label + '/' + path.relative_to(root).as_posix()] = path
    manifest = {'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(), 'files': {}}
    try:
        with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for name, path in files.items():
                digest, size = hashlib.sha256(), 0
                with path.open('rb') as source, archive.open(name, 'w', force_zip64=True) as target:
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                manifest['files'][name] = {'sha256':digest.hexdigest(),'size':size}
            archive.writestr('manifest.json', json.dumps(manifest, sort_keys=True, indent=2))
        output.chmod(0o600)
        return output
    except Exception:
        output.unlink(missing_ok=True)
        raise


def restore_bundle(archive_path, destination):
    """Restore only into a new/empty folder, never over an active database."""
    destination = Path(destination).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Restore destination must be a new or empty directory')
    with zipfile.ZipFile(archive_path) as archive:
        names = set()
        total = 0
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in info.filename or ':' in info.filename
                or info.filename in names or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1):
                raise ValueError('Unsafe backup archive entry')
            if info.filename not in {'database.sqlite','manifest.json'} and not info.filename.startswith(('artifacts/','assets/')):
                raise ValueError('Unexpected backup archive entry')
            names.add(info.filename)
            total += info.file_size
        if total > 20 * 1024**3 or len(names) > 100000:
            raise ValueError('Backup exceeds restore limits')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 1 or set(manifest['files']) != names - {'manifest.json'}:
            raise ValueError('Backup manifest does not match its contents')
        # Verify every byte before creating a restore destination.
        for name, metadata in manifest['files'].items():
            digest, size = hashlib.sha256(), 0
            with archive.open(name) as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
            if digest.hexdigest() != metadata['sha256'] or size != metadata['size']:
                raise ValueError('Backup checksum mismatch: ' + name)
        destination.mkdir(parents=True, exist_ok=True)
        for name in manifest['files']:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open('xb') as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
    with sqlite3.connect(destination/'database.sqlite') as database:
        if database.execute('pragma integrity_check').fetchone()[0] != 'ok' or database.execute('pragma foreign_key_check').fetchall():
            raise ValueError('Restored database integrity checks failed; do not activate this restore')
    return {'directory':str(destination), 'files':len(manifest['files']), 'database':'database.sqlite'}
