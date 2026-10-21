"""Original declarative compositions: CSS layout, shaped text and browser plugins.

This is OpenKatana's own format/API, not a loader for a private native ABI.
Only project assets and installed package files are served; no runtime downloads.
"""
from contextlib import contextmanager
import copy
from functools import partial
from .http_runtime import LocalHTTPServer
import json
from pathlib import Path
import re
import threading
import unicodedata
from urllib.parse import quote, unquote, urlsplit

from .contracts import ContractError, fields, local_path, number, check_font_file
from .render import Handler, chrome_path, digest, encode, guard_page, playwright, write_json
from .page_render import PageHandler, SEED, digest_bytes
from .projects import fingerprint
from . import bundled_fonts

WEB = Path(__file__).parent / 'web'
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,79}')
STYLES = set('''display position left right top bottom inset width height min-width max-width min-height max-height
margin margin-left margin-right margin-top margin-bottom padding padding-left padding-right padding-top padding-bottom
box-sizing flex flex-direction flex-wrap flex-grow flex-shrink flex-basis align-items align-self align-content
justify-content justify-items justify-self gap row-gap column-gap order grid-template-columns grid-template-rows
grid-auto-columns grid-auto-rows grid-auto-flow grid-column grid-row grid-area grid-template-areas
background-color color opacity border border-color border-width border-style border-radius box-shadow
overflow overflow-x overflow-y object-fit object-position aspect-ratio z-index transform transform-origin filter
font-family font-size font-weight font-style font-stretch font-kerning font-feature-settings font-variation-settings
font-optical-sizing font-variant-ligatures font-variant-caps font-variant-numeric font-variant-east-asian
line-height letter-spacing word-spacing text-align text-align-last text-indent text-transform text-decoration
text-shadow text-overflow white-space overflow-wrap word-break hyphens writing-mode text-orientation
unicode-bidi direction vertical-align visibility isolation mix-blend-mode'''.split())
TRACKS = {'opacity', 'translateX', 'translateY', 'rotate', 'scale', 'reveal'}


def array(value, where, limit=1000):
    if not isinstance(value, list) or len(value) > limit:
        raise ContractError(f'{where}: expected an array of at most {limit} items')
    return value


def name(value, where):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ContractError(f'{where}: use a letter followed by letters, digits, hyphens or underscores')
    return value


def styles(value, where):
    fields(value, ' '.join(STYLES), where)
    for prop, val in value.items():
        if not isinstance(val, str) or not 1 <= len(val) <= 1024 or re.search(r'url\s*\(|[{};]|!important', val, re.I):
            raise ContractError(f'{where}.{prop}: a CSS value string without URLs, rules or !important')


def asset(root, value, suffixes):
    if not isinstance(value, str) or Path(value).is_absolute() or ':' in value or '\\' in value:
        raise ContractError('Assets must use relative forward-slash paths')
    p = local_path(root, value)
    if not p.is_file() or p.suffix.lower() not in suffixes:
        raise ContractError(f'Asset missing or unsupported: {value}')
    return p


def plugin_manifests(root, paths):
    """Validate metadata without executing code. Every shipped input is hashable."""
    result = []; ids = set()
    for rel in array(paths, 'plugins', 32):
        path = asset(root, rel, {'.json'})
        m = json.loads(path.read_text(encoding='utf-8'))
        fields(m, 'api id version entry files license', 'plugin')
        if type(m.get('api')) is not int or m['api'] != 1: raise ContractError('Plugin requires OpenKatana API 1')
        key = name(m.get('id'), 'plugin.id')
        if key == 'core' or key in ids: raise ContractError('Duplicate or reserved plugin ID')
        ids.add(key)
        if not isinstance(m.get('version'), str) or not re.fullmatch(r'\d+\.\d+\.\d+', m['version']):
            raise ContractError('plugin.version: expected X.Y.Z')
        if not isinstance(m.get('license'), str) or not m['license'].strip(): raise ContractError('plugin.license: required provenance label')
        files = array(m.get('files'), 'plugin.files', 128)
        if not all(isinstance(f,str) for f in files) or len(set(files)) != len(files) or m.get('entry') not in files: raise ContractError('plugin.files must be unique and include entry')
        if not any(str(f).lower().endswith(('.txt', '.md')) for f in files): raise ContractError('Include the plugin license/notice file')
        for f in files:
            p = asset(path.parent, f, {'.js', '.json', '.txt', '.md', '.png', '.jpg', '.webp', '.svg'})
            if p.stat().st_size > 8 * 1024 * 1024: raise ContractError('Plugin file exceeds 8 MiB')
        if not m['entry'].endswith('.js'): raise ContractError('plugin.entry must be JavaScript')
        result.append({**m, 'manifest': rel, 'url': '/project/' + quote((path.parent / m['entry']).relative_to(root).as_posix(), safe='/')})
    return result


