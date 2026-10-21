import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from openkatana.contracts import ContractError,validate


class TextFeatureContracts(unittest.TestCase):
    def setUp(self):
        self.edit={'canvas':{'w':320,'h':192,'fps':60,'frames':48},
                   'clips':{'A':{'frames_dir':'frames','w':320,'h':192,'fps':30,'n':1}},
                   'shots':[{'f0':0,'f1':48,'clip':'A'}],
                   'fonts':[{'family':'Local','url':'font.ttf'}]}

    def test_parts_and_face_options(self):
        base={'type':'font','family':'Local','parts':[['NEW','bold'],['WAVE','thin']],'f0':0,'f1':48,'anchor':'face'}
        self.edit['text']=[base];validate(self.edit)
        for change in [{'parts':[]},{'parts':[['A','heavy',1]]},{'kind':'unknown'},
                       {'anchor':'head'},{'o':[0,float('inf')]},{'min':80,'max':20}]:
            self.edit['text']=[{**base,**change}]
            with self.subTest(change=change),self.assertRaises(ContractError):validate(self.edit)

    def test_manual_face_boxes(self):
        for value in [True,{'box':[1,2,0,4]},{'box':[1,2,3]},{'box':[0,0,10,10],'eyes':[]}]:
            self.edit['shots'][0]['face']=value
            with self.subTest(value=value),self.assertRaises(ContractError):validate(self.edit)
        self.edit['shots'][0]['face']=False;validate(self.edit)

    def test_track_binding_geometry_and_index(self):
        self.edit.pop('fonts')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'frames').mkdir();Image.new('RGB',(320,192)).save(root/'frames/00000.png')
            self.edit['clips']['A']['faces']='faces.json'
            for rows in [[],[{'f':1,'box':[1,2,3,4]}],[{'f':0,'box':[1,2,-3,4]}],
                         [{'f':0,'box':[1,2,3,4],'eyes':[[1,2]]}]]:
                (root/'faces.json').write_text(json.dumps(rows))
                with self.subTest(rows=rows),self.assertRaises(ContractError):validate(self.edit,root)
            (root/'faces.json').write_text('[null]');validate(self.edit,root)
            self.edit['clips']['A']['faces']='../faces.json'
            with self.assertRaises(ContractError):validate(self.edit,root)

    def test_graffiti_contract_and_layer(self):
        self.edit.pop('fonts')
        base={'type':'graffiti','word':'GO!','f0':0,'f1':48,'mode':'write','wkeys':[0,.1,.2,.3]}
        self.edit['text']=[base];validate(self.edit)
        for change in [{'word':'unsupported 😀'},{'lines':['GO']},{'region':'unknown'},
                       {'region':[.8,.2,.1,.9]},{'wkeys':[0,.1]}, {'wkeys':[0,.2,.1,.3]},
                       {'nib':0},{'line_dx':[0,1]},{'under':[True,False]}]:
            self.edit['text']=[{**base,**change}]
            with self.subTest(change=change),self.assertRaises(ContractError):validate(self.edit)
        self.edit['text']=[]
        self.edit['shots'][0]['layers']=[{'type':'graffiti','word':'GO','at':.2,'d':.3}]
        validate(self.edit)


if __name__=='__main__':unittest.main()
