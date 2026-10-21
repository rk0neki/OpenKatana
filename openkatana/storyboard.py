"""Storyboard mode: plan a music edit as slots still to be filled, then fill them with footage.

plan() turns the music's beat-aligned cut plan (music_plan.plan_cuts) into slots, each with a brief: part (hook,
build, drop, break, outro from the level sections), role (hook, build, drop_first, drop, burst, break, outro), shot
size, subject, camera and the seconds of footage it needs. Every slot gets a slate picture (an OpenKatana design set
in bundled OFL fonts), so the storyboard renders and can be reviewed before any footage exists. fill() puts an
imported clip into slots, checking there is enough footage. verdict() reports
"GAPS storyboard: k of n slots still to fill" while slates remain, else "FILLED".

Slates are clips named slot_<ID> whose frames live in .openkatana/storyboards/<id>/; the slot records are in that
folder's storyboard.json.
"""
import json
import math
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .contracts import ContractError
from .render import digest, write_json

PREFIX = 'slot_'
FOLDER = '.openkatana/storyboards'
SHOTS = {'hook': ['wide, establishing the place', 'low-angle medium, the subject against the light'],
         'build': ['medium', 'medium close-up', 'detail of hands or an object', 'wide'],
         'drop_first': ['close-up: a face or detail to crash into'],
         'drop': ['close-up', 'medium', 'wide', 'detail'],
         'burst': ['detail', 'extreme close-up'],
         'break': ['wide, calm', 'medium, still'],
         'outro': ['medium close-up that can hold at the end']}
CAMERA = {'hook': 'slow push-in', 'build': 'handheld, steady', 'drop_first': 'handheld, fast move into the subject',
          'drop': 'handheld, fast moves', 'burst': 'quick whip or snap zoom', 'break': 'locked off or slow drift', 'outro': 'locked off'}


def _font(name, size):
    from .bundled_fonts import FOLDER as FONTS
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default()


def _parts(analysis, cuts, frames, fps):
    """Part name per section index: build before the first drop, drop for loud sections, break for quiet ones after."""
    drops = {c['section'] for c in cuts if c['kind'] == 'drop'}
    first_drop = min(drops) if drops else None
    names = []
    for i, sec in enumerate(analysis['sections']):
        if sec['label'] == 'loud' and (first_drop is None or i >= first_drop):
            names.append('drop')
        elif first_drop is not None and i > first_drop:
            names.append('break')
        else:
            names.append('build')
    return names


def slots(analysis, plan, fps, subject='the main subject', camera=None):
    cuts = {c['frame']: c for c in plan['cuts']}
    parts = _parts(analysis, plan['cuts'], plan['frames'], fps)
    rows, turn = [], {}
    for k, s in enumerate(plan['shots']):
        t0 = s['f0'] / fps
        sec = next((i for i, x in enumerate(analysis['sections']) if x['t0'] <= t0 + 1e-6 < x['t1']), len(analysis['sections']) - 1)
        part = parts[sec] if parts else 'build'
        cut = cuts.get(s['f0'])
        if k == len(plan['shots']) - 1 and k > 0:
            role, part = 'outro', 'outro'
        elif t0 < 1.5:
            role, part = 'hook', 'hook'
        elif cut and cut['kind'] == 'drop':
            role = 'drop_first'
        elif cut and cut['kind'] == 'burst':
            role = 'burst'
        else:
            role = part
        options = SHOTS[role]; n = turn.get(role, 0); turn[role] = n + 1
        rows.append({'id': f'C{k + 1:02d}', 'f0': s['f0'], 'f1': s['f1'], 't0': round(t0, 3), 't1': round(s['f1'] / fps, 3),
                     'needs_s': round((s['f1'] - s['f0']) / fps, 3), 'part': part, 'role': role, 'shot': options[n % len(options)],
                     'subject': subject, 'camera': camera or CAMERA[role], 'status': 'gap', 'asset_id': None})
    return rows


