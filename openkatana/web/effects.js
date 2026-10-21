/* Independently authored processing and vector graphics. No vendor assets. */
'use strict';
window.OpenKatanaEffects=(()=>{
  const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
  const orders={glitch:10,mosaic:11,blur:12,blurIn:13,blurOut:14,rgbsplit:15,fin:30,fout:31,magenta:50,leak:52,wipe:65,vignette:5,grain:10,dust:20,big:10,burst:10,contour:10,particles:45,polygon3d:45,morph:45};
  const phase={big:'back',burst:'back',contour:'over',particles:'over',polygon3d:'over',morph:'over',vignette:'final',grain:'final',dust:'final'};
  const ease=(p,k='lin')=>k==='inout'?p*p*(3-2*p):k==='in2'?p*p:k==='in3'?p**3:k==='out2'?1-(1-p)**2:k==='out3'?1-(1-p)**3:p;
  const buffer=(w,h)=>{const c=document.createElement('canvas');c.width=Math.max(1,Math.round(w));c.height=Math.max(1,Math.round(h));return c;};
  function copy(ctx){const c=buffer(ctx.canvas.width,ctx.canvas.height);c.getContext('2d').drawImage(ctx.canvas,0,0);return c;}
  function filter(ctx,value){const c=copy(ctx);ctx.save();ctx.filter=value;ctx.clearRect(0,0,c.width,c.height);ctx.drawImage(c,0,0);ctx.restore();}
  function wash(ctx,color,alpha=1,op='source-over'){ctx.save();ctx.fillStyle=color;ctx.globalAlpha=clamp(alpha);ctx.globalCompositeOperation=op;ctx.fillRect(0,0,ctx.canvas.width,ctx.canvas.height);ctx.restore();}
  // "#rrggbb" or canonical "rgba(r,g,b,a)" -> [r,g,b] (the colour's own alpha is not used by alpha-replacing washes)
  function rgbOf(color){if(color[0]==='#')return [1,3,5].map(i=>parseInt(color.slice(i,i+2),16));return color.slice(color.indexOf('(')+1).split(',').slice(0,3).map(Number);}
  function washAlpha(ctx,color,alpha,op='source-over'){const rgb=rgbOf(color);wash(ctx,`rgba(${rgb.join(',')},${clamp(alpha)})`,1,op);}
  function mosaic(ctx,size){const {width:w,height:h}=ctx.canvas;size=Math.max(2,Math.round(size));const c=buffer(w,h),sw=Math.max(1,Math.round(w/size)),sh=Math.max(1,Math.round(h/size));c.getContext('2d').globalCompositeOperation='copy';c.getContext('2d').drawImage(ctx.canvas,0,0,sw,sh);ctx.save();ctx.imageSmoothingEnabled=false;ctx.drawImage(c,0,0,sw,sh,0,0,w,h);ctx.restore();}
  function vignette(ctx,p){const {width:w,height:h}=ctx.canvas,c=p.color??'#000000',g=ctx.createRadialGradient(w/2,h/2,h*(p.r0??.45),w/2,h/2,h*(p.r1??.95));g.addColorStop(0,`rgba(${rgbOf(c).join(',')},0)`);g.addColorStop(1,c);ctx.save();ctx.globalAlpha=clamp(p.v??p.amt??.35);ctx.fillStyle=g;ctx.fillRect(0,0,w,h);ctx.restore();}
  function look(ctx,p,frame,hash){
    if(!p||p==='none'||p==='clean')return;
    const {width:w,height:h}=ctx.canvas;
    if(p.type==='grade'||p.type==='filter'){
      if(p.filter&&p.filter!=='none')filter(ctx,p.filter);
      for(const layer of p.layers??[])wash(ctx,layer.color,layer.alpha??1,layer.op??'soft-light');return;
    }
    const data=ctx.getImageData(0,0,w,h),a=data.data,levels=p.levels??4;
    if(p.type==='posterize'){for(let i=0;i<a.length;i+=4)for(let c=0;c<3;c++)a[i+c]=Math.round(a[i+c]/255*(levels-1))*255/(levels-1);ctx.putImageData(data,0,0);return;}
    // Photocopy family (threshold/levels/xerox/neg/duotone). Behaviour characterised from observable reference output
    // with a calibration chart (audit finding F-NAT-017): luma 0.30/0.59/0.11, black/white remap, smoothstep
    // S-curve, then a blend towards the 0.5 step by `hard`. Noise (grit) uses OpenKatana's own hash generator.
    const rgb=rgbOf;
    const base={threshold:[0,1,1,0],levels:[.13,.8,.85,.42],xerox:[.13,.8,.62,.42],neg:[.13,.8,.62,.42],duotone:[.13,.8,.62,.5]}[p.type];
    const ink=rgb(p.ink??(p.type==='duotone'?'#080c04':'#0a0a0a')),paper=rgb(p.paper??(p.type==='duotone'?'#b6ff1f':'#ffffff'));
    const black=p.black??base[0],white=p.white??base[1],hard=p.hard??base[2],grit=p.grit??base[3],scale=1/Math.max(1e-3,white-black);
    const invert=p.invert||p.type==='neg',step=Math.floor(frame/(p.grain_every??1));
    const k0=p.key===true?{}:p.key,key=k0?{channel:'g',lo:.06,width:.09,vmin:.16,vw:.16,soft:15,sat:.25,val:.16,amt:1,stoch:.8,mix:.4,lift:.12,gain:1.1,
      ...k0,dark:rgb(k0.dark??'#0a2600'),light:rgb(k0.light??'#c4ff34')}:null;
    for(let i=0;i<a.length;i+=4){
      let L=(a[i]*.3+a[i+1]*.59+a[i+2]*.11)/255;
      L=(L-black)*scale;L=L<0?0:L>1?1:L;L=L*L*(3-2*L);
      const n=grit?(hash(i/4,step,p.seed??31)-.5)*grit:0;
      let v=L+((L+n>.5?1:0)-L)*hard;v=v<0?0:v>1?1:v;
      if(invert)v=1-v;
      const r0=a[i],g0=a[i+1],b0=a[i+2];
      for(let c=0;c<3;c++)a[i+c]=paper[c]+(ink[c]-paper[c])*(1-v);
      if(key){   // accent key (audit F-NAT-002): keyed pixels become a two-tone ramp between key.dark and key.light
        const k=keyStrength(r0,g0,b0,key),pix=i/4;
        if(k*key.amt>.5+(hash(pix,step,(p.seed??31)+101)-.5)*key.stoch){
          const Lk=(r0*.3+g0*.59+b0*.11)/255,cc=Math.min(1,Math.max(0,(Lk+key.lift)*key.gain+(hash(pix,step,(p.seed??31)+102)-.5)*.2));
          const t=(1-key.mix)*cc+key.mix*(cc+(hash(pix,step,(p.seed??31)+103)-.5)*.3>.5?1:0);
          for(let c=0;c<3;c++)a[i+c]=key.dark[c]+(key.light[c]-key.dark[c])*t;
        }
      }
    }ctx.putImageData(data,0,0);
  }
  // Key mask: channel mode = channel dominance over the other two (lo, width) x a value gate (vmin, vw);
  // hue mode = inside [h0, h1] degrees (wrapping) with `soft` degrees of falloff, gated by sat and val.
  function keyStrength(r,g,b,key){
    const mx=Math.max(r,g,b)/255,mn=Math.min(r,g,b)/255,ramp=(x,lo,w)=>w<=0?(x>=lo?1:0):Math.min(1,Math.max(0,(x-lo)/w));
    if(key.hue){
      if(mx<=0||mx-mn<=0)return 0;
      const d=mx-mn,R=r/255,G=g/255,B=b/255;
      let h=mx===R?((G-B)/d)%6:mx===G?(B-R)/d+2:(R-G)/d+4;h=(h*60+360)%360;
      const [h0,h1]=key.hue,span=((h1-h0)%360+360)%360,off=((h-h0)%360+360)%360;
      const dist=off<=span?0:Math.min(off-span,360-off);
      const inside=key.soft>0?Math.max(0,1-dist/key.soft):(dist===0?1:0);
      return inside*ramp(d/mx,key.sat,key.sat)*ramp(mx,key.val,key.val);
    }
    const ch={r:0,g:1,b:2}[key.channel],v=[r,g,b].map(x=>x/255),others=v.filter((_,j)=>j!==ch);
    return ramp(v[ch]-Math.max(...others),key.lo,key.width)*ramp(mx,key.vmin,key.vw);
  }
  // Block glitch (observed structure: a grid of tile px squares; a few tiles shifted sideways, one or two washed white,
  // sometimes a faint dark wash; no whole-frame mosaic). Randomness is OpenKatana's own.
  function tileGlitch(ctx,source,amt,tile,seed,step,hash){
    const {width:w,height:h}=ctx.canvas,cols=Math.ceil(w/tile),rows=Math.ceil(h/tile),n=Math.max(1,Math.round(amt*6));
    for(let i=0;i<n;i++){
      const tx=Math.floor(hash(seed,step,i)*cols)*tile,ty=Math.floor(hash(seed,step,i+31)*rows)*tile,kind=hash(seed,step,i+57);
      ctx.save();ctx.beginPath();ctx.rect(tx,ty,tile,tile);ctx.clip();
      if(kind<.5){const dx=Math.round((hash(seed,step,i+83)*2-1)*tile*.6);ctx.drawImage(source,dx,0);}
      else if(kind<.85){ctx.fillStyle='rgba(255,255,255,0.6)';ctx.fillRect(tx,ty,tile,tile);}
      else{ctx.fillStyle='rgba(0,0,0,0.22)';ctx.fillRect(tx,ty,tile,tile);}
      ctx.restore();
    }
  }
  function path(ctx,pts,closed){ctx.beginPath();pts.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));if(closed)ctx.closePath();}
  function paintPath(ctx,p){if(p.fill){ctx.fillStyle=p.fill;ctx.fill();}if(p.stroke||!p.fill){ctx.strokeStyle=p.stroke??'#ffffff';ctx.lineWidth=p.lw??3;ctx.stroke();}}
  function project3d(points,p,w,h,t=0){
    const pivot=p.pivot??[0,0,0],f=.5*h/Math.tan((p.fov??50)*Math.PI/360),near=p.near??1;
    let poly=points.map(point=>{
      let [x,y,z]=point.map((v,i)=>v-pivot[i]);
      for(const [a,b,angle] of [[1,2,p.rx??0],[2,0,(p.ry??0)+(p.spin??0)*t],[0,1,p.rz??0]]){
        let v=[x,y,z],c=Math.cos(angle),s=Math.sin(angle),va=v[a]*c-v[b]*s,vb=v[a]*s+v[b]*c;v[a]=va;v[b]=vb;[x,y,z]=v;
      }
      return [x+pivot[0],y+pivot[1],z+pivot[2]+(p.z??600)];
    });
    // Clip before division so polygons crossing the near plane stay finite.
    const clipped=[];
    for(let i=0;i<poly.length;i++){
      const a=poly[i],b=poly[(i+1)%poly.length],ai=a[2]>=near,bi=b[2]>=near;
      if(ai)clipped.push(a);if(ai!==bi){const q=(near-a[2])/(b[2]-a[2]);clipped.push(a.map((v,j)=>v+(b[j]-v)*q));}
    }
    return clipped.map(([x,y,z])=>[(p.pos?.[0]??.5)*w+x*f/z,(p.pos?.[1]??.5)*h+y*f/z]);
  }
  function particles(ctx,p,s){
    const {W:w,H:h,elapsed:t,hash}=s,life=p.life??1,rate=p.rate??30,start=p.at??0,age=t-start;
    if(age<0)return;
    const end=p.d??s.duration,burst=p.burst??0,max=p.max??2000,seed=p.seed??1;
    const first=Math.max(0,Math.ceil((age-life)*rate)),last=Math.min(Math.floor(age*rate),Math.ceil(end*rate)-1),ids=[];
    if(age<life)for(let i=0;i<Math.min(burst,max);i++)ids.push([i,0]);
    for(let i=last;i>=first&&ids.length<max;i--)ids.push([burst+i,rate?i/rate:0]);
    ctx.save();
    for(const [id,born] of ids){
      const a=age-born;if(a<0||a>=life)continue;
      const rnd=k=>hash(seed,id,k),theta=(p.angle??-Math.PI/2)+(rnd(1)-.5)*(p.cone??Math.PI/3),speed=(p.speed??300)*(.65+.7*rnd(2));
      const drag=p.drag??0,travel=drag?(1-Math.exp(-drag*a))/drag:a;
      let x=(p.pos?.[0]??.5)*w,y=(p.pos?.[1]??.5)*h;
      if(p.rect){x=(p.rect[0]+rnd(3)*p.rect[2])*w;y=(p.rect[1]+rnd(4)*p.rect[3])*h;}
      else {const r=Math.sqrt(rnd(3))*(p.radius??0),b=rnd(4)*Math.PI*2;x+=r*Math.cos(b);y+=r*Math.sin(b);}
      x+=Math.cos(theta)*speed*travel+Math.sin(a*8+rnd(5)*6.28)*(p.wobble??0);
      y+=Math.sin(theta)*speed*travel+.5*(p.gravity??0)*a*a;
      ctx.save();ctx.translate(x,y);ctx.rotate(rnd(6)*Math.PI*2+a*(rnd(7)-.5)*8);
      const q=a/life,alpha=Math.min((p.fadeIn??.1)?q/(p.fadeIn??.1):1,(p.fadeOut??.3)?(1-q)/(p.fadeOut??.3):1);
      ctx.globalAlpha=clamp(alpha);ctx.fillStyle=(p.colors??['#ffd23f','#ff5277','#66e7c8'])[Math.floor(rnd(8)*(p.colors??[1,2,3]).length)];
      const r=(p.size??6)*(.6+.8*rnd(9));
      if(p.shape==='spark'){path(ctx,[[-r,0],[0,-r*.2],[r*2,0],[0,r*.2]],true);ctx.fill();}
      else if(p.shape==='square'||p.shape==='confetti')ctx.fillRect(-r/2,-r/2,r,p.shape==='confetti'?r*.4:r);
      else {ctx.beginPath();ctx.arc(0,0,r/2,0,Math.PI*2);ctx.fill();}ctx.restore();
    }ctx.restore();
  }
  function wipe(ctx,p,q,s){
    const {W:w,H:h,hash}=s,kind=p.kind??'iris',mask=buffer(w,h),c=mask.getContext('2d');
    c.fillStyle=p.color??'#000000';
    q=ease(clamp(q),'inout');if(p.side!=='out')q=1-q;if(p.invert)q=1-q;
    if(q<=0)return;if(q>=1){wash(ctx,p.color??'#000000');return;}
    if(kind==='iris'){const cx=(p.cx??.5)*w,cy=(p.cy??.5)*h,r=Math.max(...[[0,0],[w,0],[w,h],[0,h]].map(([x,y])=>Math.hypot(x-cx,y-cy)));c.beginPath();c.arc(cx,cy,r*q,0,Math.PI*2);c.fill();}
    else {
      const vertical=['up','down'].includes(p.dir),reverse=['left','up'].includes(p.dir),length=vertical?h:w,cross=vertical?w:h;
      c.save();if(vertical)c.transform(0,1,1,0,0,0);if(reverse){c.translate(length,0);c.scale(-1,1);}
      if(kind==='stripes'){
        const n=p.n??8,st=p.stagger??.5;
        for(let i=0;i<n;i++){const u=clamp(q*(1+st)-st*i/Math.max(1,n-1));c.fillRect(0,i*cross/n,length*u,cross/n+1);}
      }else {
        const pts=[[0,0]],step=p.step??18;
        for(let y=0;y<cross+step;y+=step)pts.push([q*length+(hash(p.seed??1,Math.floor(y/step),1)-.5)*(p.amp??26)*Math.sin(q*Math.PI),Math.min(y,cross)]);
        pts.push([0,cross]);path(c,pts,true);c.fill();
      }c.restore();
    }
    ctx.save();if(p.feather)ctx.filter=`blur(${p.feather}px)`;ctx.drawImage(mask,0,0);ctx.restore();
  }
  function draw(ctx,name,p,s){
    if(!(name in orders))return false;
    p=p===true?{}:p;const {W:w,H:h,elapsed:t,duration,frame,hash,face,maskBuffer}=s;
    const defaults={mosaic:.08,blur:.12,blurIn:.12,blurOut:.5,fin:.14,fout:.07,glitch:.1,magenta:.2,wipe:.3};
    const d=p.d??defaults[name]??duration,at=p.at??(p.side==='out'||name==='fout'?duration-d:name==='blurOut'?.05:0),age=t-at,q=clamp(age/d);
    if(name==='particles'){particles(ctx,p,s);return true;}
    if(age<0||(age>=d&&name!=='blurOut'))return true;
    ctx.save();
    if(name==='mosaic'||name==='magenta'){
      const u=p.side==='out'?1-q:q; mosaic(ctx,(p.from??(name==='magenta'?40:56))+((p.to??4)-(p.from??(name==='magenta'?40:56)))*(name==='magenta'?u:ease(u,'out3')));
      if(name==='magenta'){washAlpha(ctx,p.color??'#ec46be',(1-q)*.75,'multiply');washAlpha(ctx,p.color2??'#ff96e1',(1-q)*.55,'screen');}
    }else if(name.startsWith('blur')){
      const radius=name==='blurIn'?(p.max??14)*(1-q)**3:name==='blurOut'?2+((p.max??22)-2)*ease(q,'out3'):(p.max??16)*Math.sin(q*Math.PI);
      const source=copy(ctx);ctx.save();ctx.filter=`blur(${radius}px)`;ctx.drawImage(source,-20,-15,w+40,h+30);ctx.restore();
      const frameOn=name==='blurIn'?q<.6:name==='blurOut'?q>.3:true;
      if(p.frame!==false&&frameOn){ctx.strokeStyle='rgba(55,45,60,0.8)';ctx.lineWidth=5;ctx.strokeRect(5,5,w-10,h-10);const g=ctx.createRadialGradient(w/2,h/2,h*.45,w/2,h/2,h*.85);g.addColorStop(0,'rgba(0,0,0,0)');g.addColorStop(1,'rgba(30,20,35,0.22)');ctx.fillStyle=g;ctx.fillRect(0,0,w,h);}
      if(name==='blurOut')washAlpha(ctx,p.color??'#fff8fc',q*.25);
    }else if(name==='fin'||name==='fout'){
      const k=(p.k??(name==='fout'?.8:1))*(name==='fout'?q:(1-q)**1.4),source=copy(ctx);
      ctx.save();ctx.filter=`brightness(${1+k*1.35}) contrast(${1+k*.3}) saturate(${1-k*.45})`;ctx.drawImage(source,0,0);ctx.restore();
      const x=face?.x??w/2,y=face?.y??h*.42,g=ctx.createRadialGradient(x,y,0,x,y,w*(.2+.6*k));
      g.addColorStop(0,`rgba(255,255,255,${k*.5})`);g.addColorStop(.45,`rgba(255,245,252,${k*.3})`);g.addColorStop(1,'rgba(255,255,255,0)');ctx.globalCompositeOperation='screen';ctx.fillStyle=g;ctx.fillRect(0,0,w,h);
      if(p.blocks&&k>.3)tileGlitch(ctx,copy(ctx),.35,p.tile??64,7,Math.floor(frame/(s.boil??2)),hash);
    }else if(name==='glitch'){
      const source=copy(ctx),amt=p.amt??(p.blocks?.55:.35),seed=p.seed??9;
      if(p.blocks)tileGlitch(ctx,source,amt,p.tile??64,seed,Math.floor(frame/(s.boil??2)),hash);
      else {let value=Math.imul(Math.round((seed+Math.floor(frame/(s.boil??2))*31)*1000),2654435761)>>>0;const random=()=>{value=(Math.imul(value,1664525)+1013904223)>>>0;return value/4294967296;};for(let y=0;y<h;){const sh=Math.max(1,Math.round(h*(.012+.06*random())));if(random()<amt){const dx=Math.round((random()*2-1)*h*.06);ctx.drawImage(source,0,y,w,sh,dx,y,w,sh);}y+=sh;}}
    }else if(name==='rgbsplit'){
      const source=copy(ctx),red=copy(ctx),cyan=copy(ctx),dx=(p.v??6)*(p.decay?Math.max(0,1-age/p.decay):1);
      wash(red.getContext('2d'),'#ff0000',1,'multiply');wash(cyan.getContext('2d'),'#00ffff',1,'multiply');
      ctx.globalCompositeOperation='copy';ctx.drawImage(cyan,-dx,0,w+dx*2,h);ctx.globalCompositeOperation='lighter';ctx.drawImage(red,0,0,w+dx*2,h);
    }else if(name==='wipe')wipe(ctx,p,q,s);
    else if(name==='vignette')vignette(ctx,p);
    else if(name==='grain'){
      const cell=(p.cell??2)*1.5,c=buffer(w/cell,h/cell),cctx=c.getContext('2d'),im=cctx.createImageData(c.width,c.height);
      for(let i=0;i<im.data.length;i+=4){const n=Math.floor(hash(p.seed??71,frame,i)*256);im.data.set([n,p.mono===false?Math.floor(hash(72,frame,i)*256):n,p.mono===false?Math.floor(hash(73,frame,i)*256):n,255],i);}cctx.putImageData(im,0,0);
      ctx.globalCompositeOperation=p.op??'soft-light';ctx.globalAlpha=(p.v??p.amt??.32)*.5;ctx.imageSmoothingEnabled=true;ctx.drawImage(c,0,0,w,h);   // cell size, smoothing and strength matched to observed grain statistics (audit F-NAT-014)
    }else if(name==='dust'){
      for(let i=0;i<(p.n??14);i++){ctx.fillStyle=p.color??(hash(i,frame,2)>.5?'#ffffff':'#101010');ctx.fillRect(hash(p.seed??3,frame,i)*w,hash(p.seed??4,frame,i)*h,1+hash(i,frame,8)*3,1+hash(i,frame,9)*3);}
    }else if(name==='leak'){
      const x=((p.x??.85)+Math.sin(t+(p.seed??0))*(p.drift??.1))*w,y=(p.y??.2)*h,g=ctx.createRadialGradient(x,y,0,x,y,Math.max(.001,(p.r??.6)*w));g.addColorStop(0,p.color??'#ff8c28');{const c2=rgbOf(p.color2??'#ff3c1e').join(',');g.addColorStop(.62,`rgba(${c2},0.18)`);g.addColorStop(1,`rgba(${c2},0)`);}/* falloff fitted to observed output (audit F-NAT-014) */ctx.fillStyle=g;ctx.globalAlpha=p.amt??.55;ctx.globalCompositeOperation=p.op??'screen';ctx.fillRect(0,0,w,h);
    }else if(name==='contour'&&maskBuffer){
      const c=buffer(w,h),cc=c.getContext('2d'),r=p.r??2;let matte=maskBuffer;if(p.threshold!==undefined){matte=buffer(w,h);const mc=matte.getContext('2d');mc.drawImage(maskBuffer,0,0);const pixels=mc.getImageData(0,0,w,h);for(let i=3;i<pixels.data.length;i+=4)pixels.data[i]=pixels.data[i]/255>=p.threshold?255:0;mc.putImageData(pixels,0,0);}for(const [dx,dy] of [[r,0],[-r,0],[0,r],[0,-r]])cc.drawImage(matte,dx,dy);cc.globalCompositeOperation='destination-out';cc.drawImage(matte,0,0);cc.globalCompositeOperation='source-in';cc.fillStyle=p.color??'#ffffff';cc.fillRect(0,0,w,h);ctx.globalAlpha=p.alpha??1;ctx.drawImage(c,0,0);
    }else if(name==='big'){
      ctx.translate((p.pos?.[0]??.5)*w,(p.pos?.[1]??.5)*h);ctx.rotate(p.rot??0);ctx.font=`900 ${p.size??h*.65}px "${p.family}"`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle=p.fill??'#ffd23f';ctx.fillText(p.text,0,0);if(p.stroke){ctx.strokeStyle=p.stroke;ctx.lineWidth=p.lw??3;ctx.strokeText(p.text,0,0);}
    }else if(name==='burst'){
      const D=face?.D??Math.min(w,h)*.15,x=(face?.x??w/2)+(p.dx??0)*D,y=(face?.y??h/2)+(p.dy??.4)*D,n=p.points??15,r=(p.r??3.5)*D;
      ctx.translate(x,y);ctx.rotate((face?.a??0)+(p.rot??0));
      if(!s.lettersOnly){path(ctx,Array.from({length:n*2},(_,i)=>{const a=i*Math.PI/n,rr=r*(i%2?.58:1)*(1+(hash(p.seed??1,i,4)-.5)*.08);return [Math.cos(a)*rr,Math.sin(a)*rr*(p.ry??.66)];}),true);paintPath(ctx,{fill:p.fill??'#c9b8ff',stroke:p.stroke??'#8361d1',lw:p.lw??3});if(p.rays){ctx.strokeStyle=p.rays;ctx.lineWidth=p.lw??3;for(let i=0;i<n;i++){const a=i*Math.PI*2/n;path(ctx,[[Math.cos(a)*r*.8,Math.sin(a)*r*.8*(p.ry??.66)],[Math.cos(a)*r*1.1,Math.sin(a)*r*1.1*(p.ry??.66)]],false);ctx.stroke();}}}
      else if(p.letters){const letters=[...p.letters],u=clamp(age/.15);ctx.scale(u,u);ctx.font=`900 ${(p.ls??.88)*D}px "${p.family}"`;ctx.fillStyle=p.fill??'#ffffff';ctx.textAlign='center';ctx.textBaseline='middle';letters.forEach((ch,i)=>{const a=(p.a0??-2.85)+((p.a1??-.05)-(p.a0??-2.85))*(i+.5)/letters.length;ctx.save();ctx.translate(Math.cos(a)*(p.lr??2.95)*D,Math.sin(a)*(p.lr??2.95)*D*(p.ry??.66));ctx.rotate(a+Math.PI/2);ctx.fillText(ch,0,0);ctx.restore();});}
    }else if(name==='polygon3d'){const pts=project3d(p.points,p,w,h,age);if(pts.length>=3){path(ctx,pts,true);paintPath(ctx,p);}}
    else if(name==='morph'){const u=ease(q,p.ease);path(ctx,p.from.map((a,i)=>a.map((v,j)=>(v+(p.to[i][j]-v)*u)*(j?h:w))),p.closed!==false);paintPath(ctx,p);}
    ctx.restore();return true;
  }
  return {orders,phase,look,draw,project3d};
})();
