"""Scene contracts and local Three.js rendering."""
from __future__ import annotations

import base64
import copy
from functools import partial
from http.server import ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import shutil
import struct
import threading
from urllib.parse import unquote, urlsplit

from .contracts import ContractError
from .render import Handler, chrome_path, digest, encode, guard_page, playwright, probe, write_json

WEB = Path(__file__).parent / 'web'
EXTENSIONS = set(('KHR_materials_unlit KHR_materials_clearcoat KHR_materials_transmission '
                  'KHR_materials_ior KHR_materials_volume KHR_materials_specular '
                  'KHR_materials_emissive_strength KHR_materials_iridescence '
                  'KHR_materials_sheen KHR_texture_transform KHR_lights_punctual '
                  'KHR_mesh_quantization EXT_mesh_gpu_instancing').split())


def obj(v, keys, where):
    if not isinstance(v, dict):
        raise ContractError(f'{where}: expected an object')
    extra = set(v) - set(keys.split())
    if extra:
        raise ContractError(f'{where}: unsupported fields {sorted(extra)}')


def num(v, where, lo=-1e6, hi=1e6, integer=False):
    if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi or (integer and type(v) is not int):
        raise ContractError(f'{where}: expected {"integer" if integer else "number"} in [{lo}, {hi}]')
    return v


def vec(v, where, n=3):
    if not isinstance(v, list) or len(v) != n:
        raise ContractError(f'{where}: expected {n} numbers')
    for x in v:
        num(x, where)


def color(v, where):
    if not isinstance(v, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', v):
        raise ContractError(f'{where}: use #RRGGBB')


def asset(root, rel):
    if not isinstance(rel, str) or not rel or rel.startswith('/') or '\\' in rel or urlsplit(rel).scheme or urlsplit(rel).netloc:
        raise ContractError('3D assets must be local relative paths with forward slashes')
    if urlsplit(rel).query or urlsplit(rel).fragment:
        raise ContractError('Asset query strings and fragments are unsupported')
    p = (Path(root) / unquote(rel)).resolve()
    if not p.is_relative_to(Path(root).resolve()) or not p.is_file():
        raise ContractError(f'Missing or escaping 3D asset: {rel}')
    return p


def inspect_model(source):
    source = Path(source).resolve()
    raw = source.read_bytes()
    if source.suffix.lower() == '.glb':
        if len(raw) < 20 or raw[:4] != b'glTF' or struct.unpack_from('<I', raw, 4)[0] != 2 or struct.unpack_from('<I', raw, 8)[0] != len(raw):
            raise ContractError('Invalid glTF 2 binary header')
        length, kind = struct.unpack_from('<II', raw, 12)
        if kind != 0x4E4F534A or 20 + length > len(raw):
            raise ContractError('GLB first chunk must be JSON')
        data = json.loads(raw[20:20 + length])
    elif source.suffix.lower() == '.gltf':
        data = json.loads(raw)
    else:
        raise ContractError('Import a .glb or .gltf model; convert other formats with Blender')
    if data.get('asset', {}).get('version') != '2.0':
        raise ContractError('Only glTF 2.0 is supported')
    extra = set(data.get('extensionsUsed', [])) | set(data.get('extensionsRequired', []))
    if extra - EXTENSIONS:
        raise ContractError(f'Unsupported glTF extensions: {sorted(extra - EXTENSIONS)}; export an uncompressed supported asset')
    deps = {source.name: digest(source)}
    for item in [*data.get('buffers', []), *data.get('images', [])]:
        uri = item.get('uri')
        if uri and not uri.startswith('data:'):
            p = asset(source.parent, uri)
            deps[p.relative_to(source.parent).as_posix()] = digest(p)
        elif uri:
            if not re.match(r'^data:(application/(octet-stream|gltf-buffer)|image/(png|jpeg|webp));base64,', uri):
                raise ContractError('Unsupported embedded glTF data URI')
            try:
                base64.b64decode(uri.split(',', 1)[1], validate=True)
            except ValueError as e:
                raise ContractError('Invalid embedded glTF data') from e
    return {'source': str(source), 'dependencies': deps, 'meshes': len(data.get('meshes', [])),
            'skins': len(data.get('skins', [])), 'nodes': len(data.get('nodes', [])),
            'animations': [{'name': a.get('name', ''), 'channels': len(a.get('channels', []))} for a in data.get('animations', [])],
            'morph_targets': sum(len(p.get('targets', [])) for m in data.get('meshes', []) for p in m.get('primitives', [])),
            'extensions': sorted(extra)}


def import_model(source, destination):
    info = inspect_model(source)
    source, destination = Path(source).resolve(), Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    for rel in info['dependencies']:
        out = destination / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source.parent / rel, out)
    write_json(destination / 'import-receipt.json', info)
    return {**info, 'model': str(destination / source.name), 'rights': 'user must supply redistribution rights'}


