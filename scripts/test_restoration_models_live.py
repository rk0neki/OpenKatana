"""Opt-in local RIFE/upscaler check using original moving shapes and installed weights.

No downloads or paid fallback. Reuse --out with --resume to collect recorded jobs.
Run from an installed environment to exercise the installed package.
"""
import argparse
import json
from pathlib import Path
import struct
import time
import wave

import numpy as np
from PIL import Image, ImageDraw
import openkatana
from openkatana.agent_api import AgentAPI
from openkatana.render import run, write_json


def frames(path):
    import subprocess
    data = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
                                    '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
    return np.frombuffer(data, dtype=np.uint8).reshape(-1, 96, 160, 3)


def center(frame):
    rgb = frame.astype(float)
    mask = (rgb[:,:,0] > 130) & (rgb[:,:,0] > rgb[:,:,1]*1.6) & (rgb[:,:,0] > rgb[:,:,2]*1.4)
    assert mask.sum() > 300, 'Moving object not found'
    return float(np.where(mask)[1].mean())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--rife', default='rife_v4.26.safetensors')
    p.add_argument('--upscaler', default='realesr-general-x4v3.pth')
    p.add_argument('--resume', action='store_true')
    args = p.parse_args()
    out = args.out.resolve()
    if not args.resume:
        out.mkdir(parents=True, exist_ok=False)
    api = AgentAPI(out/'projects')
    root = out/'projects/restoration'
    if not root.exists():
        api.create_project('Original restoration fixtures', 'restoration')
        seq = root/'frames'; seq.mkdir()
        for f in range(12):
            im = Image.new('RGB', (160,96), '#182638'); draw = ImageDraw.Draw(im)
            draw.line((0,80,159,80), fill='#41627a', width=2)
            x = 15+6*f
            draw.rounded_rectangle((x,28,x+25,64), radius=3, fill='#ed562c')
            draw.rectangle((x+9,35,x+12,56), fill='#ffe5c3')
            im.save(seq/f'{f:05d}.png')
        with wave.open(str(root/'tone.wav'), 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(24000)
            audio.writeframes(b''.join(struct.pack('<h', round(1200*np.sin(2*np.pi*330*i/24000))) for i in range(24000)))
        run(['ffmpeg','-v','error','-framerate','12','-i',seq/'%05d.png','-i',root/'tone.wav',
             '-c:v','libx264','-crf','10','-pix_fmt','yuv420p','-c:a','aac','-shortest',root/'moving.mp4'])
        im = Image.new('RGB',(128,128),'#182638');draw=ImageDraw.Draw(im)
        draw.rounded_rectangle((30,15,98,110),radius=10,fill='#ed562c')
        for x in range(43,87,6):
            draw.line((x,30,x,94),fill='#ffe5c3',width=2)
        im.save(root/'small.png')
    cases = {
        'model-interpolation': ({'model':args.rife,'fps':12,'multiplier':2},{'1.video':'moving.mp4'}),
        'image-upscale': ({'model':args.upscaler},{'1.image':'small.png'})}
    report = {}
    outputs = {}
    for kind, (parameters, assets) in cases.items():
        started = time.monotonic()
        while True:
            result = api.run_model_workflow('restoration',kind,parameters,assets,'test-'+kind)
            report[kind] = result
            write_json(out/'jobs.json',report)
            state = result['receipt']['state']
            print(kind,state,flush=True)
            if state == 'collected': break
            if state in ('failed','cancelled','submission_unknown'):
                raise RuntimeError(f'{kind}: {state}; inspect receipt, do not blindly resubmit')
            if time.monotonic()-started > 600:
                raise TimeoutError('Original job retained; rerun with --resume to collect')
            time.sleep(5)
        job = root/result['directory']
        paths = [job/x['file'] for x in result['receipt']['outputs']]
        outputs[kind] = paths[-1]

    source = frames(root/'moving.mp4')
    interpolated = frames(outputs['model-interpolation'])
    assert len(source)==12 and len(interpolated)==23
    sx = np.array([center(f) for f in source])
    ix = np.array([center(f) for f in interpolated])
    error = np.abs(ix[1::2]-(sx[:-1]+sx[1:])/2)
    assert error.max() < 2, ('Intermediate motion error', error.tolist())
    assert np.all(ix[1::2] > sx[:-1]+1) and np.all(ix[1::2] < sx[1:]-1)
    import subprocess
    media=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(outputs['model-interpolation'])]))
    assert next(s for s in media['streams'] if s['codec_type']=='video')['r_frame_rate']=='24/1'
    assert any(s['codec_type']=='audio' for s in media['streams'])
    up=Image.open(outputs['image-upscale']).convert('RGB')
    original=Image.open(root/'small.png').convert('RGB')
    assert up.size==(512,512)
    delta=np.abs(np.asarray(up).astype(float)-np.asarray(original.resize(up.size,Image.Resampling.BICUBIC)).astype(float)).mean()
    assert delta > .25, 'Upscale output unexpectedly matches bicubic'
    sheet=Image.new('RGB',(800,320),'#0c1119');d=ImageDraw.Draw(sheet)
    for i,frame in enumerate([source[3],interpolated[7],source[4]]):
        sheet.paste(Image.fromarray(frame).resize((240,144)),(i*260,20))
        d.text((i*260,4),['Source A','Generated midpoint','Source B'][i],fill='white')
    sheet.paste(original,(25,185));sheet.paste(up.resize((128,128)),(190,185))
    sheet.paste(up.crop((128,96,384,224)),(350,185))
    d.text((25,168),'Original / neural output downsample / output detail',fill='white')
    sheet.save(out/'contact.png')
    hashes={kind:result['receipt']['outputs'][-1]['sha256'] for kind,result in report.items()}
    result={'passed':True,'package_path':str(Path(openkatana.__file__).resolve()),
            'execution':'local official SDK',
            'weights_downloaded_by_this_script':False,'source_frames':12,'output_frames':23,
            'source_fps':12,'output_fps':24,'audio_preserved':True,
            'max_midpoint_position_error_pixels':float(error.max()),
            'upscale_input_size':[128,128],'upscale_output_size':list(up.size),
            'upscale_mean_absolute_difference_from_bicubic':float(delta),
            'output_sha256':hashes,'film_neural_execution_tested':False,
            'quality_scope':'Original moving-shape and line fixtures; not arbitrary footage or restoration ground truth.'}
    write_json(out/'validation.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
