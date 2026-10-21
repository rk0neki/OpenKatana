import copy
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from openkatana.agent_api import AgentAPI
from openkatana.contracts import ContractError,validate
from openkatana.render import write_json


class EditorToolsTests(unittest.TestCase):
    def setUp(self):
        parent=Path(__file__).resolve().parents[1]/'work';parent.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.api=AgentAPI(self.root)
        self.api.create_project('Test','test');self.project=self.root/'test'
        Image.new('RGB',(160,96)).save(self.root/'source.png')
        asset=self.api.import_media('test',str(self.root/'source.png'))
        self.edit=self.api.plan_edit('test',[asset['id']],seconds=1,width=160,height=96,fps=24)['timeline']
        self.api.save_timeline('test',self.edit,None)

    def test_reference_audit_reports_literal_text_and_cut_mismatch(self):
        plan={'source':str(self.root/'source.png'),'fps':24,'frames':24,'cut_frames':[12],
              'texts':[{'text':'EXACT WORDS','f0':0,'f1':24}],'shots':[{'index':0,'fields':{'speed':1}}]}
        self.api.save_reference_plan('test',plan)
        report=self.api.audit_reference_plan('test')
        self.assertFalse(report['matches_plan']);self.assertGreaterEqual(len(report['issues']),3)
        with self.assertRaisesRegex(ContractError,'Reference plan mismatch'):self.api.start_render('test','blocked')

    def test_reference_pass_and_source_change(self):
        self.api.save_reference_plan('test',{'source':str(self.root/'source.png'),'fps':24,'frames':24,'cut_frames':[]})
        self.assertTrue(self.api.audit_reference_plan('test')['matches_plan'])
        Image.new('RGB',(160,96),'red').save(self.root/'source.png')
        self.assertFalse(self.api.audit_reference_plan('test')['matches_plan'])

    def test_invalid_plan_not_saved(self):
        with self.assertRaises(ContractError):self.api.save_reference_plan('test',{'source':str(self.root/'source.png'),'fps':24,'frames':24,'cut_frames':[12,4]})
        self.assertFalse((self.project/'reference-plan.json').exists())

    def test_text_controls_and_rejected_bad_keys(self):
        edit=copy.deepcopy(self.edit);edit['fonts']=[{'family':'Supplied','url':'font.ttf'}]
        item={'type':'word','text':'AB','family':'Supplied','f0':0,'f1':24,'fill':None,'stroke':'#ff0000',
              'render_style':'explicit','anim':'type','tracking':2,'scale_x':.8,'scale_y':1.2,
              'opacity_keys':[[0,1],[.2,0]],'letter_opacity_keys':[[[0,1]],[[0,0],[.1,1]]],
              'flicker':{'per_letter':True,'hz':12,'duty':.8,'min_alpha':.1}}
        edit['text']=[item];validate(edit)
        for change in ({'letter_opacity_keys':[]},{'opacity_keys':[[.2,1],[.1,0]]},{'scale_x':0},
                       {'flicker':{'duty':2}},{'render_style':'guess'},{'fill':'transparent'}):
            edit['text']=[{**item,**change}]
            with self.subTest(change=change),self.assertRaises(ContractError):validate(edit)


if __name__=='__main__':unittest.main()
