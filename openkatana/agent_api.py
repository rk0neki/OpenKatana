"""One editing API for agents over MCP and for command-line automation."""
import importlib.metadata
import inspect
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Literal
import uuid
from . import __version__,projects
from .contracts import ContractError,local_path,number,validate
from .render import digest,probe,run,write_json

TOOLS=('get_capabilities','read_guide','create_project','get_project','inspect_media','preview_source','view_image',
       'import_media','plan_edit','validate_timeline','save_timeline','preview_timeline','start_render','get_render',
       'review_render','analyze_clip','build_workflow','check_workflow','submit_workflow','collect_workflow',
       'import_workflow_output','process_clip','source_contact_sheet','analyze_reference','list_fonts','preview_fonts',
       'preview_segment','compare_reference','save_reference_plan','audit_reference_plan','import_media_batch','analyze_audio','analyze_energy','plan_music_edit','make_captions','list_sfx','set_review_policy','render_page','build_recipe','revise_motion','review_mask','bind_reference','inspect_identity','transcribe_audio','plan_storyboard','fill_storyboard')
TOOLS += ('create_scene3d','inspect_model3d','import_model3d','check_scene3d','render_scene3d','render_blender','morph_images')
TOOLS += ('shape_text','edit_timeline')
TOOLS += ('import_hdr_media','render_hdr','run_model_workflow')
TOOLS += ('create_composition','save_composition','inspect_composition','render_composition','list_plugins','run_plugin_operator')
TOOLS += ('create_animation_kit','build_display_atlas','synthesize_score','assemble_blender_clips','analyze_render_motion','analyze_camera_motion')
TOOLS += ('create_webgl_kit','assemble_render_clips')
MEDIA={'.png','.jpg','.jpeg','.webp','.mp4','.mov','.mkv','.webm','.avi','.mxf','.wav','.mp3','.m4a','.flac','.ogg','.aac','.ttf','.otf','.ttc','.woff','.woff2'}

