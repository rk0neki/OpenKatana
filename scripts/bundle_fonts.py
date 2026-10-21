"""Build openkatana/fonts: SIL Open Font License fonts copied with their licence texts and a provenance manifest.

usage: python scripts/bundle_fonts.py SOURCE_DIR [SOURCE_DIR ...] [--skip FILE ...]

Only fonts whose own licence file is present beside them and is the SIL OFL 1.1 text are taken; each font's
copyright, licence URL, designer and version come from its own name table. A sources.json beside the fonts (file,
source, sha256) is checked and recorded as the upstream source. Nothing is downloaded.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from fontTools.ttLib import TTFont

OUT = Path(__file__).resolve().parents[1] / 'openkatana' / 'fonts'
OFL = 'SIL OPEN FONT LICENSE Version 1.1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def names(path):
    font = TTFont(path, lazy=True)
    table = font['name']
    get = lambda i: (table.getDebugName(i) or '').strip() or None
    axes = [a.axisTag for a in font['fvar'].axes] if 'fvar' in font else []
    return {'family': get(16) or get(1), 'style': get(17) or get(2), 'copyright': get(0), 'version': get(5),
            'designer': get(9), 'license_url': get(14), 'axes': axes}


def licence_for(font):
    """Licence text beside the font: <key>-OFL.txt (key = lowercase family file stem) or <prefix>_OFL.txt."""
    folder = font.parent
    prefix = font.name.split('_', 1)[0] if '_' in font.name else None
    stem = re.sub(r'[\[\-].*$', '', font.stem).lower()
    for candidate in ([folder / f'{prefix}_OFL.txt'] if prefix else []) + [folder / f'{stem}-OFL.txt']:
        if candidate.is_file() and OFL.upper() in candidate.read_text(encoding='utf-8', errors='replace').upper():
            return candidate
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('sources', nargs='+', type=Path)
    ap.add_argument('--skip', action='append', default=[], help='font file name to leave out (e.g. a duplicate)')
    args = ap.parse_args(argv)
    (OUT / 'licenses').mkdir(parents=True, exist_ok=True)
    manifest = {'license': 'SIL Open Font License 1.1 (each font: licenses/<file>)', 'fonts': []}
    seen = {}
    for source in args.sources:
        upstream = {}
        if (source / 'sources.json').is_file():
            upstream = {f['file']: f for f in json.loads((source / 'sources.json').read_text(encoding='utf-8'))['files']}
        for font in sorted(source.glob('*.ttf')):
            if font.name in args.skip:
                continue
            lic = licence_for(font)
            if lic is None:
                print(f'skip {font.name}: no SIL OFL 1.1 text beside it')
                continue
            digest = sha(font)
            if font.name in upstream and upstream[font.name]['sha256'] != digest:
                raise SystemExit(f'{font.name}: sha256 differs from its sources.json record')
            if digest in seen:
                print(f'skip {font.name}: same file as {seen[digest]}')
                continue
            seen[digest] = font.name
            meta = names(font)
            target = OUT / font.name
            shutil.copyfile(font, target)
            lic_name = f'{font.stem}-OFL.txt'
            shutil.copyfile(lic, OUT / 'licenses' / lic_name)
            entry = {'file': font.name, **meta, 'sha256': digest, 'license': 'OFL-1.1', 'license_file': f'licenses/{lic_name}',
                     'license_sha256': sha(lic)}
            if font.name in upstream:
                entry['source'] = upstream[font.name]['source']
                lic_up = next((f for f in upstream.values() if f['file'] == lic.name), None)
                if lic_up:
                    entry['license_source'] = lic_up['source']
            else:
                entry['source'] = 'local copy distributed with its OFL text; identity from the font name table'
            manifest['fonts'].append(entry)
            print(f'{font.name}: {meta["family"]} {meta["style"]}')
    manifest['fonts'].sort(key=lambda f: (f['family'] or '', f['style'] or ''))
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(len(manifest['fonts']), 'fonts ->', OUT)


if __name__ == '__main__':
    main()
