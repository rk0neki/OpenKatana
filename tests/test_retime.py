import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from openkatana.contracts import ContractError
from openkatana.render import write_json
from openkatana.vision import retime


def square_x(path):
    """Brightness-weighted centre x of the square in a frame (sub-pixel)."""
    a=np.asarray(Image.open(path).convert('L'),np.float32)-32
    w=np.clip(a,0,None).sum(axis=0)
    return float((w*np.arange(len(w))).sum()/w.sum())


class RetimeTests(unittest.TestCase):
    """Exact-time slow-motion plates (the AHe1 test edit's 16-20 s stutter): a 24 fps motion conformed to 30 fps by
    repeating every fifth frame must retime to evenly spaced, never-held pictures."""

    def setUp(self):
        scratch=Path(__file__).resolve().parents[1]/'work';scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch);self.root=Path(self.temp.name);self.addCleanup(self.temp.cleanup)
        frames=self.root/'frames';frames.mkdir()
        # 24p motion of 6 px per picture, written at 30 fps with every fifth frame a baked repeat (4 unique + 1 repeat)
        picture=0
        for i in range(30):
            if i%5==4:picture-=1                                  # repeat the previous picture
            im=Image.new('RGB',(160,48),'#202020');x=10+picture*6
            ImageDraw.Draw(im).rectangle((x,14,x+11,33),fill='#ffffff');im.save(frames/f'{i:05d}.png');picture+=1
        # a second take after a hard cut
        for i in range(30,36):Image.new('RGB',(160,48),'#f0f0f0').save(frames/f'{i:05d}.png')
        self.edit={'canvas':{'w':160,'h':48,'fps':60,'frames':60},
                   'clips':{'A':{'frames_dir':'frames','n':36,'fps':30,'w':160,'h':48}},'shots':[{'clip':'A','f0':0,'f1':60}]}
        write_json(self.root/'timeline.json',self.edit)

    def steps(self,clip):
        xs=[square_x(self.root/clip['frames_dir']/f'{j:05d}.png') for j in range(clip['n'])]
        return np.diff(xs)

    def test_deduplicated_retime_is_even_and_exact(self):
        clip=retime(self.root/'timeline.json','A',self.root/'analysis/rt',start=.1,seconds=.6,output_frames=48,
                    take_start=0,take_seconds=1,deduplicate=True)
        self.assertEqual((clip['n'],clip['fps']),(48,60))
        self.assertEqual(len(list((self.root/'analysis/rt').glob('*.png'))),48)
        d=self.steps(clip)
        self.assertGreater(d.min(),0,'no held or backward frames')
        self.assertLess(d.std()/d.mean(),.1,'even steps across the repeat cadence')
        report=json.loads((self.root/'analysis/rt/retime.json').read_text(encoding='utf-8'))
        self.assertEqual(report['cadence']['unique_pictures'],24)
        self.assertEqual(len(report['cadence']['repeat_runs']),6)
        self.assertEqual(report['held_output_frames'],[])
        self.assertAlmostEqual(report['effective_speed'],.75)
        self.assertEqual(report['cadence']['timing'],'even')
        # run-centre timing (an estimate) keeps the unequal repeat runs, so its steps are measurably less even
        rc=retime(self.root/'timeline.json','A',self.root/'analysis/rc',start=.1,seconds=.6,output_frames=48,
                  take_seconds=1,deduplicate=True,timing='run_centre')
        self.assertGreater(self.steps(rc).std()/self.steps(rc).mean(),d.std()/d.mean())

    def test_without_deduplication_the_repeats_show_as_holds(self):
        clip=retime(self.root/'timeline.json','A',self.root/'analysis/raw',start=.1,seconds=.6,output_frames=48,take_seconds=1)
        d=self.steps(clip)
        self.assertGreater(d.std()/d.mean(),.3)   # uneven: the baked repeats survive as pauses

    def test_holds_before_the_first_picture_are_reported(self):
        clip=retime(self.root/'timeline.json','A',self.root/'analysis/h',start=0,seconds=.3,output_frames=60,take_seconds=1)
        report=json.loads((self.root/'analysis/h/retime.json').read_text(encoding='utf-8'))
        self.assertEqual(report['held_output_frames'],[0,1,2])   # t < 0.5/30 s shows the first picture unchanged
        self.assertEqual(clip['n'],60)

    def test_motion_timing_evens_an_uneven_conversion_cadence(self):
        # frames sampled unevenly (three steps of 9 px, two of 3 px, repeating), as in a frame-blended 24p-in-30p take
        frames=self.root/'uneven';frames.mkdir();x=10.0
        for i in range(30):
            im=Image.new('RGB',(400,48),'#202020');ImageDraw.Draw(im).rectangle((round(x),14,round(x)+11,33),fill='#ffffff')
            im.save(frames/f'{i:05d}.png');x+=(9,9,9,3,3)[i%5]
        edit={**self.edit,'clips':{'U':{'frames_dir':'uneven','n':30,'fps':30,'w':400,'h':48}},'shots':[{'clip':'U','f0':0,'f1':60}]}
        write_json(self.root/'timeline.json',edit)
        plain=retime(self.root/'timeline.json','U',self.root/'analysis/u0',start=.1,seconds=.6,output_frames=60)
        timed=retime(self.root/'timeline.json','U',self.root/'analysis/u1',start=.1,seconds=.6,output_frames=60,timing='motion')
        cv_plain=self.steps(plain).std()/self.steps(plain).mean();cv_timed=self.steps(timed).std()/self.steps(timed).mean()
        self.assertGreater(cv_plain,.3)
        self.assertLess(cv_timed,.15)
        report=json.loads((self.root/'analysis/u1/retime.json').read_text(encoding='utf-8'))
        self.assertEqual(report['cadence']['timing'],'motion');self.assertEqual(len(report['cadence']['pair_motion_px']),29)

    def test_take_window_and_cuts(self):
        with self.assertRaises(ContractError):   # interval outside the take window
            retime(self.root/'timeline.json','A',self.root/'analysis/a',start=.8,seconds=.4,output_frames=10,take_seconds=1)
        with self.assertRaises(ContractError):   # window crossing the hard cut at clip frame 30
            retime(self.root/'timeline.json','A',self.root/'analysis/b',start=.5,seconds=.6,output_frames=10)

    def test_agent_api_returns_a_new_clip_and_refuses_apply(self):
        import shutil
        from openkatana import projects
        from openkatana.agent_api import AgentAPI
        workspace=self.root/'ws';project=workspace/'p1'
        projects.create(project,'retime test')
        shutil.copytree(self.root/'frames',project/'frames');write_json(project/'timeline.json',self.edit)
        api=AgentAPI(workspace)
        result=api.analyze_clip('p1','A','retime',{'start':.1,'seconds':.6,'output_frames':12,'take_seconds':1,'deduplicate':True})
        self.assertEqual((result['clip_update']['n'],result['clip_update']['fps']),(12,60))
        self.assertIsNone(result['saved'])
        with self.assertRaises(ContractError):
            api.analyze_clip('p1','A','retime',{'start':.1,'seconds':.6,'output_frames':12,'take_seconds':1},apply=True)

if __name__=='__main__':
    unittest.main()
