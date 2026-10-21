'use strict';
window.OpenKatanaFaces = (()=>{
  // Face frame: eye midpoint (x,y), eye distance D and roll a. Measured nose/mouth landmarks (YuNet tracks) are kept in
  // eye units of that frame: nose (nu,nv), mouth centre (mu,mv) and mouth width mw; absent when the track has none.
  const LANDMARKS=['nu','nv','mu','mv','mw'];
  const model=(box,eyes,nose,mouth)=>{
    const [x,y,w,h]=box,e=eyes ?? [[x+w*.3,y+h*.42],[x+w*.7,y+h*.42]];
    const f={x:(e[0][0]+e[1][0])/2,y:(e[0][1]+e[1][1])/2,D:Math.hypot(e[1][0]-e[0][0],e[1][1]-e[0][1]),a:Math.atan2(e[1][1]-e[0][1],e[1][0]-e[0][0])};
    const c=Math.cos(f.a),s=Math.sin(f.a),local=([px,py])=>[((px-f.x)*c+(py-f.y)*s)/f.D,(-(px-f.x)*s+(py-f.y)*c)/f.D];
    if(nose && f.D>0)[f.nu,f.nv]=local(nose);
    if(mouth && f.D>0){[f.mu,f.mv]=local([(mouth[0][0]+mouth[1][0])/2,(mouth[0][1]+mouth[1][1])/2]);f.mw=Math.hypot(mouth[1][0]-mouth[0][0],mouth[1][1]-mouth[0][1])/f.D;}
    return f;
  };
  function prepare(rows,clip) {
    const [w,h]=clip.faces_size ?? [clip.w,clip.h],sx=clip.w/w,sy=clip.h/h;
    const scale=([x,y])=>[x*sx,y*sy];
    const raw=rows.map(row=>{
      if(!row?.box)return null;
      const [x,y,w,h]=row.box;
      // Track boxes have a different inferred eye model from manual shot boxes.
      if(!row.eyes)return {x:(x+w*.5)*sx,y:(y+h*.4)*sy,D:w*.42*sx,a:0};
      return model([x*sx,y*sy,w*sx,h*sy],row.eyes.map(scale),row.nose && scale(row.nose),row.mouth && row.mouth.map(scale));
    });
    const valid=raw.map((f,i)=>f?i:-1).filter(i=>i>=0);
    for(let i=0;i<raw.length;i++)if(!raw[i] && valid.length) {
      const nearest=valid.reduce((a,b)=>Math.abs(b-i)<Math.abs(a-i)?b:a);
      raw[i]=raw[nearest];
    }
    return raw.map((value,i)=>{
      if(!value)return null;
      const out={};
      for(const key of ['x','y','D','a',...LANDMARKS]) {
        if(value[key]===undefined)continue;
        const sigma=key==='x'||key==='y'?1.4:2.6;
        let sum=0,total=0;
        for(let j=Math.max(0,i-7);j<=Math.min(raw.length-1,i+7);j++) {
          if(!raw[j] || raw[j][key]===undefined)continue;
          const weight=Math.exp(-((j-i)**2)/(2*sigma*sigma));sum+=raw[j][key]*weight;total+=weight;
        }
        out[key]=sum/total;
      }
      return out;
    });
  }
  function at(shot,track,index,M) {
    if(shot.face===false)return null;
    let f=track?.[index];
    if(shot.face) {const [x0,y0,x1,y1]=shot.face.box;f=model([x0,y0,x1-x0,y1-y0]);}
    if(!f)return null;
    const point=([x,y])=>[M[0]*x+M[2]*y+M[4],M[1]*x+M[3]*y+M[5]];
    const c=Math.cos(f.a)*f.D/2,s=Math.sin(f.a)*f.D/2;
    let e0=point([f.x-c,f.y-s]),e1=point([f.x+c,f.y+s]);
    const flipped=e0[0]>e1[0];
    if(flipped)[e0,e1]=[e1,e0];
    const out={x:(e0[0]+e1[0])/2,y:(e0[1]+e1[1])/2,D:Math.hypot(e1[0]-e0[0],e1[1]-e0[1]),a:Math.atan2(e1[1]-e0[1],e1[0]-e0[0])};
    // Eye-unit landmarks survive a similarity transform. A mirroring matrix flips the sideways axis of the frame and the
    // eye swap above turns it by half a turn, so: across = -1 when swapped; down = -1 when exactly one of the two applies.
    const mirrored=M[0]*M[3]-M[1]*M[2]<0,across=flipped?-1:1,down=mirrored!==flipped?-1:1;
    for(const key of LANDMARKS)if(f[key]!==undefined)out[key]=key==='mw'?f[key]:f[key]*(key[1]==='u'?across:down);
    return out;
  }
  return {prepare,at};
})();
