"""Explicit maintainer download of two OFL fonts from a pinned Google Fonts commit.
Never called by setup or rendering. Requires fontTools only for metadata auditing.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen
from fontTools.ttLib import TTFont

REVISION = '47d54ca1ebb14fd864695f1d39dc734f39017c33'
FILES = [('notosansarabic', 'NotoSansArabic[wdth,wght].ttf'),
         ('notosansdevanagari', 'NotoSansDevanagari[wdth,wght].ttf')]
ROOT = Path(__file__).resolve().parents[1] / 'openkatana/fonts'


def main():
    manifest = json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    for folder, filename in FILES:
        base = f'https://raw.githubusercontent.com/google/fonts/{REVISION}/ofl/{folder}/'
        url = base + quote(filename); license_url = base + 'OFL.txt'
        with urlopen(url, timeout=60) as r: font_bytes = r.read()
        with urlopen(license_url, timeout=60) as r: license_bytes = r.read()
        if b'SIL OPEN FONT LICENSE Version 1.1' not in license_bytes: raise RuntimeError('Missing OFL license')
        target = ROOT / filename; target.write_bytes(font_bytes)
        license_rel = f'licenses/{folder}-OFL.txt'; (ROOT/license_rel).write_bytes(license_bytes)
        with TTFont(target) as font:
            get = lambda n: font['name'].getDebugName(n)
            row = {'file': filename, 'family': get(16) or get(1), 'style': get(17) or get(2),
                   'copyright': get(0), 'version': get(5), 'designer': get(9), 'license_url': get(14),
                   'axes': [a.axisTag for a in font['fvar'].axes] if 'fvar' in font else [],
                   'sha256': hashlib.sha256(font_bytes).hexdigest(), 'license': 'OFL-1.1',
                   'license_file': license_rel, 'license_sha256': hashlib.sha256(license_bytes).hexdigest(),
                   'source': url, 'license_source': license_url, 'upstream_revision': REVISION}
        manifest['fonts'] = [f for f in manifest['fonts'] if f['file'] != filename] + [row]
        print(json.dumps(row, ensure_ascii=True))
    (ROOT/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__': main()
