"""Original WebGL fixture through the public API; no private scenes, model services or Blender."""
import argparse
import json
from pathlib import Path
import time

from openkatana.agent_api import AgentAPI
from openkatana.contracts import ContractError
from openkatana.render import digest, probe, write_json


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True)
    args=parser.parse_args();workspace=args.workspace.resolve()
    if workspace.exists():raise ValueError('Use a fresh workspace')
    api=AgentAPI(workspace);api.create_project('Original WebGL fixture','fixture');root=workspace/'fixture'
    kit=api.create_webgl_kit('fixture',width=160,height=96,fps=24,frames=12)
    checks={'contract':api.check_scene3d('fixture',kit['scene'])['valid']}
    scene_path=root/kit['scene'];scene=json.loads(scene_path.read_text())
    scene['objects'].append({'id':'step_marker','type':'group'})
    scene['tracks'].append({'target':'step_marker','property':'visible','interpolation':'step',
                            'keys':[[0,True],[.25,False],[.5,True]]})
    write_json(scene_path,scene)
    # Evaluate helper invariants inside the actual renderer, including cut shutter boundaries.
    module=root/kit['module']
    text=module.read_text().replace('helpers:H,assetURL,config','helpers:H,assetURL,config,entities')
    text=text.replace('update(t,f){',"update(t,f){if(f===6&&entities.get('step_marker').visible!==false)throw Error('Step key delayed at boundary');")
    text=text.replace('const group=new T.Group();', '''
  const cache=config._camera_cache,c=cache.cuts[0];
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  if(!same(H.sampleCamera(cache,c-.75),cache.poses[c-1])||!same(H.sampleCamera(cache,c-.25),cache.poses[c]))throw Error('Camera cut leaked across shutter');
  for(const shape of [H.roundedBox(),H.tube([[0,0,0],[0,0,0],[1,1,0]]),H.lathe([[0,0],[.5,0],[.5,1],[0,1]])]){
    if(![...shape.attributes.position.array].every(Number.isFinite))throw Error('Non-finite procedural geometry');
  }
  const group=new T.Group();''');module.write_text(text)
    preview=api.render_scene3d('fixture',kit['scene'],preview_frames=[0,5,6,11],trusted_script=True)
    checks['preview_and_shutter_assertions']=preview['determinism']['passed']
    checks['exact_step_key_boundary']=preview['determinism']['passed']
    full=api.render_scene3d('fixture',kit['scene'],trusted_script=True)
    pieces=[]
    for start,end in ((0,5),(6,11)):
        pieces.append(api.render_scene3d('fixture',kit['scene'],start=start,end=end,trusted_script=True))
    full_dir=root/full['clip']['frames_dir']
    checks['chunk_pixels_equal_full']=all(digest(root/r['clip']['frames_dir']/f'{i:05d}.png')==digest(full_dir/f'{r["source_frame_start"]+i:05d}.png') for r in pieces for i in range(r['frames']))
    states=json.loads((Path(full['output'])/'states.json').read_text())
    checks['display_clock']=all(row['authoring']['display_frame']==row['frame'] for row in states)
    checks['native_camera_cut']=states[5]['camera']['position'][0]>0 and states[6]['camera']['position'][0]<0
    checks['custom_geometry']=all(row['authoring']['custom_meshes']==4 and min(row['authoring']['geometry_vertices'])>0 for row in states)
    checks['three_not_blender']=full['runtime']['engine']=='Three.js' and full['runtime']['authoring']=='scene.js'
    checks['post_effects']=bool(full['runtime']['post']['bloom']) and bool(full['runtime']['post']['aperture'])
    checks['no_external_requests']=full['blocked_requests']==[]
    receipts=[Path(r['receipt']).relative_to(root).as_posix() for r in pieces]
    assembly=api.assemble_render_clips('fixture',receipts)
    try:api.assemble_render_clips('fixture',list(reversed(receipts)))
    except ContractError:checks['reordered_chunks_rejected']=True
    else:checks['reordered_chunks_rejected']=False
    score=api.synthesize_score('fixture',{'duration':.5,'notes':[{'at':0,'duration':.25,'midi':64,'waveform':'bell','gain':.1}]})
    timeline=assembly['timeline'];timeline['audio']={'mode':'mix','tracks':[{'src':Path(score['audio']).relative_to(root).as_posix(),'at':0,'volume':1}]}
    api.save_timeline('fixture',timeline,None)
    job=api.start_render('fixture','webgl-fixture');key=job.get('id') or job.get('job_id');deadline=time.monotonic()+180
    while job['state'] in ('queued','running'):
        if time.monotonic()>deadline:raise TimeoutError('Timeline export timed out')
        time.sleep(.5);job=api.get_render('fixture',key)
    assert job['state']=='succeeded',job
    info=probe(job['video_path']);stream=next(s for s in info['streams'] if s['codec_type']=='video')
    checks['timeline_and_audio']=int(stream['nb_read_frames'])==12 and any(s['codec_type']=='audio' for s in info['streams'])
    # An undeclared dependency is rejected before a successful receipt can be returned.
    module.write_text(text.replace('const group=new T.Group();',"await fetch(assetURL('undeclared.txt'));const group=new T.Group();"))
    (module.parent/'undeclared.txt').write_text('Original fixture')
    try:api.render_scene3d('fixture',kit['scene'],preview_frames=[0],trusted_script=True)
    except Exception as error:checks['undeclared_dependency_rejected']='fetch' in str(error).lower() or 'undeclared' in str(error).lower()
    else:checks['undeclared_dependency_rejected']=False
    module.write_text(text)
    import openkatana
    report={'passed':all(checks.values()),'checks':checks,'credits_used':0,'model_calls':0,
            'package':str(Path(openkatana.__file__).resolve()),
            'engine':full['runtime'],'video':job['video_path'],'receipts':receipts,'scene':kit['scene'],
            'source':'Original procedural fixture'}
    write_json(workspace/'validation.json',report);print(json.dumps(report,indent=2))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
