"""Non-fatal timeline warnings: valid input that probably does not do what the editor intends.

Independent static analysis of a validated timeline (no rendering). Returned by validate_timeline, save_timeline,
preview_timeline and the render receipt so an agent sees them before review (audit F-OK-014, F-DOC-001).
"""


def _merged_cam(edit, clip, shot):
    return {**edit.get('cam', {}), **clip.get('cam', {}), **shot.get('cam', {})}


def _items(edit, shot):
    """(name, params) for every effect drawn on a shot: timeline post, shot fx (fx overrides post) and layers."""
    fx = {**edit.get('post', {}), **shot.get('fx', {})}
    out = [(k, v) for k, v in fx.items() if v is not False]
    out += [(l.get('type'), l) for l in shot.get('layers', [])]
    return out


def timeline_warnings(edit, root=None):
    warnings = []
    canvas = edit['canvas']; fps = canvas['fps']; W, H = canvas['w'], canvas['h']

    def add(code, index, message):
        warnings.append({'code': code, 'shot': index, 'message': message})

    for i, shot in enumerate(edit['shots']):
        if 'special' in shot:
            continue
        clip = edit['clips'][shot['clip']]
        dur = (shot['f1'] - shot['f0']) / fps
        speed = shot.get('speed', 1); speed1 = shot.get('speed1', speed)
        start = shot['src'] if 'src' in shot else shot.get('srcf', 0) / clip['fps']
        travel = dur * (speed + speed1) / 2
        length = clip['n'] / clip['fps']
        if 'loop' not in shot:   # an explicit loop:'clamp' is a deliberate hold
            if start + travel > length + 1e-6 and max(speed, speed1) > 0:
                add('clamp_past_end', i, f'shot {i} ({shot["clip"]}) needs {start + travel:.2f}s of a {length:.2f}s clip; the last frame holds for '
                    f'{start + travel - length:.2f}s (set loop, speed or src)')
            if start + travel < -1e-6 and min(speed, speed1) < 0:
                add('clamp_before_start', i, f'shot {i} ({shot["clip"]}) plays in reverse past the first frame; the first frame holds')
        cam = _merged_cam(edit, clip, shot)
        locked = cam.get('type') == 'facelock' or cam.get('lock') is True
        if cam.get('fit', 'cover') == 'cover' and 'crop' not in cam and 'ay' not in cam and not locked and cam.get('z', 1) >= 1:
            lost = 1 - (H * clip['w']) / (W * clip['h'])
            if lost > .15:
                add('cover_crop', i, f'shot {i}: clip {shot["clip"]} ({clip["w"]}x{clip["h"]}) is cover-cropped to {W}x{H} at the default centre; '
                    f'{lost:.0%} of its height is cut (set cam.crop, cam.ay, fit or face lock)')
        names = [n for n, _ in _items(edit, shot)]
        if not clip.get('mask_dir'):
            for n in sorted({n for n in names if n in ('outline', 'cutout', 'contour')}):
                add('needs_matte', i, f'shot {i}: {n} draws nothing because clip {shot["clip"]} has no mask_dir')
        if not clip.get('faces') and not isinstance(shot.get('face'), dict):
            if any(t.get('anchor') == 'face' and t['f0'] < shot['f1'] and t['f1'] > shot['f0'] for t in edit.get('text', [])) or \
               any(l.get('type') == 'text' and l.get('anchor') == 'face' for l in shot.get('layers', [])):
                add('needs_face', i, f'shot {i}: face-anchored text has no face track or shot.face box; it falls back to a canvas-centre face model')
        outs = shot.get('out', [])
        outs = outs if isinstance(outs, list) else [outs]
        if any((o == 'magenta') or (isinstance(o, dict) and o.get('type') == 'magenta') for o in outs):
            add('magenta_out', i, f'shot {i}: outgoing magenta plays the incoming mosaic/wash in reverse')
        for n, p in _items(edit, shot):
            if n == 'polygon3d' and isinstance(p, dict) and p.get('points'):
                extent = max(abs(c) for pt in p['points'] for c in pt)
                if extent <= 1:
                    add('polygon3d_units', i, f'shot {i}: polygon3d points are world pixels; coordinates within +-{extent:g} project to sub-pixel size (use pixel units)')
    if root is not None:   # audit F-FONT-001: characters the declared font file does not contain render as fallback glyphs
        from .contracts import local_path
        from .fontcov import missing
        urls = {f['family']: f['url'] for f in edit.get('fonts', [])}
        texts = [(None, t) for t in edit.get('text', [])] + [(i, l) for i, s in enumerate(edit['shots']) for l in s.get('layers', []) if l.get('type') == 'text']
        seen = set()
        for i, t in texts:
            words = t.get('text') or ''.join(p[0] for p in t.get('parts', []))
            fam = t.get('family')
            if not words or fam not in urls or (fam, words) in seen:
                continue
            seen.add((fam, words))
            try:
                gone = missing(local_path(root, urls[fam]), words)
            except Exception:
                gone = None
            if gone:
                add('missing_glyphs', i, f'font "{fam}" has no glyph for {"".join(gone)!r} in "{words[:40]}"; the browser draws a fallback font there')
    from .storyboard import open_slots
    slates = open_slots(edit)
    if slates:
        first = edit['shots'].index(slates[0])
        add('storyboard_gaps', first, f'GAPS storyboard: {len(slates)} slot(s) still show slates '
            f'({", ".join(s["clip"][5:] for s in slates[:8])}{" ..." if len(slates) > 8 else ""}); fill them with fill_storyboard')
    return warnings
