"""Place, trim, fade and mix supplied recordings without synthesizing audio.

Validation and rendering share one track planner (`plan_tracks`), so every problem that can be known before rendering
(missing audio stream, trim beyond the recording, fades longer than the span, nothing inside the output interval,
copy-mode length, clipping without the limiter) is reported by validate_timeline instead of by a failed render job.
"""
from pathlib import Path
import subprocess
import tempfile
import numpy as np
from .contracts import ContractError,fields,number,local_path


def _stream_info(path):
    from .render import probe
    try:info=probe(path)
    except Exception as e:raise ContractError(f'Cannot read audio source {Path(path).name}: {e}') from e
    stream=next((s for s in info['streams'] if s['codec_type']=='audio'),None)
    if not stream:raise ContractError(f'No audio stream: {Path(path).name}')
    total=float(stream.get('duration') or info['format'].get('duration') or 0)
    return stream,total


def validate_audio(audio,root=None,duration=None):
    if audio is None:return
    if not isinstance(audio,dict):raise ContractError('audio must be an object')
    if audio.get('mode')=='copy':
        fields(audio,'src mode','audio')
        if not isinstance(audio.get('src'),str):raise ContractError('audio.src is required')
        if root:
            path=local_path(root,audio['src'])
            if not path.is_file():raise ContractError('Soundtrack missing')
            _stream,total=_stream_info(path)
            if duration is not None and total>duration+.05:
                raise ContractError(f'audio copy keeps the recording unchanged, but it is {total:.3f} s and the timeline is {duration:.3f} s; '
                                    'use mode "mix" with start/duration to trim it')
        return
    fields(audio,'mode tracks gain limiter loudness duck cues','audio')
    if audio.get('mode')!='mix':raise ContractError('Audio mode must be copy or mix')
    cues=audio.get('cues',[])
    if not isinstance(cues,list) or len(cues)>256:raise ContractError('audio.cues: up to 256 sound-effect cues')
    from .sfx import validate_cue
    for j,c in enumerate(cues):validate_cue(c,f'audio.cues[{j}]')
    tracks=audio.get('tracks',[])
    if not isinstance(tracks,list) or not (1 if not cues else 0)<=len(tracks)<=64:raise ContractError('audio.tracks requires 1..64 recordings (or cues); omit audio for silence')
    number(audio.get('gain',1),'audio.gain',0,16)
    if not isinstance(audio.get('limiter',False),bool):raise ContractError('audio.limiter must be boolean')
    for t in tracks:
        fields(t,'src start at duration volume fade_in fade_out speed','audio track')
        if not isinstance(t.get('src'),str):raise ContractError('Track src is required')
        for k in ('start','at','duration','volume','fade_in','fade_out','speed'):
            if k in t:number(t[k],'audio.'+k,.001 if k in ('duration','speed') else 0,16 if k=='volume' else 4 if k=='speed' else None)
        if root and not local_path(root,t['src']).is_file():raise ContractError('Audio track missing')
    if 'loudness' in audio:   # audit F-AUD-005: integrated loudness target with a true-peak ceiling
        L=audio['loudness'];fields(L,'lufs true_peak lra','audio.loudness')
        number(L.get('lufs'),'audio.loudness.lufs',-40,-5);number(L.get('true_peak',-1.5),'audio.loudness.true_peak',-9,0)
        number(L.get('lra',11),'audio.loudness.lra',1,20)
    for j,d in enumerate(audio.get('duck',[]) if isinstance(audio.get('duck',[]),list) else [None]):
        where=f'audio.duck[{j}]'
        if not isinstance(d,dict):raise ContractError('audio.duck: list of {track, under, db, threshold_db, attack, release}')
        fields(d,'track under db threshold_db attack release',where)
        for k in ('track','under'):number(d.get(k),f'{where}.{k}',0,len(tracks)-1,integer=True)
        if d['track']==d['under']:raise ContractError(f'{where}: a track cannot duck under itself')
        number(d.get('db',-10),f'{where}.db',-60,0);number(d.get('threshold_db',-40),f'{where}.threshold_db',-80,0)
        number(d.get('attack',.05),f'{where}.attack',.001,2);number(d.get('release',.3),f'{where}.release',.01,5)
    if root and duration is not None:
        audio=expanded(audio,root)
        plan=plan_tracks(audio,root,duration)
        if not audio.get('limiter') and 'loudness' not in audio:_check_clipping(audio,root,duration,plan)


