"""Original adapters to public ComfyUI node interfaces. No model weights bundled."""
import math

PARAMETERS = {
    'qwen-edit': set('model encoder vae prompt negative references resolution steps seed'.split()),
    'h3-reference': set('model encoder vae audio_vae lora prompt width height length steps seed images videos audios ref_image_size'.split()),
    'seedvr2-restore': set('model vae scale seed'.split()),
    'model-interpolation': set('model multiplier fps'.split()),
    'image-upscale': {'model'},
}
NODES = {'MiniMaxH3ReferenceToVideo', 'LoadAudio', 'LoadVideo', 'GetVideoComponents',
         'ImageScaleBy', 'SeedVR2Preprocess', 'VAEEncodeTiled', 'SeedVR2TemporalChunk',
         'SeedVR2Conditioning', 'SeedVR2TemporalMerge', 'VAEDecodeTiled', 'SeedVR2PostProcessing',
         'FrameInterpolationModelLoader', 'FrameInterpolate', 'UpscaleModelLoader', 'ImageUpscaleWithModel'}
ASSETS = {('LoadVideo', 'file'), ('LoadAudio', 'audio')}


def integer(p, key, default, low, high):
    v = p.get(key, default)
    if type(v) is not int or not low <= v <= high:
        raise ValueError(f'{key} must be an integer in {low}..{high}')
    return v


def real(p, key, default, low, high):
    v = p.get(key, default)
    if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
        raise ValueError(f'{key} must be in {low}..{high}')
    return v


def component(p, key):
    v = p.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f'Provide an installed {key} filename; no automatic model download')
    return v


def node(name, **inputs):
    return {'class_type': name, 'inputs': inputs}


