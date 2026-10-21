"""Fonts shipped with OpenKatana under the SIL Open Font License 1.1 (openkatana/fonts).

manifest.json records each font's family/style, copyright, licence file, sha256 and upstream source; it is built by
scripts/bundle_fonts.py. The OFL lets the fonts travel with software as long as each keeps its licence and copyright
notice, so importing a bundled font into a project copies its licence file beside it.
"""
import json
import shutil
from pathlib import Path

FOLDER = Path(__file__).resolve().parent / 'fonts'


def manifest():
    path = FOLDER / 'manifest.json'
    return {f['file']: f for f in json.loads(path.read_text(encoding='utf-8'))['fonts']} if path.is_file() else {}


def entry(path):
    """Manifest row for a bundled font file (None for any other file)."""
    path = Path(path).resolve()
    return manifest().get(path.name) if path.parent == FOLDER else None


def row_extras(row):
    return {'bundled': True, 'license': row['license'], 'license_file': str(FOLDER / row['license_file']),
            'copyright': row['copyright'], 'variable_axes': row['axes']}


def copy_license(source, target):
    """Put a bundled font's licence beside its project copy; returns the asset's licence record or None."""
    row = entry(source)
    if row is None:
        return None
    lic = target.with_name(target.stem + '-OFL.txt')
    shutil.copyfile(FOLDER / row['license_file'], lic)
    return {'id': row['license'], 'file': lic.name, 'copyright': row['copyright'], 'source': row['source'], 'bundled_file': row['file']}
