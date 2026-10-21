"""Optional strict review gates (audit F-OK-011). With `strict` on, start_render refuses until every source used by the
saved timeline has been looked at (preview_source or source_contact_sheet on that file) and the current timeline
revision has been previewed (preview_timeline). Records live in <project>/.openkatana/review-gates.json; they are
evidence that the images were produced for the agent, not proof of human review."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .contracts import ContractError
from .render import digest, write_json


def _path(root):
    return Path(root) / '.openkatana' / 'review-gates.json'


def load(root):
    p = _path(root)
    data = json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}
    return {'strict': data.get('strict', False), 'inspected': data.get('inspected', {}), 'previewed': data.get('previewed', {}),
            'require_motion': data.get('require_motion', False), 'motion': data.get('motion', {}), 'mattes': data.get('mattes', {})}


def record_matte(root, mask_sha, clip_id, accepted, note=''):
    data = load(root); data['mattes'][mask_sha] = {'clip': clip_id, 'accepted': bool(accepted), 'note': note, 'at': datetime.now(timezone.utc).isoformat()}
    save(root, data)


MATTE_FX = ('cutout', 'outline', 'contour', 'contour_glow')


def matte_clips(edit):
    """Clips whose matte the timeline renders (subject layers, contour glow, cut-out stickers)."""
    used = set()
    post = edit.get('post') or {}
    for s in edit.get('shots', []):
        fx = {**post, **(s.get('fx') or {})}
        names = {k for k, v in fx.items() if v} | {l.get('type') for l in s.get('layers', []) if isinstance(l, dict)}
        look = s.get('look', edit.get('look'))
        if isinstance(look, dict) and look.get('type') == 'studio':
            names |= {f.get('type') for f in look.get('fx', []) if isinstance(f, dict)}
        if names & set(MATTE_FX) and s.get('clip'):
            used.add(s['clip'])
    used |= {c.get('clip') for c in (edit.get('assets') or {}).get('cutouts', [])}
    return sorted(c for c in used if c in (edit.get('clips') or {}) and 'mask_dir' in edit['clips'][c])


def save(root, data):
    _path(root).parent.mkdir(parents=True, exist_ok=True); write_json(_path(root), data)


def set_strict(root, strict, require_motion=None):
    data = load(root); data['strict'] = bool(strict)
    if require_motion is not None:
        data['require_motion'] = bool(require_motion)
    save(root, data); return data


def record_motion(root, revision, assessment):
    """A measured motion assessment (revise_motion) for a timeline revision."""
    data = load(root); data['motion'][revision] = {**assessment, 'at': datetime.now(timezone.utc).isoformat()}
    save(root, data)


def record_inspection(root, source, via):
    data = load(root); data['inspected'][digest(source)] = {'path': str(source), 'via': via, 'at': datetime.now(timezone.utc).isoformat()}
    save(root, data)


def record_preview(root, revision, frames):
    data = load(root); data['previewed'][revision] = {'frames': list(frames), 'at': datetime.now(timezone.utc).isoformat()}
    save(root, data)


def missing(root, state):
    """What blocks a strict render: uninspected sources of timeline clips, and an unpreviewed revision."""
    data = load(root)
    if not data['strict']:
        return []
    edit = state.get('timeline') or {}
    out = []
    by_frames = {a['clip']['frames_dir']: a for a in state.get('assets', []) if 'clip' in a}
    for key, clip in (edit.get('clips') or {}).items():
        asset = by_frames.get(clip.get('frames_dir'))
        if asset is None or not asset.get('sha256'):
            continue   # frames prepared outside import, or generated material (no original source file to inspect)
        record = Path(root) / '.openkatana' / 'imports' / f'{asset["id"]}.json'   # an excerpt: its original source counts too
        original = json.loads(record.read_text(encoding='utf-8')).get('sha256') if record.is_file() else None
        if asset['sha256'] not in data['inspected'] and original not in data['inspected']:
            out.append(f'inspect source {asset["name"]} (clip {key}) with preview_source or source_contact_sheet')
    if state.get('revision') not in data['previewed']:
        out.append('preview the current timeline revision with preview_timeline')
    if edit.get('clips'):
        from .vision import mask_digest
        for key in matte_clips(edit):
            clip = edit['clips'][key]
            try:
                sha = mask_digest(Path(root), clip['mask_dir'], clip['n'])
            except Exception:
                continue
            rec = data['mattes'].get(sha)
            if rec is None:
                out.append(f'review the matte of clip {key} with review_mask (every 0.25 s and the last frame)')
            elif not rec['accepted']:
                out.append(f'the matte of clip {key} was rejected in review: refine it (analyze_clip masks mode refine) or re-run masks')
    from .identity import missing as identity_missing
    out += identity_missing(root, state)
    if data['require_motion'] and state.get('revision') not in data['motion']:
        out.append('measure the current revision against the reference with revise_motion')
    return out


def require(root, state):
    m = missing(root, state)
    if m:
        raise ContractError('Strict review mode: ' + '; '.join(m))
