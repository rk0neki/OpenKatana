import copy
import tempfile
import unittest
from pathlib import Path

from openkatana.contracts import ContractError, local_path, validate
from openkatana.comfy import local_endpoint, validate_workflow


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.edit = {'canvas':{'w':320,'h':192,'fps':60,'frames':24},
                     'clips':{'A':{'frames_dir':'a','n':10,'fps':30,'w':320,'h':192}},
                     'shots':[{'f0':0,'f1':24,'clip':'A'}]}

    def test_valid_contract(self):
        validate(self.edit)

    def test_supported_camera_and_transition_composition(self):
        self.edit['cam'] = {'push': True}
        self.edit['clips']['A']['cam'] = {'pan': {'dx': .1}}
        self.edit['post'] = {'tint': {'color': '#8ab4ef', 'op': 'screen'}}
        self.edit['shots'][0].update(cam={'push': False, 'punch': {'hits':[0,.2]}},
                                     fx={'tint':False}, **{'in': ['flash', {'type':'white','d':.05}]})
        self.assertIs(validate(self.edit), self.edit)

    def test_effect_parameters_fail_before_browser(self):
        invalid = [
            {'punch':{'hits':[]}}, {'punch':{'hits':[float('nan')]}},
            {'punch':{'d':0}}, {'ladder':{'steps':[]}}, {'ladder':{'steps':[0]}},
            {'pan':{'dx':float('inf')}}, {'roll':{'rate':True}},
            {'flash':{'amt':2}}, {'white':{'color':'red'}},
            {'tint':{'op':'made-up'}}, {'strobe':{'every':1.5}},
            {'dip':{'at':.1}}, {'flash':{'side':'middle'}},
        ]
        for fx in invalid:
            with self.subTest(fx=fx), self.assertRaises(ContractError):
                validate({**self.edit,'shots':[{**self.edit['shots'][0],'fx':fx}]})

    def test_unknown_nested_fields_remain_rejected(self):
        for key,value in [('cam',{'pan':{'speed':1}}),('fx',{'flash':{'strength':1}}),
                          ('in',{'type':'unknown-transition'})]:
            with self.subTest(key=key), self.assertRaises(ContractError):
                validate({**self.edit,'shots':[{**self.edit['shots'][0],key:value}]})

    def test_layer_contract_preserves_order_and_rejects_unknowns(self):
        layers = [{'type':'dip','side':'in','d':.1,'order':7,'phase':'final'},
                  {'type':'dip','side':'out','d':.2,'order':7}]
        self.edit['shots'][0]['layers'] = layers
        self.assertEqual(validate(self.edit)['shots'][0]['layers'],layers)
        for value in [None,[{'type':'shake'}],[{'type':'white','phase':'other'}],
                      [{'type':'white','order':float('inf')}]]:
            self.edit['shots'][0]['layers'] = value
            with self.subTest(value=value),self.assertRaises(ContractError):
                validate(self.edit)

    def test_rejects_unimplemented_effect_instead_of_ignoring(self):
        self.edit['shots'][0]['fx'] = {'unknown-effect':True}
        with self.assertRaisesRegex(ContractError,'unsupported'):
            validate(self.edit)

    def test_rejects_gaps_overlap_and_incomplete_coverage(self):
        for shots in [[{'f0':1,'f1':24,'clip':'A'}], [{'f0':0,'f1':23,'clip':'A'}],
                      [{'f0':0,'f1':13,'clip':'A'},{'f0':12,'f1':24,'clip':'A'}]]:
            with self.subTest(shots=shots), self.assertRaises(ContractError):
                validate({**self.edit,'shots':shots})

    def test_rejects_nonfinite_timing(self):
        self.edit['shots'][0]['speed'] = float('nan')
        with self.assertRaises(ContractError): validate(self.edit)

    def test_paths_stay_in_project(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ContractError): local_path(Path(d),'../secret')

    def test_missing_source_fails_before_render(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ContractError,'Missing source'):
                validate(self.edit,Path(d))

    def test_fonts_never_silently_fallback(self):
        self.edit['text']=[{'type':'font','family':'Missing','text':'HELLO','f0':0,'f1':24,'size':30}]
        with self.assertRaisesRegex(ContractError,'explicitly supplied font'): validate(self.edit)

    def test_cloud_is_never_implicit(self):
        for url in ['https://cloud.comfy.org','http://example.org','http://127.0.0.1@evil.com',
                    'http://127.0.0.1:8189?redirect=evil']:
            with self.subTest(url=url),self.assertRaises(ValueError): local_endpoint(url)
        self.assertEqual(local_endpoint('http://127.0.0.1:8189/'),'http://127.0.0.1:8189')

    def test_partner_node_rejected_even_on_local_server(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wf.json'
            p.write_text('{"1":{"class_type":"PaidProvider","inputs":{}}}')
            with self.assertRaisesRegex(ValueError,'allowlist'): validate_workflow(p)


if __name__ == '__main__': unittest.main()
