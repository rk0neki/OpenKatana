"""Source preparation, supplied-font text, audio-copy and decoded timing checks."""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from openkatana.render import prepare, render, run, write_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--font',required=True,type=Path)
    args=p.parse_args()
    root=args.out.resolve(); root.mkdir(parents=True,exist_ok=False)
    sequence=root/'source'; sequence.mkdir()
    for n in range(30):
        im=Image.new('RGB',(640,360),'#102334')
        ImageDraw.Draw(im).rectangle((30+n*10,200,90+n*10,280),fill='#37dbac')
        im.save(sequence/f'{n:05d}.png')
    source=root/'source.mp4'
    run(['ffmpeg','-v','error','-framerate','30','-i',sequence/'%05d.png','-c:v','libx264','-pix_fmt','yuv420p',source])
    clip=prepare(source,root/'prepared')
    assert clip['n']==30 and clip['fps']==30
    # This tone is an audio transport test signal, not a creative soundtrack.
    run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=1:sample_rate=48000',
         '-c:a','aac','-b:a','128k',root/'test-signal.m4a'])
    shutil.copyfile(args.font,root/'supplied-font.ttf')
    edit={'canvas':{'w':640,'h':360,'fps':60,'frames':60,'bg':'#102334'},
          'clips':{'A':clip},'shots':[{'f0':0,'f1':60,'clip':'A'}],
          'fonts':[{'family':'SuppliedFont','url':'supplied-font.ttf'}],
          'text':[{'type':'font','text':'OpenKatana','family':'SuppliedFont','size':52,'fill':'#ffffff',
                   'f0':12,'f1':48,'pos':[.5,.3],'alpha':.8}],
          'audio':{'src':'test-signal.m4a','mode':'copy'}}
    write_json(root/'timeline.json',edit)
    receipt=render(root/'timeline.json',root/'render')
    assert receipt['audio_stream_unchanged'] is True
    def bright(frame):
        pixels=np.asarray(Image.open(root/'render'/'frames'/f'{frame:05d}.png').convert('RGB'))
        return int(np.count_nonzero(pixels[60:150].min(axis=2)>120))
    bounds={f:bright(f) for f in [11,12,47,48]}
    assert bounds[11]==0 and bounds[48]==0 and bounds[12]>100 and bounds[47]>100, bounds
    pts=json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-show_frames',
                        '-show_entries','frame=best_effort_timestamp_time','-of','json',root/'render'/'video.mp4']))['frames']
    pts_error=max(abs(float(x['best_effort_timestamp_time'])-i/60) for i,x in enumerate(pts))
    assert pts_error<1e-5
    result={'passed':True,'prepared_frames':clip['n'],'output_frames':receipt['frames'],
            'audio_stream_unchanged':True,'text_boundary_bright_pixels':bounds,
            'max_pts_error_seconds':pts_error,'reference_typography_parity':'not_tested',
            'audio_listening':'not_performed; diagnostic tone transport only'}
    write_json(root/'result.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
