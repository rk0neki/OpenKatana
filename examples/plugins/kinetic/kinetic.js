/* Original OpenKatana example. MIT; no proprietary plugin implementation. */
'use strict';
OpenKatanaComposition.register({api:1,id:'kinetic',version:'1.0.0',
  components:{badge:{description:'Responsive badge with a stable text child.',params:{label:{type:'string',required:true},color:{type:'string',default:'#38bdf8'}},
    build:(p,{id})=>({id,type:'box',style:{padding:'16px','border-radius':'12px','background-color':'#172033','border':`1px solid ${p.color}`},children:[
      {id:id+'-label',type:'text',text:p.label,style:{'font-size':'clamp(18px, 3vw, 40px)',color:p.color,'line-height':'1.5'}}]})}},
  effects:{float:{description:'Absolute-time motion; no accumulated frame state.',params:{pixels:{type:'number',min:0,max:200,default:8},hz:{type:'number',min:0,max:20,default:1}},
    mount:()=>({draws:0}),render:(el,p,info,state)=>{state.draws++;el.style.transform+=` translateY(${Math.sin(info.t*2*Math.PI*p.hz)*p.pixels}px)`;},dispose:(_el,state)=>{state.draws=0;}}},
  operators:{setText:{description:'Change one plain text node. Rejects missing or structured-run nodes.',params:{id:{type:'string',required:true},text:{type:'string',required:true}},kinds:['composition'],
    run:(doc,p)=>{let found=false;function visit(n){if(n.id===p.id){if(n.type!=='text'||!('text'in n))throw Error('Expected plain text node');n.text=p.text;found=true;}for(const c of n.children??[])visit(c);}visit(doc.root);if(!found)throw Error('Node not found');return doc;}}}
});