def validate(doc, root, expanded=False):
    root = Path(root).resolve()
    try: json.dumps(doc, allow_nan=False)
    except (TypeError, ValueError) as e: raise ContractError('Composition must be finite JSON data') from e
    fields(doc, 'schema canvas fonts plugins root tracks', 'composition')
    if type(doc.get('schema')) is not int or doc['schema'] != 1: raise ContractError('composition.schema must be 1')
    c = doc.get('canvas'); fields(c, 'w h fps frames', 'canvas')
    for k in ('w', 'h'): number(c.get(k), 'canvas.' + k, 16, 7680, integer=True)
    number(c.get('fps'), 'canvas.fps', 1, 120); number(c.get('frames'), 'canvas.frames', 1, 36000, integer=True)
    font_keys = set()
    for f in array(doc.get('fonts', []), 'fonts', 64):
        fields(f, 'family src bundled weight style', 'font')
        name(f.get('family'), 'font.family')
        key = (f['family'], f.get('weight', 'normal'), f.get('style', 'normal'))
        if key in font_keys: raise ContractError('Duplicate font face')
        font_keys.add(key)
        if ('src' in f) == ('bundled' in f): raise ContractError('font: use exactly one of src or bundled')
        if 'bundled' in f:
            if f['bundled'] not in bundled_fonts.manifest(): raise ContractError('Unknown bundled font')
            p = bundled_fonts.FOLDER / f['bundled']
        else: p = asset(root, f['src'], {'.ttf', '.otf', '.woff', '.woff2'})
        check_font_file(p, f['family'])
        for prop in ('weight', 'style'):
            if prop in f and (not isinstance(f[prop], str) or len(f[prop]) > 80): raise ContractError('Font descriptors must be short strings')
    plugin_manifests(root, doc.get('plugins', []))
    seen = set(); count = 0; has_components = False

    def walk(n, depth=0):
        nonlocal count, has_components
        count += 1
        if depth > 24 or count > 1000: raise ContractError('Composition exceeds depth/node limit')
        fields(n, 'id type style responsive children text runs lang dir src component params effects', 'node')
        key = name(n.get('id'), 'node.id')
        if key in seen: raise ContractError('Duplicate node ID: ' + key)
        seen.add(key); kind = n.get('type')
        if kind not in ('box', 'text', 'image', 'component'): raise ContractError('Unknown node type')
        permitted = {'id', 'type', 'style', 'responsive', 'lang', 'dir', 'effects'} | {
            'box': {'children'}, 'text': {'text', 'runs'}, 'image': {'src'}, 'component': {'component', 'params'}}[kind]
        if set(n) - permitted: raise ContractError(f'Fields not applicable to {kind}: {sorted(set(n)-permitted)}')
        styles(n.get('style', {}), key + '.style')
        for rule in array(n.get('responsive', []), 'responsive', 32):
            fields(rule, 'min_width max_width style', 'responsive')
            lo = number(rule.get('min_width', 0), 'min_width', 0, 7680)
            hi = number(rule.get('max_width', 7680), 'max_width', lo, 7680)
            styles(rule.get('style'), 'responsive.style')
        if n.get('dir', 'auto') not in ('auto', 'ltr', 'rtl'): raise ContractError('dir: auto, ltr or rtl')
        if 'lang' in n and (not isinstance(n['lang'], str) or not re.fullmatch(r'[A-Za-z0-9-]{1,35}', n['lang'])): raise ContractError('Invalid language tag')
        for effect in array(n.get('effects', []), 'effects', 16):
            fields(effect, 'use params', 'effect')
            reference(effect.get('use'))
            if not isinstance(effect.get('params', {}), dict): raise ContractError('Effect params must be an object')
        if kind == 'box':
            for child in array(n.get('children', []), 'children'): walk(child, depth + 1)
        elif kind == 'text':
            if ('text' in n) == ('runs' in n): raise ContractError('text node: exactly one of text or runs')
            runs = [{'text': n['text']}] if 'text' in n else array(n['runs'], 'runs', 256)
            for run in runs:
                fields(run, 'text style lang dir', 'text.run')
                if not isinstance(run.get('text'), str) or len(run['text']) > 10000: raise ContractError('Text must be a string <=10000 characters')
                styles(run.get('style', {}), 'run.style')
                if set(run.get('style', {})) - TEXT_STYLES: raise ContractError('Run styles must be typographic; layout belongs on the text node')
                if run.get('dir', 'auto') not in ('auto', 'ltr', 'rtl'): raise ContractError('Invalid run direction')
                if 'lang' in run and not re.fullmatch(r'[A-Za-z0-9-]{1,35}', run['lang']): raise ContractError('Invalid run language')
        elif kind == 'image': asset(root, n.get('src'), {'.png', '.jpg', '.jpeg', '.webp'})
        else:
            if expanded: raise ContractError('Component did not fully expand')
            has_components = True; reference(n.get('component'))
            if not isinstance(n.get('params', {}), dict): raise ContractError('Component params must be an object')
    walk(doc.get('root'))
    used = set()
    for t in array(doc.get('tracks', []), 'tracks', 1000):
        fields(t, 'node property keys easing', 'track')
        if not has_components and t.get('node') not in seen: raise ContractError('Unknown track node')
        if t.get('property') not in TRACKS: raise ContractError('Unknown track property')
        key = (t.get('node'), t['property'])
        if key in used: raise ContractError('Duplicate track')
        used.add(key)
        if t.get('easing', 'linear') not in ('linear', 'smooth', 'step'): raise ContractError('Unsupported easing')
        keys = array(t.get('keys'), 'keys', 1000)
        if not keys: raise ContractError('Track needs keys')
        prev = -1
        for pair in keys:
            if not isinstance(pair, list) or len(pair) != 2: raise ContractError('keys: [frame, value] pairs')
            number(pair[0], 'key.frame', 0, c['frames'] - 1, integer=True)
            if pair[0] <= prev: raise ContractError('Track frames must increase')
            prev = pair[0]; number(pair[1], 'key.value', -100000, 100000)
            if t['property'] in ('opacity', 'reveal'): number(pair[1], t['property'], 0, 1)
    return copy.deepcopy(doc)


