/* Original OpenKatana composition/plugin API. No private native runtime or source. */
'use strict';
window.OpenKatanaComposition = (() => {
  const plugins = new Map(), elements = new Map(), events = [], effects = [], fontFaces = [];
  let expected = null, doc = null, unloaded = false;
  const clone = value => structuredClone(value);
  const fail = message => { throw Error(message); };
  const isObject = x => x !== null && typeof x === 'object' && !Array.isArray(x);
  const fields = (v, allowed, where) => {
    if (!isObject(v)) fail(`${where}: expected object`);
    for (const k of Object.keys(v)) if (!allowed.includes(k)) fail(`${where}: unsupported ${k}`);
  };
  const validName = s => typeof s === 'string' && /^[A-Za-z][A-Za-z0-9_-]{0,79}$/.test(s);
  function parameterSchema(schema) {
    if (!isObject(schema)) fail('params must be a parameter declaration object');
    for (const [key, rule] of Object.entries(schema)) {
      if (!validName(key)) fail('Invalid parameter name');
      fields(rule, ['type','required','default','min','max','enum'], `parameter ${key}`);
      if (!['string','number','integer','boolean','object','array'].includes(rule.type)) fail('Unknown parameter type');
      if ('required' in rule && typeof rule.required !== 'boolean') fail('required must be boolean');
      for (const k of ['min','max']) if (k in rule && !Number.isFinite(rule[k])) fail(`${k} must be finite`);
      if ('enum' in rule && !Array.isArray(rule.enum)) fail('enum must be an array');
    }
  }
  function parameters(schema, supplied) {
    if (!isObject(supplied)) fail('params must be an object');
    const result = {};
    for (const k of Object.keys(supplied)) if (!Object.hasOwn(schema,k)) fail(`Unknown parameter: ${k}`);
    for (const [k, r] of Object.entries(schema)) {
      const v = k in supplied ? supplied[k] : r.default;
      if (v === undefined) { if (r.required) fail(`Missing parameter: ${k}`); continue; }
      const good = r.type === 'array' ? Array.isArray(v) : r.type === 'object' ? isObject(v) : r.type === 'integer' ? Number.isInteger(v) : typeof v === r.type;
      if (!good || (typeof v === 'number' && (!Number.isFinite(v) || v < (r.min ?? -Infinity) || v > (r.max ?? Infinity)))) fail(`Invalid parameter: ${k}`);
      if (r.enum && !r.enum.some(e => JSON.stringify(e) === JSON.stringify(v))) fail(`Parameter ${k}: unsupported value`);
      result[k] = clone(v);
    }
    return result;
  }
  function register(plugin) {
    fields(plugin, ['api','id','version','components','operators','effects','setup','teardown'], 'plugin');
    if (plugin.api !== 1 || !validName(plugin.id) || plugins.has(plugin.id)) fail('Duplicate plugin or invalid API/ID');
    if (!expected || plugin.id !== expected.id || plugin.version !== expected.version) fail('Plugin registration differs from manifest');
    for (const kind of ['components','operators','effects']) {
      if (!isObject(plugin[kind] ?? {})) fail(`plugin.${kind}: expected object`);
      for (const [name, spec] of Object.entries(plugin[kind] ?? {})) {
        if (!validName(name)) fail('Invalid extension name');
        fields(spec, ['description','params', ...(kind === 'components' ? ['build'] : kind === 'operators' ? ['run','kinds'] : ['mount','render','dispose'])], kind);
        parameterSchema(spec.params ?? {});
        if (typeof spec[kind === 'components' ? 'build' : kind === 'operators' ? 'run' : 'render'] !== 'function') fail('Extension lacks required callback');
        if (kind === 'operators' && (!Array.isArray(spec.kinds) || !spec.kinds.length || spec.kinds.some(k => !['composition','timeline'].includes(k)))) fail('Operator must declare document kinds');
      }
    }
    for (const k of ['setup','teardown']) if (k in plugin && typeof plugin[k] !== 'function') fail(`plugin.${k} must be a function`);
    plugins.set(plugin.id, plugin); events.push({event:'register', plugin:plugin.id});
  }
  function builtin(plugin) { expected = {id:'core',version:'1.0.0'}; register(plugin); expected = null; }
  async function loadPlugins(manifests) {
    for (const m of manifests) {
      expected = m;
      await new Promise((resolve, reject) => {
        const s = document.createElement('script'); s.src = m.url; s.onload = resolve; s.onerror = () => reject(Error(`Cannot load ${m.id}`)); document.head.appendChild(s);
      });
      if (!plugins.has(m.id)) fail(`Plugin ${m.id} did not register`);
      expected = null;
    }
    for (const p of plugins.values()) { await p.setup?.({api:1}); events.push({event:'setup', plugin:p.id}); }
    return catalog();
  }
  function catalog() {
    return [...plugins.values()].map(p => ({id:p.id, version:p.version, api:p.api,
      ...Object.fromEntries(['components','operators','effects'].map(kind => [kind, Object.entries(p[kind] ?? {}).map(([name,s]) => ({name:`${p.id}/${name}`, params:s.params ?? {}, description:s.description ?? '', ...(s.kinds ? {kinds:s.kinds} : {})}))]))}));
  }
  function extension(ref, kind) {
    const [p,n] = ref.split('/'); const spec = plugins.get(p)?.[kind]?.[n];
    if (!spec) fail(`Unknown ${kind} extension: ${ref}`);
    return spec;
  }
  async function expand(value) {
    window.__okSeed?.(0);
    const output = clone(value); let count = 0;
    async function visit(n, depth) {
      if (++count > 1000 || depth > 24) fail('Component expansion exceeds node/depth limit');
      if (n.type === 'component') {
        const s = extension(n.component, 'components');
        const built = await s.build(parameters(s.params ?? {}, n.params ?? {}), {id:n.id, canvas:clone(value.canvas)});
        if (!isObject(built)) fail('Component must return a node');
        const next = {...built, id:n.id, style:{...built.style,...n.style}, responsive:[...(built.responsive ?? []),...(n.responsive ?? [])], effects:[...(built.effects ?? []),...(n.effects ?? [])]};
        for (const k of ['dir','lang']) if (k in n) next[k] = n[k];
        return visit(next, depth+1);
      }
      if (n.children) n.children = await Promise.all(n.children.map(c => visit(c,depth+1)));
      return n;
    }
    output.root = await visit(output.root,0); return output;
  }
  function applyStyles(el, values) {
    for (const [k,v] of Object.entries(values)) {
      if (!CSS.supports(k,v)) fail(`Unsupported CSS value: ${k}: ${v}`);
      el.style.setProperty(k,v);
    }
  }
  function attributes(el,n) { if (n.lang) el.lang=n.lang; if (n.dir) el.dir=n.dir; }
  function styleAt(n) {
    const s = {...n.style};
    for (const rule of n.responsive ?? []) if (innerWidth >= (rule.min_width ?? 0) && innerWidth <= (rule.max_width ?? 7680)) Object.assign(s,rule.style);
    return s;
  }
  async function unmount() {
    for (const e of effects.splice(0).reverse()) { await e.spec.dispose?.(e.el,e.state); events.push({event:'effect-dispose',node:e.id,use:e.use}); }
    elements.clear(); document.getElementById('stage').replaceChildren();
    for (const f of fontFaces.splice(0)) document.fonts.delete(f);
  }
  async function mount(value) {
    await unmount(); doc = clone(value); window.__okSeed?.(0);
    for (const f of doc.fonts ?? []) {
      const url = f.bundled ? `/fonts/${encodeURIComponent(f.bundled)}` : `/project/${f.src.split('/').map(encodeURIComponent).join('/')}`;
      const font = new FontFace(f.family, `url(${JSON.stringify(url)})`, {weight:f.weight ?? 'normal', style:f.style ?? 'normal'});
      await font.load(); document.fonts.add(font); fontFaces.push(font);
    }
    async function node(n) {
      const el = document.createElement(n.type === 'image' ? 'img' : 'div');
      el.dataset.node = n.id; attributes(el,n); applyStyles(el,styleAt(n)); elements.set(n.id,{el,n});
      if (n.type === 'text') {
        if ('text' in n) el.textContent=n.text;
        else for (const run of n.runs) { const span=document.createElement('span'); span.textContent=run.text; attributes(span,run); applyStyles(span,run.style ?? {}); el.appendChild(span); }
      } else if (n.type === 'image') {
        el.src = '/project/' + n.src.split('/').map(encodeURIComponent).join('/'); await el.decode();
      } else for (const child of n.children ?? []) el.appendChild(await node(child));
      return el;
    }
    document.getElementById('stage').appendChild(await node(doc.root));
    await document.fonts.ready;
    for (const [id,{el,n}] of elements) for (const fx of n.effects ?? []) {
      const spec=extension(fx.use,'effects'), params=parameters(spec.params ?? {},fx.params ?? {});
      const state=await spec.mount?.(el,clone(params),{canvas:clone(doc.canvas),id});
      effects.push({id,el,spec,params,state,use:fx.use}); events.push({event:'effect-mount',node:id,use:fx.use});
    }
    return {nodes:elements.size,fonts:fontFaces.map(f=>({family:f.family,status:f.status}))};
  }
  function valueAt(t,f) {
    const keys=t.keys; if (f<=keys[0][0]) return keys[0][1];
    for (let i=1;i<keys.length;i++) if(f<=keys[i][0]) {
      let u=(f-keys[i-1][0])/(keys[i][0]-keys[i-1][0]);
      u=t.easing==='step' ? (u===1?1:0) : t.easing==='smooth' ? u*u*(3-2*u) : u;
      return keys[i-1][1]*(1-u)+keys[i][1]*u;
    }
    return keys.at(-1)[1];
  }
  // Ranges refer to the intact DOM text. Never split contextual scripts into isolated canvas letters.
  function clusters(el, lang) {
    const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT), leaves=[];let leaf,offset=0;
    while((leaf=walker.nextNode())) { leaves.push({leaf,from:offset,to:offset+leaf.length});offset+=leaf.length; }
    const text=el.textContent, segmenter=new Intl.Segmenter(lang || 'und',{granularity:'grapheme'}), result=[];
    for(const s of segmenter.segment(text)) {
      const start=s.index,end=start+s.segment.length;
      const a=leaves.find(n=>n.to>start),b=leaves.find(n=>n.to>=end);
      if(!a||!b)continue;
      const range=document.createRange();range.setStart(a.leaf,start-a.from);range.setEnd(b.leaf,end-b.from);
      result.push({text:s.segment,start,end,rects:[...range.getClientRects()].map(r=>({x:r.x,y:r.y,w:r.width,h:r.height}))});
    }
    return result;
  }
  function reveal(el,n,amount) {
    if(n.type!=='text') { el.style.clipPath=`inset(0 ${(1-amount)*100}% 0 0)`;return; }
    if(amount>=1)return;
    const base=el.getBoundingClientRect(), list=clusters(el,n.lang), visible=Math.floor(list.length*amount);
    const masks=[];
    for(const group of list.slice(0,visible)) for(const r of group.rects) {
      // Shaped range boxes use CSS pixels. Mask is applied before transforms, which are applied after this function.
      masks.push(`linear-gradient(#000,#000) ${r.x-base.x}px ${r.y-base.y}px / ${Math.max(r.w,0.1)}px ${Math.max(r.h,0.1)}px no-repeat`);
    }
    el.style.mask=masks.length ? masks.join(',') : 'linear-gradient(transparent,transparent)';
  }
  async function frame(f) {
    if(!doc || !Number.isInteger(f)||f<0||f>=doc.canvas.frames)fail('Frame outside composition');
    window.__okSeed?.(f);
    const values=new Map();
    for(const t of doc.tracks ?? []) { if(!values.has(t.node)) values.set(t.node,{});values.get(t.node)[t.property]=valueAt(t,f); }
    for(const [id,{el,n}] of elements) { el.removeAttribute('style');applyStyles(el,styleAt(n)); }
    // Masks are measured before animated transforms, so scale/rotation do not corrupt cluster rectangles.
    const transforms=[...elements.values()].map(({el})=>[el,el.style.transform]);
    for(const [el] of transforms)el.style.transform='none';
    for(const [id,v] of values) { const {el,n}=elements.get(id) ?? fail(`Track target missing: ${id}`); if(v.reveal!==undefined)reveal(el,n,v.reveal); }
    for(const [el,transform] of transforms)el.style.transform=transform;
    for(const [id,v] of values) {
      const {el}=elements.get(id); if(v.opacity!==undefined)el.style.opacity=v.opacity;
      const x=v.translateX??0,y=v.translateY??0,r=v.rotate??0,s=v.scale??1;
      if(['translateX','translateY','rotate','scale'].some(k=>k in v))el.style.transform=`${el.style.transform} translate(${x}px,${y}px) rotate(${r}deg) scale(${s})`;
    }
    for(const e of effects) await e.spec.render(e.el,clone(e.params),{frame:f,t:f/doc.canvas.fps,canvas:clone(doc.canvas),id:e.id},e.state);
    await document.fonts.ready;
    return f;
  }
  function measure() {
    return {fonts:fontFaces.map(f=>({family:f.family,status:f.status})),nodes:[...elements].map(([id,{el,n}])=>{
      const r=el.getBoundingClientRect(),s=getComputedStyle(el);
      return {id,type:n.type,rect:{x:r.x,y:r.y,w:r.width,h:r.height},overflow:el.scrollWidth>el.clientWidth+1||el.scrollHeight>el.clientHeight+1,
        style:{display:s.display,direction:s.direction,fontFamily:s.fontFamily,fontSize:s.fontSize,fontWeight:s.fontWeight,fontFeatureSettings:s.fontFeatureSettings,fontVariationSettings:s.fontVariationSettings,writingMode:s.writingMode},
        ...(n.type==='text'?{text:el.textContent,graphemes:clusters(el,n.lang),fontRuns:('text' in n?[el]:[...el.children]).map(run=>({text:run.textContent,family:getComputedStyle(run).fontFamily}))}:{})};
    })};
  }
  async function operate(args) {
    window.__okSeed?.(0); const s=extension(args.operator,'operators');
    if(!s.kinds.includes(args.kind))fail('Operator does not support this document kind');
    const result=await s.run(clone(args.document),parameters(s.params??{},args.params),{kind:args.kind});
    if(!isObject(result))fail('Operator must return a complete document');
    const visited=new WeakSet();
    function jsonValue(x){
      if(x===null||typeof x==='string'||typeof x==='boolean')return;
      if(typeof x==='number'&&Number.isFinite(x))return;
      if(typeof x!=='object'||visited.has(x))fail('Operator output must be finite, acyclic JSON data');
      visited.add(x);for(const v of Object.values(x))jsonValue(v);visited.delete(x);
    }
    jsonValue(result);
    return JSON.parse(JSON.stringify(result));
  }
  async function dispose() {
    await unmount();
    if(!unloaded)for(const p of [...plugins.values()].reverse()){await p.teardown?.();events.push({event:'teardown',plugin:p.id});}
    unloaded=true;return events.slice();
  }
  return {register,builtin,loadPlugins,catalog,expand,mount,frame,measure,operate,dispose};
})();
