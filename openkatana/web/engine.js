/* Independent OpenKatana renderer. Contract support is intentionally explicit. */
'use strict';
window.OpenKatana = (() => {
  let edit, canvas, ctx, filterBuffer, plateBuffer, maskBuffer, subjectBuffer, outlineBuffer, bufA, bufB;
  const images = new Map();
  const faceTracks = new Map();
  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
  function wrap(index, count, mode) {
    if (mode === 'loop') return ((index % count) + count) % count;
    if (mode === 'pingpong' && count > 1) {
      const period = 2 * (count - 1), p = ((index % period) + period) % period;
      return p < count ? p : period - p;
    }
    return clamp(index, 0, count - 1);
  }
  function sample(shot, clip, frame) {
    const fps = edit.canvas.fps;
    const elapsed = (frame + .5) / fps - shot.f0 / fps;
    const duration = shot.f1 / fps - shot.f0 / fps;
    const startSpeed = shot.speed ?? 1, endSpeed = shot.speed1 ?? startSpeed;
    const speed = startSpeed + (endSpeed - startSpeed) * elapsed / duration;
    // Frame in-points in the reference sit 0.1 microseconds inside the frame.
    const source = shot.srcf != null ? shot.srcf / clip.fps + 1e-7 : (shot.src ?? 0);
    const position = (source + startSpeed * elapsed + (endSpeed - startSpeed) * elapsed * elapsed / (2 * duration)) * clip.fps;
    // Source fx stutter (audit F-NAT-005): loop n source frames from the in-point, `step` frames apart, one per output
    // frame, whatever the speed (observed: srcf 4, n 3, step 2 -> 4, 6, 8, 4, ...).
    const stutter = options(shot.fx && 'stutter' in shot.fx ? shot.fx.stutter : edit.post?.stutter);
    if (stutter) {
      const n = stutter.n ?? 3, k = frame-shot.f0;
      const held = wrap(Math.floor(source*clip.fps)+(((k%n)+n)%n)*(stutter.step ?? 1), clip.n, shot.loop);
      return {index:held, i0:held, i1:held, weight:0, speed};
    }
    const index = wrap(Math.floor(position), clip.n, shot.loop);
    const blending = Math.abs(speed) > 0 && Math.abs(speed) < 1 && shot.blend !== false && (Math.abs(speed) >= .3 || shot.blend === true);
    if (!blending) return {index, i0:index, i1:index, weight:0, speed};
    const x = position - .5;
    const low = Math.floor(x);
    if (speed > 0 && low < Math.floor(source * clip.fps)) return {index,i0:index,i1:index,weight:0,speed};
    return {index, i0:wrap(low, clip.n, shot.loop), i1:wrap(low + 1, clip.n, shot.loop), weight:x-low, speed};
  }
  function ease(p, kind) {
    p = clamp(p, 0, 1);
    if (kind === 'in2') return p*p;
    if (kind === 'in3') return p*p*p;
    if (kind === 'out2') return 1-(1-p)**2;
    if (kind === 'out3') return 1-(1-p)**3;
    if (kind === 'inout') return p*p*(3-2*p);
    if (kind === 'outback') {const c1=1.70158,q=p-1;return 1+(c1+1)*q*q*q+c1*q*q;}
    if (kind === 'inout3') return p<.5?4*p*p*p:1-Math.pow(-2*p+2,3)/2;
    return p;
  }
  // Animated numbers {from,to,ease,over,at} inside looks: progress over `over` x shot duration, starting `at` s in.
  function animate(value, elapsed, duration) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return value;
    if ('from' in value && 'to' in value) {
      const span = (value.over ?? 1)*duration;
      return value.from+(value.to-value.from)*ease(span > 0 ? (elapsed-(value.at ?? 0))/span : 1, value.ease ?? 'lin');
    }
    return Object.fromEntries(Object.entries(value).map(([k,v]) => [k, animate(v, elapsed, duration)]));
  }
  const options = value => value === true ? {} : value;
  // Numeric compatibility rule inferred from documented helper I/O and observed
  // integer multiplication calls; independently checked against 11,000 tuples.
  function noise(a,b,c) {
    const keys=[(a|0)^0x9e3779b9,(b|0)+1663821227,(c|0)+2135587861];
    const factors=[2246822507,3266489909,668265263];
    let value=keys.reduce((v,key,i)=>v^Math.imul(key,factors[i]),0);
    for(const [shift,factor] of [[15,739982445],[12,695872825]]) value=Math.imul(value^(value>>>shift),factor);
    return ((value^(value>>>15))>>>0)/4294967296;
  }
  const jitter=(item,frame)=>[1,2].map(axis=>(noise(Math.floor(frame/(edit.canvas.boil ?? 2)),axis,item.seed ?? 3)*2-1)*(item.boil ?? 0));
  // Three sine bands measured through the exposed noise helper. Absolute time
  // makes handheld drift continuous across cuts and independent of frame order.
  function drift(seed,time) {
    let sum=0;
    for(let i=0;i<3;i++)sum+=Math.sin(time*(.6+noise(seed,i,1)*1.1)*(1+i*.9)*Math.PI*2+noise(seed,i,2)*Math.PI*2)/(i+1);
    return sum/1.83;
  }
  function buffer(W,H) {const c=document.createElement('canvas');c.width=W;c.height=H;return c;}
  const plates = new Map();
  function plateFor(clip) {const key=clip.w+'x'+clip.h;if(!plates.has(key))plates.set(key,buffer(clip.w,clip.h));return plates.get(key);}
  function subjectEffect(type,params,W,H,mask,matrix,clip) {
    if(type==='cutout') {
      const c=subjectBuffer.getContext('2d');c.globalCompositeOperation='copy';c.drawImage(plateBuffer,0,0);
      c.globalCompositeOperation='destination-in';c.drawImage(maskBuffer,0,0);
      ctx.drawImage(subjectBuffer,0,0);return;
    }
    const p=options(params),c=outlineBuffer.getContext('2d'),r=p.r ?? 14;
    c.resetTransform();c.clearRect(0,0,outlineBuffer.width,outlineBuffer.height);c.globalCompositeOperation='source-over';
    for(let i=0;i<12;i++) {
      const a=i*Math.PI*2/12;c.save();
      c.setTransform(matrix[0]*.5,matrix[1]*.5,matrix[2]*.5,matrix[3]*.5,(matrix[4]+Math.cos(a)*r)*.5,(matrix[5]+Math.sin(a)*r)*.5);
      c.drawImage(mask,0,0,clip.w,clip.h);c.restore();
    }
    c.globalCompositeOperation='source-in';c.fillStyle=p.color ?? '#e2b0f0';c.fillRect(0,0,outlineBuffer.width,outlineBuffer.height);
    ctx.save();ctx.globalAlpha=p.alpha ?? .95;ctx.filter=`blur(${p.blur ?? 3}px)`;
    ctx.drawImage(outlineBuffer,p.dx ?? 16,p.dy ?? 6,W,H);ctx.restore();
  }
  function shotEffects(shot) {
    const fx = {...edit.post, ...shot.fx};
    for (const side of ['in', 'out']) {
      const entries = shot[side] == null ? [] : (Array.isArray(shot[side]) ? shot[side] : [shot[side]]);
      for (let entry of entries) {
        if (typeof entry === 'string') entry = {type:entry};
        const {type, ...params} = entry;
        const mapped=type==='blur'?(side==='in'?'blurIn':'blurOut'):type==='flashlight'?(side==='in'?'fin':'fout'):type;
        fx[mapped] = {...(type==='blur'&&side==='out'?{max:24}:{}),...params, side};
      }
    }
    return fx;
  }
  function cameraMatrix(cam, fx, clip, W, H, elapsed, duration, frame, speed, trackedFace) {
    const factors = {cover:Math.max(W/clip.w,H/clip.h),contain:Math.min(W/clip.w,H/clip.h),width:W/clip.w,height:H/clip.h};
    let scale = factors[cam.fit ?? 'cover'] * (cam.z ?? 1), angle = cam.rot ?? 0;
    const locked=(cam.type==='facelock'||cam.lock===true)&&trackedFace;
    if(locked) {
      const zoom=(cam.z0 ?? 1)+((cam.z1 ?? 1.04)-(cam.z0 ?? 1))*ease(elapsed/duration,'out3');
      scale=(cam.ld ?? .12)*W/trackedFace.D*zoom*(1+(cam.kick ?? .035)*Math.exp(-elapsed*(cam.kick_rate ?? 14)));
      angle=-trackedFace.a*(cam.lockRot ?? 1);
    }
    let dx = 0, dy = 0;
    const get = name => options(cam[name] ?? fx[name]);
    const zoom = get('zoom');
    if (zoom) scale *= (zoom.z0 ?? 1) + ((zoom.z1 ?? 1.08)-(zoom.z0 ?? 1))*ease(elapsed/duration,zoom.ease ?? 'out3');
    const push = get('push');
    if (push) scale *= 1 + (push.v ?? push.rate ?? .1)*elapsed;
    const punch = get('punch');
    if (punch) {
      let amount = 0;
      for (const hit of punch.hits ?? [punch.at ?? 0]) {
        const age = elapsed-hit, d = punch.d ?? .25;
        if (age >= 0 && age < d) amount = Math.max(amount,(punch.v ?? punch.amt ?? .07)*(1-age/d)**(punch.curve ?? 2));
      }
      scale *= 1+amount;
    }
    const ladder = get('ladder');
    if (ladder) {
      const steps = ladder.steps ?? ladder.v ?? [1,1.12,1.24,1.36];
      scale *= steps[Math.min(steps.length-1,Math.floor(elapsed/duration*steps.length))];
    }
    const pan = get('pan'), tilt = get('tilt'), roll = get('roll');
    if (pan) {dx += (pan.dx ?? pan.v ?? 0)*W*elapsed; dy += (pan.dy ?? 0)*H*elapsed;}
    if (tilt) dy += (tilt.v ?? 0)*H*elapsed;
    if (roll) angle += (roll.v ?? 0) + (roll.rate ?? 0)*elapsed
      + (roll.to != null ? ((roll.from ?? 0) + (roll.to-(roll.from ?? 0))*ease(elapsed/(roll.d ?? duration), roll.ease ?? 'inout3')) : 0);
    // measured move (audit F-NAT-015): linear over absolute frames f0..f1-1; a constant cover margin for the end state
    // (pan + roll) keeps the picture covered along the way, then the zoom ramps on top
    const lm = cam.local_measured;
    if (lm) {
      const u = clamp((frame-lm.f0)/Math.max(1,lm.f1-1-lm.f0),0,1), px = (lm.pan_x ?? 0)*W, py = (lm.pan_y ?? 0)*H, roll = (lm.roll_deg ?? 0)*Math.PI/180;
      const c = Math.cos(roll), s = Math.sin(roll);
      const need = Math.max(1, ...[[-1,-1],[1,-1],[-1,1],[1,1]].map(([sx,sy]) => {
        const x = sx*W/2-px, y = sy*H/2-py; return Math.max(Math.abs(c*x+s*y)/(W/2), Math.abs(-s*x+c*y)/(H/2)); }));
      scale *= need*(1+(lm.zoom ?? 0)*u); angle += roll*u; dx += px*u; dy += py*u;
    }
    // screen-point zooms (audit F-STU-003): crash = fast zoom toward a point landing at `at`; pulse = in-and-out on hits
    const pointZooms = [];
    const crash = get('crash');
    if (crash) {
      const d = crash.d ?? .4, at = crash.at ?? d, u = (elapsed-(at-d))/d;
      pointZooms.push([1+((crash.v ?? 4)-1)*ease(u, crash.ease ?? 'inout3'), crash.center ?? [.5,.5]]);
    }
    const pulse = get('pulse');
    if (pulse) {
      let k = 1;
      for (const hit of pulse.hits ?? [pulse.at ?? 0]) {
        const d = pulse.d ?? .25, age = elapsed-hit;
        if (age < 0 || age >= d) continue;
        const u = age/(d/2), amount = u < 1 ? ease(u,'out3') : 1-ease(u-1,'in3');
        k = Math.max(k, 1+(pulse.v ?? .3)*amount);
      }
      pointZooms.push([k, pulse.center ?? [.5,.5]]);
    }
    const handheld=get('handheld');
    if(handheld) {
      const seed=handheld.seed ?? 7,t=(frame+.5)/edit.canvas.fps*(handheld.hz ?? .7),amp=handheld.amp ?? handheld.v ?? 6;
      dx+=drift(seed,t)*amp;dy+=drift(seed+1,t)*amp*.8;
      angle+=drift(seed+2,t*.8)*(handheld.rot ?? .004);
    }
    const shake=get('shake');
    if(shake) {
      const d=shake.d ?? (speed===0?.125:.25),amps=shake.amp ?? [16,12];
      let strength=0;
      for(const hit of shake.hits ?? [shake.at ?? 0]) {
        const age=elapsed-hit;
        if(age>=0 && age<d)strength=Math.max(strength,1-age/d);
      }
      const step=Math.floor(frame/(shake.every ?? edit.canvas.boil ?? 2));
      dx+=(noise(step,1,77)*2-1)*amps[0]*strength;
      dy+=(noise(step,2,77)*2-1)*amps[1]*strength;
    }
    let anchorX=(cam.ax ?? .5)*clip.w,anchorY=(cam.ay ?? .5)*clip.h;
    if(cam.crop!=null) {anchorX=(Array.isArray(cam.crop)?cam.crop[0]:.5)*clip.w;anchorY=(Array.isArray(cam.crop)?cam.crop[1]:cam.crop)*clip.h;}
    if(locked){anchorX=trackedFace.x;anchorY=trackedFace.y;}
    const targetX=(locked?(cam.lx ?? .5):(cam.sx ?? .5))*W+dx,targetY=(locked?(cam.ly ?? .4):(cam.sy ?? .5))*H+dy;
    if(locked?cam.cover!==false:(cam.cover || cam.crop!=null)) {
      const c=Math.cos(angle),s=Math.sin(angle);
      const needed=Math.max((Math.abs(c)*W+Math.abs(s)*H)/clip.w,(Math.abs(s)*W+Math.abs(c)*H)/clip.h);
      if(needed>scale*1.0001) scale=needed*1.003;
      const corners=[[0,0],[W,0],[0,H],[W,H]].map(([x,y])=>[(c*(x-targetX)+s*(y-targetY))/scale,(-s*(x-targetX)+c*(y-targetY))/scale]);
      const xs=corners.map(p=>p[0]),ys=corners.map(p=>p[1]);
      // The tiny coverage tolerance can invert the bounds. Match the observed
      // first violated bound instead of applying both constraints in sequence.
      const fitAnchor=(v,lo,hi)=>v<lo?lo:v>hi?hi:v;
      anchorX=fitAnchor(anchorX,-Math.min(...xs),clip.w-Math.max(...xs));
      anchorY=fitAnchor(anchorY,-Math.min(...ys),clip.h-Math.max(...ys));
    }
    const mx = cam.mir ? -1 : 1;
    let aa = Math.cos(angle)*scale*mx, bb = Math.sin(angle)*scale;
    let cc = -Math.sin(angle)*scale*mx, dd = Math.cos(angle)*scale;
    let ee = (cam.mir ? W-targetX : targetX)-aa*anchorX-cc*anchorY, ff = targetY-bb*anchorX-dd*anchorY;
    for (const [k,[px,py]] of pointZooms) {   // scale about a screen point
      const X = px*W, Y = py*H; aa*=k; bb*=k; cc*=k; dd*=k; ee = X+k*(ee-X); ff = Y+k*(ff-Y);
    }
    return [aa,bb,cc,dd,ee,ff];
  }
  function postEffects(entries, elapsed, duration, W, H) {
    const wash = (color, alpha, op = 'source-over', colorAlpha = false) => {
      ctx.save(); ctx.fillStyle = color; alpha = clamp(alpha,0,1);
      if (colorAlpha) {
        const style = ctx.fillStyle;   // "#rrggbb", or "rgba(r, g, b, a)" for a translucent colour whose alpha is replaced
        const rgb = style[0] === '#' ? [1,3,5].map(i => parseInt(style.slice(i,i+2),16)) : style.slice(style.indexOf('(')+1).split(',').slice(0,3).map(Number);
        ctx.fillStyle = `rgba(${rgb.join(',')},${alpha})`;
      } else ctx.globalAlpha = alpha;
      ctx.globalCompositeOperation = op; ctx.fillRect(0,0,W,H); ctx.restore();
    };
    for (const {type:name, params} of entries) {
      const p = options(params);
      if (!p) continue;
      const d = p.d ?? ({white:.067,flash:.1,dip:.15}[name] ?? duration);
      const at = p.at ?? (p.side === 'out' ? duration-d : 0), age = elapsed-at;
      if (name === 'letterbox') {
        ctx.save(); ctx.fillStyle = p.color ?? '#000';
        ctx.fillRect(0,0,W,(p.top ?? p.v ?? .1)*H);
        const bottom = (p.bottom ?? p.v ?? .1)*H;
        ctx.fillRect(0,H-bottom,W,bottom); ctx.restore();
      } else if (name === 'tint') {
        wash(p.color ?? '#ff78dc', (p.v ?? p.amt ?? .3)*(p.d == null ? 1 : clamp(1-elapsed/p.d,0,1)),p.op ?? 'screen',true);
      } else if (age >= 0 && age < d) {
        const progress = age/d;
        if (name === 'invert') {
          const buffer = filterBuffer.getContext('2d');
          buffer.globalCompositeOperation = 'copy'; buffer.drawImage(canvas,0,0);
          ctx.save(); ctx.globalAlpha = p.amt ?? 1; ctx.filter = 'invert(1)';
          ctx.drawImage(filterBuffer,0,0); ctx.restore();
        }
        if (name === 'white') wash(p.color ?? '#fff',1);
        if (name === 'flash' || name === 'dip') wash(p.color ?? (name === 'dip' ? '#000' : '#fff'),(p.amt ?? 1)*(p.side === 'out' ? progress : 1-progress),'source-over',name === 'dip');
        if (name === 'strobe' && Math.floor(elapsed*edit.canvas.fps/(p.every ?? 2))%2 === 0) wash(p.color ?? '#fff',p.amt ?? 1);
      }
    }
  }
  function composition(shot,fx) {
    const orders = {...OpenKatanaEffects.orders,...OpenKatanaLocal.orders,...OpenKatanaDecor.orders,invert:16,tint:51,white:60,flash:61,dip:62,strobe:63,letterbox:70};
    const decorPhase = type => OpenKatanaDecor.orders[type] != null ? (OpenKatanaDecor.phase[type] ?? 'over') : undefined;
    const items = Object.entries(orders).filter(([type])=>fx[type]).map(([type,order])=>({type,order,phase:OpenKatanaEffects.phase[type]??OpenKatanaLocal.phase[type]??decorPhase(type)??'post',params:fx[type]}));
    const backCut=items.some(i=>i.phase==='back'&&['big','burst'].includes(i.type)&&i.params.cut!==false)||(shot.layers??[]).some(i=>['big','burst'].includes(i.type)&&i.cut!==false);
    for(const [type,order] of [['outline',10],['cutout',20]]) {
      if((backCut&&fx[type]!==false)||fx[type] || (type==='cutout' && fx.outline && fx.cutout!==false)) items.push({type,order,phase:'subject',params:fx[type] ?? true});
    }
    for (const [index, layer] of (shot.layers ?? []).entries()) {
      const hook = layer.type === 'hook' ? OpenKatanaHooks.defaults(layer.name) : null;
      const {type, phase=(hook?hook.phase:['text','graffiti'].includes(layer.type)?'over':(['cutout','outline'].includes(layer.type)?'subject':(OpenKatanaEffects.phase[layer.type]??OpenKatanaLocal.phase[layer.type]??decorPhase(layer.type)??'post'))), order=(hook?.order ?? OpenKatanaDecor.orders[layer.type] ?? 100+index), ...params} = layer;
      items.push({type,phase,order,params});
    }
    for(const item of items.slice())if(item.type==='burst')items.push({...item,type:'burst-letters',phase:'over',order:55});
    if((edit.stickers ?? []).length && fx.stickers!==false)items.push({type:'stickers',phase:'over',order:50});
    items.push({type:'global-text',phase:'over',order:60});
    if(fx.graffiti)items.push({type:'graffiti',phase:'over',order:61,params:{mode:'write',...fx.graffiti}});
    const phases = ['back','subject','over','post','final'];
    return items.sort((a,b)=>phases.indexOf(a.phase)-phases.indexOf(b.phase) || a.order-b.order);
  }
  async function image(clip, index) {
    const name = (clip.pattern ?? '%05d.png').replace('%05d', String(index).padStart(5, '0'));
    const url = '/project/' + clip.frames_dir.split('/').map(encodeURIComponent).join('/') + '/' + name;
    if (!images.has(url)) {
      let response;
      for (let attempt = 1; ; attempt++) {   // retry only transport failures of the loopback server, never HTTP errors
        try { response = await fetch(url); break; }
        catch (e) { if (attempt >= 3) throw Error(`Could not load source frame: ${url} (${e.message} after ${attempt} attempts)`); await new Promise(r => setTimeout(r, 150 * attempt)); }
      }
      if(!response.ok)throw Error(`Could not load source frame: ${url} (${response.status})`);
      // Video plates are display-referred pixel values. Never colour-manage them: PNG gAMA/cHRM/cICP chunks
      // (written by FFmpeg for BT.709 sources) would otherwise make Chrome convert and darken real footage.
      images.set(url,await createImageBitmap(await response.blob(),{colorSpaceConversion:'none'}));
      if (images.size > 64) {const first=images.keys().next().value;images.get(first).close();images.delete(first);}
    }
    const result=images.get(url);images.delete(url);images.set(url,result);
    return result;
  }
  // State handed to project hooks: canvas size, absolute time t (frame centre), frame f, fps, lt (s into the shot), dur.
  const hookInfo = (frame, elapsed, duration, face) => ({W:canvas.width, H:canvas.height, t:(frame+.5)/edit.canvas.fps, f:frame, fps:edit.canvas.fps, lt:elapsed, dur:duration, face, noise});
  function seededRandom(seed) {   // project hooks see a deterministic Math.random (re-seeded every frame)
    let a = seed >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  async function loadHooks(hooks) {
    OpenKatanaHooks.reset();
    let failure = null; const onerr = e => { failure = e.error || Error(String(e.message)); };
    window.addEventListener('error', onerr);
    try {
      await new Promise((ok, bad) => {
        const el = document.createElement('script');
        el.src = '/project/' + hooks.src.split('/').map(encodeURIComponent).join('/');
        el.onload = ok; el.onerror = () => bad(Error(`Hook script ${hooks.src} could not be loaded`));
        document.head.appendChild(el);
      });
    } finally { window.removeEventListener('error', onerr); }
    if (failure) throw Error(`Hook script ${hooks.src} failed: ${failure.message}`);
    const miss = OpenKatanaHooks.missing(hooks);
    if (miss.length) throw Error(`Hook script ${hooks.src} did not register ${miss.join(', ')}`);
  }
  async function boot(value) {
    faceTracks.clear();
    edit = value; for(const im of images.values())im.close();images.clear(); canvas = document.getElementById('output');
    canvas.width = edit.canvas.w; canvas.height = edit.canvas.h;
    filterBuffer = document.createElement('canvas'); filterBuffer.width = canvas.width; filterBuffer.height = canvas.height;
    [plateBuffer,maskBuffer,subjectBuffer,outlineBuffer]=Array.from({length:4},()=>buffer(canvas.width,canvas.height));
    outlineBuffer=buffer(canvas.width/2,canvas.height/2);
    [bufA,bufB]=[0,1].map(()=>{const c=buffer(canvas.width,canvas.height);c.getContext('2d',{willReadFrequently:true});return c;});
    ctx = canvas.getContext('2d');
    for(const [id,clip] of Object.entries(edit.clips))if(clip.faces) {
      const response=await fetch('/project/'+clip.faces.split('/').map(encodeURIComponent).join('/'));
      if(!response.ok)throw Error('Could not load face track');
      faceTracks.set(id,OpenKatanaFaces.prepare(await response.json(),clip));
    }
    if (edit.hooks) await loadHooks(edit.hooks);
    if (edit.stickers || edit.assets) await OpenKatanaStickers.boot(edit, image, faceAt);
    for (const f of edit.fonts ?? []) {
      const url = '/project/' + f.url.split('/').map(encodeURIComponent).join('/');
      const face = new FontFace(f.family, `url(${JSON.stringify(url)})`,{weight:String(f.weight ?? 'normal'),style:f.style ?? 'normal'});
      try { await face.load(); } catch (e) { throw Error(`Font "${f.family}" (${f.url}) could not be loaded: ${e.message}`); }
      document.fonts.add(face);
    }
  }
  // Screen-space face at a frame (sticker planning keeps clear of it).
  function faceAt(frame) {
    const shot = edit.shots.find(s => s.f0 <= frame && frame < s.f1);
    if (!shot || shot.special) return null;
    const clip = edit.clips[shot.clip], track = faceTracks.get(shot.clip); if (!track) return null;
    const pick = sample(shot, clip, frame), W = canvas.width, H = canvas.height, fps = edit.canvas.fps;
    const matrix = cameraMatrix({...edit.cam,...clip.cam,...shot.cam}, shotEffects(shot), clip, W, H, (frame+.5)/fps-shot.f0/fps, (shot.f1-shot.f0)/fps, frame, shot.speed ?? 1, track[pick.index]);
    return OpenKatanaFaces.at(shot, track, pick.index, matrix);
  }
  // Global text belongs to the timeline, not a shot: on transition frames it is drawn once over the composite.
  function globalText(shot, fx, frame, face, W, H, special=false) {
    const graffiti=(text,t,d,index)=>OpenKatanaGraffiti.draw(ctx,text,{W,H,elapsed:t,duration:d,fps:edit.canvas.fps,absolute:(frame+.5)/edit.canvas.fps,index,shotIndex:edit.shots.indexOf(shot),frame,boil:edit.canvas.boil ?? 2,face},noise);
    for (const [index,text] of (edit.text ?? []).entries()) {
      if(fx.text===false)continue;
      if (frame < text.f0 || frame >= text.f1) continue;
      if (special && text.on_specials === false) continue;   // on_specials: false hides an event on special frames
      if(text.type==='hook') {
        OpenKatanaHooks.drawText(text.name,ctx,{...(text.params ?? {}),...(text.text != null ? {text:text.text} : {}),t0:text.f0/edit.canvas.fps,t1:text.f1/edit.canvas.fps,f0:text.f0,f1:text.f1},
          hookInfo(frame,(frame+.5)/edit.canvas.fps-shot.f0/edit.canvas.fps,(shot.f1-shot.f0)/edit.canvas.fps,face),index);
        continue;
      }
      if(text.type==='graffiti') {graffiti(text,(frame+.5)/edit.canvas.fps-text.f0/edit.canvas.fps,(text.f1-text.f0)/edit.canvas.fps,index);continue;}
      OpenKatanaText(ctx,text,(frame+.5)/edit.canvas.fps-text.f0/edit.canvas.fps,text.f1/edit.canvas.fps-text.f0/edit.canvas.fps,edit.canvas.fps,W,H,jitter(text,frame),face);
    }
  }
  // Whole-frame inserts (audit F-NAT-004). Flat fills and collage panels follow observed reference output (a panel is
  // the full-frame camera image clipped to its rect); splats, sparkles and brackets are OpenKatana's own designs.
  const SPECIAL_ALLOW = {flash:['text','border'], white:['stickers','text','dust','border'], black:['border'], color:['text','stickers'], collage:['stickers','text','dust','border']};
  function blob(cx, cy, r, seed, lobes) {
    ctx.beginPath();
    for (let i = 0; i <= 48; i++) {
      const a = i/48*Math.PI*2, wob = 1+.28*Math.sin(a*lobes+seed)+.12*Math.sin(a*(lobes*2+1)+seed*1.7);
      if (i) ctx.lineTo(cx+Math.cos(a)*r*wob, cy+Math.sin(a)*r*wob); else ctx.moveTo(cx+Math.cos(a)*r*wob, cy+Math.sin(a)*r*wob);
    }
    ctx.closePath(); ctx.fill();
  }
  function splats(sp, W, H, seed, step) {
    const m = Math.min(W, H); ctx.save(); ctx.fillStyle = sp.splat;
    for (let i = 0; i < 5; i++) {
      const cx = noise(seed,i,1)*W, cy = noise(seed,i,2)*H, r = m*(.05+.08*noise(seed,i,3));
      blob(cx, cy, r, noise(seed,i,4)*6+step*.4, 3+Math.floor(noise(seed,i,5)*4));
      for (let k = 0; k < 4; k++) {   // droplets
        const a = noise(seed,i*7+k,6)*Math.PI*2, d = r*(1.5+noise(seed,i*7+k,7));
        blob(cx+Math.cos(a)*d, cy+Math.sin(a)*d, r*(.1+.15*noise(seed,i*7+k,8)), k+step, 3);
      }
    }
    if (sp.bigsplat) blob(W*(.35+.3*noise(seed,9,1)), H*(.35+.3*noise(seed,9,2)), m*.36, step*.3, 5);
    ctx.restore();
  }
  function sparkles(W, H, seed, step) {
    const m = Math.min(W, H); ctx.save(); ctx.fillStyle = '#ffffff';
    for (let i = 0; i < 7; i++) {
      const cx = noise(seed+step,i,1)*W, cy = noise(seed+step,i,2)*H, r = m*(.02+.035*noise(seed+step,i,3)), t = r*.18;
      ctx.beginPath(); ctx.moveTo(cx,cy-r); ctx.lineTo(cx+t,cy-t); ctx.lineTo(cx+r,cy); ctx.lineTo(cx+t,cy+t);
      ctx.lineTo(cx,cy+r); ctx.lineTo(cx-t,cy+t); ctx.lineTo(cx-r,cy); ctx.lineTo(cx-t,cy-t); ctx.closePath(); ctx.fill();
    }
    ctx.restore();
  }
  async function renderSpecial(sp, timing, frame, inTransition, owner) {
    const W = canvas.width, H = canvas.height, fps = edit.canvas.fps, boil = edit.canvas.boil ?? 2;
    const elapsed = (frame+.5)/fps-timing.f0/fps, duration = (timing.f1-timing.f0)/fps, step = Math.floor(frame/boil);
    ctx.resetTransform(); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none';
    if (sp.type === 'collage') {
      ctx.fillStyle = sp.bg ?? '#ffffff'; ctx.fillRect(0,0,W,H);
      for (const panel of sp.panels) {
        const clip = edit.clips[panel.clip], pick = sample({...panel, f0:timing.f0, f1:timing.f1}, clip, frame);
        const matrix = cameraMatrix({...edit.cam,...clip.cam,...panel.cam}, {}, clip, W, H, elapsed, duration, frame, panel.speed ?? 1, null);
        const a = await image(clip, pick.i0), b = pick.weight ? await image(clip, pick.i1) : null, [x,y,w,h] = panel.rect;
        ctx.save(); ctx.beginPath(); ctx.rect(x*W, y*H, w*W, h*H); ctx.clip(); ctx.setTransform(...matrix);
        ctx.drawImage(a,0,0,clip.w,clip.h); if (b) {ctx.globalAlpha = pick.weight; ctx.drawImage(b,0,0,clip.w,clip.h);}
        ctx.restore();
      }
      if (sp.look) { const lk = animate(sp.look, elapsed, duration);
        if (lk.type === 'studio') OpenKatanaStudio.apply(ctx, lk, {W, H, frame, elapsed, duration, fps, hash:noise, mask:null}); else OpenKatanaEffects.look(ctx, lk, frame, noise); }
      ctx.save(); ctx.strokeStyle = '#0b0b0b'; ctx.lineWidth = Math.max(2, W/240); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      if (sp.brackets !== false) for (const {rect:[x,y,w,h]} of sp.panels) {   // corner brackets
        const L = Math.min(w*W, h*H)*.12, x0 = x*W, y0 = y*H, x1 = (x+w)*W, y1 = (y+h)*H;
        for (const [cx,cy,sx,sy] of [[x0,y0,1,1],[x1,y0,-1,1],[x0,y1,1,-1],[x1,y1,-1,-1]]) {ctx.beginPath(); ctx.moveTo(cx+sx*L,cy); ctx.lineTo(cx,cy); ctx.lineTo(cx,cy+sy*L); ctx.stroke();}
      }
      for (const line of sp.lines ?? []) {ctx.beginPath(); line.forEach(([px,py],i) => {if (i) ctx.lineTo(px*W,py*H); else ctx.moveTo(px*W,py*H);}); ctx.stroke();}
      ctx.restore();
    } else {
      ctx.fillStyle = sp.color; ctx.fillRect(0,0,W,H);
      if (sp.splat) splats(sp, W, H, timing.f0+17, step);
      if (sp.type === 'black' && sp.sparkle) sparkles(W, H, timing.f0+29, step);
    }
    const allow = sp.allow ?? SPECIAL_ALLOW[sp.type], fx = owner ? shotEffects(owner) : {...edit.post};
    if (allow.includes('dust') && options(fx.dust)) OpenKatanaEffects.draw(ctx,'dust',fx.dust,{W,H,elapsed,duration,frame,boil,hash:noise,face:null,maskBuffer:null});
    if (allow.includes('stickers') && fx.stickers !== false) OpenKatanaStickers.draw(ctx, frame, fps, W, H);
    if (allow.includes('border') && options(fx.border)) OpenKatanaDecor.draw(ctx, 'border', fx.border, {W, H, elapsed, duration, frame, face:null, fps});
    if (!inTransition && allow.includes('text') && owner) globalText(owner, fx, frame, null, W, H, true);
    return {sample:{index:-1, i0:-1, i1:-1, weight:0, speed:0, special:sp.type}, face:null, fx};
  }
  const screenFace = f => f ? {x:Math.round(f.x*10)/10, y:Math.round(f.y*10)/10, D:Math.round(f.D*10)/10,   // for render QA
    ...Object.fromEntries(['a','nu','nv','mu','mv','mw'].filter(k => f[k] !== undefined).map(k => [k, Math.round(f[k]*1000)/1000]))} : null;
  function transitionAt(frame) {
    for (let i = 1; i < edit.shots.length; i++) {
      const spec = edit.shots[i].transition; if (!spec) continue;
      const [w0, w1] = OpenKatanaTransitions.frameWindow(spec, edit.shots[i].f0, edit.canvas.fps);
      if (w0 <= frame && frame < w1) return {i, spec, w0, w1};
    }
    return null;
  }
  async function render(frame) {
    if (!Number.isInteger(frame) || frame < 0 || frame >= edit.canvas.frames) throw Error('Frame out of range');
    if (edit.hooks) Math.random = seededRandom(frame*2654435761 + 97);
    const insert = (edit.specials ?? []).find(s => s.f0 <= frame && frame < s.f1);
    if (insert) {   // top-level specials override whatever shot is beneath them
      const r = await renderSpecial(insert, insert, frame, false, edit.shots.find(s => s.f0 <= frame && frame < s.f1));
      return {png:canvas.toDataURL('image/png').split(',')[1], sample:r.sample};
    }
    const t = edit.shots.some(s => s.transition) ? transitionAt(frame) : null;
    if (!t) {
      const r = await renderShot(edit.shots.find(s => s.f0 <= frame && frame < s.f1), frame, false);
      return {png:canvas.toDataURL('image/png').split(',')[1], sample:r.sample, face:screenFace(r.face)};
    }
    // A plays past its out-point and B pre-rolls before its in-point; both run their full pipelines.
    const shotA = edit.shots[t.i - 1], shotB = edit.shots[t.i], W = canvas.width, H = canvas.height, cut = shotB.f0;
    const ra = await renderShot(shotA, frame, true); bufA.getContext('2d').drawImage(canvas, 0, 0);
    const rb = await renderShot(shotB, frame, true); bufB.getContext('2d').drawImage(canvas, 0, 0);
    const n = t.w1 - t.w0, p = (frame - t.w0 + .5) / n;
    OpenKatanaTransitions.draw(ctx, t.spec, bufA, bufB, p, {W, H, fps:edit.canvas.fps, frame, cut, w0:t.w0, w1:t.w1, n, split:(cut - t.w0) / n, noise});
    const owner = frame < cut ? [shotA, ra] : [shotB, rb];
    globalText(owner[0], owner[1].fx, frame, owner[1].face, W, H);
    return {png:canvas.toDataURL('image/png').split(',')[1], sample:owner[1].sample, transition:{type:t.spec.type, p}, face:screenFace(owner[1].face)};
  }
  async function renderShot(shot, frame, inTransition) {
    if (shot.special) return renderSpecial(shot.special, shot, frame, inTransition, shot);
    const clip = edit.clips[shot.clip], pick = sample(shot, clip, frame);
    const a = await image(clip, pick.i0), b = pick.weight ? await image(clip, pick.i1) : null;
    const W = canvas.width, H = canvas.height, cam = {...edit.cam,...clip.cam,...shot.cam}, fx = shotEffects(shot);
    const elapsed = (frame+.5)/edit.canvas.fps-shot.f0/edit.canvas.fps;
    const duration = shot.f1/edit.canvas.fps-shot.f0/edit.canvas.fps;
    ctx.resetTransform(); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = shot.bg ?? edit.canvas.bg ?? '#ffffff'; ctx.fillRect(0, 0, W, H);
    const matrix=cameraMatrix(cam,fx,clip,W,H,elapsed,duration,frame,shot.speed ?? 1,faceTracks.get(shot.clip)?.[pick.index]);
    const face=OpenKatanaFaces.at(shot,faceTracks.get(shot.clip),pick.index,matrix);
    const graffiti=(text,t,d,index,absolute=(frame+.5)/edit.canvas.fps)=>OpenKatanaGraffiti.draw(ctx,text,{W,H,elapsed:t,duration:d,fps:edit.canvas.fps,absolute,index,shotIndex:edit.shots.indexOf(shot),frame,boil:edit.canvas.boil ?? 2,face},noise);
    ctx.save();
    // Camera motion blur (cam.shutter, 0..1 of a frame): the plate is drawn under camera samples spread across the
    // shutter interval and averaged; static cameras draw once.
    const shutter = cam.shutter ?? 0, samples = [];
    if (shutter > 0) {
      const n = 9;
      for (let i = 0; i < n; i++) {
        const dt = (i/(n-1)-.5)*shutter;
        samples.push(cameraMatrix(cam,fx,clip,W,H,elapsed+dt/edit.canvas.fps,duration,frame+dt,shot.speed ?? 1,faceTracks.get(shot.clip)?.[pick.index]));
      }
      const spread = Math.max(...samples.map(m => Math.hypot(m[0]-samples[0][0], m[1]-samples[0][1])*Math.max(clip.w,clip.h) + Math.hypot(m[4]-samples[0][4], m[5]-samples[0][5])));
      if (spread < .25) samples.length = 0;
    }
    if (samples.length) {
      const plate = plateFor(clip); const pc = plate.getContext('2d');
      pc.globalAlpha = 1; pc.globalCompositeOperation = 'copy'; pc.drawImage(a,0,0,clip.w,clip.h);
      if (b) {pc.globalCompositeOperation = 'source-over'; pc.globalAlpha = pick.weight; pc.drawImage(b,0,0,clip.w,clip.h); pc.globalAlpha = 1;}
      samples.forEach((m,i) => {ctx.setTransform(...m); ctx.globalAlpha = 1/(i+1); ctx.drawImage(plate,0,0,clip.w,clip.h);});
      ctx.globalAlpha = 1; ctx.setTransform(...matrix);
    } else {
      ctx.setTransform(...matrix);
      ctx.drawImage(a,0,0,clip.w,clip.h);
      if (b) {ctx.globalAlpha = pick.weight; ctx.drawImage(b,0,0,clip.w,clip.h);}
    }
    // Ghost trail (audit F-NAT-005): earlier source frames, oldest first, over the plate and before the look. Ghost j
    // (j steps back) gets alpha * (1 - (j-1)/(n+1)); fitted to observed output (n=1..3).
    const trail = options(fx.trail);
    if (trail) {
      const n = trail.n ?? 3, step = trail.step ?? 2, alpha = trail.alpha ?? .35;
      ctx.globalCompositeOperation = trail.op ?? 'source-over';
      for (let j = n; j >= 1; j--) {
        ctx.globalAlpha = alpha*(1-(j-1)/(n+1));
        ctx.drawImage(await image(clip, wrap(pick.index-j*step, clip.n, shot.loop)),0,0,clip.w,clip.h);
      }
    }
    ctx.restore();
    let mask;
    if(clip.mask_dir) {
      const mc=maskBuffer.getContext('2d');mc.resetTransform();mc.clearRect(0,0,W,H);
      mask=await image({...clip,frames_dir:clip.mask_dir,pattern:'%05d.png'},pick.index);
      mc.setTransform(...matrix);mc.drawImage(mask,0,0,clip.w,clip.h);
    }
    const lk=animate(shot.look??edit.look,elapsed,duration);
    if(lk&&lk.type==='studio')OpenKatanaStudio.apply(ctx,lk,{W,H,frame,elapsed,duration,fps:edit.canvas.fps,hash:noise,mask:mask?maskBuffer:null});
    else OpenKatanaEffects.look(ctx,lk,frame,noise);
    if(clip.mask_dir){const pc=plateBuffer.getContext('2d');pc.globalCompositeOperation='copy';pc.drawImage(canvas,0,0);}
    for (const item of composition(shot,fx)) {
      if(OpenKatanaEffects.draw(ctx,item.type==='burst-letters'?'burst':item.type,item.params,{W,H,elapsed,duration,frame,boil:edit.canvas.boil??2,hash:noise,face,maskBuffer:mask?maskBuffer:null,lettersOnly:item.type==='burst-letters'}))continue;
      if(OpenKatanaLocal.draw(ctx,item.type,item.params,{W,H,elapsed,duration,frame}))continue;
      if(item.type==='stickers'){OpenKatanaStickers.draw(ctx,frame,edit.canvas.fps,W,H);continue;}
      if(OpenKatanaDecor.draw(ctx,item.type,item.params,{W,H,elapsed,duration,frame,face,matrix,fps:edit.canvas.fps}))continue;
      if(item.type==='graffiti') {
        graffiti({mode:'write',...item.params},elapsed-(item.params.at ?? 0),item.params.d ?? duration,99+edit.shots.indexOf(shot));
        continue;
      }
      if(item.type==='outline' || item.type==='cutout') {
        if(clip.mask_dir)subjectEffect(item.type,item.params,W,H,mask,matrix,clip);
        continue;
      }
      if(item.type==='hook') {
        OpenKatanaHooks.drawLayer(item.params.name,ctx,item.params.params ?? {},hookInfo(frame,elapsed,duration,face));
        continue;
      }
      if(item.type==='text') {
        const at=item.params.at ?? 0;
        OpenKatanaText(ctx,item.params,elapsed-at,item.params.d ?? duration,edit.canvas.fps,W,H,jitter(item.params,frame),face);
        continue;
      }
      if (item.type !== 'global-text') {
        postEffects([item],elapsed,duration,W,H);
        continue;
      }
      if (!inTransition) globalText(shot, fx, frame, face, W, H);
    }
    return {sample:pick, face, fx};
  }
  return {boot,render};
})();