TEXT_STYLES = {k for k in STYLES if k.startswith(('font-', 'text-', 'word-', 'letter-'))} | {'color', 'line-height', 'white-space', 'direction', 'unicode-bidi', 'vertical-align'}


def reference(value):
    if not isinstance(value, str) or len(value.split('/')) != 2: raise ContractError('Plugin reference: plugin/name')
    for part in value.split('/'): name(part, 'plugin reference')


def inputs(doc, root):
    out = {}
    for f in doc.get('fonts', []):
        if 'src' in f: out[f['src']] = digest(local_path(root, f['src']))
        else:
            row = bundled_fonts.manifest()[f['bundled']]
            out['@fonts/' + row['file']] = digest(bundled_fonts.FOLDER / row['file'])
            out['@fonts/' + row['license_file']] = digest(bundled_fonts.FOLDER / row['license_file'])
    for m in plugin_manifests(root, doc.get('plugins', [])):
        out[m['manifest']] = digest(local_path(root, m['manifest']))
        folder = local_path(root, m['manifest']).parent
        for f in m['files']: out[(folder / f).relative_to(root).as_posix()] = digest(folder / f)
    def visit(n):
        if n.get('type') == 'image': out[n['src']] = digest(local_path(root, n['src']))
        for child in n.get('children', []): visit(child)
    visit(doc['root']); return out


