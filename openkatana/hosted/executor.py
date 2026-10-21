"""Disposable container entry point. No host secrets or writable host mounts."""
import json
from pathlib import Path
import sys
import time
from .dispatch import execute
from .files import pack, unpack


def main():
    request = json.loads(Path('/input/request.json').read_text())
    if len(sys.argv) > 1 and sys.argv[1] == 'pack':
        pack(Path('/workspace'), sys.stdout.buffer, request['limit'])
        return
    try:
        with Path('/input/workspace.tar').open('rb') as f:
            unpack(f, Path('/workspace'), request['limit'])
        result = execute(Path('/workspace'), request['tool'], request['arguments'])
        value = {'ok': True, **result}
    except Exception as e:
        value = {'ok': False, 'error': f'{type(e).__name__}: {e}'}
    temp = Path('/tmp/tool-result.pending')
    temp.write_text(json.dumps(value, allow_nan=False))
    temp.replace('/tmp/tool-result.json')
    # Keep tmpfs alive while the controller retrieves a bounded snapshot.
    while True:
        time.sleep(30)


if __name__ == '__main__':
    main()
