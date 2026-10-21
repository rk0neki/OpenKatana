"""Authored effect cases. Visual comparisons are evidence, never assumed parity."""
def configure(edit,root,suite):
    cases=[]
    for name in ('mosaic','blur','flashlight','glitch','magenta'):
        for side in ('in','out'):
            if name=='magenta' and side=='out':continue
            cases.append((name+'-'+side,{side:{'type':name,'d':.5}}))
    cases += [('mosaic-custom',{'fx':{'mosaic':{'at':.1,'d':.4,'from':32,'to':2}}}),
              ('blur-no-frame',{'fx':{'blur':{'d':.5,'max':8,'frame':False}}}),
              ('rgb-split',{'fx':{'rgbsplit':{'v':4}}}),
              ('grade',{'look':{'type':'grade','filter':'contrast(1.2) saturate(0.5)','layers':[{'op':'multiply','color':'#d0e4ff','alpha':.2}]}})]
    length=24
    edit['canvas'].update(fps=30,frames=len(cases)*length)
    edit['shots']=[{'clip':'A','f0':i*length,'f1':(i+1)*length,'speed':0,**p} for i,(_,p) in enumerate(cases)]
    return [{'name':name,'f0':i*length,'f1':(i+1)*length} for i,(name,_) in enumerate(cases)]