def primitive(g, where, implicit=False):
    obj(g, 'type size radius tube height radial_segments tubular_segments points depth bevel holes from to grid bound amount', where)
    allowed = {'box', 'sphere', 'torus'} if implicit else {'box', 'sphere', 'torus', 'cylinder', 'cone', 'plane', 'extrude', 'implicit'}
    if g.get('type') not in allowed:
        raise ContractError(f'{where}: supported types are {sorted(allowed)}')
    options = {'box':'size', 'plane':'size', 'sphere':'radius radial_segments',
               'torus':'radius tube radial_segments tubular_segments', 'cylinder':'radius height radial_segments',
               'cone':'radius height radial_segments', 'extrude':'points depth bevel holes',
               'implicit':'from to grid bound amount'}
    obj(g, 'type ' + options[g['type']], where)
    if implicit:
        obj(g, 'type ' + {'box':'size','sphere':'radius','torus':'radius tube'}[g['type']], where)
    for k in ('radius', 'tube', 'height', 'depth', 'bound'):
        if k in g:
            num(g[k], where + '.' + k, .0001, 10000)
    if 'size' in g:
        vec(g['size'], where + '.size')
        if min(g['size']) <= 0:
            raise ContractError('Geometry size must be positive')
    for k in ('radial_segments', 'tubular_segments'):
        if k in g:
            num(g[k], where + '.' + k, 3, 256, True)
    if 'bevel' in g:
        num(g['bevel'], where + '.bevel', 0, 100)
    if g['type'] == 'extrude':
        for ring in [g.get('points'), *g.get('holes', [])]:
            if not isinstance(ring, list) or not 3 <= len(ring) <= 2048:
                raise ContractError('Extrusions need rings of 3..2048 [x,y] points')
            for p in ring:
                vec(p, 'extrusion point', 2)
    if g['type'] == 'implicit':
        primitive(g.get('from'), where + '.from', True)
        primitive(g.get('to'), where + '.to', True)
        num(g.get('grid', 24), 'implicit.grid', 8, 64, True)
        num(g.get('amount', 0), 'implicit.amount', 0, 1)


def material(m, root):
    obj(m, 'color metalness roughness clearcoat transmission thickness ior opacity emissive emissive_intensity map normal_map double_sided', 'material')
    for k in ('color', 'emissive'):
        if k in m:
            color(m[k], 'material.' + k)
    for k in ('metalness', 'roughness', 'clearcoat', 'transmission', 'opacity'):
        if k in m:
            num(m[k], 'material.' + k, 0, 1)
    for k in ('thickness', 'emissive_intensity'):
        if k in m:
            num(m[k], 'material.' + k, 0, 1000)
    if 'ior' in m:
        num(m['ior'], 'material.ior', 1, 2.333)
    for k in ('map', 'normal_map'):
        if k in m:
            asset(root, m[k])
    if 'double_sided' in m and type(m['double_sided']) is not bool:
        raise ContractError('double_sided must be boolean')


