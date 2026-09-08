"""Local storage snapshots. Backups contain private data and pairing keys."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def create_backup(storage, destination):
    storage, destination = Path(storage).resolve(), Path(destination).resolve()
    if not storage.is_dir():
        raise ValueError('Storage directory does not exist.')
    if destination == storage or storage in destination.parents:
        raise ValueError('Backups must be outside the storage directory.')
    destination.mkdir(parents=True, exist_ok=True)
    name = 'LinguaFusion-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8] + '.zip'
    final = destination / name
    partial = destination / (name + '.partial')
    try:
        with tempfile.TemporaryDirectory(prefix='.staging-', dir=destination) as staging:
            staging = Path(staging)
            manifest = {'format': 1, 'created_utc': datetime.now(timezone.utc).isoformat(), 'files': {}}
            for source in sorted(storage.rglob('*')):
                if source.is_symlink() or (hasattr(source, 'is_junction') and source.is_junction()):
                    raise ValueError('Storage links are not supported.')
                if not source.is_file() or source.name.endswith(('-wal', '-shm', '-journal')):
                    continue
                if storage not in source.resolve().parents:
                    raise ValueError('Storage file resolves outside the storage directory.')
                relative = source.relative_to(storage)
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.suffix.lower() in {'.db', '.sqlite', '.sqlite3'}:
                    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
                        with closing(sqlite3.connect(target)) as snapshot:
                            original.backup(snapshot)
                            if snapshot.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                                raise ValueError('Database snapshot failed integrity checking.')
                else:
                    shutil.copy2(source, target)
                manifest['files'][relative.as_posix()] = {'sha256': digest(target), 'size': target.stat().st_size}
            with zipfile.ZipFile(partial, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
                for relative in manifest['files']:
                    archive.write(staging / relative, relative)
                archive.writestr('backup-manifest.json', json.dumps(manifest, indent=2))
        verify_backup(partial)
        partial.rename(final)
        return final
    finally:
        partial.unlink(missing_ok=True)


def verify_backup(path, max_bytes=2 * 1024**3):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 100000:
            raise ValueError('Invalid archive entries.')
        if sum(info.file_size for info in archive.infolist()) > max_bytes:
            raise ValueError('Backup exceeds the recovery size limit.')
        if archive.getinfo('backup-manifest.json').file_size > 16 * 1024**2:
            raise ValueError('Backup manifest is too large.')
        manifest = json.loads(archive.read('backup-manifest.json'))
        if manifest.get('format') != 1 or set(names) != set(manifest['files']) | {'backup-manifest.json'}:
            raise ValueError('Backup manifest does not match its files.')
        for name, expected in manifest['files'].items():
            relative = PurePosixPath(name)
            reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
            if not name or name != relative.as_posix() or relative.is_absolute() or any(p in {'..', '.'} or ':' in p or '\\' in p or p.endswith((' ', '.')) or p.split('.')[0].upper() in reserved for p in relative.parts):
                raise ValueError('Unsafe backup path.')
            info = archive.getinfo(name)
            if info.file_size != expected['size']:
                raise ValueError('Backup size mismatch.')
            actual = hashlib.sha256()
            with archive.open(name) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    actual.update(chunk)
            if actual.hexdigest() != expected['sha256']:
                raise ValueError('Backup checksum mismatch.')
        return manifest


def restore_backup(archive_path, destination):
    manifest = verify_backup(archive_path)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive_path) as archive:
        for name in manifest['files']:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['create', 'verify', 'restore'])
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    if args.operation == 'create':
        print(create_backup(ROOT / 'backend' / 'storage', args.destination or ROOT / 'backups'))
    elif args.operation == 'verify' and args.archive:
        result = verify_backup(args.archive)
        print(f"Verified {len(result['files'])} files.")
    elif args.operation == 'restore' and args.archive and args.destination:
        print(restore_backup(args.archive, args.destination))
    else:
        parser.error('verify needs --archive; restore needs --archive and a new --destination.')
