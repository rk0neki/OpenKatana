/* Marker lettering renderer with deterministic animation. */
'use strict';
window.OpenKatanaGraffiti=(()=>{
  // Own Switchback alphabet; animation and layout remain separate from artwork.
  const alphabet=OpenKatanaLetterforms;
  const regions={left:[.03,.07,.5,.93],full:[.03,.05,.97,.95],bl:[.02,.5,.3,.94],right:[.5,.07,.97,.93],leftwide:[.05,.05,.62,.95],br:[.7,.5,.98,.94],top:[.04,.05,.96,.47],rightwide:[.4,.05,.94,.95],tl2:[.04,.12,.32,.55],bottom:[.04,.53,.96,.95],tl:[.02,.06,.3,.5],lower:[.02,.27,.98,.975],center:[.08,.16,.92,.84],tr:[.7,.06,.98,.5],title:[.02,.21,.98,.965]};
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  function bounds(strokes) {
    const p=strokes.flatMap(s=>s.pts);
    return [Math.min(...p.map(p=>p[0])),Math.min(...p.map(p=>p[1])),Math.max(...p.map(p=>p[0])),Math.max(...p.map(p=>p[1]))];
  }
  function letterLayout(text,o={},hash) {
    text=text.toUpperCase();const cap=o.cap??100,seed=o.seed??1,slant=o.slant??.1,rot=o.rot??0,bounce=o.bounce??.11;
    const nLetters=[...text].filter(c=>c!==' ').length,trackCount=text.replace(/[ .,:'\/-]/g,'').length,gap=trackCount<=2?.1:trackCount===3?0:.05;
    const strokes=[];let cursor=0,li=0;
    const global=([x,y])=>{x-=slant*y;return [(x*Math.cos(rot)-y*Math.sin(rot))*cap+(o.x??0),(x*Math.sin(rot)+y*Math.cos(rot))*cap+(o.y??0)];};
    for(const [ci,ch] of [...text].entries()) {
      if(ch===' '){cursor+=.64+gap;continue;}
      const g=alphabet[ch],k=(.88+.24*hash(seed,ci,4))*(li===0?1.18:1),angle=(hash(seed,ci,5)-.5)*.04;
      const dy=(hash(seed,ci,3)*2-1)*bounce,cx=cursor+g.w*k/2;
      for(const [i,s] of g.s.entries()) {
        let points=s.p;
        if(o.longbar&&ch==='A'&&li===text.replaceAll(' ','').lastIndexOf('A')&&i===1)points=[[-.15,.6875],[.375,.6875],[.9,.6875]];
        const pts=points.map(([x,y])=>{x=x*k-g.w*k/2;y=(y-1)*k;return global([cx+x*Math.cos(angle)-y*Math.sin(angle),1+x*Math.sin(angle)+y*Math.cos(angle)+dy]);});
        strokes.push({pts,kind:s.k,li,ch,lcx:global([cx,.5])[0]});
      }
      cursor+=g.w*k+gap;li++;
    }
    if(o.under!==false&&nLetters>1) {
      const last=text.trim().at(-1),end=cursor-gap-('!?'.includes(last)||last==='.'?alphabet[last].w-.02+gap:0);
      [[[[-.04,1.18],[end*.42,1.25],[end+.03,1.16]],'stroke'],[[[end*.72,1.36],[end*.95,1.31]],'thin']].forEach(([pts,kind],under)=>strokes.push({pts:pts.map(global),kind,under}));
    }
    return {strokes,bb:bounds(strokes),cap,nLetters};
  }
  function layout(item,W,H,index,hash) {
    const lines=item.lines??(item.word??item.text).split('\n'),seed=item.seed??7+13*index;
    const rect=(Array.isArray(item.region)?item.region:regions[item.region??'center']).map((v,i)=>v*(i%2?H:W));
    const build=cap=>lines.map((text,i)=>letterLayout(text,{...item,cap:cap*(item.line_scale?.[i]??(i?.92:1)),seed:seed+i*3,rot:item.line_rot?.[i]??(lines.length===1?(item.rot??-.05):-.03-.02*i),under:Array.isArray(item.under)?item.under[i]:item.under===false?false:i===lines.length-1},hash));
    let cap=item.cap??300,rows=build(cap);
    const size=rows=>[Math.max(...rows.map(r=>r.bb[2]-r.bb[0])),rows.reduce((s,r,i)=>s+(r.bb[3]-r.bb[1])*(i?1-(item.leading??.25):1),0)];
    const [w,h]=size(rows),fit=Math.min(1,(rect[2]-rect[0]-cap*.1-(lines.length>1?W*.07:0))/w,(rect[3]-rect[1])/h);
    if(fit<1){cap*=fit;rows=build(cap);}
    let top=(rect[1]+rect[3]-size(rows)[1])/2;
    rows=rows.map((row,i)=>{
      const dx=(rect[0]+rect[2]-row.bb[0]-row.bb[2])/2+(item.line_dx?.[i]??0)*W,dy=top-row.bb[1];
      top+=row.bb[3]-row.bb[1]-(item.leading??.25)*(rows[i+1]?rows[i+1].bb[3]-rows[i+1].bb[1]:0);
      const strokes=row.strokes.map(s=>({...s,pts:s.pts.map(([x,y])=>[x+dx,y+dy]),...(s.lcx===undefined?{}:{lcx:s.lcx+dx})}));
      return {...row,strokes,bb:[row.bb[0]+dx,row.bb[1]+dy,row.bb[2]+dx,row.bb[3]+dy]};
    });
    // Offset lines are shifted together into the region, or centered when wider.
    const bb=bounds(rows.flatMap(r=>r.strokes)),pad=(item.cap??300)*.012;
    const shift=[0,1].map(a=>bb[a+2]-bb[a]>rect[a+2]-rect[a]-2*pad?(rect[a]+rect[a+2]-bb[a]-bb[a+2])/2:clamp(0,rect[a]+pad-bb[a],rect[a+2]-pad-bb[a+2]));
    for(const row of rows){row.bb=row.bb.map((v,i)=>v+shift[i%2]);for(const s of row.strokes){s.pts=s.pts.map(([x,y])=>[x+shift[0],y+shift[1]]);if(s.lcx!==undefined)s.lcx+=shift[0];}}
    return {rows,seed,cap,letters:rows.reduce((n,r)=>n+r.nLetters,0),bbox:bounds(rows.flatMap(r=>r.strokes)),center:[(rect[0]+rect[2])/2,(rect[1]+rect[3])/2]};
  }
  function curve(points,n=9) {
    const out=[];
    for(let i=0;i<points.length-1;i++)for(let j=0;j<n;j++) {
      const t=j/n;
      if(points.length===2){out.push(points[0].map((v,k)=>v+(points[1][k]-v)*t));continue;}
      const a=points[Math.max(0,i-1)],b=points[i],c=points[i+1],d=points[Math.min(points.length-1,i+2)];
      out.push([0,1].map(k=>.5*(2*b[k]+(-a[k]+c[k])*t+(2*a[k]-5*b[k]+4*c[k]-d[k])*t*t+(-a[k]+3*b[k]-3*c[k]+d[k])*t*t*t)));
    }
    out.push(points.at(-1));return out;
  }
  function paintLayout(ctx,L,o,hash) {
    const cap=L.cap,seed=o.seed??0,b=o.b??0,nib=(o.nib??.14)*cap,th=o.th??-.62,halo=o.halo??'#fff',haloK=(o.haloK??.02)*cap;
    const ink=o.ink??'rgba(17,17,17,.92)',echo=o.echo??'#b6ff1f',alpha=o.alpha??1,c=Math.cos(th),s=Math.sin(th);
    const prepared=L.strokes.map((stroke,i)=>{
      const jitter=stroke.pts.map(([x,y],j)=>[x+(hash(seed+i,b*17+j,1)*2-1)*cap*(o.jitk??.008),y+(hash(seed+i,b*17+j,2)*2-1)*cap*(o.jitk??.008)]);
      const p=curve(jitter),length=p.slice(1).reduce((v,q,j)=>v+Math.hypot(q[0]-p[j][0],q[1]-p[j][1]),0);
      return {...stroke,p,i,length,width:nib*(stroke.kind==='thin'?.28:stroke.kind==='dot'?1.3:1)};
    });
    const total=prepared.reduce((n,p)=>n+p.length,0);let consumed=0;
    const paths=prepared.map(p=>{
      const u=o.prog?.[p.i]??clamp(((o.u??1)*total-consumed)/p.length,0,1);consumed+=p.length;
      return u<=0?null:{...p,p:u>=1?p.p:p.p.slice(0,Math.max(2,Math.ceil(u*p.p.length)))};
    }).filter(Boolean);
    const line=(p,dx=0,dy=0)=>{ctx.beginPath();p.forEach(([x,y],i)=>i?ctx.lineTo(x+dx,y+dy):ctx.moveTo(x+dx,y+dy));ctx.stroke();};
    const chisel=(p,w,dx=0,dy=0,taper=true)=>{
      const corners=p.map(([x,y],i)=>{const k=taper?(i/(p.length-1)<.04?.92:i/(p.length-1)>.94?.96:1):1;return [x+dx+c*w*k/2,y+dy+s*w*k/2,x+dx-c*w*k/2,y+dy-s*w*k/2];});
      ctx.beginPath();for(let i=0;i<corners.length-1;i++){const a=corners[i],b=corners[i+1];ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.lineTo(b[2],b[3]);ctx.lineTo(a[2],a[3]);ctx.closePath();}ctx.fill();
    };
    ctx.save();ctx.globalAlpha=alpha;ctx.lineJoin='round';ctx.lineCap='round';
    if(halo){ctx.fillStyle=halo;ctx.strokeStyle=halo;for(const p of paths){ctx.lineWidth=p.width*.22+haloK;line(p.p);chisel(p.p,p.width+haloK,0,0,false);}}
    if(echo){ctx.fillStyle=echo;for(const p of paths)chisel(p.p,p.width*.9,cap*(o.echoD?.[0]??14)/300,cap*(o.echoD?.[1]??10)/300,p.kind!=='dot');}
    ctx.fillStyle=ink;ctx.strokeStyle=ink;
    for(const p of paths) {
      if(p.kind==='thin'){ctx.strokeStyle=ink;ctx.lineWidth=p.width;line(p.p);}
      else chisel(p.p,p.width,0,0,p.kind!=='dot');
    }
    for(const p of paths) {
      if((o.streaks??true)&&p.kind==='stroke'&&p.p.length>=8&&p.i%(o.streakEvery??1)===0) {
        ctx.strokeStyle=halo||'#fff';ctx.lineWidth=Math.max(1,cap*.0035);ctx.globalAlpha=alpha*.8;
        const n=2+Math.floor(hash(seed+p.i,3,21)*3);
        for(let k=0;k<n;k++) {
          const offset=(k%2?1:-1)*p.width*(.3+.12*hash(seed+p.i,k,22)),start=Math.floor(p.p.length*(.55+.2*hash(seed+p.i,k,23)));
          line(p.p.slice(start),c*offset,s*offset);
        }
        ctx.globalAlpha=alpha;
      }
    }
    if(o.dashes) {
      ctx.lineCap='butt';
      for(const p of prepared) {
        if(p.li===undefined||!paths.some(q=>q.i===p.i&&q.p.length>=7))continue;
        let points=p.p;const first=points[0],last=points.at(-1);
        if(p.kind!=='stroke'||Math.abs(last[0]-first[0])>Math.abs(last[1]-first[1])*.35||(!('I!'.includes(p.ch)&&L.nLetters<=3)&&hash(seed,p.i,9)>=.6))continue;
        if(last[1]<first[1])points=points.toReversed();
        const offset=('I!'.includes(p.ch)?1:(first[0]+last[0])/2<p.lcx?-1:1)*nib*.72,start=Math.floor(points.length*.06),dash=points.slice(start,Math.floor(points.length*.55));
        const unit=nib*(.7+.6*hash(seed,p.i,14));ctx.setLineDash([unit*.9,nib*.5,unit*.4,nib*.5]);ctx.lineDashOffset=nib*hash(seed,p.i,3);
        if(halo){ctx.strokeStyle=halo;ctx.lineWidth=nib*.3+(o.haloK||.02)*cap;line(dash,offset,0);}
        ctx.strokeStyle=ink;ctx.lineWidth=nib*.3;line(dash,offset,0);
      }
    }
    ctx.restore();
  }
  function draw(ctx,item,state,hash) {
    const {W,H,elapsed,duration,fps,absolute,index,shotIndex,frame,boil,face}=state;
    if(elapsed<0||elapsed>=duration)return;
    const L=layout(item,W,H,index,hash),mode=item.mode??'static';let scale=1,dx=0,dy=0;
    if(mode!=='hold'){dx=(hash(shotIndex,1,40+index)*2-1)*7;dy=(hash(shotIndex,2,40+index)*2-1)*6;}
    if(mode==='slam') {
      const n=Math.floor(elapsed*fps),sc=item.sc??[1.3,.9,1.06,1];scale=sc[Math.min(n,sc.length-1)];
      if(n<5){dx+=(hash(frame,1,index)*2-1)*12;dy+=(hash(frame,2,index)*2-1)*10;}
    }
    if(mode==='slam'&&face&&Math.abs(L.center[0]-face.x)<(L.bbox[2]-L.bbox[0])/2+face.D&&Math.abs(L.center[1]-face.y)<(L.bbox[3]-L.bbox[1])/2+face.D){scale=Math.min(scale,1);L.center[0]=L.bbox[0];}
    if(mode==='slam')while(scale>1&&L.bbox.some((v,i)=>{const a=i%2,size=a?H:W,p=L.center[a]+(v-L.center[a])*scale;return i<2?p<size*.03:p>size*.97;}))scale=Math.max(1,scale-.05);
    ctx.save();ctx.translate(L.center[0]+dx,L.center[1]+dy);ctx.scale(scale,scale);ctx.translate(-L.center[0],-L.center[1]);
    const wdur=item.wdur??Math.min(Math.max(.2,.75*duration),.12+.22*L.letters);let offset=0;
    for(const [i,row] of L.rows.entries()) {
      let prog;
      if(mode==='write'&&item.wkeys)prog=row.strokes.map((stroke,j)=>{
        let start,span;
        if(stroke.li===undefined){start=item.wkeys.at(-1)+(stroke.under===0?0:stroke.under+1)/fps;span=(stroke.under===0?2:1)/fps;}
        else {const n=offset+stroke.li,count=row.strokes.filter(s=>s.li===stroke.li).length,rank=row.strokes.slice(0,j).filter(s=>s.li===stroke.li).length;span=Math.min(2/fps,(item.wkeys[n+1]-item.wkeys[n])/count);start=item.wkeys[n]+rank*span;}
        return clamp((absolute-start)/span,0,1);
      });
      paintLayout(ctx,row,{seed:L.seed+i*5,b:mode==='hold'?0:Math.floor(frame/boil),jitk:.008,nib:item.nib,halo:item.halo_color??'#fff',haloK:item.halo,ink:item.ink,echo:item.echo,prog,dashes:true,streaks:true,streakEvery:(item.nib??.14)>.15?2:1,u:mode==='write'?clamp(elapsed/wdur,0,1):1},hash);
      offset+=row.nLetters;
    }
    ctx.restore();
  }
  return {draw,layout,letterLayout,paintLayout,curve};
})();
