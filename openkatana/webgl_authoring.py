"""Original authoring bridge for the bundled MIT Three.js renderer. No vendor workflow code."""
import math
from pathlib import Path
import shutil

from .camera_path import CameraTrack
from .contracts import ContractError, local_path
from .render import write_json


def validate_authoring(value, root):
    from .scene3d import obj, asset
    obj(value, 'module files', 'authoring')
    module = asset(root, value.get('module'))
    if module.suffix.lower() not in ('.js', '.mjs'):
        raise ContractError('authoring.module must be a local .js or .mjs ES module')
    files = value.get('files', [])
    if not isinstance(files, list) or len(files) > 1024 or any(not isinstance(p, str) for p in files):
        raise ContractError('authoring.files must list up to 1024 local dependency paths')
    if len(set(files)) != len(files):
        raise ContractError('Duplicate authoring file')
    for rel in files:
        asset(root, rel)


def camera_schedule(value, canvas):
    """Bake a native-frame camera cache; the browser interpolates within each shot only."""
    from .scene3d import obj, num
    obj(value, 'segments schedule_fps sensor_width', 'camera_path')
    rate = num(value.get('schedule_fps', canvas['fps']), 'schedule_fps', 1, 240)
    sensor = num(value.get('sensor_width', 36), 'sensor_width', 1, 100)
    fps, count = canvas['fps'], canvas['frames']
    track = CameraTrack(value.get('segments'), step=rate/fps)
    if track.segs[0]['f0'] != 0 or track.segs[-1]['f1'] < (count-1)*rate/fps:
        raise ContractError('camera_path must cover every output frame, starting at zero')
    cuts = []
    for c in track.cuts():
        native = c*fps/rate
        if abs(native-round(native)) > 1e-7 or not 1 <= native < count:
            raise ContractError('Camera cuts must align to native integer frames inside the clip')
        cuts.append(round(native))
    poses = []
    aspect = canvas['width']/canvas['height']
    for frame in range(count):
        p = track.sample(frame*rate/fps)
        if math.dist(p['pos'], p['tgt']) < 1e-8:
            raise ContractError('Camera path position and target must differ')
        fov = math.degrees(2*math.atan(sensor/(2*p['lens']*aspect)))
        if not 1 <= fov <= 170:
            raise ContractError('Camera path lens produces an unsupported vertical FOV')
        poses.append({'position': p['pos'], 'target': p['tgt'], 'fov': fov})
    return {'poses': poses, 'cuts': cuts, 'fps': fps, 'sensor_width': sensor}


def create_kit(root, directory='webgl', width=640, height=360, fps=30, frames=60):
    from .production import display_atlas
    from .scene3d import starter, num, validate
    for v, name, lo, hi in ((width,'width',64,4096),(height,'height',64,4096),
                            (fps,'fps',1,120),(frames,'frames',6,36000)):
        num(v, name, lo, hi, True)
    if width % 2 or height % 2:
        raise ContractError('Video dimensions must be even')
    out = local_path(root, directory)
    if out.exists():
        raise FileExistsError('WebGL kit destination already exists')
    mid = frames//2
    pose = lambda pos: {'pos':pos,'tgt':[0,1.1,0],'lens':40}
    scene = starter(width=width,height=height,fps=fps,frames=frames)
    # The floor is declarative. The editable module adds its own geometry and animation.
    scene['objects'] = scene['objects'][:1]
    scene['tracks'] = []
    scene['post'] = {'bloom':.16,'focus':5,'aperture':.00005,'max_blur':.003}
    scene['motion_blur'] = {'samples':4,'shutter':.5}
    scene['camera_path'] = {'schedule_fps':fps,'segments':[
        {'f0':0,'f1':mid,'type':'push','poses':[pose([3,2.6,6]),pose([1.8,2.4,5.6])]},
        {'f0':mid,'f1':frames-1,'type':'hold','cut':True,
         'poses':[pose([-2.5,2.5,5.6]),pose([-1.8,2.4,5.6])]}]}
    camera_schedule(scene['camera_path'],scene['canvas'])
    display = {'cols':32,'rows':9,'frames':frames,'fps':fps,'tiles_x':min(frames,32),
               'cues':[{'start':0,'end':mid,'text':'GO','reveal_frames':min(4,mid)},
                       {'start':mid,'end':frames,'text':'PLAY','channel':1}]}
    scene['authoring'] = {'module':'scene.js','files':['display/atlas.png','display/receipt.json']}
    out.mkdir(parents=True)
    display_atlas(display,out/'display')
    write_json(out/'display.json',display)
    shutil.copyfile(Path(__file__).with_name('templates')/'webgl_scene.js',out/'scene.js')
    write_json(out/'scene.json',validate(scene,out))
    return {'directory':str(out),'scene':(out/'scene.json').relative_to(root).as_posix(),
            'module':(out/'scene.js').relative_to(root).as_posix(),'guide':'webgl',
            'engine':'bundled MIT Three.js; no Blender required','credits_used':0,
            'next':'Edit scene.js and scene.json for the brief; check_scene3d, then render_scene3d(trusted_script=true) with preview_frames or an inclusive start/end range'}