def validate(scene, root):
    scene = copy.deepcopy(scene)
    obj(scene, 'schema canvas background environment exposure camera lights objects tracks physics post motion_blur authoring camera_path', 'scene')
    if type(scene.get('schema')) is not int or scene.get('schema') != 1:
        raise ContractError('Scene schema must be 1')
    c = scene.get('canvas')
    obj(c, 'width height fps frames transparent', 'canvas')
    for k in ('width', 'height'):
        num(c.get(k), 'canvas.' + k, 16, 4096, True)
        if c[k] % 2:
            raise ContractError('Scene dimensions must be even for video export')
    num(c.get('fps'), 'fps', 1, 120, True)
    num(c.get('frames'), 'frames', 1, 36000, True)
    if 'transparent' in c and type(c['transparent']) is not bool:
        raise ContractError('transparent must be boolean')
    color(scene.get('background', '#101820'), 'background')
    num(scene.get('exposure', 1), 'exposure', .01, 20)
    env = scene.get('environment', 'studio')
    if env not in ('studio', 'none'):
        if asset(root, env).suffix.lower() != '.hdr':
            raise ContractError('Environment must be studio, none, or a local .hdr file')
    cam = scene.get('camera')
    obj(cam, 'type position target fov near far span', 'camera')
    if cam.get('type', 'perspective') not in ('perspective', 'orthographic'):
        raise ContractError('Camera type must be perspective or orthographic')
    vec(cam.get('position'), 'camera.position'); vec(cam.get('target', [0, 0, 0]), 'camera.target')
    if cam['position'] == cam.get('target', [0, 0, 0]):
        raise ContractError('Camera position and target must differ')
    num(cam.get('fov', 45), 'fov', 1, 170)
    num(cam.get('span', 5), 'span', .01, 10000)
    num(cam.get('near', .01), 'near', .0001, 10000)
    num(cam.get('far', 1000), 'far', cam.get('near', .01) + .0001, 100000)
    entities = {'camera': cam}
    objects = scene.get('objects', [])
    lights = scene.get('lights', [])
    if not isinstance(objects, list) or not 1 <= len(objects) <= 512 or not isinstance(lights, list) or len(lights) > 32:
        raise ContractError('Use 1..512 objects and at most 32 lights')
    for o in objects + lights:
        id_ = o.get('id')
        if not isinstance(id_, str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,63}', id_) or id_ in entities:
            raise ContractError(f'Invalid or duplicate scene ID: {id_}')
        entities[id_] = o
        for k in ('position', 'rotation', 'scale'):
            if k in o:
                vec(o[k], id_ + '.' + k)
        if 'scale' in o and min(o['scale']) <= 0:
            raise ContractError('Scale must be positive')
    for light in lights:
        obj(light, 'id type position target color intensity shadow angle distance decay', 'light')
        if light.get('type') not in ('ambient', 'directional', 'point', 'spot'):
            raise ContractError('Unsupported light type')
        light_keys={'ambient':'', 'directional':'position target shadow', 'point':'position shadow distance decay',
                    'spot':'position target shadow angle distance decay'}
        obj(light, 'id type color intensity '+light_keys[light['type']], 'light')
        color(light.get('color', '#ffffff'), 'light.color')
        for k in ('intensity', 'distance', 'decay'):
            if k in light:
                num(light[k], 'light.' + k, 0, 100000)
        if 'angle' in light:
            num(light['angle'], 'light.angle', .01, math.pi / 2)
        if 'target' in light:
            vec(light['target'], 'light.target')
        if 'shadow' in light and type(light['shadow']) is not bool:
            raise ContractError('shadow must be boolean')
    for o in objects:
        obj(o, 'id type parent position rotation scale geometry material model animation morph_weights visible cast_shadow receive_shadow body', o['id'])
        if o.get('type', 'mesh') not in ('mesh', 'group', 'model'):
            raise ContractError('Object type must be mesh, model or group')
        common='id type parent position rotation scale visible'
        if o.get('type')=='group':obj(o,common,o['id'])
        elif o.get('type')=='model':obj(o,common+' material model animation morph_weights cast_shadow receive_shadow body',o['id'])
        else:obj(o,common+' geometry material cast_shadow receive_shadow body',o['id'])
        for k in ('visible', 'cast_shadow', 'receive_shadow'):
            if k in o and type(o[k]) is not bool:
                raise ContractError(f'{k} must be boolean')
        if o.get('type', 'mesh') == 'mesh':
            primitive(o.get('geometry'), o['id'] + '.geometry')
        if o.get('type') == 'model':
            inspect_model(asset(root, o.get('model')))
        if 'material' in o:
            material(o['material'], root)
        if 'animation' in o:
            a = o['animation']; obj(a, 'clip speed offset loop', 'animation')
            if o.get('type') != 'model' or not isinstance(a.get('clip'), (str, int)):
                raise ContractError('Model animation requires a clip name or index')
            num(a.get('speed', 1), 'animation.speed', 0, 100)
            num(a.get('offset', 0), 'animation.offset', 0, 10000)
            if 'loop' in a and type(a['loop']) is not bool:
                raise ContractError('animation.loop must be boolean')
        if 'morph_weights' in o:
            if o.get('type') != 'model' or not isinstance(o['morph_weights'], dict):
                raise ContractError('morph_weights requires a model and name/weight object')
            for v in o['morph_weights'].values():
                num(v, 'morph weight', 0, 1)
        seen = {o['id']}; parent = o.get('parent')
        while parent:
            if parent in seen or parent not in entities or entities[parent].get('type') != 'group':
                raise ContractError('Parents must form an acyclic hierarchy of groups')
            seen.add(parent); parent = entities[parent].get('parent')
        if 'body' in o:
            b = o['body']; obj(b, 'shape mass size radius velocity angular_velocity friction restitution', 'body')
            if o.get('parent') or o.get('scale', [1, 1, 1]) != [1, 1, 1]:
                raise ContractError('Physics objects must be root objects at unit scale')
            if b.get('shape') not in ('sphere', 'box', 'plane'):
                raise ContractError('Physics collider must be sphere, box or plane')
            num(b.get('mass', 0), 'mass', 0, 100000)
            if b['shape'] == 'plane' and b.get('mass', 0):
                raise ContractError('Plane colliders must be static')
            if b['shape'] == 'sphere':
                num(b.get('radius'), 'body.radius', .001, 10000)
            if b['shape'] == 'box':
                vec(b.get('size'), 'body.size')
                if min(b['size']) <= 0:
                    raise ContractError('Collider sizes must be positive')
            for k in ('velocity', 'angular_velocity'):
                if k in b:
                    vec(b[k], 'body.' + k)
            for k in ('friction', 'restitution'):
                num(b.get(k, .3), 'body.' + k, 0, 1)
    physics = scene.get('physics', {})
    obj(physics, 'gravity substeps', 'physics')
    vec(physics.get('gravity', [0, -9.81, 0]), 'gravity')
    num(physics.get('substeps', 4), 'substeps', 1, 32, True)
    tracks = scene.get('tracks', [])
    if not isinstance(tracks, list) or len(tracks) > 2048:
        raise ContractError('tracks must be a list of at most 2048 tracks')
    used = set()
    for t in tracks:
        obj(t, 'target property keys interpolation', 'track')
        target, prop = t.get('target'), t.get('property')
        if target not in entities or not isinstance(prop, str) or (target, prop) in used:
            raise ContractError('Unknown target or duplicate animation property')
        used.add((target, prop)); entity = entities[target]
        allowed = {'position', 'rotation', 'scale', 'visible'}
        if target == 'camera':
            allowed = {'position', 'target', 'fov'}
            if cam.get('type')=='orthographic':allowed.remove('fov')
        elif entity in lights:
            allowed = {'color', 'intensity'}
            if entity['type']!='ambient':allowed.add('position')
            if entity['type'] in ('spot','directional'):allowed.add('target')
        else:
            if entity.get('type', 'mesh') != 'group':
                allowed |= {'color', 'opacity', 'metalness', 'roughness', 'emissive_intensity'}
            if entity.get('geometry', {}).get('type') == 'implicit':
                allowed.add('amount')
            if entity.get('type') == 'model' and prop.startswith('morph.'):
                allowed.add(prop)
        if prop not in allowed:
            raise ContractError(f'Unsupported track property: {target}.{prop}')
        if 'body' in entity and prop in ('position', 'rotation', 'scale'):
            raise ContractError('Physics owns transforms; do not keyframe the same body')
        if t.get('interpolation', 'linear') not in ('linear', 'smooth', 'step'):
            raise ContractError('Interpolation must be linear, smooth or step')
        if prop == 'visible' and t.get('interpolation') != 'step':
            raise ContractError('Visibility requires step interpolation')
        keys = t.get('keys')
        if not isinstance(keys, list) or not keys:
            raise ContractError('A track needs nonempty [seconds,value] keys')
        prev = -1
        for key in keys:
            if not isinstance(key, list) or len(key) != 2:
                raise ContractError('Use [seconds,value] keys')
            sec, value = key
            num(sec, 'key time', 0, c['frames'] / c['fps'])
            if sec <= prev:
                raise ContractError('Key times must strictly increase')
            prev = sec
            if prop in ('position', 'rotation', 'scale', 'target'):
                vec(value, prop)
                if prop == 'scale' and min(value) <= 0:
                    raise ContractError('Animated scales must be positive')
            elif prop == 'color':
                color(value, prop)
            elif prop == 'visible':
                if type(value) is not bool:
                    raise ContractError('Visibility must be boolean')
            else:
                lo, hi = ((1, 170) if prop == 'fov' else (0, 1) if prop in ('amount', 'opacity', 'metalness', 'roughness') or prop.startswith('morph.') else (0, 100000))
                num(value, prop, lo, hi)
    post = scene.get('post', {})
    obj(post, 'bloom focus aperture max_blur', 'post')
    for k, upper in [('bloom', 5), ('focus', 10000), ('aperture', .1), ('max_blur', .1)]:
        if k in post:
            num(post[k], 'post.' + k, 0, upper)
    if c.get('transparent') and any(post.values()):
        raise ContractError('Transparent output currently requires post effects disabled')
    blur = scene.get('motion_blur', {})
    obj(blur, 'samples shutter', 'motion_blur')
    num(blur.get('samples', 1), 'motion_blur.samples', 1, 32, True)
    num(blur.get('shutter', .5), 'motion_blur.shutter', 0, 1)
    if 'authoring' in scene:
        from .webgl_authoring import validate_authoring
        validate_authoring(scene['authoring'], root)
    if 'camera_path' in scene:
        from .webgl_authoring import camera_schedule
        if cam.get('type') == 'orthographic':
            raise ContractError('camera_path currently requires a perspective camera')
        if any(t['target'] == 'camera' for t in tracks):
            raise ContractError('camera_path owns the camera; remove conflicting camera tracks')
        camera_schedule(scene['camera_path'], c)
    return scene


