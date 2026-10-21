"""Identity references (audit F-ID-001). `bind_reference` records named reference assets (a person, product or
character) with their hashes; `inspect_identity` builds a side-by-side sheet of the largest detected face (or the
centre when none is found) in the reference assets and in chosen frames of a candidate asset, and records the
editor's accept/reject decision. It is a visual comparison only: there is no biometric identity score. In strict review
mode a timeline that uses generated material (clips imported from a Comfy job, marked by comfy-origin.json) is refused
until that material was accepted against every bound identity reference."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .contracts import ContractError, local_path, number
from .render import digest, write_json

ROLES = ('identity', 'style', 'product', 'location')


def _path(root):
    return Path(root) / '.openkatana' / 'references.json'


def load(root):
    p = _path(root)
    return json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {'references': {}, 'reviews': {}}


def _save(root, data):
    _path(root).parent.mkdir(parents=True, exist_ok=True); write_json(_path(root), data)


def asset_frame(root, asset, f=0):
    if 'clip' not in asset:
        raise ContractError(f'asset {asset["id"]}: an imported image or video')
    clip = asset['clip']
    number(f, 'frame', 0, clip['n'] - 1, integer=True)
    return local_path(root, f'{clip["frames_dir"]}/{clip.get("pattern", "%05d.png") % f}')


def asset_key(root, asset):
    """Content key of an asset: its import hash, or the hash of a generated clip's provenance and first frame."""
    if asset.get('sha256'):
        return asset['sha256']
    clip = asset['clip']; h = hashlib.sha256()
    origin = local_path(root, clip['frames_dir']) / 'comfy-origin.json'
    if origin.is_file():
        h.update(digest(origin).encode())
    h.update(digest(asset_frame(root, asset, 0)).encode())
    return h.hexdigest()


def bind(root, name, assets, role='identity', subject_type='person', description=''):
    if not isinstance(name, str) or not name or len(name) > 64:
        raise ContractError('name: 1..64 characters')
    if role not in ROLES:
        raise ContractError(f'role: one of {", ".join(ROLES)}')
    if not assets:
        raise ContractError('asset_ids: at least one imported image or video')
    entries = [{'id': a['id'], 'sha256': asset_key(root, a)} for a in assets]
    record = {'name': name, 'role': role, 'subject_type': subject_type, 'description': description, 'assets': entries,
              'digest': hashlib.sha256(json.dumps([name, role, entries], sort_keys=True).encode()).hexdigest(),
              'at': datetime.now(timezone.utc).isoformat()}
    data = load(root); data['references'][name] = record; _save(root, data)
    return record


def largest_face(path):
    import cv2
    rgb = np.asarray(Image.open(path).convert('RGB')); g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    s = min(1.0, 640 / g.shape[1]); small = cv2.equalizeHist(cv2.resize(g, (int(g.shape[1] * s), int(g.shape[0] * s))) if s < 1 else g)
    found = []
    for name in ('haarcascade_frontalface_default.xml', 'haarcascade_frontalface_alt2.xml'):
        d = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / name))
        found += [[v / s for v in b] for b in d.detectMultiScale(small, 1.08, 5, minSize=(24, 24))]
    H, W = g.shape
    if not found:
        return None, rgb, (W, H)
    x, y, w, h = max(found, key=lambda b: b[2] * b[3])
    return [round(x), round(y), round(w), round(h)], rgb, (W, H)


def _crop(rgb, box, size):
    H, W = rgb.shape[:2]
    if box is None:   # centre square when no face is found
        side = min(W, H); x0, y0 = (W - side) // 2, (H - side) // 2; x1, y1 = x0 + side, y0 + side
    else:
        x, y, w, h = box; cx, cy, side = x + w / 2, y + h / 2, max(w, h) * 1.6
        x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2)); x1, y1 = int(min(W, cx + side / 2)), int(min(H, cy + side / 2))
    return Image.fromarray(rgb[y0:y1, x0:x1]).resize((size, size)), [x0, y0, x1, y1]


def inspect(root, asset, refs, frames, out):
    out.mkdir(parents=True, exist_ok=False)
    tiles, detections = [], []
    for ref in refs:
        for entry in ref['assets']:
            a = next((x for x in json.loads((Path(root) / 'project.json').read_text(encoding='utf-8'))['assets'] if x['id'] == entry['id']), None)
            if a is None:
                raise ContractError(f'reference {ref["name"]}: asset {entry["id"]} is no longer in the project')
            box, rgb, size = largest_face(asset_frame(root, a, 0)); im, crop = _crop(rgb, box, 240)
            tiles.append((f'REF {ref["name"]}', im)); detections.append({'asset_id': a['id'], 'frame': 0, 'face': box, 'crop': crop, 'reference': ref['name']})
    for f in frames:
        box, rgb, size = largest_face(asset_frame(root, asset, f)); im, crop = _crop(rgb, box, 240)
        tiles.append((f'{asset["id"][:8]} f{f}', im)); detections.append({'asset_id': asset['id'], 'frame': f, 'face': box, 'crop': crop})
    sheet = Image.new('RGB', (240 * len(tiles), 260), (18, 18, 22)); d = ImageDraw.Draw(sheet)
    for k, (label, im) in enumerate(tiles):
        sheet.paste(im, (240 * k, 20)); d.text((240 * k + 4, 4), label + ('' if detections[k]['face'] else ' (no face: centre)'), fill=(255, 255, 255))
    p = out / 'identity.jpg'; sheet.save(p, quality=90)
    return {'sheet': str(p), 'detections': detections, 'meaning': 'visual comparison only; a detected face is not a biometric identity match'}


def record_review(root, key, refs, accepted, note=''):
    data = load(root)
    for ref in refs:
        data['reviews'][f'{key}:{ref["digest"]}'] = {'reference': ref['name'], 'accepted': bool(accepted), 'note': note, 'at': datetime.now(timezone.utc).isoformat()}
    _save(root, data)


def missing(root, state):
    """Strict-mode blockers: generated clips in the timeline not accepted against every identity reference."""
    data = load(root); refs = [r for r in data['references'].values() if r['role'] == 'identity']
    edit = state.get('timeline') or {}
    if not refs or not edit.get('clips'):
        return []
    by_dir = {a['clip']['frames_dir']: a for a in state.get('assets', []) if 'clip' in a}
    out = []
    for key, clip in edit['clips'].items():
        if not (local_path(root, clip['frames_dir']) / 'comfy-origin.json').is_file():
            continue
        asset = by_dir.get(clip['frames_dir']) or {'id': key, 'clip': clip}
        k = asset_key(root, asset)
        for ref in refs:
            rev = data['reviews'].get(f'{k}:{ref["digest"]}')
            if rev is None:
                out.append(f'inspect generated clip {key} against identity reference {ref["name"]} with inspect_identity')
            elif not rev['accepted']:
                out.append(f'generated clip {key} was rejected against identity reference {ref["name"]}')
    return out