def font_coverage(doc, root, report):
    """Report dependence on undeclared/system fallback, without pretending cmap == shaping proof."""
    from .fontcov import codepoints
    families = {}
    for f in doc.get('fonts', []):
        path = bundled_fonts.FOLDER / f['bundled'] if 'bundled' in f else local_path(root, f['src'])
        families.setdefault(f['family'], []).append(codepoints(str(path)))
    warnings = []
    for node in report['nodes']:
        for run in node.get('fontRuns', []):
            names = [n.strip().strip('\"\'') for n in run['family'].split(',')]
            sets = [s for n in names for s in families.get(n, [])]
            if not sets or any(s is None for s in sets):
                warnings.append({'node': node['id'], 'reason': 'Font coverage unknown or system font family used', 'family': run['family']})
                continue
            supported = set().union(*sets)
            missing = sorted({ch for ch in run['text'] if not ch.isspace() and unicodedata.category(ch) != 'Cf'
                              and not 0xFE00 <= ord(ch) <= 0xFE0F and not 0xE0100 <= ord(ch) <= 0xE01EF and ord(ch) not in supported})
            if missing: warnings.append({'node': node['id'], 'reason': 'Undeclared fallback may be used; supply a licensed font covering these characters', 'characters': missing})
    return {'warnings': warnings, 'note': 'Character-map coverage only; not glyph-ID or shaping verification. Browser version and visual inspection still matter.'}


class CompositionHandler(PageHandler):
    def __init__(self, *args, allowed, **kwargs):
        self.allowed = allowed
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        rel = unquote(urlsplit(path).path)
        if rel.startswith('/fonts/'):
            p = (bundled_fonts.FOLDER / rel[7:]).resolve()
            if p.is_relative_to(bundled_fonts.FOLDER.resolve()): return str(p)
            return str(self.project / '__not_found__')
        result = super().translate_path(path)
        if rel.startswith('/project/') and Path(result).resolve() not in self.allowed:
            return str(self.project / '__not_found__')
        return result


@contextmanager
def session(root, manifests):
    """Ephemeral browser context. Plugins are trusted JS, not an OS security boundary."""
    root = Path(root).resolve(); metadata = plugin_manifests(root, manifests)
    allowed = set()
    for m in metadata:
        path = local_path(root, m['manifest']); allowed.add(path)
        allowed.update((path.parent / f).resolve() for f in m['files'])
    plugin_hashes = {str(p.relative_to(root).as_posix()): digest(p) for p in sorted(allowed)}
    server = LocalHTTPServer(('127.0.0.1', 0), partial(CompositionHandler, project=root, allowed=allowed))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        with playwright()() as pw:
            browser = pw.chromium.launch(executable_path=chrome_path(), headless=True, args=['--disable-gpu'])
            try:
                page = browser.new_page(viewport={'width': 640, 'height': 360}, device_scale_factor=1)
                page.set_default_timeout(30000)
                errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                blocked = guard_page(page, server.server_port)
                page.on('response', lambda r: errors.append(f'HTTP {r.status}: {r.url}') if r.status >= 400 else None)
                page.add_init_script(f'({SEED})()')
                page.goto(f'http://127.0.0.1:{server.server_port}/app/composition.html')
                def call(method, args=None):
                    result = page.evaluate('async ([method, args]) => await Promise.race([OpenKatanaComposition[method](args), new Promise((_,reject)=>setTimeout(()=>reject(Error("Composition operation timed out")), 30000))])', [method, args])
                    violations = page.evaluate('() => window.__okViolations || []')
                    if errors or blocked or violations: raise ContractError('Composition runtime: ' + '; '.join(errors + blocked + violations)[:3000])
                    return result
                call.allow = lambda paths: allowed.update(local_path(root, p) for p in paths if not p.startswith('@fonts/'))
                call.provenance = plugin_hashes
                try:
                    call('loadPlugins', metadata)
                    yield page, call, browser.version
                finally:
                    call('dispose')
                    if plugin_hashes != {p:digest(local_path(root,p)) for p in plugin_hashes}:
                        raise ContractError('Plugin inputs changed while executing')
            finally: browser.close()
    finally: server.shutdown(); server.server_close(); thread.join()


