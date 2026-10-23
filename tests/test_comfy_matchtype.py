"""V3 MatchType sockets (COMFY_MATCHTYPE_V3) take the type linked into their template.

ComfyUI's server leaves MatchType links to its editor, which lets an input accept what its template allows and
what matches the template's other links, and gives a mapped output the common linked type. preflight() follows
the same rules, so an allowed link passes and a mismatch is still reported where the linked type decides it.
Contracts are the input and output fields served at /object_info by ComfyUI 0.42.0, without tooltips.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from openkatana.workflow_schema import check_graph
from openkatana.workflows import preflight

ROOT=Path(__file__).resolve().parents[1]

# If/Else Switch (comfy_extras/nodes_logic.py): both branches share the "switch" template, which allows any type.
SWITCH={'input':{'required':{'switch':['BOOLEAN',{}]},
                 'optional':{'on_false':['COMFY_MATCHTYPE_V3',{'lazy':True,'template':{'template_id':'switch','allowed_types':'*'}}],
                             'on_true':['COMFY_MATCHTYPE_V3',{'lazy':True,'template':{'template_id':'switch','allowed_types':'*'}}]}},
        'output':['COMFY_MATCHTYPE_V3'],'output_matchtypes':['switch']}
# Resize Image/Mask (comfy_extras/nodes_post_processing.py): its template allows IMAGE or MASK only.
# resize_type has nine options; only the one used here is kept.
RESIZE={'input':{'required':{
            'input':['COMFY_MATCHTYPE_V3',{'template':{'template_id':'input_type','allowed_types':'IMAGE,MASK'}}],
            'resize_type':['COMFY_DYNAMICCOMBO_V3',{'options':[{'key':'scale by multiplier','inputs':{'required':{
                'multiplier':['FLOAT',{'default':1.0,'min':0.01,'max':8.0,'step':0.01}]}}}]}],
            'scale_method':['COMBO',{'default':'area','multiselect':False,'options':['nearest-exact','bilinear','area','bicubic','lanczos']}]}},
        'output':['COMFY_MATCHTYPE_V3'],'output_matchtypes':['input_type']}
# Start Loop (comfy_extras/nodes_loop.py): the list_item template's input sits inside the mode dynamic combo.
START_LOOP={'input':{'required':{
                'mode':['COMFY_DYNAMICCOMBO_V3',{'options':[
                    {'key':'simple','inputs':{'required':{'num_iterations':['INT',{'default':4,'min':0}]}}},
                    {'key':'For','inputs':{'required':{'start_iteration_index':['INT',{'default':0}],
                        'max_iteration':['INT',{'default':4,'max':18446744073709551615}],'step':['INT',{'default':1,'min':1}]}}},
                    {'key':'List','inputs':{'required':{'list':['COMFY_MATCHTYPE_V3',{'template':{'template_id':'list_item','allowed_types':'*'}}]}}}]}],
                'cache_iterations':['BOOLEAN',{'advanced':True,'default':False}]},
            'optional':{'parent_iteration':['INT',{'forceInput':True}],
                'initial_iteration_value':['COMFY_MATCHTYPE_V3',{'template':{'template_id':'carried_value','allowed_types':'*'}}]}},
    'output':['INT','BOOLEAN','BOOLEAN','COMFY_MATCHTYPE_V3','COMFY_MATCHTYPE_V3'],
    'output_matchtypes':[None,None,None,'list_item','carried_value']}
# Prompt enhancer on the switch's on_true branch in the LTX-2.5 example (comfy_extras/nodes_textgen.py).
TEXT_GENERATE_LTX2={'input':{
    'required':{'clip':['CLIP',{}],'prompt':['STRING',{'default':'','multiline':True,'dynamicPrompts':True}],
        'max_length':['INT',{'default':512,'min':1,'max':32768}],
        'sampling_mode':['COMFY_DYNAMICCOMBO_V3',{'display_name':'Sampling Mode','options':[
            {'key':'on','inputs':{'required':{'temperature':['FLOAT',{'default':0.7,'min':0.01,'max':2.0,'step':1e-06}],
                'top_k':['INT',{'default':64,'min':0,'max':1000}],'top_p':['FLOAT',{'default':0.95,'min':0.0,'max':1.0,'step':0.01}],
                'min_p':['FLOAT',{'default':0.05,'min':0.0,'max':1.0,'step':0.01}],
                'repetition_penalty':['FLOAT',{'default':1.05,'min':0.0,'max':5.0,'step':0.01}],
                'seed':['INT',{'default':0,'min':0,'max':18446744073709551615}]},
                'optional':{'presence_penalty':['FLOAT',{'default':0.0,'min':0.0,'max':5.0,'step':0.01}]}}},
            {'key':'off','inputs':{'required':{}}}]}]},
    'optional':{'image':['IMAGE',{}],'video':['IMAGE',{}],'audio':['AUDIO',{}],'thinking':['BOOLEAN',{'default':False}],
        'use_default_template':['BOOLEAN',{'advanced':True,'default':True}],
        'mtp':['COMBO',{'default':'auto','multiselect':False,'options':['auto','off','2','3','4','5']}],
        'system_prompt':['STRING',{'forceInput':True,'multiline':False}]}},
    'output':['STRING','STRING']}
NODES={'ComfySwitchNode':SWITCH,'ResizeImageMaskNode':RESIZE,'StartLoop':START_LOOP,'TextGenerateLTX2Prompt':TEXT_GENERATE_LTX2,
       'PrimitiveBoolean':{'input':{'required':{'value':['BOOLEAN',{}]}},'output':['BOOLEAN']},
       'PrimitiveStringMultiline':{'input':{'required':{'value':['STRING',{'multiline':True}]}},'output':['STRING']},
       'StringLength':{'input':{'required':{'string':['STRING',{'multiline':True}]}},'output':['INT']},
       'CLIPTextEncode':{'input':{'required':{'text':['STRING',{'multiline':True,'dynamicPrompts':True}],'clip':['CLIP',{}]}},'output':['CONDITIONING']},
       'PreviewAny':{'input':{'required':{'source':['*',{}]}},'output':['STRING']},
       'EmptyImage':{'input':{'required':{'width':['INT',{'default':512,'min':1,'max':16384,'step':1}],
           'height':['INT',{'default':512,'min':1,'max':16384,'step':1}],'batch_size':['INT',{'default':1,'min':1,'max':4096}],
           'color':['INT',{'default':0,'min':0,'max':16777215,'step':1,'display':'color'}]}},'output':['IMAGE']},
       'SolidMask':{'input':{'required':{'value':['FLOAT',{'default':1.0,'min':0.0,'max':1.0,'step':0.01}],
           'width':['INT',{'default':512,'min':1,'max':16384,'step':1}],'height':['INT',{'default':512,'min':1,'max':16384,'step':1}]}},'output':['MASK']},
       'MaskToImage':{'input':{'required':{'mask':['MASK',{}]}},'output':['IMAGE']},
       'ImageInvert':{'input':{'required':{'image':['IMAGE']}},'output':['IMAGE']}}
CYCLE='Workflow contains a dependency cycle or excessive depth'


def node(class_type,**inputs):return {'class_type':class_type,'inputs':inputs}


def errors(graph):
    with patch('openkatana.workflows.capabilities',return_value=NODES):
        return preflight(graph,'local')['errors']


class SwitchTests(unittest.TestCase):
    """If/Else Switch: the output carries the type linked into its branches."""
    def setUp(self):
        self.graph={'1':node('PrimitiveBoolean',value=False),
                    '2':node('PrimitiveStringMultiline',value='plain prompt'),
                    '3':node('PrimitiveStringMultiline',value='enhanced prompt'),
                    '4':node('ComfySwitchNode',switch=['1',0],on_false=['2',0],on_true=['3',0]),
                    '5':node('StringLength',string=['4',0])}
        self.branches=self.graph['4']['inputs']

    def test_branches_and_output_take_the_linked_type(self):
        self.assertEqual(errors(self.graph),[])

    def test_output_mismatch_is_still_reported(self):
        self.graph['5']=node('ImageInvert',image=['4',0])
        self.assertEqual(errors(self.graph),['5.image: STRING output cannot feed IMAGE'])

    def test_type_passes_through_chained_switches(self):
        self.graph['6']=node('ComfySwitchNode',switch=['1',0],on_false=['4',0],on_true=['3',0])
        self.graph['7']=node('ImageInvert',image=['6',0])
        self.assertEqual(errors(self.graph),['7.image: STRING output cannot feed IMAGE'])

    def test_branches_must_match_each_other(self):
        self.graph['6']=node('EmptyImage',width=64,height=64,batch_size=1,color=0)
        self.branches['on_true']=['6',0]
        # The output type is then undecided, so the STRING consumer is not reported as well.
        self.assertEqual(errors(self.graph),['4.on_false: STRING output cannot feed IMAGE','4.on_true: IMAGE output cannot feed STRING'])

    def test_one_branch_decides_and_none_leaves_the_output_open(self):
        del self.branches['on_true']
        self.graph['5']=node('ImageInvert',image=['4',0])
        self.assertEqual(errors(self.graph),['5.image: STRING output cannot feed IMAGE'])
        del self.branches['on_false']
        self.assertEqual(errors(self.graph),[])


class RestrictedTemplateTests(unittest.TestCase):
    """Resize Image/Mask: the template allows IMAGE or MASK, and the output carries whichever is linked."""
    def setUp(self):
        self.graph={'1':node('EmptyImage',width=64,height=64,batch_size=1,color=0),
                    '2':node('ResizeImageMaskNode',**{'input':['1',0],'resize_type':'scale by multiplier','resize_type.multiplier':0.5,'scale_method':'area'}),
                    '3':node('ImageInvert',image=['2',0])}

    def test_allowed_types_pass_and_decide_the_output(self):
        self.assertEqual(errors(self.graph),[])
        self.graph['1']=node('SolidMask',value=1.0,width=64,height=64)
        self.assertEqual(errors(self.graph),['3.image: MASK output cannot feed IMAGE'])
        self.graph['3']=node('MaskToImage',mask=['2',0])
        self.assertEqual(errors(self.graph),[])

    def test_disallowed_type_fails_directly_and_through_a_switch(self):
        self.graph['1']=node('PrimitiveStringMultiline',value='not an image')
        self.assertEqual(errors(self.graph),['2.input: STRING output cannot feed IMAGE,MASK'])
        self.graph['4']=node('ComfySwitchNode',switch=True,on_false=['1',0])
        self.graph['2']['inputs']['input']=['4',0]
        self.assertEqual(errors(self.graph),['2.input: STRING output cannot feed IMAGE,MASK'])


class NestedTemplateInputTests(unittest.TestCase):
    def test_template_input_inside_a_dynamic_combo_decides_the_output(self):
        graph={'1':node('EmptyImage',width=64,height=64,batch_size=1,color=0),
               '2':node('StartLoop',**{'mode':'List','mode.list':['1',0],'cache_iterations':False}),
               '3':node('StringLength',string=['2',3])}
        self.assertEqual(errors(graph),['3.string: IMAGE output cannot feed STRING'])
        graph['3']=node('ImageInvert',image=['2',3])
        self.assertEqual(errors(graph),[])
        # current_iteration_value follows another template, which has nothing linked yet.
        graph['4']=node('StringLength',string=['2',4])
        self.assertEqual(errors(graph),[])
        graph['2']['inputs']['initial_iteration_value']=['1',0]
        self.assertEqual(errors(graph),['4.string: IMAGE output cannot feed STRING'])


class TestedCloudGraphTests(unittest.TestCase):
    def test_ltx_example_prompt_switch_has_no_type_errors(self):
        """The LTX-2.5 example ran on Comfy Cloud. Its prompt switch used to fail with three type errors."""
        graph=json.loads((ROOT/'examples/comfy/ltx25-generate.api.json').read_text(encoding='utf-8'))
        names=('ComfySwitchNode','PrimitiveBoolean','PrimitiveStringMultiline','TextGenerateLTX2Prompt','CLIPTextEncode','PreviewAny')
        # Only the switch and its neighbours have contracts here; check_graph skips nodes without one.
        self.assertEqual(check_graph(graph,{name:NODES[name] for name in names},set()),[])


class ResolutionLimitTests(unittest.TestCase):
    def test_switch_feeding_itself_is_a_cycle(self):
        graph={'1':node('PrimitiveStringMultiline',value='x'),'2':node('ComfySwitchNode',switch=True,on_false=['1',0],on_true=['2',0]),
               '3':node('StringLength',string=['2',0])}
        self.assertEqual(check_graph(graph,NODES,set()),[CYCLE])

    def test_very_deep_switch_chain_is_left_undecided(self):
        # The consumer comes first, so resolving its link walks the whole chain at once.
        graph={'end':node('ImageInvert',image=['3000',0])}
        for i in range(3000,0,-1):graph[str(i)]=node('ComfySwitchNode',switch=True,on_false=[str(i-1),0])
        graph['0']=node('PrimitiveStringMultiline',value='x')
        self.assertEqual(check_graph(graph,NODES,set()),[CYCLE])


if __name__=='__main__':unittest.main()