def expanded(audio,root):
    """Mix with each sound-effect cue appended as a track of its generated file (audit F-SFX-001)."""
    if not audio or audio.get('mode')!='mix' or not audio.get('cues'):return audio
    from .sfx import cue_track
    return {**{k:v for k,v in audio.items() if k!='cues'},'tracks':list(audio.get('tracks',[]))+[cue_track(c,root) for c in audio['cues']]}


def plan_tracks(audio,root,duration):
    """Resolve every track against its recording and the output interval; raise ContractError on anything unrenderable."""
    plan=[]
    for i,t in enumerate(audio['tracks']):
        path=local_path(root,t['src']);_stream,total=_stream_info(path)
        start=t.get('start',0);at=t.get('at',0);speed=t.get('speed',1);label=f'audio track {i} ({t["src"]})'
        if at>=duration:raise ContractError(f'{label}: placed at {at} s, at or after the end of the {duration:.3f} s timeline')
        if start>=total:raise ContractError(f'{label}: start {start} s is beyond the {total:.3f} s recording')
        span=min(t.get('duration',max(0,(total-start)/speed)),duration-at)
        if span<=0:raise ContractError(f'{label}: no samples inside the output interval')
        if start+span*speed>total+.002:
            raise ContractError(f'{label}: trim {start}+{span*speed:.3f} s extends beyond the {total:.3f} s recording (duration is output seconds after speed)')
        if t.get('fade_in',0)+t.get('fade_out',0)>span:raise ContractError(f'{label}: fades ({t.get("fade_in",0)}+{t.get("fade_out",0)} s) exceed its {span:.3f} s span')
        plan.append({'path':path,'src':t['src'],'start':start,'at':at,'span':span,'speed':speed,'total':total,'track':t})
    return plan


def _segment_peak(p):
    raw=subprocess.run(['ffmpeg','-v','error','-ss',str(p['start']),'-t',str(p['span']*p['speed']),'-i',str(p['path']),'-ac','2','-f','f32le','-'],
                       capture_output=True,check=True,stdin=subprocess.DEVNULL).stdout
    samples=np.frombuffer(raw,dtype='<f4')
    return float(np.max(np.abs(samples),initial=0))


def _check_clipping(audio,root,duration,plan):
    bound=sum(_segment_peak(p)*p['track'].get('volume',1) for p in plan)*audio.get('gain',1)
    if bound<=1.00001:return
    with tempfile.TemporaryDirectory() as tmp:
        peak=_render_mix(audio,root,Path(tmp)/'check.wav',duration,plan)[1]
    if peak>1.00001:
        raise ContractError(f'Audio mix clips (peak {peak:.3f} > 1.0). Lower gain/track volumes or set audio.limiter true')


def source_paths(audio):
    if not audio:return []
    return [audio['src']] if audio['mode']=='copy' else [t['src'] for t in audio['tracks']]


def _track_chain(p):
    t=p['track'];start,at,speed,span=p['start'],p['at'],p['speed'],p['span']
    chain=[f'atrim=start={start}:duration={span*speed}','asetpts=PTS-STARTPTS','aresample=48000','aformat=sample_fmts=fltp:channel_layouts=stereo']
    rate=speed
    while rate<.5:chain.append('atempo=0.5');rate/=.5
    while rate>2:chain.append('atempo=2');rate/=2
    if rate!=1:chain.append(f'atempo={rate}')
    chain+=[f'atrim=duration={span}',f'volume={t.get("volume",1)}']
    if t.get('fade_in'):chain.append(f'afade=t=in:st=0:d={t["fade_in"]}')
    if t.get('fade_out'):chain.append(f'afade=t=out:st={span-t["fade_out"]}:d={t["fade_out"]}')
    chain.append(f'adelay={round(at*48000)}S:all=1')
    return chain


