import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np
from PIL import Image

from openkatana.agent_api import AgentAPI, TOOLS
from openkatana.camera_path import CameraTrack, spring_follow
from openkatana.contracts import ContractError
from openkatana.motion_qa import analyze_camera, analyze_video, flow_flags
from openkatana.production import assemble_chunks, display_atlas, synthesize_score
from openkatana.render import digest, encode, write_json


def pose(x):
    return {'pos':[x,-5,2],'tgt':[x,0,0],'lens':35,'fstop':4}


def segments():
    return [{'f0':0,'f1':10,'type':'push','poses':[pose(0),pose(1),pose(1)]},
            {'f0':10,'f1':20,'cut':True,'type':'hold','poses':[pose(-4),pose(-3)]}]


class AnimationTests(unittest.TestCase):
    def setUp(self):
        work=Path(__file__).resolve().parents[1]/'work';work.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=work);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_repeated_waypoints_do_not_reverse_at_landing(self):
        s=segments()[:1];s[0]['type']='hold'
        track=CameraTrack(s)
        xs=[track.sample(i/10)['pos'][0] for i in range(101)]
        self.assertTrue(all(b>=a-1e-10 for a,b in zip(xs,xs[1:])))
        self.assertEqual(xs[-1],1)

    def test_cut_finishes_previous_move_and_reverse_seek_is_stable(self):
        track=CameraTrack(segments(),step=.5)
        self.assertAlmostEqual(track.sample(9.5)['pos'][0],1)
        self.assertEqual(track.sample(10)['pos'][0],-4)
        frames=[i/2 for i in range(41)]
        forward={f:track.sample(f) for f in frames}
        self.assertEqual(forward,{f:track.sample(f) for f in reversed(frames)})
        self.assertEqual(track.sample(-5)['pos'],pose(0)['pos'])

    def test_continuous_motion_matches_across_native_frame_rates(self):
        s=segments()[:1]
        a=CameraTrack(s,step=1);b=CameraTrack(s,step=.5)
        for f in range(11): self.assertEqual(a.sample(f),b.sample(f))
        s[0]['poses'][-1]['fstop']=8
        track=CameraTrack(s)
        self.assertEqual(track.sample(0)['fstop'],4)
        self.assertEqual(track.sample(10)['fstop'],8)

    def test_invalid_camera_specs_rejected(self):
        for change in (lambda s:s[0].update(f1=0),lambda s:s[1].update(f0=11),
                       lambda s:s[0].update(unknown=True),lambda s:s[0]['poses'][0].update(lens=float('nan'))):
            s=segments();change(s)
            with self.assertRaises(ContractError):CameraTrack(s)

    def test_spring_smooths_snap_and_resets_at_cut(self):
        values=[0.]*10+[1.]*50
        result=spring_follow(values,60,cuts=[30])
        self.assertLess(result[10],.2)
        self.assertAlmostEqual(result[30],1)
        self.assertEqual(result,spring_follow(values,60,cuts=[30]))
        fast=spring_follow(values,12,hz=90,damping=4)
        self.assertTrue(all(math.isfinite(x) for x in fast))

    def test_atlas_frame_index_reveal_channels_and_bounds(self):
        spec={'cols':32,'rows':9,'frames':6,'fps':24,'tiles_x':3,'cues':[
            {'start':0,'end':3,'text':'GO','reveal_frames':3}, {'start':3,'end':6,'text':'PLAY','channel':1}]}
        a=display_atlas(spec,self.root/'atlas');b=display_atlas(spec,self.root/'atlas2')
        self.assertEqual(a['sha256'],b['sha256'])
        pixels=np.array(Image.open(a['atlas']))
        self.assertLess(pixels[:9,:32,0].sum(),pixels[:9,64:96,0].sum())
        self.assertGreater(pixels[9:18,:32,1].sum(),0)
        self.assertEqual(pixels[9:18,:32,0].sum(),0)
        spec['cues'][0]['text']='漢'
        with self.assertRaises(ContractError):display_atlas(spec,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())

    def test_score_is_deterministic_stereo_and_bounded(self):
        spec={'duration':.2,'seed':4,'sample_rate':8000,'notes':[
            {'at':0,'duration':.2,'waveform':'noise','pan':-1,'gain':1}]}
        a=synthesize_score(spec,self.root/'score');b=synthesize_score(spec,self.root/'score2')
        self.assertEqual(a['sha256'],b['sha256'])
        with wave.open(a['audio'],'rb') as f:
            self.assertEqual(f.getnframes(),1600)
            pcm=np.frombuffer(f.readframes(1600),dtype='<i2').reshape(-1,2)
        self.assertGreater(np.abs(pcm[:,0]).max(),100)
        self.assertEqual(np.abs(pcm[:,1]).max(),0)
        self.assertLessEqual(np.abs(pcm).max(),31130)
        spec['notes'][0]['duration']=1
        with self.assertRaises(ContractError):synthesize_score(spec,self.root/'bad-score')

    def fixture_receipt(self,name,start=0,fps=24):
        out=self.root/name;(out/'frames').mkdir(parents=True)
        for i in range(3):Image.new('RGB',(64,64),(i*60,20,40)).save(out/'frames'/f'{i:05d}.png')
        receipt={'width':64,'height':64,'frames':3,'fps':fps,'source_frame_start':start,'source_frame_end':start+2,
                 'source_sha256':'fixture','clip':{'frames_dir':str(out/'frames'),'n':3,'w':64,'h':64,'fps':fps,'pattern':'%05d.png'}}
        write_json(out/'receipt.json',receipt)
        return name+'/receipt.json'

    def test_chunk_assembly_preserves_every_native_frame(self):
        receipts=[self.fixture_receipt('a'),self.fixture_receipt('b',3)]
        result=assemble_chunks(self.root,receipts,self.root/'assembled')
        self.assertEqual(result['timeline']['canvas']['frames'],6)
        self.assertEqual([s['f0'] for s in result['timeline']['shots']],[0,3])
        self.assertFalse(result['saved_to_project'])
        self.assertFalse((self.root/'timeline.json').exists())
        with self.assertRaises(ContractError):assemble_chunks(self.root,receipts[::-1],self.root/'reversed')
        with self.assertRaises(ContractError):assemble_chunks(self.root,[receipts[0]]*2,self.root/'dup')
        (self.root/'b/frames/00001.png').unlink()
        with self.assertRaises(ContractError):assemble_chunks(self.root,receipts,self.root/'missing')

    def test_chunk_rate_mismatch_and_escaping_paths_fail(self):
        a=self.fixture_receipt('a');b=self.fixture_receipt('b',3,30)
        with self.assertRaises(ContractError):assemble_chunks(self.root,[a,b],self.root/'mix')
        with self.assertRaises(ContractError):assemble_chunks(self.root,['../receipt.json'],self.root/'escape')

    def test_flow_excludes_cuts_and_reports_stalls(self):
        rows=[{'frame':i,'median_px':v} for i,v in enumerate([None,3,3,0,3,3,3])]
        self.assertEqual(flow_flags(rows)[0]['kind'],'stall')
        rows[3]['median_px']=None
        self.assertEqual(flow_flags(rows),[])

    def test_real_encoded_video_flow(self):
        try:import cv2
        except ImportError:self.skipTest('vision extra not installed')
        folder=self.root/'frames';folder.mkdir()
        rng=np.random.default_rng(2);texture=rng.integers(0,255,(64,96,3),dtype=np.uint8)
        for i,x in enumerate([0,2,4,6,8,8,10,12,14,16]):
            Image.fromarray(np.roll(texture,x,axis=1)).save(folder/f'{i:05d}.png')
        encode(folder,{'width':96,'height':64,'frames':10,'fps':24},self.root/'test.mp4')
        report=analyze_video(self.root/'test.mp4',self.root/'flow',work_width=96,moving=.5)
        self.assertEqual(report['frames'],10)
        self.assertTrue(any(f['frame']==5 and f['kind']=='stall' for f in report['flags']))
        cut=analyze_video(self.root/'test.mp4',self.root/'cut-flow',cuts=[5],work_width=96,moving=.5)
        self.assertFalse(any(f['frame']==5 for f in cut['flags']))

    def test_camera_report_excludes_cut_speed_but_checks_shutter(self):
        rows=[{'f':i,'pos':[i if i<3 else i+100,0,0],'fwd':[0,0,-1],
               'fwd_open':[0,0,-1],'fwd_close':[0,0,-1],'hfov_deg':60} for i in range(6)]
        report=analyze_camera({'fps':24,'width':960,'cuts':[3],'rows':rows},self.root/'camera')
        self.assertEqual(report['max_shutter_rotation_px'],0)
        self.assertEqual(report['flags'],[])
        csv=(self.root/'camera/metrics.csv').read_text()
        self.assertIn('3,True,,,',csv)

    def test_kit_and_api_discoverable_without_private_project(self):
        api=AgentAPI(self.root);api.create_project('Example','example')
        result=api.create_animation_kit('example',frames=8,fps=24)
        self.assertTrue(Path(result['config']).is_file())
        expected={'create_animation_kit','build_display_atlas','synthesize_score',
                  'assemble_blender_clips','analyze_render_motion','analyze_camera_motion'}
        self.assertTrue(expected<=set(TOOLS))
        self.assertTrue(all(callable(getattr(api,name,None)) for name in expected))
        with self.assertRaises(FileExistsError):api.create_animation_kit('example')
        with self.assertRaises(ContractError):api.create_animation_kit('example','../outside')
        with self.assertRaises(ContractError):api.call('create_animation_kit',{'project_id':'example','bogus':True})


if __name__=='__main__':unittest.main()
