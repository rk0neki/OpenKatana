import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from openkatana.contracts import ContractError,validate


class CameraTrackingContracts(unittest.TestCase):
    def setUp(self):
        self.edit={'canvas':{'w':320,'h':192,'fps':60,'frames':48},
                   'clips':{'A':{'frames_dir':'frames','w':320,'h':192,'fps':30,'n':1}},
                   'shots':[{'f0':0,'f1':48,'clip':'A'}]}

    def test_handheld_scalar_amplitude_and_finite_parameters(self):
        for p in [True,False,{'amp':0,'hz':0,'seed':-7},{'v':3,'rot':-.01}]:
            self.edit['shots'][0]['cam']={'handheld':p};validate(self.edit)
        for p in [{'amp':[6,4]},{'hz':-1},{'seed':1.5},{'rot':float('nan')},{'every':2}]:
            self.edit['shots'][0]['cam']={'handheld':p}
            with self.subTest(p=p),self.assertRaises(ContractError):validate(self.edit)

    def test_lock_requires_track_after_camera_inheritance(self):
        self.edit['cam']={'lock':True}
        with self.assertRaisesRegex(ContractError,'supplied clip face track'):validate(self.edit)
        self.edit['shots'][0]['cam']={'lock':False};validate(self.edit)
        self.edit['shots'][0]['cam']={'type':'facelock','lock':False}
        with self.assertRaisesRegex(ContractError,'supplied clip face track'):validate(self.edit)
        self.edit['clips']['A']['faces']='faces.json';validate(self.edit)

    def test_lock_parameters_reject_invalid_values(self):
        self.edit['clips']['A']['faces']='faces.json'
        for p in [{'type':'other'},{'lock':1},{'ld':0},{'z0':0},{'kick_rate':-1},
                  {'lockRot':1.1},{'lx':-1},{'facelock':True}]:
            self.edit['shots'][0]['cam']={'type':'facelock',**p}
            with self.subTest(p=p),self.assertRaises(ContractError):validate(self.edit)

    def test_empty_or_degenerate_lock_track_fails_before_browser(self):
        self.edit['cam']={'type':'facelock'};self.edit['clips']['A']['faces']='faces.json'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'frames').mkdir();Image.new('RGB',(320,192)).save(root/'frames/00000.png')
            for rows in [[None],[{'f':0,'box':[20,30,80,100],'eyes':[[50,60],[50,60]]}]]:
                (root/'faces.json').write_text(json.dumps(rows))
                with self.subTest(rows=rows),self.assertRaises(ContractError):validate(self.edit,root)
            (root/'faces.json').write_text(json.dumps([{'f':0,'box':[20,30,80,100]}]));validate(self.edit,root)


if __name__=='__main__':unittest.main()
