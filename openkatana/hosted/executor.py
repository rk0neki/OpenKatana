"""Disposable container entry point. No host secrets or writable host mounts."""
import json
import hashlib
from pathlib import Path
import sys
import time
from .dispatch import execute
from .files import pack, unpack


def main():
    request = json.loads(Path('/input/request.json').read_text())
    if len(sys.argv) > 1 and sys.argv[1] == 'pack':
        digest = hashlib.sha256()
        class Output:
            def write(self, data):
                written = sys.stdout.buffer.write(data)
                digest.update(data[:written])
                return written
        pack(Path('/workspace'), Output(), request['limit'])
        sys.stdout.buffer.flush()
        Path('/tmp/export.sha256').write_text(digest.hexdigest())
        return
    stage = 'import workspace'
    try:
        with Path('/input/workspace.tar').open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != request['workspace_sha256']:
                raise ValueError('Workspace upload checksum mismatch')
            f.seek(0)
            unpack(f, Path('/workspace'), request['limit'])
        stage = 'execute tool'
        result = execute(Path('/workspace'), request['tool'], request['arguments'])
        value = {'ok': True, **result}
    except Exception as e:
        value = {'ok': False, 'error': f'{stage}: {type(e).__name__}: {e}'}
    temp = Path('/tmp/tool-result.pending')
    temp.write_text(json.dumps(value, allow_nan=False))
    temp.replace('/tmp/tool-result.json')
    # Keep tmpfs alive while the controller retrieves a bounded snapshot.
    while True:
        time.sleep(30)


if __name__ == '__main__':
    main()
