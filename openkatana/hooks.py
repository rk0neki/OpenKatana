"""Project hooks (audit F-NAT-011): declaration, normalisation and validation. The timeline declares
`"hooks": {"src": "comp/fx.js", "layers": [names], "text_types": [names]}` (a string is just `src`;
`custom_text_types` adds text types). Declared layer names may then appear as fx keys or layer types, and declared text
types as global text types; everything else stays rejected. web/hooks.js runs the script in the render page."""
import json
import re

from .contracts import ContractError, fields, local_path, number

NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_-]{0,63}')
MAX_BYTES = 512 * 1024


def declared(edit):
    h = edit.get('hooks')
    if h is None:
        if edit.get('custom_text_types'):
            raise ContractError('custom_text_types needs a hooks script: "hooks": {"src": "comp/fx.js", ...}')
        return None
    h = {'src': h} if isinstance(h, str) else h
    if not isinstance(h, dict):
        raise ContractError('hooks: use "path.js" or {"src", "layers", "text_types"}')
    fields(h, 'src layers text_types', 'hooks')
    out = {'src': h.get('src'), 'layers': list(h.get('layers', [])), 'text_types': list(h.get('text_types', []))}
    for t in edit.get('custom_text_types', []) or []:
        if t not in out['text_types']:
            out['text_types'].append(t)
    return out


def normalize(edit, e):
    """Rewrite declared hook names in the (copied) edit `e` into explicit hook items."""
    h = declared(edit)
    e.pop('custom_text_types', None)
    if h is None:
        return
    e['hooks'] = h
    names = set(h['layers'])
    text_types = set(h['text_types'])
    post_hooks = {}
    if isinstance(e.get('post'), dict):
        for k in [k for k in e['post'] if k in names]:
            post_hooks[k] = e['post'].pop(k)
    for shot in e.get('shots', []) if isinstance(e.get('shots'), list) else []:
        if not isinstance(shot, dict):
            continue
        fx = shot.get('fx') if isinstance(shot.get('fx'), dict) else {}
        entries = {**post_hooks, **{k: fx.pop(k) for k in [k for k in fx if k in names]}}
        items = []
        for k, v in entries.items():
            if v is False:
                continue
            params = {} if v is True else v
            if not isinstance(params, dict):
                raise ContractError(f'fx.{k}: a hook layer takes true, false or an object of parameters')
            extra = {key: params[key] for key in ('phase', 'order') if key in params}
            items.append({'type': 'hook', 'name': k, **extra, 'params': {key: val for key, val in params.items() if key not in ('phase', 'order')}})
        layers = []
        for layer in shot.get('layers', []) if isinstance(shot.get('layers'), list) else []:
            if isinstance(layer, dict) and layer.get('type') in names:
                extra = {key: layer[key] for key in ('phase', 'order') if key in layer}
                layers.append({'type': 'hook', 'name': layer['type'], **extra,
                               'params': {key: val for key, val in layer.items() if key not in ('type', 'phase', 'order')}})
            else:
                layers.append(layer)
        if items or layers:
            shot['layers'] = items + layers
        if 'fx' in shot and not shot['fx']:
            shot.pop('fx')
    for i, item in enumerate(e.get('text', []) if isinstance(e.get('text'), list) else []):
        if isinstance(item, dict) and item.get('type') in text_types:
            rest = {k: v for k, v in item.items() if k not in ('type', 'f0', 'f1', 'text')}
            e['text'][i] = {'type': 'hook', 'name': item['type'], **{k: item[k] for k in ('f0', 'f1', 'text') if k in item}, 'params': rest}


def _params(p, where):
    if not isinstance(p, dict):
        raise ContractError(f'{where}.params: expected an object')
    if len(json.dumps(p)) > 64 * 1024:
        raise ContractError(f'{where}.params: larger than 64 KB')


def validate(edit, root):
    h = edit.get('hooks')
    if h is None:
        return set(), set()
    from .effects import CAMERA, POST, SUBJECT, SOURCE, EXTRA
    builtin = set(CAMERA + POST + SUBJECT + SOURCE + EXTRA + ('text', 'graffiti', 'hook', 'font', 'caption', 'word'))
    for kind in ('layers', 'text_types'):
        for n in h[kind]:
            if not isinstance(n, str) or not NAME.fullmatch(n):
                raise ContractError(f'hooks.{kind}: invalid name {n!r}')
            if n in builtin:
                raise ContractError(f'hooks.{kind}: {n!r} is a built-in name')
    if not isinstance(h.get('src'), str) or not h['src'].endswith('.js'):
        raise ContractError('hooks.src: a project-relative .js file')
    if root:
        path = local_path(root, h['src'])
        if not path.is_file():
            raise ContractError(f'hooks.src: file missing: {h["src"]}')
        data = path.read_bytes()
        if len(data) > MAX_BYTES:
            raise ContractError('hooks.src: larger than 512 KB')
        try:
            data.decode('utf-8')
        except UnicodeDecodeError as err:
            raise ContractError('hooks.src: not UTF-8 text') from err
    return set(h['layers']), set(h['text_types'])


def check_layer(item, location, names):
    fields(item, 'type name params phase order', location)
    if item.get('name') not in names:
        raise ContractError(f'{location}: hook layer {item.get("name")!r} is not declared in hooks.layers')
    _params(item.get('params', {}), location)


def check_text(item, location, names, frames):
    fields(item, 'type name f0 f1 text params', location)
    if item.get('name') not in names:
        raise ContractError(f'{location}: hook text type {item.get("name")!r} is not declared in hooks.text_types')
    number(item.get('f0'), location + '.f0', 0, frames - 1, integer=True)
    number(item.get('f1'), location + '.f1', item['f0'] + 1, frames, integer=True)
    if 'text' in item and not isinstance(item['text'], str):
        raise ContractError(f'{location}.text: expected a string')
    _params(item.get('params', {}), location)
