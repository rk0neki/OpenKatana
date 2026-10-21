"""Runs only inside installed Blender; independently authored bridge."""
import json
from pathlib import Path
import runpy
import sys


def main():
    import bpy
    spec=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
    source=Path(spec['source']);out=Path(spec['output'])
    if source.suffix.lower()=='.py':
        # The separately installed Blender has its own Python. Expose this installed
        # OpenKatana package to trusted authors without machine-specific sys.path edits.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        sys.path.insert(0, str(source.parent))
        runpy.run_path(str(source),run_name='__main__')
    scene=bpy.context.scene
    scene.render.engine=spec['engine']
    # Relative asset references resolve against the loaded .blend, or script directory.
    dependencies={}
    for image in bpy.data.images:
        if image.source=='FILE' and not image.packed_file and image.filepath:
            from hashlib import sha256
            p=Path(bpy.path.abspath(image.filepath))
            if not p.is_file():raise RuntimeError(f'Missing Blender texture: {p}')
            dependencies[str(p)]=sha256(p.read_bytes()).hexdigest()
    start=scene.frame_start if spec['start'] is None else spec['start']
    end=scene.frame_end if spec['end'] is None else spec['end']
    if end<start or end-start+1>36000:raise RuntimeError('Invalid Blender frame range')
    width=scene.render.resolution_x*scene.render.resolution_percentage//100
    height=scene.render.resolution_y*scene.render.resolution_percentage//100
    if width%2 or height%2:raise RuntimeError('Blender video dimensions must be even')
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
    (out/'frames').mkdir()
    # Step from the simulation start to preserve unbaked forward simulation behavior.
    for f in range(min(scene.frame_start,start),start):scene.frame_set(f)
    for i,f in enumerate(range(start,end+1)):
        scene.frame_set(f);scene.render.filepath=str(out/'frames'/f'{i:05d}.png')
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'rendered-scene.blend'),copy=True)
    result={'blender':bpy.app.version_string,'frames':end-start+1,'fps':scene.render.fps/scene.render.fps_base,
            'width':width,'height':height,'source_frame_start':start,'source_frame_end':end,'dependencies':dependencies,
            'determinism':'Sequential render; bake simulations before random-access reuse'}
    (out/'blender-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')


if __name__=='__main__':main()
