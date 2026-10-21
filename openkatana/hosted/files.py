"""File boundaries for uploads and container snapshots; archives never carry links."""
import io
from pathlib import Path, PurePosixPath
import tarfile


def safe_path(root, name):
    if not isinstance(name, str) or '\\' in name or '\x00' in name or ':' in name:
        raise ValueError('Use a workspace-relative POSIX path')
    rel = PurePosixPath(name)
    if rel.is_absolute() or not rel.parts or any(p in ('..', '.') for p in rel.parts):
        raise ValueError('Path must stay in this workspace')
    root = Path(root).resolve()
    target = root.joinpath(*rel.parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError('Path escaped the workspace')
    current = target
    while current != root:
        if current.is_symlink():
            raise ValueError('Symbolic links are not workspace files')
        current = current.parent
    return target


def inventory(root, limit):
    total = 0; rows = []
    root = Path(root)
    if not root.exists():
        return rows
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError('Workspace contains a symbolic link')
        if p.is_file():
            size = p.stat().st_size; total += size
            if total > limit or len(rows) >= 100000:
                raise ValueError('Workspace storage quota exceeded')
            rows.append((p.relative_to(root).as_posix(), size))
    return rows


def pack(root, output, limit):
    rows = inventory(root, limit)
    class CompleteWrites:
        # tarfile's stream writer assumes write() accepts the whole block.
        # Unbuffered container stdout may legitimately make a short pipe write.
        def write(self, data):
            remaining = memoryview(data)
            total = len(remaining)
            while remaining:
                written = output.write(remaining)
                if not written or written < 0 or written > len(remaining):
                    raise OSError('Snapshot destination stopped accepting data')
                remaining = remaining[written:]
            return total
    with tarfile.open(fileobj=CompleteWrites(), mode='w|') as archive:
        for name, _ in rows:
            archive.add(safe_path(root, name), arcname=name, recursive=False)


def unpack(source, root, limit):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    total = 0; count = 0; seen = set()
    with tarfile.open(fileobj=source, mode='r|') as archive:
        for item in archive:
            target = safe_path(root, item.name)
            if not item.isfile() or item.name in seen:
                raise ValueError('Snapshot may contain only unique regular files')
            seen.add(item.name); count += 1; total += item.size
            if item.size < 0 or total > limit or count > 100000:
                raise ValueError('Snapshot exceeds the storage quota')
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.extractfile(item) as src, target.open('xb') as dst:
                    while chunk := src.read(1024 * 1024):
                        dst.write(chunk)
            except tarfile.ReadError as exc:
                raise ValueError(f'Incomplete snapshot member {item.name!r} ({item.size} bytes)') from exc
    return total