def open_composition(root, doc, page, call, width=None, height=None):
    value = validate(doc, root)
    w = width if width is not None else value['canvas']['w']; h = height if height is not None else value['canvas']['h']
    number(w, 'width', 16, 7680, integer=True); number(h, 'height', 16, 7680, integer=True)
    value['canvas'].update(w=w, h=h); page.set_viewport_size({'width': w, 'height': h})
    expanded = call('expand', value)
    if fingerprint(expanded) != fingerprint(call('expand', value)):
        raise ContractError('Component expansion is not deterministic')
    value = expanded
    validate(value, root, expanded=True)
    call.allow(inputs(value, Path(root).resolve()))
    call('mount', value)
    return value


def inspect_composition(root, doc, frame=0, width=None, height=None, preview=None):
    root = Path(root).resolve(); validate(doc, root)
    with session(root, doc.get('plugins', [])) as (page, call, version):
        value = open_composition(root, doc, page, call, width, height)
        number(frame, 'frame', 0, value['canvas']['frames'] - 1, integer=True)
        call('frame', frame); report = call('measure'); report['font_coverage'] = font_coverage(value, Path(root), report)
        if preview:
            preview = Path(preview); preview.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(preview), omit_background=True, animations='disabled')
        return {'valid': True, 'browser': version, 'canvas': value['canvas'], 'frame': frame, 'layout': report,
                'inputs': inputs(value, Path(root)), 'expanded': value, 'revision': fingerprint(doc),
                'preview_images': [str(preview.resolve())] if preview else []}


def render_composition(root, doc, out, width=None, height=None, video=True):
    root = Path(root).resolve(); out = Path(out).resolve()
    if not out.is_relative_to(root): raise ContractError('Composition outputs must stay inside the project')
    if type(video) is not bool: raise ContractError('video must be boolean')
    validate(doc, root); out.mkdir(parents=True, exist_ok=False); (out / 'frames').mkdir()
    with session(root, doc.get('plugins', [])) as (page, call, version):
        value = open_composition(root, doc, page, call, width, height); c = value['canvas']
        if video and (c['w'] % 2 or c['h'] % 2): raise ContractError('MP4 needs even dimensions; use PNG output for odd dimensions')
        before = inputs(value, root)
        def capture(f):
            call('frame', f)
            return page.screenshot(omit_background=True, animations='disabled')
        picks = sorted({round(k * (c['frames'] - 1) / 4) for k in range(5)})
        forward = {f: digest_bytes(capture(f)) for f in picks}
        reverse = {f: digest_bytes(capture(f)) for f in reversed(picks)}
        if forward != reverse: raise ContractError('Composition is not deterministic when seeking backwards')
        # A fresh mount also catches lifecycle state that only happened to settle during the first pass.
        call('mount', value)
        if forward != {f: digest_bytes(capture(f)) for f in picks}: raise ContractError('Composition differs after remount')
        measures = {}
        for f in range(c['frames']):
            (out / 'frames' / f'{f:05d}.png').write_bytes(capture(f))
            if f in picks:
                measures[str(f)] = call('measure')
                measures[str(f)]['font_coverage'] = font_coverage(value, root, measures[str(f)])
        if before != inputs(value, root): raise ContractError('Composition input changed during render')
        lifecycle = call('dispose')
    clip = {'frames_dir': (out / 'frames').relative_to(root).as_posix(), 'pattern': '%05d.png', 'n': c['frames'], 'fps': c['fps'], 'w': c['w'], 'h': c['h']}
    receipt = {'schema': 1, 'engine': 'OpenKatana CSS composition', 'browser': version, 'clip': clip,
               'document_sha256': fingerprint(doc), 'expanded_sha256': fingerprint(value), 'inputs': before,
               'runtime': {p.name: digest(p) for p in [Path(__file__), WEB/'composition.js', WEB/'composition_builtin.js', WEB/'composition.html']},
               'determinism_sample': picks, 'remount_match': True, 'measurements': measures, 'lifecycle': lifecycle,
               'credits_used': 0, 'hosted_parity': 'not established'}
    if video:
        encode(out / 'frames', c, out / 'video.mp4'); receipt.update(video=str(out / 'video.mp4'), sha256=digest(out / 'video.mp4'))
    write_json(out / 'composition.json', doc); write_json(out / 'expanded.json', value); write_json(out / 'receipt.json', receipt)
    return receipt


