import tempfile
import unittest
from pathlib import Path
from PIL import Image
from openkatana.contracts import ContractError,validate


class AdvancedContractTests(unittest.TestCase):
    def setUp(self):
        self.edit={'canvas':{'w':320,'h':192,'fps':60,'frames':48},
                   'clips':{'A':{'frames_dir':'frames','w':320,'h':192,'fps':30,'n':1}},
                   'shots':[{'f0':0,'f1':48,'clip':'A'}]}

    def test_shake_crop_and_cover_reject_bad_inputs(self):
        for cam in [{'cover':'yes'},{'crop':[.5]},{'crop':float('nan')},
                    {'shake':{'amp':4}},{'shake':{'amp':[1,-1]}},
                    {'shake':{'every':0}},{'shake':{'d':0}},
                    {'shake':{'hits':[float('nan')]}}]:
            self.edit['shots'][0]['cam']=cam
            with self.subTest(cam=cam),self.assertRaises(ContractError):validate(self.edit)

    def test_alpha_mask_geometry_and_completeness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'frames').mkdir();(root/'masks').mkdir()
            Image.new('RGB',(320,192)).save(root/'frames/00000.png')
            self.edit['clips']['A']['mask_dir']='masks'
            with self.assertRaisesRegex(ContractError,'Missing mask'):validate(self.edit,root)
            Image.new('RGBA',(160,96)).save(root/'masks/00000.png')
            with self.assertRaisesRegex(ContractError,'geometry'):validate(self.edit,root)
            Image.new('RGB',(320,192)).save(root/'masks/00000.png')
            with self.assertRaisesRegex(ContractError,'alpha channel'):validate(self.edit,root)
            Image.new('RGBA',(320,192),(255,255,255,128)).save(root/'masks/00000.png')
            validate(self.edit,root)

    def test_typography_fields_are_checked_before_rendering(self):
        self.edit['fonts']=[{'family':'Local','url':'font.ttf'}]
        base={'type':'font','family':'Local','text':'Hello','f0':0,'f1':48}
        for params in [{'shadow':{'blur':-1}},{'sc':[]},{'dt':0},{'anim':'unsupported'},
                       {'rot':float('nan')},{'weight':2000},{'style':'fantasy'},
                       {'shadow':{'typo':1}},{'parts':[['A','unknown']]}]:
            self.edit['text']=[{**base,**params}]
            with self.subTest(params=params),self.assertRaises(ContractError):validate(self.edit)

    def test_layer_text_cannot_bypass_font_or_timing_checks(self):
        self.edit['fonts']=[{'family':'Local','url':'font.ttf'}]
        layer={'type':'text','text':'Hello','family':'Local','at':.1,'d':.2}
        self.edit['shots'][0]['layers']=[layer]
        validate(self.edit)
        for change in [{'family':'Missing'},{'at':-1},{'d':0},{'unknown':True}]:
            self.edit['shots'][0]['layers']=[{**layer,**change}]
            with self.subTest(change=change),self.assertRaises(ContractError):validate(self.edit)


if __name__=='__main__':unittest.main()