def slate(slot, W, H, total, path):
    """An OpenKatana slate: dark card, slot ID, brief lines, a frame range bar and a TO FILL tag."""
    im = Image.new('RGB', (W, H), (20, 22, 27)); d = ImageDraw.Draw(im)
    m = min(W, H); pad = int(m * .07)
    d.rectangle([pad // 2, pad // 2, W - pad // 2, H - pad // 2], outline=(70, 76, 90), width=max(2, m // 180))
    big = _font('anton_Anton-Regular.ttf', int(m * .26)); mid = _font('Inter[opsz,wght].ttf', int(m * .045)); small = _font('jetbrainsmono_JetBrainsMono-VF.ttf', int(m * .034))
    d.text((pad, pad), slot['id'], font=big, fill=(240, 240, 240))
    y = pad + int(m * .32)
    lines = [f'{slot["part"].upper()}  ·  {slot["role"].replace("_", " ")}', f'shot: {slot["shot"]}', f'subject: {slot["subject"]}',
             f'camera: {slot["camera"]}', f'needs {slot["needs_s"]:.2f} s  ·  {slot["t0"]:.2f}-{slot["t1"]:.2f} s']
    for line in lines:
        words, cur = line.split(), ''
        for w in words:   # wrap to the card width
            trial = (cur + ' ' + w).strip()
            if d.textlength(trial, font=mid) > W - 2 * pad and cur:
                d.text((pad, y), cur, font=mid, fill=(200, 205, 215)); y += int(m * .06); cur = w
            else:
                cur = trial
        d.text((pad, y), cur, font=mid, fill=(200, 205, 215)); y += int(m * .065)
    bar_y = H - pad - int(m * .05); x0, x1 = pad, W - pad
    d.rectangle([x0, bar_y, x1, bar_y + int(m * .018)], fill=(50, 54, 64))
    a = x0 + (x1 - x0) * slot['f0'] / total; b = x0 + (x1 - x0) * slot['f1'] / total
    d.rectangle([a, bar_y, max(a + 2, b), bar_y + int(m * .018)], fill=(255, 196, 0))
    tag = 'TO FILL'; tw = d.textlength(tag, font=small)
    d.rectangle([W - pad - tw - m * .04, pad, W - pad, pad + m * .065], fill=(255, 196, 0))
    d.text((W - pad - tw - m * .02, pad + m * .012), tag, font=small, fill=(20, 22, 27))
    path.parent.mkdir(parents=True, exist_ok=True); im.save(path)


def plan(root, source, analysis, cut_plan, fps, width, height, subject, camera, audio):
    sid = uuid.uuid4().hex[:12]; folder = root / FOLDER / sid
    rows = slots(analysis, cut_plan, fps, subject, camera)
    clips, shots = {}, []
    for s in rows:
        rel = f'{FOLDER}/{sid}/{s["id"]}'
        slate(s, width, height, cut_plan['frames'], root / rel / '00000.png')
        clips[PREFIX + s['id']] = {'frames_dir': rel, 'n': 1, 'fps': fps, 'w': width, 'h': height, 'pattern': '%05d.png'}
        shots.append({'f0': s['f0'], 'f1': s['f1'], 'clip': PREFIX + s['id'], 'speed': 0})
    edit = {'canvas': {'w': width, 'h': height, 'fps': fps, 'frames': cut_plan['frames']}, 'clips': clips, 'shots': shots}
    if audio:
        edit['audio'] = audio
    board = {'id': sid, 'source': str(source), 'source_sha256': digest(source), 'fps': fps, 'width': width, 'height': height,
             'frames': cut_plan['frames'], 'bpm': analysis.get('bpm'), 'slots': rows}
    write_json(folder / 'storyboard.json', board)
    return board, edit


def load(root, sid):
    path = root / FOLDER / sid / 'storyboard.json'
    if not path.is_file():
        raise ContractError(f'Unknown storyboard {sid!r}')
    return json.loads(path.read_text(encoding='utf-8')), path


def fill(root, board, timeline, assets, fills, fps):
    """Fill slots in the timeline (slate shots only; other shot settings are kept). Returns the changes made."""
    index = {s['id']: s for s in board['slots']}
    changes = []
    for item in fills:
        slot = index.get(item.get('slot'))
        if slot is None:
            raise ContractError(f'Unknown slot {item.get("slot")!r}; slots: {", ".join(index)}')
        asset = assets.get(item.get('asset_id'))
        if not asset or 'clip' not in asset:
            raise ContractError(f'slot {slot["id"]}: asset_id must be an imported video or image')
        shot = next((s for s in timeline['shots'] if s.get('clip') == PREFIX + slot['id'] and s['f0'] == slot['f0']), None)
        if shot is None:
            raise ContractError(f'slot {slot["id"]}: its slate shot is no longer in the saved timeline (already filled or edited)')
        clip = asset['clip']; n = shot['f1'] - shot['f0']
        srcf = item.get('srcf', 0)
        if not isinstance(srcf, int) or srcf < 0:
            raise ContractError('srcf: a non-negative source frame')
        new = {k: v for k, v in shot.items() if k not in ('clip', 'speed', 'srcf', 'src', 'loop')}
        new['clip'] = asset['id']
        if asset['kind'] == 'image':
            new['speed'] = 0
        else:
            need = math.ceil(n * clip['fps'] / fps)
            if srcf + need > clip['n']:
                raise ContractError(f'slot {slot["id"]} needs {slot["needs_s"]:.2f} s of footage; {asset["id"]} has '
                                    f'{max(0, clip["n"] - srcf) / clip["fps"]:.2f} s from srcf {srcf}')
            new.update(srcf=srcf, speed=1, loop='clamp')
        timeline['shots'][timeline['shots'].index(shot)] = new
        timeline['clips'][asset['id']] = clip
        slot.update(status='filled', asset_id=asset['id'], srcf=srcf if asset['kind'] != 'image' else None)
        changes.append({'slot': slot['id'], 'asset_id': asset['id'], 'srcf': new.get('srcf')})
    used = {s.get('clip') for s in timeline['shots']}
    for key in [k for k in timeline['clips'] if k.startswith(PREFIX) and k not in used]:
        del timeline['clips'][key]
    return changes


def open_slots(edit):
    return [s for s in edit.get('shots', []) if str(s.get('clip', '')).startswith(PREFIX)
            and FOLDER in str(edit['clips'].get(s['clip'], {}).get('frames_dir', ''))]


def verdict(board, edit=None):
    gaps = [s for s in board['slots'] if s['status'] == 'gap']
    if edit is not None:   # the saved timeline is the truth: a slate removed by hand is no longer a gap
        live = {s['clip'][len(PREFIX):] for s in open_slots(edit)}
        gaps = [s for s in gaps if s['id'] in live]
    n = len(board['slots'])
    if not gaps:
        return {'verdict': 'FILLED', 'slot_count': n, 'gaps': []}
    head = '; '.join(f'{s["id"]} f{s["f0"]}-{s["f1"] - 1} {s["needs_s"]:.1f} s {s["shot"]}' for s in gaps[:6])
    return {'verdict': f'GAPS storyboard: {len(gaps)} of {n} slots still to fill: {head}{" ..." if len(gaps) > 6 else ""}',
            'slot_count': n, 'gaps': [{k: s[k] for k in ('id', 'f0', 'f1', 't0', 't1', 'needs_s', 'part', 'role', 'shot', 'subject', 'camera')} for s in gaps]}
