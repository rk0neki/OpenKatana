from __future__ import annotations

import argparse
import importlib.metadata
import json
import shutil
from pathlib import Path

from . import __version__


def main():
    parser = argparse.ArgumentParser(description='OpenKatana independent video editing')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor', help='Check installed runtime components')
    p=sub.add_parser('setup',help='Prepare a project and install its agent-neutral video skill')
    p.add_argument('--project',type=Path,default=Path('projects/my-first-film'))
    p.add_argument('--name',default='My first film')
    p=sub.add_parser('hdr',help='High-precision HDR finishing; separate from SDR Canvas timelines')
    hs=p.add_subparsers(dest='hdr_command',required=True)
    for verb in ('check','render'):
        q=hs.add_parser(verb);q.add_argument('document',type=Path);q.add_argument('--project',type=Path)
        if verb=='render':q.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('shape-text',help='Export shaped glyph IDs, clusters, contours and SVG; requires text extra')
    p.add_argument('font',type=Path);p.add_argument('text');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--size',type=float,default=72);p.add_argument('--direction',choices=['ltr','rtl','ttb','btt']);p.add_argument('--language',default='und');p.add_argument('--script')
    p.add_argument('--features',type=json.loads);p.add_argument('--variations',type=json.loads);p.add_argument('--radius',type=float)
    p=sub.add_parser('composition',help='Original responsive layout, shaped text and plugin compositions')
    s=p.add_subparsers(dest='composition_command',required=True)
    q=s.add_parser('init');q.add_argument('directory',type=Path)
    q.add_argument('--width',type=int,default=1280);q.add_argument('--height',type=int,default=720)
    q.add_argument('--fps',type=int,default=30);q.add_argument('--frames',type=int,default=90)
    for verb in ('check','render'):
        q=s.add_parser(verb);q.add_argument('document',type=Path);q.add_argument('--project',type=Path,help='Asset root; defaults to document folder')
        q.add_argument('--width',type=int);q.add_argument('--height',type=int)
        if verb=='render':q.add_argument('--out',type=Path,required=True);q.add_argument('--no-video',action='store_true')
        else:q.add_argument('--frame',type=int,default=0)
    p=sub.add_parser('morph-images',help='Local feature/landmark image warp with an importable video plate')
    p.add_argument('source',type=Path);p.add_argument('target',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--width',type=int,default=512);p.add_argument('--height',type=int,default=512);p.add_argument('--fps',type=int,default=30);p.add_argument('--frames',type=int,default=60)
    p.add_argument('--points',type=Path,help='JSON source/target normalized landmark lists; omit for feature registration')
    p=sub.add_parser('scene3d',help='Create, validate and render independent offline 3D scenes')
    s=p.add_subparsers(dest='scene_command',required=True)
    q=s.add_parser('init');q.add_argument('directory',type=Path);q.add_argument('--template',choices=['product','morph','physics','webgl'],default='product')
    q.add_argument('--width',type=int,default=640);q.add_argument('--height',type=int,default=360);q.add_argument('--fps',type=int,default=30);q.add_argument('--frames',type=int,default=90)
    q=s.add_parser('check');q.add_argument('scene',type=Path)
    q=s.add_parser('render');q.add_argument('scene',type=Path);q.add_argument('--out',type=Path,required=True)
    q.add_argument('--stills',help='Comma-separated frame indices; omit for the full clip');q.add_argument('--no-video',action='store_true')
    q.add_argument('--start',type=int);q.add_argument('--end',type=int)
    q.add_argument('--trusted-script',action='store_true',help='Execute a reviewed local JavaScript authoring module')
    q=s.add_parser('inspect-model');q.add_argument('source',type=Path)
    q=s.add_parser('import-model');q.add_argument('source',type=Path);q.add_argument('destination',type=Path)
    q=s.add_parser('blender');q.add_argument('source',type=Path);q.add_argument('--out',type=Path,required=True)
    q.add_argument('--engine',choices=['BLENDER_EEVEE','CYCLES'],default='BLENDER_EEVEE');q.add_argument('--start',type=int);q.add_argument('--end',type=int)
    q.add_argument('--trusted-script',action='store_true',help='Explicitly execute a trusted local Python authoring script; not sandboxed')
    p = sub.add_parser('validate', help='Validate the supported timeline contract')
    p.add_argument('timeline', type=Path)
    p = sub.add_parser('render', help='Render a timeline into a new output directory')
    p.add_argument('timeline', type=Path); p.add_argument('--out', required=True, type=Path)
    p = sub.add_parser('prepare', help='Extract a CFR source into lossless frames')
    p.add_argument('source', type=Path); p.add_argument('--out', required=True, type=Path)
    p = sub.add_parser('comfy-submit', help='Submit a local or explicitly authorized paid Comfy Cloud workflow')
    p.add_argument('workflow', type=Path); p.add_argument('--out', required=True, type=Path)
    p.add_argument('--endpoint', default='http://127.0.0.1:8189')
    p.add_argument('--execution', choices=['local','cloud'], default='local')
    p.add_argument('--allow-paid', action='store_true', help='Authorize charges and upload for this cloud workflow')
    p.add_argument('--asset', action='append', default=[], help='NODE.INPUT=local-file')
    p.add_argument('--native-endpoint', default='http://127.0.0.1:8000', help='Local ComfyUI endpoint for installed-node/model checks')
    p.add_argument('--reviewed-local-node',action='append',default=[],help='Inspected local, no-download node class; repeat per additional class')
    p = sub.add_parser('comfy-collect', help='Collect a previously submitted job without resubmission')
    p.add_argument('directory', type=Path)
    p = sub.add_parser('comfy-build', help='Build an explicit local workflow and dependency manifest')
    p.add_argument('kind', choices=['matte','segmentation','interpolation','generation','qwen-generation','h3-generation','cutout','qwen-edit','h3-reference','seedvr2-restore','model-interpolation','image-upscale']);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--parameters',type=Path,help='JSON parameter object for any builder; cannot be combined with parameter flags')
    p.add_argument('--points',type=json.loads,help='cutout: JSON [[x, y], ...] clicks on the subject, 0..1 first-frame coordinates')
    p.add_argument('--negative-points',type=json.loads,help='cutout: JSON [[x, y], ...] clicks off the subject')
    p.add_argument('--device');p.add_argument('--precision')
    p.add_argument('--model');p.add_argument('--prompt');p.add_argument('--negative');p.add_argument('--seed',type=int)
    p.add_argument('--encoder');p.add_argument('--vae');p.add_argument('--width',type=int);p.add_argument('--height',type=int);p.add_argument('--steps',type=int)
    p.add_argument('--audio-vae');p.add_argument('--lora');p.add_argument('--length',type=int,help='H3 frame count: 17k+5 at 24 fps')
    p.add_argument('--input-mode',choices=['t2v','i2v','first-last']);p.add_argument('--sage-attention',action='store_true',default=None)
    p.add_argument('--key',help='matte key colour');p.add_argument('--tolerance',type=float);p.add_argument('--softness',type=float);p.add_argument('--multiplier',type=int)
    p = sub.add_parser('comfy-check', help='Check installed nodes/models without submitting a job')
    p.add_argument('workflow',type=Path);p.add_argument('--native-endpoint',default='http://127.0.0.1:8000')
    p.add_argument('--reviewed-local-node',action='append',default=[])
    p = sub.add_parser('comfy-capabilities', help='List supported local nodes and model choices')
    p.add_argument('--native-endpoint',default='http://127.0.0.1:8000')
    p = sub.add_parser('comfy-import', help='Import collected image frames, masks or selected video/audio')
    p.add_argument('directory',type=Path);p.add_argument('--project',type=Path,required=True)
    p.add_argument('--output-file',help='Exact output filename from the collected receipt')
    p.add_argument('--kind',choices=['clip','mask'],default='clip');p.add_argument('--clip');p.add_argument('--fps',type=float,default=30)
    p=sub.add_parser('comfy-process',help='Process a clip through Comfy, resuming recorded jobs without resubmission')
    p.add_argument('timeline',type=Path);p.add_argument('--clip',required=True);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--kind',choices=['matte','segmentation','interpolation','cutout'],required=True);p.add_argument('--model')
    p.add_argument('--points',type=json.loads,help='cutout: JSON [[x, y], ...] clicks on the subject, 0..1 first-frame coordinates')
    p.add_argument('--negative-points',type=json.loads,help='cutout: JSON [[x, y], ...] clicks off the subject')
    p.add_argument('--endpoint',default='http://127.0.0.1:8189');p.add_argument('--native-endpoint',default='http://127.0.0.1:8000')
    for name in ('masks','faces','interpolate'):
        p=sub.add_parser(name,help='Analyze supplied source frames locally')
        p.add_argument('timeline',type=Path);p.add_argument('--clip',required=True);p.add_argument('--out',type=Path,required=True)
        if name=='masks':
            p.add_argument('--mode',choices=['chroma','luma','alpha','grabcut'],default='chroma');p.add_argument('--key',default='#00ff00')
            p.add_argument('--tolerance',type=float,default=.18);p.add_argument('--softness',type=float,default=.08)
            p.add_argument('--rect',type=float,nargs=4);p.add_argument('--feather',type=float,default=0)
        if name=='faces':p.add_argument('--cascade',type=Path);p.add_argument('--min-size',dest='min_size',type=int,default=24)
        if name=='interpolate':p.add_argument('--multiplier',type=int,default=2)
    p=sub.add_parser('project-init',help='Create a local project');p.add_argument('directory',type=Path);p.add_argument('--name',default='Untitled')
    p=sub.add_parser('project-import',help='Import media into a project');p.add_argument('directory',type=Path);p.add_argument('source',type=Path);p.add_argument('--rights',default='review_pending')
    p=sub.add_parser('plan',help='Prepare a structured edit for review from imported assets');p.add_argument('directory',type=Path);p.add_argument('--recipe',default='Drift');p.add_argument('--seconds',type=float,default=3);p.add_argument('--caption',default='')
    p=sub.add_parser('studio',help='Open a loopback-only local editor');p.add_argument('directory',type=Path);p.add_argument('--port',type=int,default=0)
    p=sub.add_parser('mcp',help='Run the official MCP SDK stdio server for local agents')
    p.add_argument('--workspace',type=Path,default=Path('work/agent-projects'))
    p=sub.add_parser('tools',help='List the shared agent tools and their parameters')
    p.add_argument('--workspace',type=Path,default=Path('work/agent-projects'))
    p=sub.add_parser('call',help='Call the same editing tool exposed over MCP; return JSON')
    p.add_argument('tool');p.add_argument('--arguments',type=Path,help='UTF-8 JSON object file; omit for no arguments')
    p.add_argument('--workspace',type=Path,default=Path('work/agent-projects'))
    args = parser.parse_args()
    try:
        if args.command=='setup':
            from .onboarding import setup_project
            result=setup_project(args.project,args.name)
        elif args.command=='mcp':
            from .mcp_server import serve
            serve(args.workspace);return
        elif args.command in ('tools','call'):
            from .agent_api import AgentAPI
            api=AgentAPI(args.workspace)
            result=api.catalog() if args.command=='tools' else api.call(args.tool,json.loads(args.arguments.read_text(encoding='utf-8')) if args.arguments else {})
        elif args.command == 'hdr':
            from . import hdr
            doc=json.loads(args.document.read_text(encoding='utf-8'));root=(args.project or args.document.parent).resolve()
            result=hdr.render(doc,root,args.out) if args.hdr_command=='render' else {'valid':bool(hdr.validate(doc,root))}
        elif args.command == 'shape-text':
            from .text_shape import export_text
            result=export_text(args.font,args.text,args.out,size=args.size,direction=args.direction,language=args.language,script=args.script,features=args.features,variations=args.variations,radius=args.radius)
        elif args.command == 'composition':
            from . import composition
            if args.composition_command=='init':
                args.directory.mkdir(parents=True,exist_ok=False)
                result=composition.save_composition(args.directory,'composition.json',composition.starter(args.width,args.height,args.fps,args.frames),None)
            else:
                root=(args.project or args.document.parent).resolve();doc=json.loads(args.document.read_text(encoding='utf-8'))
                if args.composition_command=='check':result=composition.inspect_composition(root,doc,args.frame,args.width,args.height)
                else:result=composition.render_composition(root,doc,args.out,args.width,args.height,not args.no_video)
        elif args.command == 'morph-images':
            from .image_morph import morph_images
            result=morph_images(args.source,args.target,args.out,args.width,args.height,args.fps,args.frames,json.loads(args.points.read_text(encoding='utf-8')) if args.points else None)
        elif args.command == 'scene3d':
            from . import scene3d
            from .render import write_json
            if args.scene_command=='init':
                if args.template=='webgl':
                    from .webgl_authoring import create_kit
                    target=args.directory.resolve()
                    result=create_kit(target.parent,target.name,args.width,args.height,args.fps,args.frames)
                    result['scene']=str(target/'scene.json')
                else:
                    value=scene3d.validate(scene3d.starter(args.template,args.width,args.height,args.fps,args.frames),args.directory)
                    args.directory.mkdir(parents=True,exist_ok=False);path=args.directory/'scene.json';write_json(path,value)
                    result={'scene':str(path.resolve()),'template':args.template}
            elif args.scene_command=='check':
                value=scene3d.validate(json.loads(args.scene.read_text(encoding='utf-8')),args.scene.resolve().parent)
                result={'valid':True,'canvas':value['canvas'],'inputs':scene3d.input_manifest(value,args.scene.resolve().parent)}
            elif args.scene_command=='inspect-model':result=scene3d.inspect_model(args.source)
            elif args.scene_command=='import-model':result=scene3d.import_model(args.source,args.destination)
            elif args.scene_command=='blender':
                from .blender_bridge import render_blender
                result=render_blender(args.source,args.out,args.engine,args.start,args.end,args.trusted_script)
            else:result=scene3d.render_scene(args.scene,args.out,[int(f) for f in args.stills.split(',')] if args.stills else None,not args.no_video,args.start,args.end,args.trusted_script)
        elif args.command == 'doctor':
            from .render import chrome_path
            versions = {}
            for name in ('comfy-sdk', 'playwright', 'Pillow', 'numpy', 'opencv-python-headless', 'mcp'):
                try: versions[name] = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError: versions[name] = None
            try: chrome = chrome_path()
            except RuntimeError: chrome = None
            optional = {'opencv-python-headless', 'mcp'}
            missing = [k for k, v in {'ffmpeg': shutil.which('ffmpeg'), 'ffprobe': shutil.which('ffprobe'), 'chrome': chrome, **versions}.items() if not v and k not in optional]
            result = {'version': __version__, 'ffmpeg': shutil.which('ffmpeg'), 'ffprobe': shutil.which('ffprobe'),
                      'chrome': chrome, 'dependencies': versions, 'missing': missing,
                      'optional_missing': [k for k in sorted(optional) if not versions[k]],
                      'ready_to_render': not ({'ffmpeg', 'ffprobe', 'chrome', 'playwright', 'Pillow', 'numpy'} & set(missing)),
                      'comfy_live_connection': 'not_tested'}
        elif args.command == 'validate':
            from .contracts import validate
            validate(json.loads(args.timeline.read_text(encoding='utf-8')), args.timeline.resolve().parent)
            result = {'valid': True}
        elif args.command == 'render':
            from .render import render
            result = render(args.timeline, args.out)
        elif args.command == 'prepare':
            from .render import prepare
            result = prepare(args.source, args.out)
        elif args.command == 'comfy-submit':
            from .comfy import submit
            result = submit(args.workflow, args.out, args.endpoint, args.asset, args.native_endpoint, args.execution, args.allow_paid,args.reviewed_local_node)
        elif args.command == 'comfy-collect':
            from .comfy import collect
            result = collect(args.directory)
        elif args.command=='comfy-build':
            from .workflows import save
            params={key:getattr(args,key) for key in ('model','prompt','negative','seed','encoder','vae','width','height','steps','key','tolerance','softness','multiplier','device','precision','audio_vae','lora','length','input_mode','sage_attention') if getattr(args,key) is not None}
            if args.points is not None:params['positive']=args.points
            if args.negative_points is not None:params['negative']=args.negative_points
            if args.parameters:
                if params:raise ValueError('Use --parameters or parameter flags, not both')
                params=json.loads(args.parameters.read_text(encoding='utf-8'))
                if not isinstance(params,dict):raise ValueError('Expected a JSON parameter object')
            result=save(args.kind,args.out,**params)
        elif args.command=='comfy-check':
            from .comfy import validate_workflow
            from .workflows import preflight
            result=preflight(validate_workflow(args.workflow,reviewed_local_nodes=args.reviewed_local_node),args.native_endpoint,args.reviewed_local_node)
        elif args.command=='comfy-capabilities':
            from .workflows import capabilities
            result=capabilities(args.native_endpoint)
        elif args.command=='comfy-import':
            from .comfy_assets import import_outputs
            result=import_outputs(args.directory,args.project,args.kind,args.clip,args.fps,args.output_file)
        elif args.command=='comfy-process':
            from .comfy_sequence import process
            result=process(args.timeline,args.clip,args.out,args.kind,args.endpoint,args.native_endpoint,args.model,args.points,args.negative_points)
        elif args.command in ('masks','faces','interpolate'):
            from . import vision
            options={k:v for k,v in vars(args).items() if k not in ('command','timeline','clip','out')}
            result=getattr(vision,args.command)(args.timeline,args.clip,args.out,**options)
        elif args.command=='studio':
            from .studio import serve
            serve(args.directory,args.port);return
        else:
            from . import projects
            if args.command=='project-init':result=projects.create(args.directory,args.name)
            elif args.command=='project-import':result=projects.import_asset(args.directory,args.source,args.rights)
            else:
                data=projects.state(args.directory)
                result=projects.plan(args.directory,[a['id'] for a in data['assets'] if 'clip' in a],args.recipe,args.seconds,caption=args.caption)
                projects.save(args.directory,result['timeline'],data['revision'])
        print(json.dumps(result, indent=2))
    except Exception as error:
        parser.exit(1, f'{type(error).__name__}: {error}\n')
