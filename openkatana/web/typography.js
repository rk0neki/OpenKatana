'use strict';
window.OpenKatanaText = (ctx, item, elapsed, duration, fps, W, H, jitter=[0,0], face=null) => {
  if(elapsed<0 || elapsed>=duration) return;
  let scale=1, alpha=item.alpha ?? 1;
  const progress=Math.max(0,Math.min(1,elapsed/(item.anim_d ?? (item.anim==='fade'?.15:.1))));
  if(item.anim==='pop') scale=1+(item.pop ?? .18)*Math.max(0,1-elapsed*fps/3);
  if(item.anim==='slam') {const steps=item.sc ?? [1.3,.9,1.06,1];scale=steps[Math.min(steps.length-1,Math.floor(elapsed*fps))];}
  if(item.anim==='fade') alpha*=progress;
  if(item.anim==='grow') scale=.85+.15*(1-(1-progress)**3);
  if(item.fade_out) alpha*=Math.max(0,Math.min(1,(duration-elapsed)/item.fade_out));
  const keyed=(keys)=>{let a=1;for(const [t,v] of keys ?? []){if(t>elapsed)break;a=v;}return a;};
  const flicker=(index)=>{const f=item.flicker;if(!f)return 1;const n=Math.floor(elapsed*(f.hz ?? 12));const v=Math.sin((n+1)*127.1+(f.seed ?? 1)*311.7+index*74.7)*43758.5453;return v-Math.floor(v)<(f.duty ?? .8)?1:(f.min_alpha ?? 0);};
  alpha*=keyed(item.opacity_keys)*(item.flicker?.per_letter?1:flicker(0));
  const typed=item.anim==='type' || item.parts;
  const explicit=item.render_style==='explicit';
  const letters=typed || item.tracking!=null || item.letter_opacity_keys || item.flicker?.per_letter || item.karaoke;
  // Karaoke (audit F-CAP-001): characters of words whose time has come take the highlight colour; `sweep` also fills
  // the current word left to right. Word times are seconds from the item start.
  const karaokeFill=(()=>{
    const k=item.karaoke;if(!k)return null;
    const text=item.text ?? '',owner=new Array(text.length).fill(-1);let from=0;
    k.words.forEach((w,wi)=>{const at=text.indexOf(w.text,from);if(at>=0){for(let c=at;c<at+w.text.length;c++)owner[c]=wi;from=at+w.text.length;}});
    return i=>{
      const wi=owner[i];if(wi<0)return null;const w=k.words[wi];
      if(elapsed>=w.t1)return k.highlight;
      if(elapsed<w.t0)return null;
      if(k.mode!=='sweep')return k.highlight;
      const first=owner.indexOf(wi),n=w.text.length;return (i-first+.5)/n<=(elapsed-w.t0)/Math.max(1e-3,w.t1-w.t0)?k.highlight:null;
    };
  })();
  let x=(item.pos?.[0] ?? .5)*W,y=(item.pos?.[1] ?? .5)*H,size=item.size ?? 96,rot=item.rot ?? 0;
  if(item.anchor==='face') {
    const f=face ?? {x:W*.5,y:H*.42,D:W*.1,a:0},o=item.o ?? [0,1.05];
    x=f.x+(o[0]*Math.cos(f.a)-o[1]*Math.sin(f.a))*f.D;
    y=f.y+(o[0]*Math.sin(f.a)+o[1]*Math.cos(f.a))*f.D;
    rot+=f.a;
    if(item.size_eu!=null)size=Math.max(item.min ?? 1,Math.min(item.max ?? 2000,f.D*item.size_eu));
  }
  const font=(kind=item.kind ?? 'bold',override=true)=>`${override && item.style!=null?item.style:kind==='thin'?'normal':'italic'} ${override && item.weight!=null?item.weight:kind==='thin'?300:kind==='heavy'?900:800} ${Math.round(size)}px ${JSON.stringify(item.family)}`;
  ctx.save();
  ctx.translate(x+jitter[0],y+jitter[1]);
  ctx.rotate(rot);ctx.scale(typed?1:scale,typed?1:scale);
  ctx.scale((item.scale_x ?? 1)*(typed && explicit?scale:1),(item.scale_y ?? 1)*(typed && explicit?scale:1));
  ctx.globalAlpha=alpha;ctx.font=font();
  ctx.textAlign=item.align ?? 'center';ctx.textBaseline='middle';ctx.lineJoin='round';
  const shadow=item.shadow ?? 'glow';
  const applyShadow=()=>{
    if(shadow===false)return;
    if(typeof shadow==='object') {ctx.shadowColor=shadow.color ?? 'rgba(190,110,220,.55)';ctx.shadowBlur=shadow.blur ?? 10;ctx.shadowOffsetX=shadow.dx ?? 0;ctx.shadowOffsetY=shadow.dy ?? 0;}
    else {ctx.shadowColor=shadow==='dark'?'rgba(0,0,0,.45)':'rgba(190,110,220,.55)';ctx.shadowBlur=shadow==='dark'?8:14;}
  };
  const draw=(text,x,typed=false,kind=item.kind ?? 'bold',fill=null)=>{
    applyShadow();
    const stroke=typed && !explicit ? (item.stroke ?? '#c98be0') : (item.stroke===null?null:(item.stroke ?? '#c98be0'));
    const lw=typed && !explicit?(kind==='thin'?4:5):(item.lw ?? 5);
    if(stroke && lw>0) {ctx.strokeStyle=stroke;ctx.lineWidth=lw;ctx.strokeText(text,x,0);}
    ctx.shadowColor='transparent';ctx.shadowBlur=0;
    if(explicit && (!stroke || lw===0))applyShadow();
    if(item.fill!==null || fill){ctx.fillStyle=fill ?? item.fill ?? '#ffffff';ctx.fillText(text,x,0);}
  };
  if(letters) {
    const chars=(item.parts ?? [[item.text,item.kind ?? 'bold']]).flatMap(([text,kind])=>Array.from(text,ch=>({ch,kind})));
    const widths=chars.map(({ch,kind})=>{ctx.font=font(kind,explicit || !typed);return ctx.measureText(ch).width;});
    const tracking=item.tracking ?? 0;
    const width=widths.reduce((a,b)=>a+b,0)+Math.max(0,chars.length-1)*tracking;
    let x=explicit || !typed ? (item.align==='left'?0:item.align==='right'?-width:-width/2) : -width/2;
    ctx.textAlign='left';
    const count=item.anim==='type'?Math.min(chars.length,(item.base ?? 0)+Math.floor(elapsed/(item.dt ?? .05))+1):chars.length;
    for(let i=0;i<count;i++){ctx.globalAlpha=alpha*keyed(item.letter_opacity_keys?.[i])*(item.flicker?.per_letter?flicker(i):1);ctx.font=font(chars[i].kind);draw(chars[i].ch,x,!!typed,chars[i].kind,karaokeFill?karaokeFill(i):null);x+=widths[i]+tracking;}
  } else draw(item.text,0);
  ctx.restore();
};