def _ducked_mix(audio,target,duration,plan):
    """Ducking (audit F-AUD-005): tracks rendered separately; while the `under` track's level is above threshold_db the
    `track` is lowered by `db`, with attack/release smoothing; then summed, gain and optional limiter applied."""
    from .render import run
    n=round(duration*48000);signals=[]
    for p in plan:
        chain=_track_chain(p)+[f'apad=whole_len={n}',f'atrim=end_sample={n}']
        raw=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(p['path']),'-af',','.join(chain),'-ar','48000','-ac','2','-f','f32le','-'],
                           capture_output=True,check=True,stdin=subprocess.DEVNULL).stdout
        x=np.frombuffer(raw,dtype='<f4').reshape(-1,2)[:n];signals.append(np.pad(x,((0,n-len(x)),(0,0))))
    gains=[np.ones(n,dtype=np.float32) for _ in plan];win=480   # 10 ms level windows
    for d in audio.get('duck',[]):
        sc=signals[d['under']].mean(axis=1);m=n//win
        level=20*np.log10(np.maximum(1e-9,np.sqrt(np.mean(sc[:m*win].reshape(m,win)**2,axis=1))))
        active=(level>d.get('threshold_db',-40)).astype(np.float32)
        a=1-np.exp(-win/(48000*d.get('attack',.05)));r=1-np.exp(-win/(48000*d.get('release',.3)));env=np.zeros(m,dtype=np.float32);v=0.0
        for k in range(m):
            v+=(a if active[k]>v else r)*(active[k]-v);env[k]=v
        g=10**(d.get('db',-10)*np.repeat(env,win)/20);g=np.pad(g,(0,n-len(g)),mode='edge')
        gains[d['track']]=np.minimum(gains[d['track']],g.astype(np.float32))
    mixed=sum(s*g[:,None] for s,g in zip(signals,gains))*audio.get('gain',1)
    tmp=Path(str(target)+'.ducked.f32')
    tmp.write_bytes(mixed.astype('<f4').tobytes())
    af=['alimiter=limit=0.95:level=0:latency=1'] if audio.get('limiter') else ['anull']
    run(['ffmpeg','-v','error','-f','f32le','-ar','48000','-ac','2','-i',tmp,'-af',','.join(af),'-c:a','pcm_f32le',target]);tmp.unlink()


def _render_mix(audio,root,target,duration,plan):
    from .render import run
    if audio.get('duck'):
        _ducked_mix(audio,target,duration,plan)
        placements=[{'src':p['src'],'source_start':p['start'],'output_start':p['at'],'output_duration':p['span'],'speed':p['speed']} for p in plan]
        result=subprocess.run(['ffmpeg','-v','error','-i',str(target),'-f','f32le','-'],capture_output=True,check=True,stdin=subprocess.DEVNULL)
        samples=np.frombuffer(result.stdout,dtype='<f4');return placements,float(np.max(np.abs(samples),initial=0)),len(samples)//2
    args=['ffmpeg','-v','error'];filters=[];labels=[];placements=[]
    for i,p in enumerate(plan):
        t=p['track'];start,at,speed,span=p['start'],p['at'],p['speed'],p['span']
        args+=['-i',p['path']]
        chain=[f'atrim=start={start}:duration={span*speed}','asetpts=PTS-STARTPTS','aresample=48000','aformat=sample_fmts=fltp:channel_layouts=stereo']
        rate=speed
        while rate<.5:chain.append('atempo=0.5');rate/=.5
        while rate>2:chain.append('atempo=2');rate/=2
        if rate!=1:chain.append(f'atempo={rate}')
        chain+=[f'atrim=duration={span}',f'volume={t.get("volume",1)}']
        if t.get('fade_in'):chain.append(f'afade=t=in:st=0:d={t["fade_in"]}')
        if t.get('fade_out'):chain.append(f'afade=t=out:st={span-t["fade_out"]}:d={t["fade_out"]}')
        chain.append(f'adelay={round(at*48000)}S:all=1')
        filters.append(f'[{i}:a:0]'+','.join(chain)+f'[a{i}]');labels.append(f'[a{i}]')
        placements.append({'src':p['src'],'source_start':start,'output_start':at,'output_duration':span,'speed':speed})
    tail=f'amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,volume={audio.get("gain",1)}'
    if audio.get('limiter'):tail+=',alimiter=limit=0.95:level=0:latency=1'
    # Both pad and output have finite sample bounds. Never use an unbounded apad
    # source: some FFmpeg builds keep draining it after a downstream atrim ends.
    sample_count=round(duration*48000)
    tail+=f',apad=whole_len={sample_count},atrim=end_sample={sample_count}[mix]'
    filters.append(''.join(labels)+tail)
    run(args+['-filter_complex',';'.join(filters),'-map','[mix]','-ar','48000','-t',str(duration),'-c:a','pcm_f32le',target])
    result=subprocess.run(['ffmpeg','-v','error','-i',str(target),'-f','f32le','-'],capture_output=True,check=True,stdin=subprocess.DEVNULL)
    samples=np.frombuffer(result.stdout,dtype='<f4');peak=float(np.max(np.abs(samples),initial=0))
    return placements,peak,len(samples)//2