def build(kind, p):
    extra = set(p)-PARAMETERS[kind]
    if extra:
        raise ValueError(f'Unsupported {kind} parameters: {sorted(extra)}')
    if kind == 'qwen-edit':
        from .workflows import build as build_base
        g = build_base('qwen-generation', **{k: p[k] for k in ('model', 'encoder', 'vae', 'prompt', 'negative') if k in p})
        count = integer(p, 'references', 1, 1, 16)
        resolution = integer(p, 'resolution', 1024, 0, 2048)
        if resolution % 32:
            raise ValueError('resolution must be 0 or a multiple of 32')
        g['4']['inputs'].update(vae=['3', 0], resolution=resolution)
        for i in range(1, count+1):
            key = str(20+i)
            g[key] = node('LoadImage', image=f'reference-{i}.png')
            g['4']['inputs'][f'images.image_{i}'] = [key, 0]
        # Match the reference-conditioned latent geometry, not a disconnected empty latent.
        del g['5']
        g['7']['inputs'].update(latent_image=['4', 2], steps=integer(p, 'steps', 25, 1, 100), seed=integer(p, 'seed', 1, 0, 2**64-1))
        return g
    if kind == 'h3-reference':
        from .workflows import build as build_base
        # Reuse only our own AV sampler scaffold; reference models do not get an FL2V LoRA by default.
        g = build_base('h3-generation', **{k: component(p,k) for k in ('model','encoder','vae','audio_vae')},
                       lora=p.get('lora') or 'not-used', input_mode='t2v', prompt=p.get('prompt',''),
                       width=p.get('width',864),height=p.get('height',480),length=p.get('length',124),
                       steps=integer(p,'steps',20,1,100),seed=integer(p,'seed',1,0,2**64-1))
        if not p.get('lora'):
            del g['5']
            g['8']['inputs']['model'] = g['10']['inputs']['model'] = ['1',0]
        size = p.get('ref_image_size','match')
        if size not in ('match','max'):raise ValueError('ref_image_size must be match or max')
        inputs = {k:g['7']['inputs'][k] for k in ('clip','prompt','width','height','length')}
        inputs.update(vae=['3',0],audio_vae=['4',0],ref_image_size=size)
        counts = [integer(p,'images',1,0,9),integer(p,'videos',0,0,3),integer(p,'audios',0,0,3)]
        if not sum(counts):raise ValueError('At least one image, video or audio reference is required')
        for i in range(counts[0]):
            k=str(20+i);g[k]=node('LoadImage',image=f'picture-{i+1}.png');inputs[f'ref_images.ref_image_{i}']=[k,0]
        for i in range(counts[1]):
            k=str(40+i)
            # Deliberate 24 fps, at most the generation duration. Original soundtrack is not implicitly used.
            g[k]=node('VHS_LoadVideo',video=f'video-{i+1}.mp4',force_rate=24,custom_width=0,custom_height=0,frame_load_cap=p.get('length',124),skip_first_frames=0,select_every_nth=1)
            inputs[f'ref_videos.ref_video_{i}']=[k,0]
        for i in range(counts[2]):
            k=str(60+i);g[k]=node('LoadAudio',audio=f'audio-{i+1}.wav');inputs[f'ref_audios.ref_audio_{i}']=[k,0]
        g['7']=node('MiniMaxH3ReferenceToVideo',**inputs)
        return g
    if kind == 'seedvr2-restore':
        scale=real(p,'scale',2,1,4)
        return {
            '1':node('LoadVideo',file='source.mp4'), '2':node('GetVideoComponents',video=['1',0]),
            '3':node('UNETLoader',unet_name=component(p,'model'),weight_dtype='default'),
            '4':node('VAELoader',vae_name=component(p,'vae')),
            '5':node('ImageScaleBy',image=['2',0],upscale_method='lanczos',scale_by=scale),
            '6':node('SeedVR2Preprocess',resized_images=['5',0]),
            '7':node('VAEEncodeTiled',pixels=['6',0],vae=['4',0],tile_size=512,overlap=128,temporal_size=64,temporal_overlap=8),
            '8':node('SeedVR2TemporalChunk',latent=['7',0],temporal_overlap=0,chunking_mode='auto'),
            '9':node('SeedVR2Conditioning',model=['3',0],vae_conditioning=['8',0]),
            '10':node('KSampler',model=['3',0],positive=['9',0],negative=['9',1],latent_image=['8',0],seed=integer(p,'seed',1,0,2**64-1),steps=1,cfg=1.,sampler_name='euler',scheduler='simple',denoise=1.),
            '11':node('SeedVR2TemporalMerge',latents=['10',0],temporal_overlap=['8',1]),
            '12':node('VAEDecodeTiled',samples=['11',0],vae=['4',0],tile_size=512,overlap=128,temporal_size=64,temporal_overlap=8),
            '13':node('SeedVR2PostProcessing',images=['12',0],original_resized_images=['5',0],color_correction_method='lab'),
            '14':node('CreateVideo',images=['13',0],audio=['2',1],fps=['2',2]),
            '15':node('SaveVideo',video=['14',0],filename_prefix='OpenKatana/restored',format='auto',**{'format.codec':'auto'})}
    if kind == 'model-interpolation':
        multiplier=integer(p,'multiplier',2,2,16)
        fps=real(p,'fps',24,1,120)
        if fps*multiplier>120:raise ValueError('Output fps exceeds the core CreateVideo limit of 120')
        return {'1':node('VHS_LoadVideo',video='source.mp4',force_rate=fps,custom_width=0,custom_height=0,frame_load_cap=0,skip_first_frames=0,select_every_nth=1),
                '2':node('FrameInterpolationModelLoader',model_name=component(p,'model')),
                '3':node('FrameInterpolate',interp_model=['2',0],images=['1',0],multiplier=multiplier),
                '4':node('CreateVideo',images=['3',0],audio=['1',2],fps=fps*multiplier),
                '5':node('SaveVideo',video=['4',0],filename_prefix='OpenKatana/interpolated',format='auto',**{'format.codec':'auto'})}
    if kind == 'image-upscale':
        return {'1':node('LoadImage',image='source.png'), '2':node('UpscaleModelLoader',model_name=component(p,'model')),
                '3':node('ImageUpscaleWithModel',upscale_model=['2',0],image=['1',0]),
                '4':node('SaveImage',images=['3',0],filename_prefix='OpenKatana/upscaled')}
    raise ValueError('Unknown workflow')


def asset_ports(graph):
    from .workflows import ASSET_INPUTS
    return {f'{key}.{name}':value for key,n in graph.items() for name,value in n['inputs'].items() if (n['class_type'],name) in ASSET_INPUTS}