def list_plugins(root, manifests):
    with session(root, manifests) as (_, call, version):
        return {'plugins': call('catalog'), 'browser': version, 'inputs': call.provenance}


def run_operator(root, manifests, operator, document, parameters=None, kind='composition'):
    """Pure proposal: browser receives a clone; validate before returning. Saving is separate."""
    root = Path(root).resolve(); reference(operator)
    if kind not in ('composition', 'timeline'): raise ContractError('kind: composition or timeline')
    from .contracts import validate as validate_timeline
    checker = validate if kind == 'composition' else validate_timeline
    checker(document, root)
    if parameters is not None and not isinstance(parameters, dict): raise ContractError('parameters must be an object')
    with session(root, manifests) as (_, call, version):
        args = {'operator': operator, 'document': document, 'params': parameters or {}, 'kind': kind}
        result = call('operate', args); again = call('operate', args)
        if fingerprint(result) != fingerprint(again): raise ContractError('Operator is not deterministic')
        checker(result, root)
    return {'document': result, 'before_revision': fingerprint(document), 'revision': fingerprint(result),
            'changed': result != document, 'saved': False, 'operator': operator, 'browser': version,
            'inputs': call.provenance, 'parameters_sha256': fingerprint(parameters or {}),
            'runtime_sha256': digest(WEB/'composition_builtin.js')}


def save_composition(root, path, document, revision):
    root = Path(root).resolve(); dest = local_path(root, path)
    if dest.suffix != '.json' or dest in (root/'timeline.json',root/'project.json'): raise ContractError('Use a composition .json path distinct from project/timeline')
    validate(document, root); dest.parent.mkdir(parents=True, exist_ok=True)
    lock = dest.with_suffix('.json.lock')
    acquired = False
    try:
        with lock.open('x', encoding='utf-8'):
            acquired = True
            old = json.loads(dest.read_text(encoding='utf-8')) if dest.exists() else None
            if (fingerprint(old) if old is not None else None) != revision: raise ContractError('Composition changed; reload before saving')
            if old is not None: write_json(root / '.openkatana/composition-history' / (fingerprint(old) + '.json'), old)
            write_json(dest, document)
    except FileExistsError as e: raise ContractError('Composition save is already in progress; inspect a stale lock before retrying') from e
    finally:
        if acquired: lock.unlink(missing_ok=True)
    return {'path': dest.relative_to(root).as_posix(), 'revision': fingerprint(document)}


def starter(width=1280, height=720, fps=30, frames=90):
    return {'schema': 1, 'canvas': {'w': width, 'h': height, 'fps': fps, 'frames': frames},
            'fonts': [{'family': 'Inter', 'bundled': 'Inter[opsz,wght].ttf', 'weight': '100 900'}],
            'root': {'id': 'stage', 'type': 'box', 'style': {'width': '100vw', 'height': '100vh', 'display': 'flex',
                     'align-items': 'center', 'justify-content': 'center', 'padding': '6vw', 'background-color': '#111827', 'color': '#f8fafc', 'font-family': 'Inter'},
                     'children': [{'id': 'title', 'type': 'component', 'component': 'core/titleCard',
                                   'params': {'title': 'Create in motion', 'subtitle': 'Original OpenKatana composition'}}]},
            'tracks': [{'node': 'title', 'property': 'opacity', 'keys': [[0, 0], [min(20, frames - 1), 1]], 'easing': 'smooth'}] if frames > 1 else []}
