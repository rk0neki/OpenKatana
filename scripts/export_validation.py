"""Export a local JSON receipt with portable paths; unknown personal paths fail closed."""
import argparse
import json
from pathlib import Path
import re


def portable(value, roots):
    if isinstance(value, dict): return {k: portable(v, roots) for k, v in value.items()}
    if isinstance(value, list): return [portable(v, roots) for v in value]
    if not isinstance(value, str): return value
    text = value
    for root in sorted(roots, key=len, reverse=True):
        for spelling in {root.rstrip('/\\'), root.rstrip('/\\').replace('\\', '/')}:
            text = text.replace(spelling + '\\', '').replace(spelling + '/', '')
            if text == spelling: text = '.'
    if re.search(r'[A-Za-z]:[\\/]+Users[\\/]+|/(?:Users|home)/[^/\s]+/', text):
        raise ValueError('Unmapped personal path in validation data; supply its --root')
    return text.replace('\\', '/') if '\\' in text and '/' not in text else text


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--root', action='append', required=True)
    args = p.parse_args()
    data = portable(json.loads(args.source.read_text(encoding='utf8')), args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf8')


if __name__ == '__main__': main()
