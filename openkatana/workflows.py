"""Local Comfy workflow builders and discovery. No credentials or downloads."""
import json
import urllib.request
from pathlib import Path
from .comfy import local_endpoint
from .render import write_json

LOCAL_NODES={'CheckpointLoaderSimple','CLIPTextEncode','EmptyLatentImage','KSampler','VAEDecode','VAEEncode',
             'LoadRembgByBiRefNetModel','RembgByBiRefNet','ImageBatch','OpenKatanaMatte','OpenKatanaInterpolate',
             'UNETLoader','CLIPLoader','VAELoader','TextEncodeQwenImage21','QwenImage21Cache',
             'VHS_LoadVideo','DownloadAndLoadSAM2Model','Sam2VideoSegmentationAddPoints','Sam2VideoSegmentation','OpenKatanaPoints'}
# Local H3 sampling/encoding only. No partner nodes or automatic model loaders.
LOCAL_NODES.update({'MiniMaxH3ImageToVideo','LoraLoaderModelOnly','BasicGuider','KSamplerSelect',
                    'BasicScheduler','RandomNoise','SamplerCustomAdvanced','VAEDecodeAudio',
                    'CreateVideo','SaveVideo','MiniMaxH3MemoryEfficientSageAttentionPatch'})
from .model_workflows import NODES as MODEL_NODES, PARAMETERS as MODEL_PARAMETERS, ASSETS as MODEL_ASSETS
LOCAL_NODES.update(MODEL_NODES)
# Inputs filled by an uploaded asset at submission, so their placeholder is not checked against the installed list.
ASSET_INPUTS={('LoadImage','image'),('VHS_LoadVideo','video')} | MODEL_ASSETS

def sam2_file(model,precision):
    """File the SAM2 loader node reads for this choice (2.1 models below fp32 use the -fp16 file)."""
    base,_,ext=model.rpartition('.')
    return f'{base}-fp16.{ext}' if precision!='fp32' and '2.1' in model else model

def installed_models(endpoint,folder):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f'{local_endpoint(endpoint)}/models/{folder}',timeout=15) as r:return {x.replace(chr(92),'/') for x in json.load(r)}
    except Exception:return set()

def capabilities(endpoint='http://127.0.0.1:8000',reviewed_local_nodes=None):
    endpoint=local_endpoint(endpoint)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(endpoint+'/object_info',timeout=15) as r:data=json.load(r)
    from .comfy import BASE_NODES,reviewed_nodes
    return {name:value for name,value in data.items() if name in LOCAL_NODES|BASE_NODES|reviewed_nodes(reviewed_local_nodes)}

def preflight(graph,endpoint,reviewed_local_nodes=None):
    info=capabilities(endpoint,reviewed_local_nodes) if reviewed_local_nodes else capabilities(endpoint)
    errors=[]
    for node_id,node in graph.items():
        name=node['class_type']
        if name not in info:errors.append(f'{node_id}: missing local node {name}');continue
        spec=info[name]
        if spec.get('api_node'):errors.append(f'{node_id}: hosted API nodes are not permitted')
        required=spec.get('input',{}).get('required',{})
        optional=spec.get('input',{}).get('optional',{})
        for key,rule in {**optional,**required}.items():
            if key not in required and key not in node['inputs']:continue
            # A V3 autogrow container never appears under its own key: the workflow carries its flattened ports
            # (images.image0, ...). check_graph validates those ports and the template's minimum count.
            if rule[0]=='COMFY_AUTOGROW_V3':continue
            if key not in node['inputs']:errors.append(f'{node_id}.{key}: missing required input');continue
            value=node['inputs'][key]
            choices=rule[0] if isinstance(rule[0],list) else (rule[1].get('options') if rule[0]=='COMBO' and len(rule)>1 else None)
            linked=isinstance(value,list) and len(value)==2 and str(value[0]) in graph
            if not linked and (name,key) not in ASSET_INPUTS and choices is not None and value not in choices:errors.append(f'{node_id}.{key}: value/model not installed: {value}')
        if name=='DownloadAndLoadSAM2Model':
            # This third-party loader downloads a missing file; OpenKatana only submits it when the file is present.
            wanted=sam2_file(str(node['inputs'].get('model','')),node['inputs'].get('precision','fp16'))
            if wanted not in installed_models(endpoint,'sam2'):
                errors.append(f'{node_id}.model: models/sam2/{wanted} is not installed (this loader would download it; OpenKatana never submits downloads)')
    from .workflow_schema import check_graph
    errors.extend(check_graph(graph,info,ASSET_INPUTS))
    errors=list(dict.fromkeys(errors))
    return {'ready':not errors,'errors':errors,'endpoint':endpoint,'nodes':sorted({n['class_type'] for n in graph.values()})}

