"""Explicitly re-source bundled OFL fonts from a pinned Google Fonts revision.

Run with --download. No models are downloaded. Filenames remain stable for projects.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

from fontTools.ttLib import TTFont

PIN = '5e8a3ba899557829a76cfdac30fa512bda91d7ca'
ROOT = Path(__file__).resolve().parents[1] / 'openkatana/fonts'


def fetch(path):
    url = 'https://raw.githubusercontent.com/google/fonts/' + PIN + '/' + urllib.parse.quote(path, safe='/')
    with urllib.request.urlopen(url, timeout=60) as response:
        return url, response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', required=True)
    parser.parse_args()
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf8'))
    staged = []
    for row in manifest['fonts']:
        if not row['source'].startswith('local copy'):
            continue
        family = re.sub('[^a-z0-9]', '', row['family'].lower())
        _, metadata = fetch('ofl/' + family + '/METADATA.pb')
        files = re.findall(r'filename:\s*"([^"]+\.ttf)"', metadata.decode())
        original = row['file'].split('_', 1)[-1]
        candidates = [x for x in files if ('Italic' in x) == ('Italic' in original)]
        filename = original if original in files else candidates[0] if len(candidates) == 1 else None
        if not filename:
            raise ValueError('Ambiguous upstream file for ' + row['file'] + ': ' + repr(files))
        url, data = fetch('ofl/' + family + '/' + filename)
        license_url, license_data = fetch('ofl/' + family + '/OFL.txt')
        if b'SIL OPEN FONT LICENSE Version 1.1' not in license_data:
            raise ValueError('Missing OFL text for ' + family)
        with TTFont(io.BytesIO(data)) as font:
            get = lambda n: (font['name'].getDebugName(n) or '').strip() or None
            metadata = {'family': get(16) or get(1), 'style': get(17) or get(2),
                'copyright': get(0), 'version': get(5), 'designer': get(9), 'license_url': get(14),
                'axes': [a.axisTag for a in font['fvar'].axes] if 'fvar' in font else []}
        staged.append((row, data, license_data, {**metadata, 'source': url, 'license_source': license_url,
            'sha256': hashlib.sha256(data).hexdigest(), 'license_sha256': hashlib.sha256(license_data).hexdigest()}))
    # Validate every download before changing the installed set.
    for row, data, license_data, metadata in staged:
        changed = row['sha256'] != metadata['sha256']
        (ROOT / row['file']).write_bytes(data)
        (ROOT / row['license_file']).write_bytes(license_data)
        row.update(metadata)
        print(row['file'], 'updated upstream bytes' if changed else 'identical bytes; pinned source verified')
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n', encoding='utf8')


if __name__ == '__main__':
    main()
