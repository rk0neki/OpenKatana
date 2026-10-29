"""Exercise typed media nodes against a local ComfyUI server; no models or paid calls."""
import argparse
import json
from pathlib import Path
import time
import uuid

from openkatana.render import probe, write_json
from scripts.test_comfy_apps_live import request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', default='http://127.0.0.1:8188')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--audio', help='Optional existing ComfyUI input audio filename for soundtrack round-trip')
    args = parser.parse_args()
    from openkatana.comfy import local_endpoint
    local_endpoint(args.endpoint)
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    info = request(args.endpoint, '/object_info')
    assert sum(n.startswith('OpenKatana') for n in info) == 85
    project = 'typed-' + uuid.uuid4().hex[:10]
    graph = {
        '1': {'class_type': 'EmptyImage', 'inputs': {'width': 160, 'height': 96, 'batch_size': 4, 'color': 3407837}},
        '2': {'class_type': 'OpenKatanaInterpolate', 'inputs': {'images': ['1',0], 'multiplier': 2}},
        '3': {'class_type': 'OpenKatanaImportMedia', 'inputs': {'images': ['2',0], 'project_id': project, 'fps': 8, 'rights': 'own'}},
        '4': {'class_type': 'OpenKatanaMakeEdit', 'inputs': {'media_id': ['3',0], 'project_id': project,
            'preset': 'ramp-freeze', 'seconds': 1, 'width': 160, 'height': 96, 'fps': 8, 'replace_existing': False}},
        '5': {'class_type': 'OpenKatanaRenderVideo', 'inputs': {'project_id': project, 'preview_frames': 4, 'after': ['4',0]}},
        # Import the returned VIDEO to prove a native typed round-trip too.
        '6': {'class_type': 'OpenKatanaImportMedia', 'inputs': {'video': ['5',0], 'project_id': project+'-roundtrip', 'fps': 8, 'rights': 'own'}},
        '7': {'class_type': 'SaveImage', 'inputs': {'images': ['5',1], 'filename_prefix': 'OpenKatana/typed-check'}},
    }
    if args.audio:
        graph['8'] = {'class_type': 'LoadAudio', 'inputs': {'audio': args.audio}}
        graph['3']['inputs']['audio'] = ['8', 0]
        graph['4']['inputs']['music_asset_id'] = ['3', 1]
    write_json(out/'prompt.json',graph)
    submitted = request(args.endpoint,'/prompt',{'prompt':graph,'client_id':'openkatana-typed-check'})
    write_json(out/'submitted.json',submitted)
    key=submitted['prompt_id']; deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        history=request(args.endpoint,'/history/'+key).get(key)
        if history:
            break
        time.sleep(.3)
    else:
        raise TimeoutError('Prompt did not complete: '+key)
    write_json(out/'history.json',history)
    assert history['status']['status_str']=='success',history['status']
    result=json.loads(history['outputs']['5']['text'][0])
    video=probe(result['video_path'])
    stream=next(s for s in video['streams'] if s['codec_type']=='video')
    assert stream['width']==160 and stream['height']==96 and int(stream['nb_read_frames'])==8
    imported=json.loads(history['outputs']['6']['text'][0])
    assert imported['asset']['clip']['n']==8
    if args.audio:
        assert any(s['codec_type']=='audio' for s in video['streams']), 'Soundtrack missing from VIDEO'
        assert imported['music_asset_id'] and imported['audio']['kind']=='audio', 'VIDEO audio was not re-imported'
    assert len(history['outputs']['7']['images'])==4
    write_json(out/'validation.json',{'passed':True,'nodes':85,'project':project,'prompt_id':key,
        'isolated_optical_flow':True,'image_import':True,'video_roundtrip':True,
        'typed_image_output':True,'audio_roundtrip':bool(args.audio),'timeline_render_frames':8,'video':result['video_path'],
        'model_inference_tested':False,'paid_calls':0})
    print(json.dumps({'passed':True,'video':result['video_path']}))


if __name__=='__main__':
    main()
