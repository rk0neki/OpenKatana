"""Sticker events (audit F-NAT-008): top-level `assets` (sticker images and die-cut subject cut-outs) and `stickers`
events drawn as an over-phase layer (order 50), with placement, pop-in animation, shadow and die-cut
drawing in web/stickers.js.

assets: {"stickers": [project image paths] | {"dir", "n", "pattern", "start"},
         "cutouts": [{"clip": id with mask_dir, "t": s | "f": source frame}], "cutout_border": px, "cutout_border_color"}
stickers[]: {"f0"/"t0", "f1"/"t1", "kind": graphic|cutout, "n", "mode": hold|burst, "step": s, "ids": [1-based],
             "size": [min, max] px, "slots": [[x, y]], "avoid": [[x0, y0, x1, y1]], "rot": rad, "shadow": bool, "seed"}
A shot hides them with fx.stickers false; specials show them when their allow list has "stickers"."""
from .contracts import ContractError, color, fields, local_path, number

IMAGE = ('.png', '.webp', '.jpg', '.jpeg')


def expand_assets(assets):
    """{dir, n, pattern, start} -> explicit paths (native authoring form)."""
    if isinstance(assets, dict) and isinstance(assets.get('stickers'), dict):
        s = assets['stickers']
        fields(s, 'dir n pattern start', 'assets.stickers')
        n = number(s.get('n'), 'assets.stickers.n', 1, 256, integer=True)
        start = number(s.get('start', 1), 'assets.stickers.start', 0, 100000, integer=True)
        pattern = s.get('pattern', '%02d.png')
        if not isinstance(pattern, str) or pattern.count('%') != 1 or not isinstance(s.get('dir'), str):
            raise ContractError('assets.stickers: dir and a printf pattern such as "s%02d.png"')
        try:
            names = [pattern % (start + i) for i in range(n)]
        except (TypeError, ValueError) as e:
            raise ContractError('assets.stickers.pattern: one integer placeholder such as %02d') from e
        assets = {**assets, 'stickers': [s['dir'].rstrip('/') + '/' + name for name in names]}
    return assets


def validate(edit, root, frames, fps):
    assets, events = edit.get('assets'), edit.get('stickers')
    if assets is None and events is None:
        return
    assets = assets or {}
    fields(assets, 'stickers cutouts cutout_border cutout_border_color', 'assets')
    images = assets.get('stickers', [])
    if not isinstance(images, list) or len(images) > 256 or not all(isinstance(p, str) and p for p in images):
        raise ContractError('assets.stickers: up to 256 project image paths')
    for p in images:
        if not p.lower().endswith(IMAGE):
            raise ContractError(f'assets.stickers: {p} is not a PNG/WebP/JPEG image')
        if root is not None and not local_path(root, p).is_file():
            raise ContractError(f'assets.stickers: missing file {p}')
    cutouts = assets.get('cutouts', [])
    if not isinstance(cutouts, list) or len(cutouts) > 32:
        raise ContractError('assets.cutouts: up to 32 cut-outs')
    clips = edit.get('clips', {})
    for i, c in enumerate(cutouts):
        where = f'assets.cutouts[{i}]'
        if not isinstance(c, dict):
            raise ContractError(f'{where}: expected an object')
        fields(c, 'clip t f', where)
        clip = clips.get(c.get('clip'))
        if clip is None:
            raise ContractError(f'{where}.clip: unknown clip')
        if 'mask_dir' not in clip:
            raise ContractError(f'{where}: cutout needs a clip with mask_dir (analyze_clip masks)')
        if ('t' in c) == ('f' in c):
            raise ContractError(f'{where}: give t (seconds) or f (source frame)')
        if 't' in c:
            number(c['t'], where + '.t', 0, (clip['n'] - 1) / clip['fps'])
        else:
            number(c['f'], where + '.f', 0, clip['n'] - 1, integer=True)
    if 'cutout_border' in assets:
        number(assets['cutout_border'], 'assets.cutout_border', 0, 200)
    if 'cutout_border_color' in assets:
        color(assets['cutout_border_color'], 'assets.cutout_border_color')
    if not isinstance(events or [], list) or len(events or []) > 256:
        raise ContractError('stickers: up to 256 events')
    for i, ev in enumerate(events or []):
        where = f'stickers[{i}]'
        if not isinstance(ev, dict):
            raise ContractError(f'{where}: expected an object')
        fields(ev, 'f0 f1 kind n mode step ids size slots avoid rot shadow seed', where)
        f0 = number(ev.get('f0'), where + '.f0', 0, frames - 1, integer=True)
        number(ev.get('f1'), where + '.f1', f0 + 1, frames, integer=True)
        kind = ev.get('kind', 'graphic')
        if kind not in ('graphic', 'cutout'):
            raise ContractError(f'{where}.kind: graphic or cutout')
        pool = images if kind == 'graphic' else cutouts
        if not pool:
            raise ContractError(f'{where}: kind {kind} needs assets.{"stickers" if kind == "graphic" else "cutouts"}')
        n = number(ev.get('n', 1), where + '.n', 1, 24, integer=True)
        if ev.get('mode', 'hold') not in ('hold', 'burst'):
            raise ContractError(f'{where}.mode: hold or burst')
        if 'step' in ev:
            number(ev['step'], where + '.step', .01, 10)
        if 'ids' in ev:
            if not isinstance(ev['ids'], list) or not ev['ids']:
                raise ContractError(f'{where}.ids: 1-based indices into the {kind} assets')
            for k in ev['ids']:
                number(k, where + '.ids', 1, len(pool), integer=True)
        if 'size' in ev:
            s = ev['size']
            if not isinstance(s, list) or len(s) != 2:
                raise ContractError(f'{where}.size: [min, max] px')
            number(s[0], where + '.size', 4, 4000); number(s[1], where + '.size', s[0], 4000)
        for key, n_ in (('slots', 2), ('avoid', 4)):
            if key in ev:
                if not isinstance(ev[key], list) or not ev[key]:
                    raise ContractError(f'{where}.{key}: a nonempty list')
                for pt in ev[key]:
                    if not isinstance(pt, list) or len(pt) != n_:
                        raise ContractError(f'{where}.{key}: entries of {n_} numbers (0..1 of the frame)')
                    for v in pt:
                        number(v, where + '.' + key, 0, 1)
        if 'slots' in ev and len(ev['slots']) < n:
            raise ContractError(f'{where}.slots: at least n ({n}) slots')
        if 'rot' in ev:
            number(ev['rot'], where + '.rot', 0, 3.1416)
        if 'shadow' in ev and not isinstance(ev['shadow'], bool):
            raise ContractError(f'{where}.shadow: expected boolean')
        if 'seed' in ev:
            number(ev['seed'], where + '.seed', -10 ** 9, 10 ** 9, integer=True)


def manifest_paths(edit):
    """Project files the sticker layer reads (for the render's input manifest)."""
    return list((edit.get('assets') or {}).get('stickers', []))
