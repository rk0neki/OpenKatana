"""Original marker-text fixture inputs for comparison with the external oracle."""
def configure(edit,root,suite='graffiti'):
    cases=[('hold',{'word':'GO','mode':'hold'}),('write',{'word':'GO','mode':'write'}),
           ('slam',{'word':'GO','mode':'slam'}),('static',{'word':'GO'}),
           ('no-passes',{'word':'GO','mode':'hold','under':False,'echo':False,'halo_color':False}),
           ('colors',{'word':'GO','mode':'hold','ink':'#8020b0','halo_color':'#25aaff','echo':'#f08020','nib':.22}),
           ('two-lines',{'lines':['NEW','WAVE'],'mode':'hold','under':[False,True]}),
           ('custom-region',{'word':'YES!','region':[.1,.2,.5,.7],'mode':'hold','rot':.2}),
           ('top-left',{'word':'HI','region':'tl','mode':'hold'}),
           ('write-duration',{'word':'GO','mode':'write','wdur':.25}),
           ('letter-keys',{'word':'GO','mode':'write','wkeys':[8.05,8.2,8.45]}),
           ('face-avoid',{'word':'GO','mode':'slam'}),
           ('alphabet',{'lines':['ABCDEFG','HIJKLMN','OPQRSTU','VWXYZ'],'mode':'hold'}),
           ('digits',{'lines':['0123456789',"!?.,:-'/+*#&"],'mode':'hold'}),
           ('shot-layer',{'word':'go','at':.15,'d':.4,'region':'bottom'}),
           ('shot-fx',{'word':'YES','at':.1,'d':.5,'region':'top'}),
           ('hidden',{'word':'GO','mode':'hold'}),
           ('layer-order',{'word':'GO','mode':'hold','region':'center'})]
    if suite=='graffiti-detail':
        cases=[(f'seed-{seed}',{'word':'GO','seed':seed}) for seed in (0,1,19,42)]
        cases += [(f'spacing-{i}',{'word':word}) for i,word in enumerate(('A B',' AB ','AB!','AB?','AB.','AB,','I','IIII','STUDIO'))]
        cases += [('longbar',{'word':'AAA','longbar':True}),
                  ('lean',{'word':'STYLE','slant':.3,'bounce':.2,'rot':.15}),
                  ('small-cap',{'word':'INK','cap':40,'halo':0}),
                  ('fine-nib',{'word':'TEXT','nib':.08}),
                  ('wide-nib',{'word':'TEXT','nib':.3}),
                  ('line-settings',{'lines':['NEW','STYLE'],'line_scale':[1,.7],'line_dx':[.03,-.02],'line_rot':[.1,-.1],'leading':.1}),
                  ('two-lines-write',{'lines':['NEW','WAVE'],'mode':'write'}),
                  ('slam-corner',{'word':'HI','region':'tl','mode':'slam'}),
                  ('offset-lines',{'lines':['LONGWORD','ANOTHER'],'line_dx':[.1,-.1]})]
        cases=[(name,{'mode':'hold',**params}) for name,params in cases]
    edit['canvas']['frames']=len(cases)*48;edit['shots']=[];edit['text']=[]
    for i,(name,params) in enumerate(cases):
        shot={'f0':i*48,'f1':(i+1)*48,'clip':'A','srcf':0,'speed':0}
        if name=='face-avoid':shot['face']={'box':[90,35,230,170]}
        if name=='shot-layer':shot['layers']=[{'type':'graffiti',**params}]
        if name=='shot-fx':shot['fx']={'graffiti':params}
        if name=='hidden':shot['fx']={'text':False}
        if name=='layer-order':shot['layers']=[{'type':'graffiti','phase':'back',**params},{'type':'white','phase':'over','d':.8}]
        edit['shots'].append(shot)
        if name not in ('shot-layer','shot-fx','layer-order'):edit['text'].append({'type':'graffiti','f0':i*48,'f1':(i+1)*48,**params})
    return [{'name':name,'f0':i*48,'f1':(i+1)*48} for i,(name,_) in enumerate(cases)]
