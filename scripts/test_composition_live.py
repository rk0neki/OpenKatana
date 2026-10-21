"""Real offline browser checks, original fixtures; optionally use an isolated wheel install."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import sys

if os.environ.get('OPENKATANA_TEST_PACKAGE'):
    sys.path.insert(0,os.environ['OPENKATANA_TEST_PACKAGE'])
else: sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openkatana import composition as c
from openkatana.contracts import ContractError
from openkatana.render import render, write_json, probe, digest
from openkatana.projects import fingerprint


def fixture():
    def text(key,value,family='Inter',**extra):
        return {'id':key,'type':'text','text':value,'style':{'font-family':family,'font-size':'clamp(20px, 4vw, 34px)','line-height':'2.2'},**extra}
    def card(key,title,body):
        return {'id':key,'type':'box','style':{'display':'flex','flex-direction':'column','justify-content':'center','min-width':'0','padding':'12px','background-color':'#172033','border-radius':'12px'},
                'children':[{'id':key+'-caption','type':'text','text':title,'style':{'font-size':'12px','letter-spacing':'1px','color':'#7dd3fc'}},body]}
    return {'schema':1,'canvas':{'w':640,'h':360,'fps':12,'frames':6},
            'fonts':[{'family':'Inter','bundled':'Inter[opsz,wght].ttf','weight':'100 900'},
                     {'family':'Arabic','bundled':'NotoSansArabic[wdth,wght].ttf','weight':'100 900'},
                     {'family':'Indic','bundled':'NotoSansDevanagari[wdth,wght].ttf','weight':'100 900'},
                     {'family':'Cormorant','bundled':'Cormorant[wght].ttf','weight':'300 700'}],
            'plugins':['plugins/kinetic/plugin.json'],
            'root':{'id':'stage','type':'box','style':{'width':'100vw','height':'100vh','padding':'3vw','display':'flex','flex-direction':'column','gap':'12px','font-family':'Inter','color':'#f1f5f9','background-color':'#0b1120'},
                    'children':[{'id':'label','type':'text','text':'OPENKATANA / TYPE IN MOTION','style':{'font-size':'14px','font-weight':'800'}},
                                {'id':'cards','type':'box','style':{'display':'grid','grid-template-columns':'repeat(2,minmax(0,1fr))','gap':'12px','flex':'1'},
                                 'responsive':[{'max_width':480,'style':{'grid-template-columns':'1fr'}}],
                                 'children':[card('ar-card','ARABIC / CONTEXTUAL SHAPING',text('arabic','مرحبا بالعالم','Arabic',dir='rtl',lang='ar')),
                                             card('hi-card','DEVANAGARI / CONJUNCTS',text('indic','नमस्ते दुनिया','Indic',lang='hi')),
                                             card('marks-card','GRAPHEMES / COMBINING MARKS',text('marks','Cafe\u0301 + ffi')),
                                             card('mix-card','MIXED RUNS / VARIABLE WEIGHT',{'id':'mixed','type':'text','dir':'ltr','style':{'font-size':'24px','line-height':'2.2'},'runs':[
                                                 {'text':'Motion ','style':{'font-variation-settings':'"wght" 750'}},
                                                 {'text':'مرحبا','dir':'rtl','lang':'ar','style':{'font-family':'Arabic'}},
                                                 {'text':' 2026','style':{'font-variant-numeric':'tabular-nums'}}]})]},
                                {'id':'badge','type':'component','component':'kinetic/badge','params':{'label':'One design. Multiple formats.'},
                                 'effects':[{'use':'kinetic/float','params':{'pixels':2,'hz':1}}]}]},
            'tracks':[{'node':'arabic','property':'reveal','keys':[[0,0],[5,1]]},
                      {'node':'badge','property':'opacity','keys':[[0,.4],[5,1]]}]}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    root=args.out.resolve();root.mkdir(parents=True,exist_ok=False);checks=[]
    def passed(name,details=None):checks.append({'name':name,'passed':True,'details':details})
    package=Path(c.__file__).resolve().parent.parent
    examples=next((p for p in (Path(sys.prefix)/'share/openkatana/examples',package/'share/openkatana/examples',package/'examples') if (p/'plugins/kinetic/plugin.json').is_file()),None)
    if examples is None:raise RuntimeError('Packaged kinetic example is missing')
    shutil.copytree(examples/'plugins/kinetic',root/'plugins/kinetic')
    doc=fixture();write_json(root/'composition.json',doc)
    catalog=c.list_plugins(root,doc['plugins'])
    assert {p['id'] for p in catalog['plugins']}=={'core','kinetic'}
    passed('actual plugin discovery and parameter schemas')
    with c.session(root,doc['plugins']) as (page,call,browser):
        expanded=c.open_composition(root,doc,page,call)
        call('frame',5);wide=call('measure');rows={n['id']:n for n in wide['nodes']}
        assert all(f['status']=='loaded' for f in wide['fonts'])
        assert rows['ar-card']['rect']['y']==rows['hi-card']['rect']['y']
        assert rows['ar-card']['rect']['x']<rows['hi-card']['rect']['x']
        assert not any(n['overflow'] for n in wide['nodes'])
        page.screenshot(path=str(root/'wide.png'))
        passed('grid and intrinsic layout at 640x360; no content overflow')
        assert any(g['text']=='e\u0301' for g in rows['marks']['graphemes'])
        assert len(rows['indic']['graphemes'])<len(rows['indic']['text'])
        ar=rows['arabic']['graphemes'];assert ar[0]['rects'][0]['x']>ar[-1]['rects'][0]['x']
        passed('Arabic RTL, Indic conjunct and combining-mark grapheme ranges')
        # Test contextual shaping and optional OpenType ligatures using intact text runs.
        metric=page.evaluate('''() => {
          function width(family,text,features='normal',axes='normal') {
            const el=document.createElement('span');Object.assign(el.style,{fontFamily:family,fontSize:'60px',fontFeatureSettings:features,fontVariationSettings:axes,position:'absolute',whiteSpace:'pre'});el.textContent=text;document.body.append(el);const w=el.getBoundingClientRect().width;el.remove();return w;
          }
          return {joined:width('Arabic','سلام'),isolated:width('Arabic','س\\u200cل\\u200cا\\u200cم'),
            liga:width('Cormorant','ffi','"liga" 1'),noLiga:width('Cormorant','ffi','"liga" 0'),
            narrow:width('Arabic','مرحبا','normal','"wdth" 75'),wide:width('Arabic','مرحبا','normal','"wdth" 100')};
        }''')
        assert abs(metric['joined']-metric['isolated'])>3,metric
        assert abs(metric['liga']-metric['noLiga'])>.1,metric
        passed('actual contextual joins and OpenType ligature metrics',metric)
        assert metric['wide']>metric['narrow']+1,metric
        passed('variable font width axis changes real layout metrics')
        before=rows['arabic']['graphemes'];call('frame',2);during=call('measure')
        assert next(n for n in during['nodes'] if n['id']=='arabic')['graphemes']==before
        assert page.locator('[data-node="arabic"]').evaluate('(el)=>el.style.mask')
        passed('reveal retains full shaped run and stable cluster geometry')
        c.open_composition(root,doc,page,call,360,640);call('frame',5);portrait=call('measure');nodes={n['id']:n for n in portrait['nodes']}
        assert nodes['hi-card']['rect']['y']>nodes['ar-card']['rect']['y']
        assert abs(nodes['hi-card']['rect']['x']-nodes['ar-card']['rect']['x'])<.1
        assert not any(n['overflow'] for n in portrait['nodes'])
        page.screenshot(path=str(root/'portrait.png'))
        passed('responsive portrait reflow at 360x640 without scaled-down text')
        c.open_composition(root,doc,page,call,1280,720);call('frame',5);large=call('measure')
        assert next(n for n in large['nodes'] if n['id']=='ar-card')['rect']['w']>rows['ar-card']['rect']['w']
        passed('larger viewport recomputes layout and clamped font sizes')
        vertical=copy.deepcopy(doc);vertical['root']['children']=[{'id':'vertical','type':'text','text':'Motion','style':{'writing-mode':'vertical-rl','text-orientation':'upright','font-size':'30px','line-height':'1.5','height':'250px','align-self':'flex-start'}}];vertical['tracks']=[]
        c.open_composition(root,vertical,page,call);call('frame',0);v=call('measure')['nodes'][1]
        assert v['style']['writingMode']=='vertical-rl' and v['graphemes'][0]['rects'][0]['y']<v['graphemes'][-1]['rects'][0]['y']
        passed('vertical writing uses actual top-to-bottom glyph placement')
        # Browser-only emoji segmentation is tested without asserting missing bundled emoji glyph coverage.
        assert page.evaluate("() => [...new Intl.Segmenter('und',{granularity:'grapheme'}).segment('👩🏽‍💻')].length")==1
        passed('emoji ZWJ grapheme segmentation (not bundled emoji-font rendering)')
        life=call('dispose');assert sum(e['event']=='effect-mount' for e in life)==sum(e['event']=='effect-dispose' for e in life)
        passed('plugin effect mount/dispose lifecycle across viewport and document changes')
    proposed=c.run_operator(root,doc['plugins'],'kinetic/setText',doc,{'id':'label','text':'Updated by a plugin'})
    assert proposed['document']['root']['children'][0]['text']=='Updated by a plugin' and not proposed['saved']
    assert fingerprint(doc)==proposed['before_revision']
    passed('custom operator produces validated proposal without mutating input')
    ops=[{'op':'test','path':'/root/children/0/text','value':doc['root']['children'][0]['text']},
         {'op':'copy','from':'/root/children/0','path':'/root/children/-'},
         {'op':'replace','path':'/root/children/3/id','value':'copied'},
         {'op':'move','from':'/root/children/3','path':'/root/children/1'},
         {'op':'add','path':'/root/children/1/style/color','value':'#ffffff'},
         {'op':'remove','path':'/root/children/1'}]
    result=c.run_operator(root,[],'core/batch',doc,{'ops':ops})
    assert result['document']==doc
    passed('batch add/replace/remove/copy/move/test transaction')
    def rejects(name,fn):
        try:fn()
        except Exception as e:passed(name,str(e).splitlines()[0][:200])
        else:raise AssertionError(name+' did not fail')
    rejects('failed batch leaves caller document unchanged',lambda:c.run_operator(root,[],'core/batch',doc,{'ops':[ops[1],{'op':'remove','path':'/missing'}]}))
    assert doc==fixture()
    rejects('unsupported operator parameter rejected',lambda:c.run_operator(root,doc['plugins'],'kinetic/setText',doc,{'id':'label','text':'x','oops':1}))
    rejects('post-operation invalid document rejected',lambda:c.run_operator(root,[],'core/batch',doc,{'ops':[{'op':'add','path':'/magic','value':1}]}))
    bad=copy.deepcopy(doc);bad['root']['style']['width']='not-a-size'
    rejects('unsupported CSS value rejected by browser',lambda:c.inspect_composition(root,bad))
    original=(root/'plugins/kinetic/kinetic.js').read_text(encoding='utf-8')
    # Off-origin requests and undeclared project reads must fail, not become missing visuals in a success receipt.
    (root/'plugins/kinetic/kinetic.js').write_text(original+'\nfetch("https://example.invalid/never-download");',encoding='utf-8')
    rejects('off-origin plugin request blocked',lambda:c.list_plugins(root,doc['plugins']))
    (root/'plugins/kinetic/kinetic.js').write_text(original,encoding='utf-8')
    result=c.render_composition(root,doc,root/'wide-render')
    assert all(not m['font_coverage']['warnings'] for m in result['measurements'].values())
    assert result['remount_match'] and result['clip']['n']==6
    assert next(s for s in probe(result['video'])['streams'] if s['codec_type']=='video')['nb_read_frames']=='6'
    passed('plugin effects + RTL reveal render, backwards seek, remount and exact video frames')
    p=c.render_composition(root,doc,root/'portrait-render',360,640)
    assert p['clip']['w']==360 and p['clip']['h']==640
    passed('same composition renders portrait with responsive layout')
    # Deliberately accumulated visual state must be caught by deterministic seeking.
    (root/'plugins/kinetic/kinetic.js').write_text(original.replace('state.draws++;','state.draws++;el.style.opacity=String(state.draws/100);'),encoding='utf-8')
    rejects('stateful visual plugin fails deterministic render',lambda:c.render_composition(root,doc,root/'stateful-failed',video=False))
    (root/'plugins/kinetic/kinetic.js').write_text(original,encoding='utf-8')
    timeline={'canvas':doc['canvas'],'clips':{'graphic':result['clip']},'shots':[{'f0':0,'f1':6,'clip':'graphic'}]}
    t=c.run_operator(root,[],'core/batch',timeline,{'ops':[{'op':'add','path':'/shots/0/speed','value':1}]},'timeline')['document']
    write_json(root/'timeline.json',t);movie=render(root/'timeline.json',root/'timeline-render')
    passed('composition clip and native operator proposal work in existing timeline renderer',{'output':str(root/'timeline-render')})
    report={'passed':True,'checks':checks,'browser':browser,'package':str(package),'credits_used':0,'parity':'Independent fixtures only; no hosted comparison',
            'previews':['wide.png','portrait.png'],'videos':['wide-render/video.mp4','portrait-render/video.mp4'],
            'font_manifest_sha256':digest(c.bundled_fonts.FOLDER/'manifest.json')}
    write_json(root/'validation.json',report)
    print(json.dumps({'passed':True,'checks':len(checks),'report':str(root/'validation.json')}))


if __name__=='__main__':main()
