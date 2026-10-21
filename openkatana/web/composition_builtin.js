/* Independently authored reusable components, effects and transactional document operations. MIT. */
'use strict';
(() => {
  const fail=s=>{throw Error(s);};
  const copy=x=>structuredClone(x);
  const canonical=x=>Array.isArray(x)?x.map(canonical):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])])):x;
  function tokens(path) {
    if(typeof path!=='string'||!path.startsWith('/')||/~(?![01])/u.test(path))fail('Use a JSON Pointer beginning with /');
    const out=path.slice(1).split('/').map(x=>x.replace(/~1/g,'/').replace(/~0/g,'~'));
    if(out.some(x=>['__proto__','prototype','constructor'].includes(x)))fail('Reserved path token');return out;
  }
  function locate(doc,path,add=false) {
    const keys=tokens(path),key=keys.pop();let parent=doc;
    for(const k of keys){if(parent===null||typeof parent!=='object'||!Object.hasOwn(parent,k))fail('Path missing: '+path);parent=parent[k];}
    if(parent===null||typeof parent!=='object')fail('Path parent is not an object');
    if(Array.isArray(parent)){
      if(key==='-'&&add)return{parent,key:parent.length};
      if(!/^(0|[1-9][0-9]*)$/.test(key)||Number(key)>parent.length||(!add&&Number(key)===parent.length))fail('Array index out of bounds');
      return{parent,key:Number(key)};
    }
    if(!add&&!Object.hasOwn(parent,key))fail('Path missing: '+path);
    return{parent,key};
  }
  function batch(doc,params) {
    if(params.ops.length>1000)fail('At most 1000 operations per batch');
    for(const op of params.ops){
      if(!op||typeof op!=='object'||Array.isArray(op))fail('Operation must be an object');
      const allowed={add:['op','path','value'],replace:['op','path','value'],remove:['op','path'],test:['op','path','value'],copy:['op','path','from'],move:['op','path','from']}[op.op];
      if(!allowed||Object.keys(op).some(k=>!allowed.includes(k))||allowed.some(k=>!Object.hasOwn(op,k)))fail('Invalid operation fields');
      if(op.op==='test'){const{parent,key}=locate(doc,op.path);if(JSON.stringify(canonical(parent[key]))!==JSON.stringify(canonical(op.value)))fail('Operation test failed');continue;}
      let value=op.value;
      if(['copy','move'].includes(op.op)){
        if(op.op==='move'&&(op.path===op.from||op.path.startsWith(op.from+'/')))fail('Cannot move a node into itself');
        const{parent,key}=locate(doc,op.from);value=copy(parent[key]);
        if(op.op==='move'){if(Array.isArray(parent))parent.splice(key,1);else delete parent[key];}
      }
      const{parent,key}=locate(doc,op.path,['add','copy','move'].includes(op.op));
      if(op.op==='remove'){if(Array.isArray(parent))parent.splice(key,1);else delete parent[key];}
      else if(Array.isArray(parent)&&['add','copy','move'].includes(op.op))parent.splice(key,0,copy(value));
      else parent[key]=copy(value);
    }
    return doc;
  }
  OpenKatanaComposition.builtin({api:1,id:'core',version:'1.0.0',
    components:{
      titleCard:{description:'A responsive title and supporting line; children have stable IDs.',params:{title:{type:'string',required:true},subtitle:{type:'string',default:''},accent:{type:'string',default:'#60a5fa'}},
        build:(p,{id})=>({id,type:'box',style:{display:'flex','flex-direction':'column',gap:'2vh','max-width':'100%'},children:[
          {id:id+'-heading',type:'text',text:p.title,style:{'font-size':'clamp(24px, 6vw, 100px)','font-weight':'800','line-height':'1.1','overflow-wrap':'anywhere'}},
          {id:id+'-subtitle',type:'text',text:p.subtitle,style:{'font-size':'clamp(14px, 2.4vw, 40px)',color:p.accent,'line-height':'1.4'}}]})},
      lowerThird:{description:'A reusable name/role graphic with responsive font size.',params:{name:{type:'string',required:true},role:{type:'string',default:''},color:{type:'string',default:'#0f172a'}},
        build:(p,{id})=>({id,type:'box',style:{padding:'3vw','background-color':p.color,'border-radius':'12px',color:'#ffffff',display:'flex','flex-direction':'column'},children:[
          {id:id+'-name',type:'text',text:p.name,style:{'font-size':'clamp(20px, 4vw, 64px)','font-weight':'700'}},
          {id:id+'-role',type:'text',text:p.role,style:{'font-size':'clamp(14px, 2vw, 32px)'}}]})}
    },
    effects:{pulse:{description:'Deterministic time-based brightness pulse; reversible seeks.',params:{amplitude:{type:'number',default:.15,min:0,max:1},hz:{type:'number',default:1,min:0,max:20}},render:(el,p,ctx)=>{el.style.filter=`${el.style.filter} brightness(${1+p.amplitude*Math.sin(2*Math.PI*p.hz*ctx.t)})`;}}},
    operators:{batch:{description:'Atomic JSON Pointer add/replace/remove/move/copy/test proposal. The host validates the complete result before saving.',params:{ops:{type:'array',required:true}},kinds:['composition','timeline'],run:batch}}
  });
})();