PARAMETERS={'segmentation':{'model'},'matte':{'key','tolerance','softness'},'interpolation':{'multiplier'},
            'generation':{'model','prompt','negative','width','height','seed','steps'},
            'qwen-generation':{'model','encoder','vae','prompt','negative','width','height','seed','steps'},
            'cutout':{'model','positive','negative','device','precision'}}
PARAMETERS['h3-generation']={'model','encoder','vae','audio_vae','lora','prompt','width','height',
                             'length','steps','seed','input_mode','sage_attention'}

PARAMETERS.update(MODEL_PARAMETERS)

def points(value,name,required):
    """Click points as [[x, y], ...] in 0..1 frame coordinates."""
    if value is None:value=[]
    if not isinstance(value,list) or (required and not value):
        raise ValueError(f'{name}: give at least one [x, y] point in 0..1 frame coordinates' if required else f'{name}: expected a list of [x, y] points')
    for p in value:
        if not (isinstance(p,list) and len(p)==2 and all(isinstance(v,(int,float)) and not isinstance(v,bool) and 0<=v<=1 for v in p)):
            raise ValueError(f'{name}: each point is [x, y] with both values in 0..1, got {p!r}')
    return [[float(x),float(y)] for x,y in value]


def build(kind,**p):
    if kind not in PARAMETERS:raise ValueError('Unknown workflow kind')
    unknown=sorted(set(p)-PARAMETERS[kind])
    if unknown:raise ValueError(f'Unsupported {kind} parameters: {", ".join(unknown)} (supported: {", ".join(sorted(PARAMETERS[kind]))})')
    def node(name,**inputs):return {'class_type':name,'inputs':inputs}
    if kind in MODEL_PARAMETERS:
        from .model_workflows import build as build_model
        return build_model(kind,p)
    if kind=='h3-generation':
        if not all(isinstance(p.get(k),str) and p[k].strip() for k in ('model','encoder','vae','audio_vae','lora')):
            raise ValueError('H3 requires installed model, encoder, vae, audio_vae and FL2V turbo lora filenames')
        width,height=p.get('width',864),p.get('height',480)
        if any(type(v) is not int or not 256<=v<=2048 or v%32 for v in (width,height)):
            raise ValueError('H3 dimensions must be multiples of 32 between 256 and 2048')
        length=p.get('length',107)
        if type(length) is not int or not 5<=length<=362 or (length-5)%17:
            raise ValueError('H3 length must be 17k+5 frames between 5 and 362, at 24 fps')
        steps,seed=p.get('steps',8),p.get('seed',1)
        if type(steps) is not int or not 1<=steps<=100 or type(seed) is not int or not 0<=seed<2**64:
            raise ValueError('H3 steps must be 1..100 and seed an unsigned 64-bit integer')
        mode=p.get('input_mode','i2v')
        if mode not in ('t2v','i2v','first-last'):raise ValueError('H3 input_mode must be t2v, i2v or first-last')
        sage=p.get('sage_attention',False)
        if type(sage) is not bool:raise ValueError('sage_attention must be a boolean')
        model=['6',0] if sage else ['5',0]
        graph={
            '1':node('UNETLoader',unet_name=p['model'],weight_dtype='default'),
            '2':node('CLIPLoader',clip_name=p['encoder'],type='minimax',device='default'),
            '3':node('VAELoader',vae_name=p['vae']),
            '4':node('VAELoader',vae_name=p['audio_vae']),
            '5':node('LoraLoaderModelOnly',model=['1',0],lora_name=p['lora'],strength_model=1.),
            '7':node('MiniMaxH3ImageToVideo',clip=['2',0],vae=['3',0],prompt=p.get('prompt',''),width=width,height=height,length=length),
            '8':node('BasicGuider',model=model,conditioning=['7',0]),
            '9':node('KSamplerSelect',sampler_name='res_multistep'),
            '10':node('BasicScheduler',model=model,scheduler='simple',steps=steps,denoise=1.),
            '11':node('RandomNoise',noise_seed=seed),
            '12':node('SamplerCustomAdvanced',noise=['11',0],guider=['8',0],sampler=['9',0],sigmas=['10',0],latent_image=['7',1]),
            '13':node('VAEDecode',samples=['12',0],vae=['3',0]),
            '14':node('VAEDecodeAudio',samples=['12',0],vae=['4',0]),
            '15':node('CreateVideo',images=['13',0],audio=['14',0],fps=24),
            '16':node('SaveVideo',video=['15',0],filename_prefix='OpenKatana/generated-h3',format='auto',**{'format.codec':'auto'})}
        if sage:graph['6']=node('MiniMaxH3MemoryEfficientSageAttentionPatch',model=['5',0])
        if mode!='t2v':
            graph['17']=node('LoadImage',image='first-frame.png');graph['7']['inputs']['first_frame']=['17',0]
        if mode=='first-last':
            graph['18']=node('LoadImage',image='last-frame.png');graph['7']['inputs']['last_frame']=['18',0]
        return graph
    if kind=='segmentation':
        if not p.get('model'):raise ValueError('Specify an already installed BiRefNet model filename')
        return {'1':node('LoadImage',image='input.png'),
                '2':node('LoadRembgByBiRefNetModel',model=p['model'],device='CPU',dtype='float32'),
                '3':node('RembgByBiRefNet',model=['2',0],images=['1',0]),
                '4':node('MaskToImage',mask=['3',1]),'5':node('SaveImage',images=['4',0],filename_prefix='OpenKatana/matte')}
    if kind=='cutout':
        # Point-prompted subject cut-out: clicks on the clip's first frame, propagated forward through the clip by a
        # SAM2 video model. The whole clip is one uploaded video, so the job returns one mask per source frame.
        if not p.get('model'):raise ValueError('Specify an installed SAM2 model choice, e.g. sam2.1_hiera_base_plus.safetensors')
        positive=points(p.get('positive'),'positive',True);negative=points(p.get('negative'),'negative',False)
        add={'sam2_model':['2',0],'coordinates_positive':['3',0],'frame_index':0,'object_index':0,'image':['1',0]}
        if negative:add['coordinates_negative']=['3',1]
        return {'1':node('VHS_LoadVideo',video='input.mp4',force_rate=0,custom_width=0,custom_height=0,frame_load_cap=0,skip_first_frames=0,select_every_nth=1),
                '2':node('DownloadAndLoadSAM2Model',model=p['model'],segmentor='video',device=p.get('device','cuda'),precision=p.get('precision','fp16')),
                '3':node('OpenKatanaPoints',image=['1',0],positive=json.dumps(positive),negative=json.dumps(negative)),
                '4':node('Sam2VideoSegmentationAddPoints',**add),
                '5':node('Sam2VideoSegmentation',sam2_model=['4',0],inference_state=['4',1],keep_model_loaded=False),
                '6':node('MaskToImage',mask=['5',0]),'7':node('SaveImage',images=['6',0],filename_prefix='OpenKatana/cutout')}
    if kind=='matte':return {'1':node('LoadImage',image='input.png'),
        '2':node('OpenKatanaMatte',image=['1',0],key=p.get('key','#00ff00'),tolerance=p.get('tolerance',.18),softness=p.get('softness',.08)),
        '3':node('MaskToImage',mask=['2',0]),'4':node('SaveImage',images=['3',0],filename_prefix='OpenKatana/matte')}
    if kind=='interpolation':return {'1':node('LoadImage',image='first.png'),'2':node('LoadImage',image='second.png'),
        '3':node('ImageBatch',image1=['1',0],image2=['2',0]),'4':node('OpenKatanaInterpolate',images=['3',0],multiplier=p.get('multiplier',2)),
        '5':node('SaveImage',images=['4',0],filename_prefix='OpenKatana/interpolated')}
    if kind=='generation':
        if not p.get('model'):raise ValueError('Specify an installed diffusion checkpoint filename')
        return {'1':node('CheckpointLoaderSimple',ckpt_name=p['model']),
            '2':node('CLIPTextEncode',text=p.get('prompt',''),clip=['1',1]),
            '3':node('CLIPTextEncode',text=p.get('negative',''),clip=['1',1]),
            '4':node('EmptyLatentImage',width=p.get('width',512),height=p.get('height',512),batch_size=1),
            '5':node('KSampler',model=['1',0],positive=['2',0],negative=['3',0],latent_image=['4',0],seed=p.get('seed',1),steps=p.get('steps',20),cfg=7.,sampler_name='euler',scheduler='normal',denoise=1.),
            '6':node('VAEDecode',samples=['5',0],vae=['1',2]),'7':node('SaveImage',images=['6',0],filename_prefix='OpenKatana/generated')}
    if kind=='qwen-generation':
        if not all(p.get(key) for key in ('model','encoder','vae')):
            raise ValueError('Qwen 2.1 requires installed diffusion model, text encoder and VAE filenames')
        width,height=p.get('width',1024),p.get('height',1024)
        if any(not isinstance(v,int) or not 256<=v<=2048 or v%32 for v in (width,height)):
            raise ValueError('Qwen image dimensions must be multiples of 32 between 256 and 2048')
        # Component contract/settings follow the installed official Qwen 2.1 T2I
        # template. No prompt-enhancer model, reference image or download node.
        return {'1':node('UNETLoader',unet_name=p['model'],weight_dtype='default'),
            '2':node('CLIPLoader',clip_name=p['encoder'],type='qwen_image',device='default'),
            '3':node('VAELoader',vae_name=p['vae']),
            '4':node('TextEncodeQwenImage21',clip=['2',0],prompt=p.get('prompt',''),negative_prompt=p.get('negative',''),resolution=1024),
            '5':node('EmptyLatentImage',width=width,height=height,batch_size=1),
            '6':node('QwenImage21Cache',model=['1',0],device='auto',dtype='default'),
            '7':node('KSampler',model=['6',0],positive=['4',0],negative=['4',1],latent_image=['5',0],seed=p.get('seed',1),steps=p.get('steps',25),cfg=1.,sampler_name='euler',scheduler='simple',denoise=1.),
            '8':node('VAEDecode',samples=['7',0],vae=['3',0]),'9':node('SaveImage',images=['8',0],filename_prefix='OpenKatana/generated')}
    raise ValueError('Unknown workflow kind')

def build_from_form(kind,values):
    """UI/sequence entry point: keep only this kind's parameters that were actually filled in (agent calls stay strict)."""
    if kind not in PARAMETERS:raise ValueError('Unknown workflow kind')
    return build(kind,**{k:v for k,v in values.items() if k in PARAMETERS[kind] and v not in (None,'')})


def save(kind,out:Path,**params):
    if out.exists():raise FileExistsError(out)
    from .model_workflows import asset_ports
    graph=build(kind,**params);write_json(out,graph)
    write_json(out.with_suffix('.manifest.json'),{'kind':kind,'execution':'local only','nodes':sorted({v['class_type'] for v in graph.values()}),
        'model':params.get('model'),'model_license':'user must supply and review the selected model license' if params.get('model') else 'no model weights',
        'encoder':params.get('encoder'),'vae':params.get('vae'),'audio_vae':params.get('audio_vae'),'lora':params.get('lora'),
        'asset_ports':asset_ports(graph),'downloads':False,'output_review':'required before use in a release'})
    return graph