class AgentAPI:
    def __init__(self,workspace):self.workspace=Path(workspace).resolve()

    def _project(self,project_id):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',project_id):raise ContractError('Project ID must use letters, digits, hyphens or underscores')
        p=(self.workspace/project_id).resolve()
        if not p.is_relative_to(self.workspace):raise ContractError('Project must stay inside the configured workspace')
        return p

    def _source(self,source):
        p=Path(source).expanduser().resolve()
        if p.suffix.lower() not in MEDIA or not p.is_file():raise ContractError('Supply an existing local media file')
        return p

    def _output(self,root,kind):return root/'.openkatana'/kind/uuid.uuid4().hex

    def get_capabilities(self) -> dict:
        """Discover actual tools, supported workflows, runtime readiness and limits before editing."""
        dependencies={}
        for name in ('comfy-sdk','playwright','Pillow','numpy','mcp','opencv-python-headless','faster-whisper','uharfbuzz','fonttools'):
            try:dependencies[name]=importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:dependencies[name]=None
        from .render import chrome_path
        from .transitions import catalog as shot_transitions
        from .studio_looks import catalog as studio_looks
        from .transcribe import available as transcribe_ready,installed as whisper_models
        from .presets import catalog as preset_catalog
        try:chrome=chrome_path()
        except RuntimeError:chrome=None
        return {'name':'OpenKatana','version':__version__,'workspace':str(self.workspace),'tools':list(TOOLS),
            'ffmpeg':shutil.which('ffmpeg'),'ffprobe':shutil.which('ffprobe'),'chrome':chrome,'dependencies':dependencies,
            'guides':['agent','timeline','effects','compatibility','tool-audit','comfy-models','scene3d','composition','release-tools','hdr','animation','webgl'],'comfy_execution':'official SDK: local by default; cloud requires explicit execution, endpoint and allow_paid plus COMFY_API_KEY; no automatic fallback',
            'roles':'Your agent chooses and reviews the edit; OpenKatana executes it. No automatic publication.',
            'limits':['Canvas timelines use SDR CFR; HDR finishing uses the separate float32 render_hdr route','Face detector needs visual review',
                      'Semantic segmentation needs installed BiRefNet weights; point-click cut-outs need ComfyUI with the SAM2 and OpenKatana nodes and an installed SAM2 model','3D scene rendering is available; automatic scene reconstruction and semantic video morphing still need separate models',
                      'Cut/onset detection gives candidates; analyze_audio beat grids assume constant tempo and are estimates','No automatic OCR or exact font identification; transcription needs faster-whisper and a Whisper model already in the local cache (never downloaded)',
                      'Video/audio playback depends on the client; agent approval is not human approval'],
            'reference_matching':['contact sheets','cut/onset candidates','local font inventory and specimens','comparison frames',
                                  'literal text/cut/font/effect plan checks before rendering'],
            'typography':['supplied font files','hollow fill:null','render_style:explicit for clean typewriter',
                          'tracking','scale_x/scale_y','opacity_keys','letter_opacity_keys','seeded flicker'],
            'transcription':{'available':transcribe_ready(),'installed_models':whisper_models()},
            'scene3d':{'engine':'bundled MIT Three.js 0.180.0','templates':['product','morph','physics'],
                       'features':['PBR materials and local textures/HDR','perspective and orthographic cameras','lights and shadows','GLB/glTF animation, skinning and morph targets','keyframes and hierarchy','topology-changing implicit morphs','baked rigid-body physics','depth of field and bloom','linear-light temporal motion blur','PNG plates and MP4 export'],
                       'guide':'scene3d','authoring_guide':'webgl',
                       'authoring':['trusted local ES modules with bundled Three.js','procedural geometry and animated display helpers','cut-safe camera paths','inclusive frame chunks and validated assembly'],
                       'renderer_choice':'WebGL for authored rasterized 3D; installed Blender for Cycles, Blender-specific scenes or simulations; both feed the same timeline'},
            'composition':{'guide':'composition','layout':'CSS flex/grid, responsive rules, intrinsic sizing','text':'Chromium shaping, bidi, grapheme masks, OpenType features/variable fonts','plugins':'OpenKatana API 1 components/effects/operators; not a private binary ABI'},
            'hdr':{'guide':'hdr','working_space':'float32 linear BT.2020','exports':['16-bit FFV1 PQ/HLG','10-bit HEVC PQ/HLG','SDR preview'],'limits':'Separate finishing contract; Canvas effects remain SDR'},
            'model_builders':['qwen-edit','h3-reference','seedvr2-restore','model-interpolation','image-upscale','h3-generation','qwen-generation','generation','cutout','segmentation','matte','interpolation'],
            'animation':{'guide':'animation','kit':'Original geometry, frame-indexed displays, cut-safe camera paths and tracking; installed Blender bridge', 'qa':'Optical-flow and evaluated-camera candidates; visual review required'},
            'image_morph':'morph_images: local ORB/RANSAC or explicit-landmark triangle warp; not semantic video generation',
            'presets':preset_catalog(),
            'shot_transitions':shot_transitions(),'studio_looks':studio_looks()}

    def read_guide(self,topic:Literal['agent','timeline','effects','compatibility','tool-audit','comfy-models','scene3d','composition','release-tools','hdr','animation','webgl']='agent') -> dict:
        """Read the exact supported timeline contract and editing workflow; do not guess parameters."""
        names={'agent':'AGENT_INTERFACE.md','timeline':'TIMELINE.md','effects':'EXPANSION.md','compatibility':'COMPATIBILITY.md','tool-audit':'EDITOR_TOOLS.md','comfy-models':'COMFY_MODELS.md','scene3d':'SCENE3D.md','composition':'COMPOSITIONS.md','release-tools':'RELEASE-TOOLS.md','hdr':'HDR.md','animation':'ANIMATION.md','webgl':'WEBGL.md'}
        if topic not in names:raise ContractError('Unknown guide')
        for base in (Path(__file__).resolve().parent.parent/'docs',Path(sys.prefix)/'share/openkatana/docs',Path(__file__).resolve().parent.parent/'share/openkatana/docs'):
            p=base/names[topic]
            if p.is_file():return {'topic':topic,'markdown':p.read_text(encoding='utf-8')}
        raise ContractError('Guide not installed; reinstall the OpenKatana package')

    def edit_timeline(self,project_id:str,operations:list[dict],revision:str,save:bool=False) -> dict:
        """Propose or atomically save RFC 6902 timeline operations against an exact revision. Default is a validated proposal. Whole-batch failure leaves the project unchanged."""
        from .json_ops import apply
        if type(save) is not bool:raise ContractError('save must be boolean')
        root=self._project(project_id);current=projects.state(root)
        if current['revision']!=revision:raise ContractError('Timeline changed; reload before editing')
        if current['timeline'] is None:raise ContractError('Save an initial timeline before editing')
        result=validate(apply(current['timeline'],operations),root)
        record=projects.save(root,result,revision) if save else {'revision':revision}
        return {**record,'timeline':result,'saved':save,'operations':len(operations),'needs_preview':True}

    def shape_text(self,project_id:str,font:str,text:str,size:float=72,direction:Literal['ltr','rtl','ttb','btt']|None=None,language:str='und',script:str|None=None,features:dict|None=None,variations:dict|None=None,radius:float|None=None) -> dict:
        """Export one shaped text run as glyph IDs, clusters, positions, contours and SVG. Requires the licensed text extra. For paragraph bidi/fallback use compositions."""
        from .text_shape import export_text
        root=self._project(project_id)
        if not (root/'project.json').is_file():raise ContractError('Create the project before exporting glyphs')
        return export_text(self._source(font),text,self._output(root,'glyphs'),size=size,direction=direction,language=language,script=script,features=features,variations=variations,radius=radius)

    def import_hdr_media(self,project_id:str,source:str,source_color:Literal['pq','hlg','bt709','srgb']|None=None,
                         fps:int=30,start:float=0,duration:float=3,peak_nits:float=1000,rights:str='review_pending') -> dict:
        """Keep an original HDR source and import an explicitly tone-mapped SDR editing proxy.

        Returns an HDR finishing document referencing the untouched source copy. Ordinary
        Canvas timelines use the proxy; render_hdr preserves source highlight precision.
        """
        from . import hdr
        root=self._project(project_id);projects.state(root);src=self._source(source)
        hdr.numeric(fps,1,120,'fps',True);hdr.numeric(start,0,86400,'start');hdr.numeric(duration,.1,600,'duration')
        profile=hdr.source_profile(src,source_color)
        out=self._output(root,'hdr-imports');out.mkdir(parents=True)
        original=out/('source'+src.suffix.lower());shutil.copyfile(src,original)
        doc={'schema':'openkatana.hdr/1','canvas':{'width':profile['width']//2*2,'height':profile['height']//2*2,'fps':fps,'frames':round(duration*fps)},
             'output':{'transfer':'hlg' if profile['transfer']=='arib-std-b67' else 'pq','peak_nits':peak_nits},
             'clips':[{'source':original.relative_to(root).as_posix(),'start':0,'frames':round(duration*fps),'trim_seconds':start}]}
        if source_color:doc['clips'][0]['source_color']=source_color
        rendered=hdr.render(doc,root,out/'conform')
        asset=projects.register(root,Path(rendered['preview']),src.stem+' (SDR proxy)',rights)
        return {'asset':asset,'hdr_document':doc,'original':original.relative_to(root).as_posix(),
                'manifest':str(out/'conform/manifest.json'),'proxy_color':'BT.709 SDR; original HDR retained'}

    def render_hdr(self,project_id:str,document:dict) -> dict:
        """Finish HDR clips in float32 linear BT.2020; export 16-bit FFV1, 10-bit HEVC and SDR preview.

        Uses the separate openkatana.hdr/1 contract (hdr guide). Supports trims, scaling,
        exposure, linear dissolves and explicit sRGB PNG overlays. Canvas effects are SDR.
        """
        from . import hdr
        root=self._project(project_id);projects.state(root)
        return hdr.render(document,root,self._output(root,'hdr-renders'))

    def create_project(self,name:str,project_id:str|None=None) -> dict:
        """Create a fresh editing project. Existing projects are never replaced."""
        key=project_id or uuid.uuid4().hex[:12];root=self._project(key)
        data=projects.create(root,name);return {'project_id':key,'directory':str(root),'state':data}

    def get_project(self,project_id:str) -> dict:
        """Read media IDs, the current timeline and its revision for conflict-safe saving."""
        root=self._project(project_id);return {'project_id':project_id,'directory':str(root),**projects.state(root)}

    def inspect_media(self,source:str) -> dict:
        """Inspect a local media file's duration, dimensions, rates and streams without changing it."""
        p=self._source(source)
        if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp'):
            from PIL import Image
            with Image.open(p) as im:info={'width':im.width,'height':im.height,'mode':im.mode}
        else:info=probe(p)
        return {'source':str(p),'sha256':digest(p),'bytes':p.stat().st_size,'media':info}

    def preview_source(self,project_id:str,source:str,times:list[float]) -> dict:
        """See source frames at explicit times BEFORE choosing shots. Request up to 12 times."""
        from .preview import source_frames
        root=self._project(project_id);projects.state(root);src=self._source(source)
        result=source_frames(src,self._output(root,'source-previews'),times)
        from .gates import record_inspection
        record_inspection(root,src,'preview_source');return result

    def view_image(self,project_id:str,path:str) -> dict:
        """View a saved image or matte inside the project. Path is relative to that project."""
        p=local_path(self._project(project_id),path)
        if p.suffix.lower() not in ('.png','.jpg','.jpeg','.webp') or not p.is_file():raise ContractError('Expected a project image')
        return {'preview_images':[str(p)],'sha256':digest(p)}

    def import_media(self,project_id:str,source:str,rights:str='review_pending',start:float=0,
                     duration:float|None=None,max_width:int|None=None,audio_only:bool=False) -> dict:
        """Import media, optionally a trimmed/resized video excerpt or its audio. Originals stay untouched.

        Inspect first; use a short excerpt to avoid extracting an entire long video.
        Rights records are provenance, not legal clearance. HDR/rotation need explicit conformance.
        """
        return self._import_media(project_id,source,rights,start,duration,max_width,audio_only)

    def _import_media(self,project_id,source,rights='review_pending',start=0,duration=None,max_width=None,audio_only=False,source_sha256=None):
        root=self._project(project_id);projects.state(root);p=self._source(source)
        number(start,'start',0)
        if duration is not None:number(duration,'duration',.01)
        if max_width is not None:number(max_width,'max_width',64,8192,integer=True)
        if start or duration is not None or max_width is not None or audio_only or p.suffix.lower()=='.mxf':
            from .editor_tools import metadata
            info=metadata(p);video=next((s for s in info['streams'] if s['codec_type']=='video'),None)
            if not audio_only:
                if not video:raise ContractError('Excerpt options require video, or audio_only=true')
                rotations=[float(x.get('rotation',0)) for x in video.get('side_data_list',[])]+[float(video.get('tags',{}).get('rotate',0))]
                if video.get('color_transfer') in ('smpte2084','arib-std-b67') or any(abs(a)%360>.001 for a in rotations):raise ContractError('HDR/rotated video needs explicit conformance first')
            folder=root/'media';folder.mkdir(exist_ok=True);target=folder/(uuid.uuid4().hex+('.wav' if audio_only else '.mp4'))
            args=['ffmpeg','-v','error','-ss',str(start),'-i',p]
            if duration is not None:args+=['-t',str(duration)]
            if audio_only:args+=['-vn','-map','0:a:0','-c:a','pcm_s16le']
            else:
                args+=['-map','0:v:0','-an']
                if max_width is not None:args+=['-vf',f'scale={min(max_width,video["width"])//2*2}:-2']
                args+=['-c:v','libx264','-crf','15','-preset','fast','-pix_fmt','yuv420p']
            run(args+[target]);asset=projects.register(root,target,p.stem+' excerpt',rights)
            write_json(root/'.openkatana/imports'/(asset['id']+'.json'),{'source':str(p),'sha256':source_sha256 or digest(p),
                'start':start,'duration':duration,'max_width':max_width,'audio_only':audio_only,'asset_id':asset['id']})
            return asset
        return projects.import_asset(root,p,rights)

    def plan_edit(self,project_id:str,asset_ids:list[str],recipe:str='Drift',seconds:float=3,
                  width:int=1280,height:int=720,fps:float=30,caption:str='') -> dict:
        """Optional original recipe starting point. Returns a timeline for the agent to edit; does not save it."""
        return projects.plan(self._project(project_id),asset_ids,recipe,seconds,width,height,fps,caption)

    def validate_timeline(self,project_id:str,timeline:dict) -> dict:
        """Check a complete timeline against real local assets before saving or rendering."""
        from .warnings import timeline_warnings
        root=self._project(project_id);canonical=validate(timeline,root);return {'valid':True,'frames':canonical['canvas']['frames'],'warnings':timeline_warnings(canonical,root)}

    def save_timeline(self,project_id:str,timeline:dict,revision:str|None) -> dict:
        """Save the agent's authored timeline; pass the revision from get_project (null for first save)."""
        from .warnings import timeline_warnings
        root=self._project(project_id);saved=projects.save(root,timeline,revision);saved['warnings']=timeline_warnings(validate(timeline,root),root);return saved

    def preview_timeline(self,project_id:str,frames:list[int]) -> dict:
        """See actual rendered frames of the saved timeline, including text/masks/camera/effects."""
        from .preview import timeline_frames
        root=self._project(project_id);data=projects.state(root);edit=data['timeline']
        if edit is None:raise ContractError('Save a timeline first')
        from .warnings import timeline_warnings
        from .gates import record_preview
        result=timeline_frames(edit,root,self._output(root,'timeline-previews'),frames);result['warnings']=timeline_warnings(validate(edit,root),root)
        record_preview(root,data['revision'],frames);return result

    def start_render(self,project_id:str,request_id:str) -> dict:
        """Render a saved timeline asynchronously. Reuse request_id after uncertain results to avoid duplicate jobs."""
        from .jobs import start
        from .gates import require
        root=self._project(project_id);require(root,projects.state(root))
        if (root/'reference-plan.json').exists():
            audit=self.audit_reference_plan(project_id)
            if not audit['matches_plan']:raise ContractError('Reference plan mismatch; call audit_reference_plan and resolve issues before rendering: '+json.dumps(audit['issues']))
        return start(root,request_id)

    def source_contact_sheet(self,project_id:str,source:str,start:float=0,end:float|None=None,step:float=.5,columns:int=4) -> dict:
        """Inspect up to 96 timestamped source frames as contact sheets. Use smaller intervals around cut candidates."""
        from .editor_tools import contact_sheet
        root=self._project(project_id);projects.state(root);src=self._source(source)
        result=contact_sheet(src,self._output(root,'contact-sheets'),start,end,step,columns)
        from .gates import record_inspection
        record_inspection(root,src,'source_contact_sheet');return result

    def analyze_reference(self,project_id:str,source:str,start:float=0,duration:float=30,scene_threshold:float=.25) -> dict:
        """Find scene-change and audio energy-rise candidates in up to 120 seconds. These are NOT verified cuts/beats/lyrics."""
        from .editor_tools import analyze_reference
        root=self._project(project_id);projects.state(root)
        return analyze_reference(self._source(source),self._output(root,'reference-analysis'),start,duration,scene_threshold)

    def analyze_audio(self,project_id:str,source:str,start:float=0,duration:float|None=None,fps:float|None=None,beats_per_bar:int=4) -> dict:
        """Measure music for cutting: BPM with octave candidates, a constant beat grid fitted to onsets, downbeats, onsets
        (all/strong/low), level-based sections, silence and EBU R128 loudness, plus a timeline image. Times are seconds
        from `start`; pass fps for frame numbers. Estimates for planning cuts, not verified musical structure."""
        from .audio_analysis import analyze,timeline_image
        number(start,'start',0)
        if duration is not None:number(duration,'duration',1,1800)
        if fps is not None:number(fps,'fps',1,240)
        number(beats_per_bar,'beats_per_bar',2,12,integer=True)
        root=self._project(project_id);projects.state(root);src=self._source(source)
        result,curves=analyze(src,start,duration,fps,beats_per_bar)
        out=self._output(root,'audio-analysis');out.mkdir(parents=True)
        image=timeline_image(result,curves,out/'timeline.png');write_json(out/'analysis.json',result)
        return {**result,'analysis_path':str(out/'analysis.json'),'preview_images':[image],
                'limits':'Tempo, downbeats and level-based sections are estimates for planning cuts; confirm by listening/review.'}

    def transcribe_audio(self,project_id:str,source:str,model:str|None=None,language:str|None=None,start:float=0,
                         duration:float|None=None) -> dict:
        """Transcribe speech locally with word timings (faster-whisper; a Whisper model already in the local cache, see
        get_capabilities transcription; never downloaded). Writes a words file for make_captions; times are seconds of
        the source file. Machine output: check words, names and timings against the audio before captioning."""
        from .transcribe import transcribe
        number(start,'start',0)
        if duration is not None:number(duration,'duration',.2,7200)
        if language is not None and not re.fullmatch(r'[a-z]{2,3}',language):raise ContractError('language: an ISO 639-1 code such as en, or null to detect')
        root=self._project(project_id);projects.state(root);src=self._source(source)
        return transcribe(src,self._output(root,'transcripts'),model,language,start,duration)

    def analyze_energy(self,project_id:str,source:str,reference:str|None=None,start:float=0,duration:float|None=None,canvas_w:int=1080,floor:float=.6) -> dict:
        """Measure a video's energy: cuts, white/black flashes, shake bursts, pans and motion hits (each with a ready
        timeline entry: specials / cam.shake / cam.pan / cam.punch), per-second rates and a 0.5 s energy curve, plus a
        chart image. With `reference`, also measure it and check the source's rates against it (FAIL below floor x the
        reference, or too much shake/jitter). Event times are seconds of the file; amplitudes are px of a canvas_w canvas."""
        from .energy import measure,check,chart
        number(start,'start',0)
        if duration is not None:number(duration,'duration',.2,3600)
        number(canvas_w,'canvas_w',64,7680,integer=True);number(floor,'floor',0,1)
        root=self._project(project_id);projects.state(root)
        result=measure(self._source(source),start,duration,canvas_w)
        out=self._output(root,'energy');out.mkdir(parents=True);images=[chart(result,out/'energy.png')]
        if reference is not None:
            ref=measure(self._source(reference),0.0,None,canvas_w)
            result['reference']={'source':ref['source'],'rates':ref['rates']};result['check']=check(result,ref,floor)
            images.append(chart(ref,out/'reference-energy.png'))
        write_json(out/'energy.json',result)
        return {**result,'analysis_path':str(out/'energy.json'),'preview_images':images,
                'limits':'Measured candidates: inspect the frames around each event before reproducing it; a fast camera move can read as a cut.'}

    def plan_music_edit(self,project_id:str,source:str,asset_ids:list[str]|None=None,start:float=0,duration:float|None=None,
                        fps:float=30,width:int=1080,height:int=1920,pace:str='auto',min_shot:float=.15,burst:bool=True) -> dict:
        """Plan cuts to music: analyse the track, then return a beat-aligned cut list (tempo-aware pace per level section:
        the smallest of 1/2/4/8 beats lasting >= 0.5 s loud, 1 s mid, 2 s quiet; half-beat burst after a drop), shot spans, suggested specials/punch/shake entries and,
        with asset_ids, a draft timeline (clips assigned in order; the track is included when it lives in the project).
        A starting point for the editor; nothing is saved."""
        from .audio_analysis import analyze
        from .music_plan import plan_cuts,draft_timeline
        number(start,'start',0);number(fps,'fps',1,120);number(min_shot,'min_shot',.05,10)
        if duration is not None:number(duration,'duration',1,1800)
        number(width,'width',16,7680,integer=True);number(height,'height',16,7680,integer=True)
        root=self._project(project_id);data=projects.state(root);src=self._source(source)
        analysis,_=analyze(src,start,duration,fps)
        plan=plan_cuts(analysis,fps,pace,min_shot,burst)
        assets=None;audio=None;notes=['Cuts follow the detected beat grid; check the grid by listening before committing.']
        if asset_ids:
            index={a['id']:a for a in data['assets']}
            bad=[k for k in asset_ids if k not in index or 'clip' not in index[k]]
            if bad:raise ContractError(f'asset_ids must be imported video/image assets: {", ".join(map(str,bad))}')
            assets=[(k,index[k]) for k in asset_ids]
            if src.is_relative_to(root.resolve()):
                audio={'mode':'mix','tracks':[{'src':src.relative_to(root.resolve()).as_posix(),'start':start,'duration':round(plan['frames']/fps,4)}]}
            else:notes.append('The track is outside the project: import it to include it in the draft timeline.')
        timeline=draft_timeline(plan,assets,fps,width,height,audio)
        if timeline is not None:validate(timeline,root)
        return {'bpm':analysis['bpm'],'sections':analysis['sections'],'beats':len(analysis['beats']),**plan,'timeline':timeline,
                'notes':notes,'needs_review':True}

    def plan_storyboard(self,project_id:str,source:str,start:float=0,duration:float|None=None,fps:float=30,width:int=1080,
                        height:int=1920,pace:str='auto',subject:str='the main subject',camera:str|None=None,save:bool=False) -> dict:
        """Storyboard mode: plan a music edit as slots to fill before footage exists. Each beat-aligned slot gets a brief
        (part, role, shot size, subject, camera, seconds of footage needed) and a slate picture, so the draft timeline
        renders for review. save=true makes it the project timeline. The verdict stays "GAPS storyboard: k of n slots
        still to fill" until fill_storyboard puts imported footage into every slot."""
        from .audio_analysis import analyze
        from .music_plan import plan_cuts
        from . import storyboard
        number(start,'start',0);number(fps,'fps',1,120)
        if duration is not None:number(duration,'duration',1,1800)
        number(width,'width',16,7680,integer=True);number(height,'height',16,7680,integer=True)
        if not isinstance(subject,str) or not 1<=len(subject)<=120:raise ContractError('subject: 1..120 characters')
        if camera is not None and (not isinstance(camera,str) or not 1<=len(camera)<=120):raise ContractError('camera: 1..120 characters')
        root=self._project(project_id);data=projects.state(root);src=self._source(source)
        analysis,_=analyze(src,start,duration,fps)
        cut_plan=plan_cuts(analysis,fps,pace,.15,True)
        audio=None
        if src.is_relative_to(root.resolve()):
            audio={'mode':'mix','tracks':[{'src':src.relative_to(root.resolve()).as_posix(),'start':start,'duration':round(cut_plan['frames']/fps,4)}]}
        board,edit=storyboard.plan(root,src,analysis,cut_plan,fps,width,height,subject,camera,audio)
        validate(edit,root)
        saved=projects.save(root,edit,data['revision']) if save else None
        return {'storyboard_id':board['id'],'slots':board['slots'],'bpm':board['bpm'],**storyboard.verdict(board,edit),'timeline':edit,'saved':saved,
                'slates':[str(root/edit['clips'][storyboard.PREFIX+s['id']]['frames_dir']/'00000.png') for s in board['slots'][:4]],
                'notes':(['The music is outside the project: import it to hear it in the storyboard.'] if audio is None else [])+
                        ['Import footage for the briefs, then fill_storyboard(storyboard_id, fills=[{slot, asset_id, srcf}]).']}

    def fill_storyboard(self,project_id:str,storyboard_id:str,fills:list[dict]|None=None) -> dict:
        """Put imported footage into storyboard slots of the saved timeline (fills: [{slot, asset_id, srcf?}]; each
        slot's other shot settings are kept) and save a new revision. Video slots need enough footage from srcf. With no
        fills, only report the verdict: "GAPS storyboard: k of n slots still to fill" with the briefs, or "FILLED"."""
        from . import storyboard
        from .contracts import fields
        root=self._project(project_id);data=projects.state(root)
        if not re.fullmatch(r'[0-9a-f]{12}',storyboard_id or ''):raise ContractError('storyboard_id: as returned by plan_storyboard')
        board,path=storyboard.load(root,storyboard_id)
        timeline=data['timeline']
        if timeline is None:raise ContractError('Save the storyboard timeline first (plan_storyboard save=true)')
        changes=[];saved=None
        if fills:
            if not isinstance(fills,list) or len(fills)>500:raise ContractError('fills: a list of {slot, asset_id, srcf}')
            for item in fills:fields(item,'slot asset_id srcf','storyboard fill')
            changes=storyboard.fill(root,board,timeline,{a['id']:a for a in data['assets']},fills,timeline['canvas']['fps'])
            validate(timeline,root)
            saved=projects.save(root,timeline,data['revision']);write_json(path,board)
        return {'changes':changes,'saved':saved,**storyboard.verdict(board,timeline)}

    def make_captions(self,project_id:str,words:str,family:str,fps:float=30,style:str='clean',size:int|None=None,height:int=1080,
                      offset:float=0,highlight:str='#ffd200',karaoke_mode:str='word',max_chars:int=32,max_words:int=7,max_gap:float=.6,
                      max_duration:float=3) -> dict:
        """Turn supplied word timings (words JSON or SRT/VTT; no transcription) into caption text events for the timeline,
        grouped for reading (max_chars/max_words/max_gap/max_duration, sentence ends), in a style (clean, bold_pop,
        karaoke with per-word highlight, lower_third, title_card), plus SRT and WebVTT files. `offset` subtracts seconds
        (e.g. the audio start used in the timeline). Insert the events into the timeline's `text` yourself."""
        from .captions import make,srt,vtt
        from .contracts import color
        number(fps,'fps',1,240);number(height,'height',16,7680,integer=True);number(offset,'offset',-36000,36000)
        if size is not None:number(size,'size',4,2000,integer=True)
        number(max_chars,'max_chars',4,200,integer=True);number(max_words,'max_words',1,50,integer=True)
        number(max_gap,'max_gap',0,30);number(max_duration,'max_duration',.2,60);color(highlight,'highlight',alpha=True)
        if karaoke_mode not in ('word','sweep'):raise ContractError('karaoke_mode: word or sweep')
        root=self._project(project_id);projects.state(root)
        src=Path(words).expanduser().resolve()
        if src.suffix.lower() not in ('.json','.srt','.vtt') or not src.is_file():raise ContractError('words: an existing .json, .srt or .vtt file')
        events,cues=make(src,fps,family,style,size,height,offset,highlight,karaoke_mode,max_chars,max_words,max_gap,max_duration)
        out=self._output(root,'captions');out.mkdir(parents=True)
        (out/'captions.srt').write_text(srt(cues),encoding='utf-8');(out/'captions.vtt').write_text(vtt(cues),encoding='utf-8')
        write_json(out/'events.json',events)
        return {'events':events,'count':len(events),'srt':str(out/'captions.srt'),'vtt':str(out/'captions.vtt'),
                'timing_basis':'seconds of the words file minus offset; retime after trims or speed changes',
                'limits':'No transcription: timings come from the supplied file and must be checked against the audio.'}

    def build_recipe(self,project_id:str,family:str,asset_ids:list[str],music_asset_id:str|None=None,text:str|None=None,
                     font_family:str|None=None,font_file:str|None=None,seconds:float=6,width:int=1080,height:int=1920,fps:float=30) -> dict:
        """Starting-point timeline for one of 8 recipe families (beat_cut_punch, xerox_ink, mono_noir, cutout_collage,
        speed_ramp_freeze, facelock_strobe, timed_type, glitch_hits) from imported assets; music (an imported audio
        asset) drives beat-based families. `family` may also be one of OpenKatana's 12 presets (get_capabilities
        presets: a family plus a look and finishing, e.g. neon-beat, travel-diary). Returned validated, not saved; the
        editor adapts it."""
        from .recipes import build
        from .audio_analysis import analyze
        number(seconds,'seconds',.5,600);number(fps,'fps',1,120);number(width,'width',16,7680,integer=True);number(height,'height',16,7680,integer=True)
        root=self._project(project_id);data=projects.state(root);index={a['id']:a for a in data['assets']}
        bad=[k for k in asset_ids if k not in index or 'clip' not in index[k]]
        if not asset_ids or bad:raise ContractError(f'asset_ids: imported video/image assets ({", ".join(bad) or "none given"})')
        saved_clips={c.get('frames_dir'):c for c in ((data.get('timeline') or {}).get('clips') or {}).values()}
        # reuse analysis already applied to the saved timeline (faces, mattes) for the same frames
        clips=[(k,{**saved_clips.get(index[k]['clip']['frames_dir'],{}),**index[k]['clip']}) for k in asset_ids]
        music=analysis=None
        if music_asset_id is not None:
            if music_asset_id not in index or index[music_asset_id].get('kind')!='audio':raise ContractError('music_asset_id: an imported audio asset')
            music=index[music_asset_id]['path'];analysis,_=analyze(root/music,0,min(seconds+.5,1800),fps)
        from .presets import resolve,finish
        recipe,preset=resolve(family)
        edit,notes=build(recipe,clips,fps,width,height,seconds,music,analysis,text,font_family);finish(edit,preset)
        if font_family:
            fonts=[{'family':font_family,'url':font_file}] if font_file else [f for f in (data.get('timeline') or {}).get('fonts',[]) if f.get('family')==font_family]
            if not fonts:raise ContractError(f'font_family {font_family!r}: give font_file (a project font file) or declare it in the saved timeline fonts')
            edit['fonts']=fonts
        validate(edit,root)
        return {'timeline':edit,'family':recipe,**({'preset':family} if preset else {}),'notes':notes,'needs_review':True}

    def render_page(self,project_id:str,page:str,frames:int|None=None,fps:float|None=None) -> dict:
        """Render a project HTML/CSS/SVG/Canvas page that defines window.openkatanaPage = {width, height, fps, frames, render(t, f)}
        into PNG frames (render(f/fps, f) per frame) after a forward/reverse determinism check; returns a clip to add to
        the timeline. Same-origin only: requests outside the project server are blocked and listed."""
        from .page_render import render_page
        root=self._project(project_id);projects.state(root)
        result=render_page(root,page,self._output(root,'pages'),frames,fps)
        first=root/result['clip']['frames_dir']/'00000.png';last=root/result['clip']['frames_dir']/f"{result['clip']['n']-1:05d}.png"
        return {**result,'preview_images':[str(first),str(last)]}

    def create_scene3d(self,project_id:str,name:str='scene',template:Literal['product','morph','physics']='product',scene:dict|None=None) -> dict:
        """Create an editable 3D scene, never overwrite one. Read scene3d guide. Optional scene is a complete schema-1 scene; asset paths are relative to scenes/NAME/."""
        from .scene3d import starter,validate as check
        root=self._project(project_id);projects.state(root)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',name):raise ContractError('Use a simple scene name')
        folder=root/'scenes'/name;value=check(scene if scene is not None else starter(template),folder)
        folder.mkdir(parents=True,exist_ok=False);path=folder/'scene.json';write_json(path,value)
        return {'scene':path.relative_to(root).as_posix(),'definition':value,'next':'check_scene3d, render_scene3d with preview_frames, then full render'}

    def inspect_model3d(self,source:str) -> dict:
        """Inspect a supplied local GLB/glTF model's clips, skins, morph targets and dependencies. No import, generation or download."""
        from .scene3d import inspect_model
        return inspect_model(source)

    def import_model3d(self,project_id:str,source:str,destination:str) -> dict:
        """Copy a supplied GLB/glTF and its local dependencies into a NEW project-relative folder, normally scenes/NAME/assets/MODEL. Rights remain the user's responsibility."""
        from .scene3d import import_model
        root=self._project(project_id);projects.state(root)
        return import_model(source,local_path(root,destination))

    def check_scene3d(self,project_id:str,scene:str) -> dict:
        """Validate scene JSON, animation targets, local model dependencies and supported fields before rendering. Does not establish visual quality."""
        from .scene3d import validate as check,input_manifest
        root=self._project(project_id);projects.state(root);path=local_path(root,scene)
        value=check(json.loads(path.read_text(encoding='utf-8')),path.parent)
        return {'valid':True,'canvas':value['canvas'],'inputs':input_manifest(value,path.parent)}

    def render_scene3d(self,project_id:str,scene:str,preview_frames:list[int]|None=None,video:bool=True,start:int|None=None,end:int|None=None,trusted_script:bool=False) -> dict:
        """Render WebGL 3D locally with reverse-seek checks. Preview stills or an inclusive start/end chunk; omit range for full clip. Custom ES modules need trusted_script=true after review. Returns PNG clip, optional MP4 and a receipt usable by assemble_render_clips. No model services or Blender required."""
        from .scene3d import render_scene
        root=self._project(project_id);projects.state(root)
        result=render_scene(local_path(root,scene),self._output(root,'scene3d'),preview_frames,video,start,end,trusted_script)
        if 'clip' in result:result['clip']['frames_dir']=Path(result['clip']['frames_dir']).relative_to(root).as_posix()
        return result

    def render_blender(self,project_id:str,source:str,engine:Literal['BLENDER_EEVEE','CYCLES']='BLENDER_EEVEE',start:int|None=None,end:int|None=None,trusted_script:bool=False) -> dict:
        """Render a project .blend or explicitly trusted .py scene script using separately installed Blender. Full Blender geometry/material/rigging/simulation authoring is available to scripts; this is NOT a security sandbox. Returns PNG clip and MP4. No automatic downloads or services."""
        from .blender_bridge import render_blender
        root=self._project(project_id);projects.state(root)
        result=render_blender(local_path(root,source),self._output(root,'blender'),engine,start,end,trusted_script)
        result['clip']['frames_dir']=Path(result['clip']['frames_dir']).relative_to(root).as_posix()
        return result

    def morph_images(self,project_id:str,source:str,target:str,width:int=512,height:int=512,fps:int=30,frames:int=60,points:dict|None=None) -> dict:
        """Morph two local images using geometric ORB correspondence or explicit normalized landmarks. Refuses unreliable matches/folded triangles. Returns an editable correspondence receipt and timeline clip; not semantic video generation."""
        from .image_morph import morph_images
        root=self._project(project_id);projects.state(root)
        result=morph_images(self._source(source),self._source(target),self._output(root,'image-morph'),width,height,fps,frames,points)
        result['clip']['frames_dir']=Path(result['clip']['frames_dir']).relative_to(root).as_posix()
        return result

    def bind_reference(self,project_id:str,name:str,asset_ids:list[str],role:str='identity',subject_type:str='person',description:str='') -> dict:
        """Record a named reference (role identity, style, product or location) from imported assets, with their hashes.
        In strict review mode, generated material (clips imported from a Comfy job) must then be accepted against every
        identity reference with inspect_identity before it renders."""
        from .identity import bind
        root=self._project(project_id);data=projects.state(root);index={a['id']:a for a in data['assets']}
        bad=[k for k in asset_ids if k not in index or 'clip' not in index[k]]
        if bad:raise ContractError(f'asset_ids: imported images or videos ({", ".join(bad)})')
        if len(description)>500:raise ContractError('description: up to 500 characters')
        return bind(root,name,[index[k] for k in asset_ids],role,subject_type,description)

    def inspect_identity(self,project_id:str,asset_id:str,references:list[str]|None=None,frames:list[int]|None=None,
                         accept:bool|None=None,note:str='') -> dict:
        """Compare an asset with bound references: a sheet of the largest detected face (or the centre) in each reference
        and in the chosen frames of the asset. Visual comparison only - no biometric identity score. Look at the sheet,
        then call again with accept true/false to record the decision used by the strict review gate."""
        from .identity import load,inspect,record_review,asset_key
        root=self._project(project_id);data=projects.state(root);index={a['id']:a for a in data['assets']}
        if asset_id not in index or 'clip' not in index[asset_id]:raise ContractError('asset_id: an imported image or video')
        refs_all=load(root)['references']
        names=references if references is not None else [n for n,r in refs_all.items() if r['role']=='identity']
        if not names or any(n not in refs_all for n in names):raise ContractError(f'references: bound names ({", ".join(refs_all) or "none bound - use bind_reference"})')
        if accept is not None and not isinstance(accept,bool):raise ContractError('accept must be true or false')
        frames=frames if frames is not None else [0];asset=index[asset_id]
        if not 1<=len(frames)<=8:raise ContractError('frames: 1..8 source frames')
        refs=[refs_all[n] for n in names];result=inspect(root,asset,refs,frames,self._output(root,'identity'))
        if accept is not None:record_review(root,asset_key(root,asset),refs,accept,note);result['recorded']={'accepted':accept,'references':names}
        else:result['next']='inspect the sheet, then call inspect_identity again with accept true or false'
        result['preview_images']=[result['sheet']];return result

    def review_mask(self,project_id:str,clip_id:str,step:float=.25,accept:bool|None=None,note:str='') -> dict:
        """Review a clip's matte: sheets of the source every `step` s plus the last frame with the background tinted, the
        matte edge outlined and coverage per frame; flags empty/full mattes and coverage jumps. Look at the sheets, then
        call again with accept true/false to record the decision (strict mode blocks matte-dependent renders - cutout,
        outline, contour, contour_glow, cut-out stickers - until the current matte is accepted)."""
        from . import vision
        from .gates import record_matte
        root=self._project(project_id);state=projects.state(root)
        if not state['timeline'] or clip_id not in state['timeline']['clips']:raise ContractError('clip_id: a clip of the saved timeline')
        if accept is not None and not isinstance(accept,bool):raise ContractError('accept must be true or false')
        result=vision.review_masks(root/'timeline.json',clip_id,self._output(root,'mask-review'),step)
        if accept is not None:record_matte(root,result['mask_sha256'],clip_id,accept,note);result['recorded']={'accepted':accept,'note':note}
        else:result['next']='inspect the sheets, then call review_mask again with accept true or false'
        result['preview_images']=result['sheets'];return result

    def set_review_policy(self,project_id:str,strict:bool,require_motion:bool|None=None) -> dict:
        """Optional strict mode: start_render then refuses until every source used by the timeline was inspected
        (preview_source / source_contact_sheet) and the current revision was previewed (preview_timeline); with
        require_motion also until revise_motion measured the current revision against a reference."""
        from .gates import set_strict,missing
        if not isinstance(strict,bool):raise ContractError('strict must be true or false')
        if require_motion is not None and not isinstance(require_motion,bool):raise ContractError('require_motion must be true or false')
        root=self._project(project_id);data=set_strict(root,strict,require_motion)
        return {'strict':data['strict'],'require_motion':data['require_motion'],'blocking':missing(root,projects.state(root))}

    def revise_motion(self,project_id:str,reference:str,max_revisions:int=2,locked_shots:list[int]|None=None,floor:float=.6,
                      reference_start:float=0,reference_duration:float|None=None,apply:bool=False,ceiling:float|None=None) -> dict:
        """Bounded motion revision loop: render the saved timeline, measure per-second cuts, flashes, shake frames,
        jitter, camera movement and motion energy against a reference video (analyze_energy measures), then up to
        max_revisions (0-4) times propose camera-only edits on unlocked shots (shake bursts, pans, punch hits at the
        reference's event times; amplitude scaling bounded 0.5-2x per step), re-render and re-measure; the best attempt
        is kept. Clips, shot spans, sources, transitions, flashes, text, looks, post and audio never change; cut/flash
        shortfalls are listed for the editor. ceiling (e.g. 2) also fails camera movement / motion energy above
        ceiling x the reference and scales camera moves down (0.5x minimum per step). apply=true saves the best
        attempt only if it scores better. Records the
        assessment for the strict review gate. Slow: one full render per attempt."""
        from .motion_loop import run
        from .gates import record_motion
        from .render import digest
        number(max_revisions,'max_revisions',0,4,integer=True);number(floor,'floor',0,1);number(reference_start,'reference_start',0)
        if reference_duration is not None:number(reference_duration,'reference_duration',.5,3600)
        if ceiling is not None:number(ceiling,'ceiling',1.05,20)
        if not isinstance(apply,bool):raise ContractError('apply must be true or false')
        root=self._project(project_id);state=projects.state(root)
        if not state['timeline']:raise ContractError('Save a timeline first')
        ref=self._source(reference);out=self._output(root,'motion')
        result=run(root,state['timeline'],ref,out,max_revisions,locked_shots or [],floor,reference_start,reference_duration,ceiling=ceiling)
        result['report']=str(out)
        ref_sha=digest(ref);first=result['attempts'][0]
        record_motion(root,state['revision'],{'status':'pass' if first['ok'] else 'needs_editor','score':first['score'],'reference_sha256':ref_sha})
        result['saved']=None
        if apply and result['best_attempt']>0:
            saved=projects.save(root,result['timeline'],state['revision']);result['saved']=saved
            best=result['attempts'][result['best_attempt']]
            record_motion(root,saved['revision'],{'status':'pass' if best['ok'] else 'needs_editor','score':best['score'],'reference_sha256':ref_sha})
        result['images']=[result['attempts'][result['best_attempt']]['chart'],str(out/'reference-energy.png')]
        result['needs_review']=True
        return result

    def list_sfx(self,category:str|None=None) -> dict:
        """Browse OpenKatana's own synthesised sound effects (no recordings or licences involved): name, category,
        variants, duration and default level. Place them with timeline audio.cues [{sfx, variant, at, level_db}]."""
        from .sfx import catalog
        items=[c for c in catalog() if category is None or c['category']==category]
        if category is not None and not items:raise ContractError(f'Unknown sfx category {category!r}')
        return {'sfx':items,'usage':'audio: {"mode":"mix","tracks":[...music...],"cues":[{"sfx":"whoosh","at":1.2}]}',
                'provenance':'generated by openkatana/sfx.py (deterministic synthesis)'}

    def list_fonts(self,directory:str|None=None,query:str='',limit:int=100,text:str|None=None) -> dict:
        """List actual local font family/style/path metadata. Use a supplied folder for project fonts. No downloads or automatic matching.
        With `text`, each font reports the characters it lacks (`missing`) and whether it `covers` the text."""
        from .editor_tools import list_fonts
        return list_fonts(directory,query,limit,text)

    def preview_fonts(self,project_id:str,sources:list[str],text:str='AFTER HOURS') -> dict:
        """See side-by-side specimens and exact hashes of up to eight local TTF/OTF/TTC font files before choosing one (TTC: first face, as browsers load it)."""
        from .editor_tools import preview_fonts
        root=self._project(project_id);projects.state(root)
        return preview_fonts([self._source(p) for p in sources],text,self._output(root,'font-specimens'))

    def preview_segment(self,project_id:str,source:str,start:float=0,duration:float=5,max_width:int=960) -> dict:
        """Create a playable video excerpt (up to 15s) and an audio preview for clients supporting audio input. Never claim listening from metadata."""
        from .editor_tools import preview_segment
        root=self._project(project_id);projects.state(root)
        return preview_segment(self._source(source),self._output(root,'segment-previews'),start,duration,max_width)

    def compare_reference(self,project_id:str,reference:str,rendered:str,times:list[float],render_offset:float=0) -> dict:
        """See paired reference/render pictures at the same requested times (render time = reference time + offset)."""
        from .editor_tools import compare_frames
        root=self._project(project_id);projects.state(root)
        return compare_frames(self._source(reference),self._source(rendered),self._output(root,'comparisons'),times,render_offset)

    def save_reference_plan(self,project_id:str,plan:dict) -> dict:
        """Record verified reference timing/text/font/effect requirements. Read tool-audit guide for schema. Render blocks mismatches; do not invent or silently weaken requirements."""
        from .editor_tools import validate_plan
        root=self._project(project_id);projects.state(root);validate_plan(plan)
        source=self._source(plan['source']);plan={**plan,'source':str(source)}
        path=root/'reference-plan.json'
        if path.exists():write_json(root/'history'/('reference-plan-'+uuid.uuid4().hex+'.json'),json.loads(path.read_text(encoding='utf-8')))
        write_json(path,{'plan':plan,'source_sha256':digest(source),'recorded_at':projects.stamp()})
        return {'saved':str(path),'note':'This records an agent/user-verified specification, not automatic reference recognition.'}

    def audit_reference_plan(self,project_id:str) -> dict:
        """Check saved timeline against exact cut frames, literal timed text, font file hashes and specified shot settings."""
        from .editor_tools import audit_plan
        root=self._project(project_id);edit=projects.state(root)['timeline']
        if edit is None:raise ContractError('Save a timeline before auditing')
        return audit_plan(root,edit)

    def import_media_batch(self,project_id:str,source:str,excerpts:list[dict],request_id:str,rights:str='review_pending') -> dict:
        """Import 1..32 excerpts, hashing a large source once. Each excerpt has start/duration and optional max_width/audio_only. Repeated request IDs return recorded partial/completed results without duplicating imports."""
        from .contracts import fields
        root=self._project(project_id);projects.state(root);source=self._source(source)
        if not isinstance(excerpts,list) or not 1<=len(excerpts)<=32:raise ContractError('Supply 1..32 excerpts')
        if not request_id or len(request_id)>128:raise ContractError('Supply a request ID of 1..128 characters')
        for e in excerpts:
            fields(e,'start duration max_width audio_only','excerpt');number(e.get('start',0),'start',0);number(e.get('duration'),'duration',.01)
            if 'max_width' in e:number(e['max_width'],'max_width',64,8192,integer=True)
            if 'audio_only' in e and not isinstance(e['audio_only'],bool):raise ContractError('audio_only must be boolean')
        signature={'source':str(source),'excerpts':excerpts,'rights':rights};key=uuid.uuid5(uuid.NAMESPACE_URL,str(root)+'/batch/'+request_id).hex
        path=root/'.openkatana/import-batches'/key/'receipt.json'
        if path.exists():
            previous=json.loads(path.read_text(encoding='utf-8'))
            if previous['request']!=signature:raise ContractError('Request ID already used with different import arguments')
            return previous
        stat=source.stat();fingerprint=(stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
        sha=digest(source);result={'request':signature,'source_sha256':sha,'state':'running','assets':[]}
        write_json(path,result)
        try:
            for e in excerpts:
                stat=source.stat()
                if (stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)!=fingerprint:raise ContractError('Source changed during batch import')
                asset=self._import_media(project_id,str(source),rights=rights,source_sha256=sha,**e)
                result['assets'].append(asset);write_json(path,result)
            stat=source.stat()
            if (stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)!=fingerprint:raise ContractError('Source changed during batch import')
            result['state']='succeeded'
        except Exception as e:result.update(state='failed',error=str(e),note='Inspect recorded assets; this request is not automatically restarted.')
        write_json(path,result);return result

    def get_render(self,project_id:str,job_id:str) -> dict:
        """Read a recorded render status and output path, also after MCP reconnects. Never resubmits."""
        from .jobs import status
        return status(self._project(project_id),job_id)

    def review_render(self,project_id:str,job_id:str,decision:Literal['approved','changes_requested'],notes:str) -> dict:
        """Record the agent's review against rendered source/timeline hashes. Does not publish or imply human approval."""
        from .jobs import folder
        return projects.review(self._project(project_id),folder(self._project(project_id),job_id),decision,'Agent review: '+notes)

    def analyze_clip(self,project_id:str,clip_id:str,operation:Literal['masks','faces','interpolate','retime'],
                     options:dict|None=None,apply:bool=False) -> dict:
        """Run local source analysis. Preview results; apply=true saves a new timeline revision.

        masks options: mode (chroma, luma, alpha, grabcut, refine), key, tolerance, softness, rect, feather;
        mode refine (an existing matte): grow (px, - shrinks), feather, fill_holes, smooth (frames), keep_largest. faces: min_size,
        detector (auto: the bundled YuNet model with eyes, nose tip and mouth corners; cascade: OpenCV cascades, eyes
        only), cascade (a classifier file, cascade detector). interpolate: multiplier. retime (slow motion as a plate with
        one new picture per output frame): start, seconds (clip source interval), output_frames, fps (default the
        canvas fps), take_start/take_seconds (one take; cuts inside are refused), deduplicate (collapse baked repeats,
        run-centre timing), duplicate_threshold; returns a new clip to add and use at speed 1 from src 0 (apply is not
        available for retime). No models are automatically downloaded.
        """
        from . import vision
        if operation not in ('masks','faces','interpolate','retime'):raise ContractError('Unknown analysis operation')
        if operation=='retime' and apply:raise ContractError('retime makes a new plate for one source interval; add the returned clip under a new name and use it at speed 1 from src 0')
        root=self._project(project_id);state=projects.state(root);out=self._output(root,operation)
        opts=dict(options or {})
        if operation=='masks' and opts.get('mode')=='refine':   # refine an existing matte: grow, feather, fill_holes, smooth
            opts.pop('mode');result=vision.refine_masks(root/'timeline.json',clip_id,out,**opts)
        else:result=getattr(vision,operation)(root/'timeline.json',clip_id,out,**opts)
        update=result if operation in ('interpolate','retime') else result['clip_update']
        changes=[]
        if apply:
            timeline=state['timeline'];clip=timeline['clips'][clip_id]
            for key,value in update.items():
                if clip.get(key)!=value:changes.append({'path':f'clips.{clip_id}.{key}','before':clip.get(key),'after':value})
            clip.update(update)
            if operation=='interpolate':
                # srcf counts source frames, which are now `multiplier` times denser; src (seconds) and speed keep timing.
                multiplier=(options or {}).get('multiplier',2)
                for i,shot in enumerate(timeline['shots']):
                    if shot.get('clip')==clip_id and 'srcf' in shot:
                        after=shot['srcf']*multiplier;changes.append({'path':f'shots[{i}].srcf','before':shot['srcf'],'after':after});shot['srcf']=after
            saved=projects.save(root,timeline,state['revision'])
        else:saved=None
        return {'result':result,'clip_update':update,'changes':changes,'saved':saved,'output':str(out),'quality_review':'pending'}

    def build_workflow(self,project_id:str,kind:Literal['matte','segmentation','interpolation','generation','qwen-generation','h3-generation','cutout','qwen-edit','h3-reference','seedvr2-restore','model-interpolation','image-upscale'],parameters:dict|None=None) -> dict:
        """Build an audited LOCAL workflow with explicit installed model names; returns a project-relative file."""
        from .workflows import save
        root=self._project(project_id);projects.state(root);p=self._output(root,'workflows').with_suffix('.json')
        from .model_workflows import asset_ports
        graph=save(kind,p,**(parameters or {}));return {'workflow':p.relative_to(root).as_posix(),'graph':graph,'asset_ports':asset_ports(graph)}

    def check_workflow(self,project_id:str,workflow:str,native_endpoint:str='http://127.0.0.1:8000',reviewed_local_nodes:list[str]|None=None) -> dict:
        """Check local nodes/models without execution. For imported API workflows, reviewed_local_nodes
        extends this workflow's supported nodes after inspecting their implementation for local-only,
        no-download behavior. It never permits partner API nodes. See the comfy-models guide."""
        from .comfy import validate_workflow
        from .workflows import preflight
        return preflight(validate_workflow(local_path(self._project(project_id),workflow),reviewed_local_nodes=reviewed_local_nodes),native_endpoint,reviewed_local_nodes)

    def run_model_workflow(self,project_id:str,kind:str,parameters:dict,assets:dict[str,str],request_id:str,
                           endpoint:str='http://127.0.0.1:8189',native_endpoint:str='http://127.0.0.1:8000') -> dict:
        """Build, check, submit or collect an installed LOCAL model workflow with stable request ID.

        assets must bind every returned build_workflow asset port to a project-relative file.
        Repeating identical arguments collects the original job; it never resubmits failures
        or uncertain outcomes. Outputs still need visual/identity review and explicit import.
        """
        from .workflows import build
        from .model_workflows import asset_ports
        from .comfy import local_endpoint
        local_endpoint(endpoint);local_endpoint(native_endpoint)
        root=self._project(project_id);projects.state(root)
        if not isinstance(request_id,str) or not 1<=len(request_id)<=128:raise ContractError('Supply a stable request_id of 1..128 characters')
        graph=build(kind,**parameters);ports=asset_ports(graph)
        if set(assets)!=set(ports):raise ContractError(f'Bind exactly these asset ports: {sorted(ports)}')
        signature={'graph':graph,'assets':{k:digest(local_path(root,v)) for k,v in assets.items()},'endpoint':endpoint,'native_endpoint':native_endpoint}
        folder=root/'.openkatana/model-runs'/uuid.uuid5(uuid.NAMESPACE_URL,request_id).hex
        if folder.exists():
            if not (folder/'plan.json').is_file() or json.loads((folder/'plan.json').read_text(encoding='utf-8'))!=signature:
                raise ContractError('Model request changed or preparation interrupted; use the original inputs and inspect the receipt')
        else:
            folder.mkdir(parents=True);write_json(folder/'plan.json',signature);write_json(folder/'workflow.json',graph)
        submitted=self.submit_workflow(project_id,(folder/'workflow.json').relative_to(root).as_posix(),request_id,assets,endpoint,native_endpoint)
        if submitted['receipt'].get('job_id'):
            submitted['receipt']=self.collect_workflow(project_id,submitted['directory'])
        return {**submitted,'asset_ports':ports,'review_required':True,'quality_note':'Model precision and reference adherence require separate review; success is not a quality guarantee'}

    def submit_workflow(self,project_id:str,workflow:str,request_id:str,assets:dict[str,str]|None=None,
                        endpoint:str='http://127.0.0.1:8189',native_endpoint:str='http://127.0.0.1:8000',
                        execution:Literal['local','cloud']='local',allow_paid:bool=False,reviewed_local_nodes:list[str]|None=None) -> dict:
        """Submit through official Comfy SDK. assets maps NODE.INPUT to project-relative files.

        Use a stable request_id. Existing receipts are returned, including unknown submission
        outcomes; the server never blindly retries them. Local is the default. For paid workflows,
        use execution=cloud, endpoint=https://cloud.comfy.org and allow_paid=true only after
        user authorization for the job and media upload. COMFY_API_KEY comes from the environment.
        Supply an API-format workflow supported by Comfy Cloud; build_workflow remains local.
        Imported local workflows may supply reviewed_local_nodes after source/schema inspection
        establishes no paid calls or automatic downloads. The extension is recorded in the receipt.
        """
        from .comfy import submit, authorize_execution, reviewed_nodes
        authorize_execution(endpoint, execution, allow_paid)
        root=self._project(project_id);path=local_path(root,workflow)
        if not request_id or len(request_id)>128:raise ContractError('Supply a request ID of 1..128 characters')
        bindings={k:local_path(root,v) for k,v in (assets or {}).items()}
        signature={'workflow_sha256':digest(path),'assets':{k:digest(v) for k,v in bindings.items()},'endpoint':endpoint,'native_endpoint':native_endpoint}
        if reviewed_local_nodes:signature['reviewed_local_nodes']=sorted(reviewed_nodes(reviewed_local_nodes))
        if execution != 'local':signature.update(execution=execution,allow_paid=allow_paid)
        key=uuid.uuid5(uuid.NAMESPACE_URL,str(root)+'/comfy/'+request_id).hex;out=root/'.openkatana/comfy-agent'/key
        if out.exists():
            if json.loads((out/'request.json').read_text(encoding='utf-8'))!=signature:raise ContractError('Request ID already used with different workflow inputs')
            receipt=out/'job/job.json'
            if not receipt.exists():raise ContractError('Previous submission did not record a receipt; inspect the existing request before retrying')
            result=json.loads(receipt.read_text(encoding='utf-8'))
        else:
            out.mkdir(parents=True);write_json(out/'request.json',signature)
            extra={'reviewed_local_nodes':reviewed_local_nodes} if reviewed_local_nodes else {}
            result=submit(path,out/'job',endpoint,[f'{k}={v}' for k,v in bindings.items()],native_endpoint,execution,allow_paid,**extra)
        return {'directory':(out/'job').relative_to(root).as_posix(),'receipt':result}

    def collect_workflow(self,project_id:str,directory:str) -> dict:
        """Collect the previously submitted Comfy job; never submit a replacement."""
        from .comfy import collect
        return collect(local_path(self._project(project_id),directory))

    def import_workflow_output(self,project_id:str,directory:str,kind:Literal['clip','mask']='clip',clip_id:str|None=None,fps:float=30,output_file:str|None=None) -> dict:
        """Import collected images/masks or one video/audio output. Select output_file for mixed outputs."""
        from .comfy_assets import import_outputs
        root=self._project(project_id);return import_outputs(local_path(root,directory),root,kind,clip_id,fps,output_file)

    def process_clip(self,project_id:str,clip_id:str,kind:Literal['matte','segmentation','interpolation','cutout'],directory:str,
                     endpoint:str='http://127.0.0.1:8189',native_endpoint:str='http://127.0.0.1:8000',model:str|None=None,
                     points:list[list[float]]|None=None,negative_points:list[list[float]]|None=None) -> dict:
        """Advance a resumable whole-clip Comfy sequence. Reuse directory and settings to collect/continue.

        cutout: point-click subject cut-out. points/negative_points are [x, y] clicks in 0..1 coordinates of the clip's
        first frame (on / off the subject); a SAM2 video model (model, e.g. sam2.1_hiera_base_plus.safetensors, must
        already be installed) carries the selection through the clip in one job and the masks become the clip's mask_dir
        after review. Preview the first frame (preview_source) to place the clicks."""
        from .comfy_sequence import process
        root=self._project(project_id)
        return process(root/'timeline.json',clip_id,local_path(root,directory),kind,endpoint,native_endpoint,model,points,negative_points)

    def create_composition(self,project_id:str,name:str='composition',width:int=1280,height:int=720,fps:int=30,frames:int=90) -> dict:
        """Create an original responsive composition. Use for CSS layout and fully shaped multilingual text."""
        from . import composition
        root=self._project(project_id);projects.state(root);composition.name(name,'name')
        doc=composition.starter(width,height,fps,frames)
        return {**composition.save_composition(root,f'compositions/{name}.json',doc,None),'document':doc}

    def save_composition(self,project_id:str,path:str,document:dict,revision:str|None) -> dict:
        """Validate/save a composition with a revision guard and history. Null revision means create only."""
        from . import composition
        root=self._project(project_id);projects.state(root)
        return composition.save_composition(root,path,document,revision)

    def inspect_composition(self,project_id:str,path:str,frame:int=0,width:int|None=None,height:int|None=None) -> dict:
        """Preview actual layout, font loading, grapheme ranges and overflow at a viewport size. Runs trusted declared plugins."""
        from . import composition
        root=self._project(project_id);projects.state(root);doc=json.loads(local_path(root,path).read_text(encoding='utf-8'))
        return composition.inspect_composition(root,doc,frame,width,height,self._output(root,'composition-previews')/'preview.png')

    def render_composition(self,project_id:str,path:str,width:int|None=None,height:int|None=None,video:bool=True) -> dict:
        """Render a responsive composition offline with deterministic seeking checks. Returns a normal timeline clip."""
        from . import composition
        root=self._project(project_id);projects.state(root);doc=json.loads(local_path(root,path).read_text(encoding='utf-8'))
        return composition.render_composition(root,doc,self._output(root,'compositions'),width,height,video)

    def list_plugins(self,project_id:str,manifests:list[str]|None=None) -> dict:
        """Load trusted project plugin manifests; list actual components, effects, operators and parameter contracts."""
        from . import composition
        root=self._project(project_id);projects.state(root)
        return composition.list_plugins(root,manifests if manifests is not None else [])

    def run_plugin_operator(self,project_id:str,operator:str,document:dict,parameters:dict|None=None,
                            manifests:list[str]|None=None,kind:Literal['composition','timeline']='composition') -> dict:
        """Run an original plugin operation as a validated, deterministic proposal; never saves. core/batch supports atomic do/ops-style document changes. Save with the returned before_revision through save_composition/save_timeline."""
        from . import composition
        root=self._project(project_id);projects.state(root)
        return composition.run_operator(root,manifests if manifests is not None else [],operator,document,parameters,kind)

    def create_animation_kit(self,project_id:str,directory:str='animation',width:int=640,height:int=360,fps:int=30,frames:int=60) -> dict:
        """Create an editable original Blender animation starter and display atlas. No render/download. Existing paths are never overwritten. Read the animation guide; customize the scene for the brief."""
        from .production import create_kit
        root=self._project(project_id);projects.state(root)
        return create_kit(root,directory,width,height,fps,frames)

    def create_webgl_kit(self,project_id:str,directory:str='webgl',width:int=640,height:int=360,fps:int=30,frames:int=60) -> dict:
        """Create an original editable JavaScript/Three.js scene, cut-safe camera schedule and animated display atlas. No render or download; existing paths preserved. Read webgl guide and customize for the brief. Uses the bundled WebGL renderer instead of Blender."""
        from .webgl_authoring import create_kit
        root=self._project(project_id);projects.state(root)
        return create_kit(root,directory,width,height,fps,frames)

    def assemble_render_clips(self,project_id:str,receipts:list[str],contiguous:bool=True) -> dict:
        """Assemble ordered WebGL or Blender receipt paths into a validated timeline proposal. Checks frame files, dimensions/fps, source/renderer hashes and contiguous ranges. Set contiguous=false for independent shots or mixed renderers. Does not save the timeline."""
        from .production import assemble_chunks
        root=self._project(project_id);projects.state(root)
        return assemble_chunks(root,receipts,self._output(root,'assemblies'),contiguous)

    def build_display_atlas(self,project_id:str,document:dict) -> dict:
        """Create frame-indexed RGB LED masks from text cues (animation guide). Returns atlas/tiles/receipt. Limited original dot glyphs; use compositions for shaped multilingual text."""
        from .production import display_atlas
        root=self._project(project_id);projects.state(root)
        return display_atlas(document,self._output(root,'display-atlases'))

    def synthesize_score(self,project_id:str,document:dict) -> dict:
        """Render an original deterministic local oscillator/noise score from explicit notes. No AI model or paid service. Returns WAV plus reproducible recipe and preview_audio."""
        from .production import synthesize_score
        root=self._project(project_id);projects.state(root)
        return synthesize_score(document,self._output(root,'scores'))

    def assemble_blender_clips(self,project_id:str,receipts:list[str],contiguous:bool=True) -> dict:
        """Validate ordered project-relative Blender receipts and return a timeline proposal with frame hashes. Reject missing frames, dimensions/fps drift and (by default) source-range gaps. Does not save the project timeline."""
        from .production import assemble_chunks
        root=self._project(project_id);projects.state(root)
        return assemble_chunks(root,receipts,self._output(root,'assemblies'),contiguous)

    def analyze_render_motion(self,project_id:str,source:str,cuts:list[int]|None=None,work_width:int=480,moving:float=1.5,ratio:float=2.2,stall:float=.25) -> dict:
        """Measure decoded-frame optical flow and candidate judder/stalls, excluding planned cuts. source is a local video; thresholds use source pixels/frame. Requires vision extra. Analysis only; never interpolates or revises the video."""
        from .motion_qa import analyze_video
        root=self._project(project_id);projects.state(root)
        return analyze_video(self._source(source),self._output(root,'motion-reports'),cuts,work_width,moving,ratio,stall)

    def analyze_camera_motion(self,project_id:str,document:dict,jolt_threshold:float=2500,jolt_ratio:float=3) -> dict:
        """Analyze evaluated camera_samples from blender_helpers: speed, aim jolts and rotational shutter streak estimates. Includes constraints; not a full image-space blur or aesthetic verdict."""
        from .motion_qa import analyze_camera
        root=self._project(project_id);projects.state(root)
        return analyze_camera(document,self._output(root,'camera-reports'),jolt_threshold,jolt_ratio)

    def call(self,tool,arguments):
        if tool not in TOOLS:raise ContractError('Unknown OpenKatana tool')
        if not isinstance(arguments,dict):raise ContractError(f'{tool}: arguments must be a JSON object')
        params=inspect.signature(getattr(self,tool)).parameters
        unknown=sorted(set(arguments)-set(params))
        if unknown:raise ContractError(f'{tool}: unsupported arguments: {", ".join(unknown)} (supported: {", ".join(params)})')
        missing=[n for n,p in params.items() if p.default is inspect.Parameter.empty and n not in arguments]
        if missing:raise ContractError(f'{tool}: missing required arguments: {", ".join(missing)}')
        return getattr(self,tool)(**arguments)

    def catalog(self):
        return [{'name':name,'description':inspect.getdoc(getattr(self,name)),'signature':str(inspect.signature(getattr(self,name)))} for name in TOOLS]