def input_manifest(scene, root):
    result = {}
    for o in scene['objects']:
        if o.get('type') == 'model':
            p = asset(root, o['model'])
            for rel, sha in inspect_model(p)['dependencies'].items():
                result[(p.parent / rel).relative_to(root).as_posix()] = sha
        for k in ('map', 'normal_map'):
            if k in o.get('material', {}):
                p = asset(root, o['material'][k]); result[p.relative_to(root).as_posix()] = digest(p)
    if scene.get('environment', 'studio') not in ('studio', 'none'):
        p = asset(root, scene['environment']); result[p.relative_to(root).as_posix()] = digest(p)
    if 'authoring' in scene:
        for rel in [scene['authoring']['module'], *scene['authoring'].get('files', [])]:
            p = asset(root, rel); result[p.relative_to(root).as_posix()] = digest(p)
    return result


class SceneHandler(Handler):
    def end_headers(self):
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' data:; worker-src 'none'")
        super(Handler, self).end_headers()


def render_scene(path, out, samples=None, video=True, start=None, end=None, trusted_script=False):
    if type(video) is not bool:
        raise ContractError('video must be a boolean')
    path, out = Path(path).resolve(), Path(out).resolve()
    root = path.parent; scene = validate(json.loads(path.read_text(encoding='utf-8')), root)
    if type(trusted_script) is not bool:
        raise ContractError('trusted_script must be boolean')
    if scene.get('authoring') and not trusted_script:
        raise ContractError('An authoring module requires trusted_script=true; review the local JavaScript first')
    c = scene['canvas']; count = c['frames']
    if samples is not None and (not isinstance(samples, list) or not samples or any(type(f) is not int or not 0 <= f < count for f in samples)):
        raise ContractError('Preview frames must be a nonempty list of valid integer frame indices')
    if samples is not None and (start is not None or end is not None):
        raise ContractError('Choose preview frames or a start/end chunk, not both')
    first = 0 if start is None else num(start, 'start', 0, count-1, True)
    last = count-1 if end is None else num(end, 'end', first, count-1, True)
    frames_to_render = sorted(set(samples)) if samples is not None else range(first,last+1)
    out.mkdir(parents=True, exist_ok=False); (out / 'frames').mkdir()
    dependencies = input_manifest(scene, root)
    dependencies[path.name] = digest(path)
    implementation = {p.relative_to(WEB).as_posix(): digest(p) for p in [WEB / 'scene3d.html', WEB / 'scene3d.js', WEB / 'implicit3d.js', WEB / 'webgl_helpers.js', *(WEB / 'vendor3d').rglob('*')] if p.is_file()}
    implementation['python/scene3d.py'] = digest(Path(__file__))
    for name in ('temporal.py','webgl_authoring.py','camera_path.py'):
        implementation['python/'+name] = digest(Path(__file__).with_name(name))
    runtime_scene = copy.deepcopy(scene)
    if 'camera_path' in scene:
        from .webgl_authoring import camera_schedule
        runtime_scene['_camera_cache'] = camera_schedule(scene['camera_path'], c)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SceneHandler, project=root))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    errors, checks, states = [], {}, []
    try:
        with playwright()() as pw:
            browser = pw.chromium.launch(executable_path=chrome_path(), headless=True,
                args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            try:
                page = browser.new_page(viewport={'width': c['width'], 'height': c['height']})
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
                blocked = guard_page(page, server.server_port)
                def declared_only(route):
                    rel = unquote(urlsplit(route.request.url).path[len('/project/'):])
                    if rel in dependencies:
                        route.continue_()
                    else:
                        blocked.append('Undeclared scene dependency: '+rel); route.abort()
                page.route(f'http://127.0.0.1:{server.server_port}/project/**', declared_only)
                from .page_render import SEED
                page.add_init_script(f'({SEED})()')
                page.goto(f'http://127.0.0.1:{server.server_port}/app/scene3d.html')
                # Module scripts and their imports finish before the load event. Avoid
                # expression-string polling: its eval can be rejected by the strict CSP.
                if not page.evaluate('() => Boolean(window.OpenKatana3D)'):
                    raise ContractError(f'3D module failed to load: {errors}; blocked requests: {blocked}')
                info = page.evaluate('(s) => OpenKatana3D.boot(s)', runtime_scene)

                from .temporal import sample_times, average_png
                blur = scene.get('motion_blur', {})
                def shot(f):
                    times = sample_times(f, count, blur.get('samples', 1), blur.get('shutter', .5))
                    def pixels():
                        for t in times:
                            yield base64.b64decode(page.evaluate('(f) => OpenKatana3D.frame(f)', t)['png'])
                    if len(times) == 1:
                        result = page.evaluate('(f) => OpenKatana3D.frame(f)', f)
                        return base64.b64decode(result['png']), {**result['state'], 'shutter_samples': times}
                    data = average_png(pixels())
                    state = page.evaluate('(f) => OpenKatana3D.frame(f)', f)['state']
                    return data, {**state, 'shutter_samples': times}

                picks = sorted(set([0, count // 4, count // 2, 3 * count // 4, count - 1, first, last]))
                import hashlib
                for f in picks:
                    checks[f] = hashlib.sha256(shot(f)[0]).hexdigest()
                for f in reversed(picks):
                    if hashlib.sha256(shot(f)[0]).hexdigest() != checks[f]:
                        raise ContractError(f'3D reverse-seek determinism failed at frame {f}')
                for f in frames_to_render:
                    data, state = shot(f)
                    name = f if samples is not None else f-first
                    (out / 'frames' / f'{name:05d}.png').write_bytes(data)
                    states.append({'frame': f, **state})
                blocked += page.evaluate('() => window.__okViolations || []')
                if errors or blocked:
                    raise ContractError(f'3D renderer failed: {errors}; blocked requests: {blocked}')
            finally:
                browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join()
    if dependencies != {rel: digest(root / rel) for rel in dependencies}:
        raise ContractError('3D input changed during rendering')
    result = {'scene': str(path), 'output': str(out), 'canvas': c, 'runtime': info,
              'frames_rendered': len(states), 'determinism': {'passed': True, 'frames': picks},
              'preview_images': [str(out / 'frames' / f'{(f if samples is not None else f-first):05d}.png') for f in (list(frames_to_render) if samples is not None else [f for f in picks if first<=f<=last])][:4],
              'inputs': dependencies, 'implementation': implementation,
              'blocked_requests': blocked, 'receipt': str(out/'receipt.json'),
              'comparison_scope': 'independent local behavior tests, not hosted pixel parity', 'credits_used': 0}
    if samples is None:
        n = last-first+1
        result.update({'width':c['width'],'height':c['height'],'fps':c['fps'],'frames':n,
                       'source_frame_start':first,'source_frame_end':last,
                       'source_sha256':hashlib.sha256(json.dumps(dependencies,sort_keys=True).encode()).hexdigest()})
        result['clip'] = {'frames_dir': str(out / 'frames'), 'pattern': '%05d.png', 'n': n,
                          'fps': c['fps'], 'w': c['width'], 'h': c['height']}
        if video:
            encode(out / 'frames', {'frames': n, 'fps': c['fps']}, out / 'video.mp4')
            stream = next(s for s in probe(out / 'video.mp4')['streams'] if s['codec_type'] == 'video')
            if int(stream['nb_read_frames']) != n:
                raise ContractError('Encoded 3D frame count mismatch')
            result['video'] = str(out / 'video.mp4')
            result['video_sha256'] = digest(out / 'video.mp4')
            result['alpha_note'] = 'PNG sequence retains alpha; MP4 is opaque' if c.get('transparent') else 'opaque'
    write_json(out / 'states.json', states); write_json(out / 'receipt.json', result)
    return result


def starter(template='product', width=640, height=360, fps=30, frames=90):
    if template not in ('product', 'morph', 'physics'):
        raise ContractError('Templates: product, morph, physics')
    scene = {'schema': 1, 'canvas': {'width': width, 'height': height, 'fps': fps, 'frames': frames},
        'background': '#101820', 'environment': 'studio', 'exposure': 1.15,
        'camera': {'position': [4, 2.8, 5], 'target': [0, .5, 0], 'fov': 40},
        'lights': [{'id': 'key', 'type': 'directional', 'position': [3, 5, 4], 'color': '#fff3df', 'intensity': 4, 'shadow': True},
                   {'id': 'rim', 'type': 'point', 'position': [-3, 2, -2], 'color': '#50bfff', 'intensity': 30}],
        'objects': [{'id': 'floor', 'geometry': {'type': 'plane', 'size': [30, 30, 1]}, 'rotation': [-math.pi/2, 0, 0],
                     'material': {'color': '#192632', 'roughness': .4, 'metalness': .2}, 'receive_shadow': True},
                    {'id': 'hero', 'position': [0, 1.1, 0], 'geometry': {'type': 'torus', 'radius': .7, 'tube': .23},
                     'material': {'color': '#ff742f', 'metalness': .65, 'roughness': .22, 'clearcoat': 1}, 'cast_shadow': True}],
        'tracks': [{'target': 'hero', 'property': 'rotation', 'keys': [[0, [0, 0, 0]], [frames/fps, [0, math.tau, .5]]]},
                   {'target': 'camera', 'property': 'position', 'interpolation': 'smooth', 'keys': [[0, [4, 2.8, 5]], [frames/fps, [-3, 2, 5]]]}]}
    if template == 'morph':
        scene['objects'][1]['geometry'] = {'type': 'implicit', 'from': {'type': 'sphere', 'radius': .85},
            'to': {'type': 'torus', 'radius': .65, 'tube': .25}, 'grid': 28, 'bound': 1.25, 'amount': 0}
        scene['tracks'].append({'target': 'hero', 'property': 'amount', 'interpolation': 'smooth',
            'keys': [[0, 0], [.2*frames/fps, 0], [.8*frames/fps, 1], [frames/fps, 1]]})
    if template == 'physics':
        scene['objects'][0]['body'] = {'shape': 'plane', 'mass': 0}
        scene['objects'][1].update({'position': [0, 3, 0], 'geometry': {'type': 'box', 'size': [1, 1, 1]},
            'body': {'shape': 'box', 'size': [1, 1, 1], 'mass': 1, 'restitution': .5, 'angular_velocity': [1, .5, .8]}})
        scene['tracks'] = []
    return scene