def measure_loudness(path,target=None):
    """loudnorm analysis pass: integrated loudness, true peak, LRA, threshold (and target offset when given)."""
    import json as _json,re
    L=target or {'lufs':-23,'true_peak':-1,'lra':11}
    err=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-nostats','-i',str(path),'-af',
                        f'loudnorm=I={L["lufs"]}:TP={L.get("true_peak",-1.5)}:LRA={L.get("lra",11)}:print_format=json','-f','null','-'],
                       capture_output=True,text=True,errors='replace',stdin=subprocess.DEVNULL).stderr
    return _json.loads(re.findall(r'\{[^{}]*\}',err)[-1])


def _normalise(target,L):
    from .render import run
    m=measure_loudness(target,L);tmp=Path(str(target)+'.norm.wav')
    run(['ffmpeg','-v','error','-i',target,'-af',
         f'loudnorm=I={L["lufs"]}:TP={L.get("true_peak",-1.5)}:LRA={L.get("lra",11)}:measured_I={m["input_i"]}:measured_TP={m["input_tp"]}:'
         f'measured_LRA={m["input_lra"]}:measured_thresh={m["input_thresh"]}:offset={m["target_offset"]}:linear=true',
         '-ar','48000','-ac','2','-c:a','pcm_f32le',tmp])
    tmp.replace(target)
    after=measure_loudness(target,L)
    return {'target':{'lufs':L['lufs'],'true_peak':L.get('true_peak',-1.5),'lra':L.get('lra',11)},
            'before':{'lufs':float(m['input_i']),'true_peak':float(m['input_tp']),'lra':float(m['input_lra'])},
            'after':{'lufs':float(after['input_i']),'true_peak':float(after['input_tp']),'lra':float(after['input_lra'])},
            'mode':m.get('normalization_type','linear'),'tool':'ffmpeg loudnorm (two-pass)'}


def mix(audio,root:Path,target:Path,duration:float):
    validate_audio(audio,root)
    cues=audio.get('cues')
    audio=expanded(audio,root)
    plan=plan_tracks(audio,root,duration)
    placements,peak,frames=_render_mix(audio,root,target,duration,plan)
    loudness=None
    if audio.get('loudness'):
        loudness=_normalise(target,audio['loudness'])
        result=subprocess.run(['ffmpeg','-v','error','-i',str(target),'-f','f32le','-'],capture_output=True,check=True,stdin=subprocess.DEVNULL)
        samples=np.frombuffer(result.stdout,dtype='<f4');peak=float(np.max(np.abs(samples),initial=0))
    receipt={'peak':peak,'sample_frames':frames,'sample_rate':48000,'duration':duration,'placements':placements,'limiter':audio.get('limiter',False),
             'loudness':loudness,'duck':audio.get('duck'),'cues':cues}
    if peak>1.00001:raise ContractError('Audio mix clips. Lower gain/track volumes or explicitly enable the limiter')
    return receipt
