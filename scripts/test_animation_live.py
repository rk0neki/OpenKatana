"""Offline production-kit fixture through public API, installed Blender and normal timeline export.

Run from a checkout or installed source bundle with --workspace NEW_DIRECTORY.
Creates original tiny fixtures only; no model services or private project inputs.
"""
import argparse
import json
from pathlib import Path
import time

from openkatana.agent_api import AgentAPI
from openkatana.render import probe, write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);args=p.parse_args()
    workspace=args.workspace.resolve()
    if workspace.exists(): raise ValueError('Use a fresh workspace')
    api=AgentAPI(workspace);api.create_project('Original animation fixture','fixture')
    root=workspace/'fixture'
    kit=api.create_animation_kit('fixture',width=160,height=96,fps=24,frames=12)
    script=root/kit['script']
    # Assert the actual Blender 5 action-channel fix after all tracking constraints are attached.
    with script.open('a',encoding='utf8') as f:
        f.write('''
cuts=list(cam['openkatana_cuts'])
for owner in (cam,aim,cam.data):
    for curve in H.iter_fcurves(owner.animation_data.action):
        if curve.data_path.startswith('constraints['):
            assert all(k.interpolation=='LINEAR' for k in curve.keyframe_points)
        else:
            for k in curve.keyframe_points:
                if any(abs(float(k.co.x)-(c-1))<1e-6 for c in cuts):
                    assert k.interpolation=='CONSTANT', (curve.data_path, k.co.x)
for c in cuts:
    scene.frame_set(c-1,subframe=.25);a=cam.matrix_world.translation.copy()
    scene.frame_set(c-1);b=cam.matrix_world.translation.copy()
    assert (a-b).length<1e-6, 'Old camera leaked across pre-cut shutter'
    scene.frame_set(c-1,subframe=.75);a=cam.matrix_world.translation.copy()
    scene.frame_set(c);b=cam.matrix_world.translation.copy()
    assert (a-b).length<1e-6, 'New camera not stable at post-cut shutter'
observed={}
for frame in (0,5,6,11):
    scene.frame_set(frame);observed[frame]=tuple(cam.matrix_world.translation)
for frame in (11,6,5,0):
    scene.frame_set(frame);assert tuple(cam.matrix_world.translation)==observed[frame]
(ROOT/'live_assertions.json').write_text(json.dumps({'cut_keys_preserved':True,'shutter_cut_safe':True,'reverse_camera_seek':True}))
''')
    receipts=[]
    for start,end in ((0,5),(6,11)):
        r=api.render_blender('fixture',kit['script'],start=start,end=end,trusted_script=True)
        folder=Path(r['video']).parent
        receipts.append((folder/'receipt.json').relative_to(root).as_posix())
    assembled=api.assemble_blender_clips('fixture',receipts)
    score=api.synthesize_score('fixture',json.loads((root/'animation/score.json').read_text()))
    timeline=assembled['timeline']
    timeline['audio']={'mode':'mix','tracks':[{'src':Path(score['audio']).relative_to(root).as_posix(),'at':0,'volume':1}]}
    api.save_timeline('fixture',timeline,None)
    api.preview_timeline('fixture',frames=[0,5,6,11])
    job=api.start_render('fixture','animation-fixture-1')
    key=job.get('id') or job.get('job_id')
    deadline=time.monotonic()+180
    while True:
        job=api.get_render('fixture',key)
        if job['state'] not in ('queued','running'): break
        if time.monotonic()>deadline: raise TimeoutError('Timeline fixture timed out')
        time.sleep(.5)
    assert job['state']=='succeeded',job
    video=Path(job['video_path'])
    info=probe(video)
    stream=next(s for s in info['streams'] if s['codec_type']=='video')
    assert int(stream['nb_read_frames'])==12 and stream['width']==160 and stream['height']==96
    assert any(s['codec_type']=='audio' for s in info['streams'])
    motion=api.analyze_render_motion('fixture',str(video),cuts=[6],work_width=160)
    camera=api.analyze_camera_motion('fixture',json.loads((root/'animation/camera_samples.json').read_text()))
    assert camera['max_shutter_rotation_px']<50,camera
    result={'passed':True,'frames':12,'dimensions':[160,96],'fps':24,'audio':True,
            'blender_receipts':receipts,'video':str(video),'credits_used':0,
            'assertions':json.loads((root/'animation/live_assertions.json').read_text()),
            'motion_report':motion['report'],'camera_report':camera['report']}
    write_json(workspace/'validation.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
