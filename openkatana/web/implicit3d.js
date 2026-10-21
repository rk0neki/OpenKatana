// Independently authored marching-tetrahedra mesher for signed-distance blends.
// Topology can change; vertex correspondence between unrelated meshes is not assumed.
import * as THREE from 'three';

function field(shape, x, y, z) {
  if (shape.type === 'sphere') return Math.hypot(x,y,z) - (shape.radius ?? 1);
  if (shape.type === 'torus') return Math.hypot(Math.hypot(x,z) - (shape.radius ?? .7), y) - (shape.tube ?? .2);
  const s = shape.size ?? [1,1,1], q = [Math.abs(x)-s[0]/2, Math.abs(y)-s[1]/2, Math.abs(z)-s[2]/2];
  return Math.hypot(...q.map(v=>Math.max(v,0))) + Math.min(Math.max(...q),0);
}

export function implicitGeometry(config, amount) {
  const n=config.grid??24, bound=config.bound??1.5, step=2*bound/n;
  const sdf=(x,y,z)=>field(config.from,x,y,z)*(1-amount)+field(config.to,x,y,z)*amount;
  const positions=[], normals=[];
  const corners=[[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]];
  const tetra=[[0,1,2,6],[0,2,3,6],[0,3,7,6],[0,7,4,6],[0,4,5,6],[0,5,1,6]];
  const gradient=p=>{
    const e=step*.08;
    return new THREE.Vector3(sdf(p[0]+e,p[1],p[2])-sdf(p[0]-e,p[1],p[2]),
      sdf(p[0],p[1]+e,p[2])-sdf(p[0],p[1]-e,p[2]),sdf(p[0],p[1],p[2]+e)-sdf(p[0],p[1],p[2]-e)).normalize();
  };
  function triangle(a,b,c) {
    const normal=gradient(a.map((v,i)=>(v+b[i]+c[i])/3));
    const cross=new THREE.Vector3(...b).sub(new THREE.Vector3(...a)).cross(new THREE.Vector3(...c).sub(new THREE.Vector3(...a)));
    if(cross.lengthSq()===0)return;
    if(cross.dot(normal)<0)[b,c]=[c,b];
    for(const p of [a,b,c]) {positions.push(...p);normals.push(...gradient(p).toArray());}
  }
  const grid=new Float32Array((n+1)**3), ix=(x,y,z)=>(z*(n+1)+y)*(n+1)+x;
  for(let z=0;z<=n;z++)for(let y=0;y<=n;y++)for(let x=0;x<=n;x++)grid[ix(x,y,z)]=sdf(x*step-bound,y*step-bound,z*step-bound);
  let boundaryCrossings=0;
  for(let z=0;z<=n;z++)for(let y=0;y<=n;y++)for(let x=0;x<=n;x++)
    if((x===0||y===0||z===0||x===n||y===n||z===n)&&grid[ix(x,y,z)]<0)boundaryCrossings++;
  if(boundaryCrossings)throw Error('Implicit surface crosses its bounding grid; increase geometry.bound');
  for(let z=0;z<n;z++)for(let y=0;y<n;y++)for(let x=0;x<n;x++) {
    const values=corners.map(c=>grid[ix(x+c[0],y+c[1],z+c[2])]);
    if(values.every(v=>v>=0)||values.every(v=>v<0))continue;
    const points=corners.map(c=>[(x+c[0])*step-bound,(y+c[1])*step-bound,(z+c[2])*step-bound]);
    const edge=(i,j)=>{const a=values[i]/(values[i]-values[j]);return points[i].map((v,k)=>v+(points[j][k]-v)*a);};
    for(const t of tetra) {
      const inside=t.filter(i=>values[i]<0), outside=t.filter(i=>values[i]>=0);
      if(!inside.length||!outside.length)continue;
      if(inside.length===1)triangle(...outside.map(i=>edge(inside[0],i)));
      else if(inside.length===3)triangle(...inside.map(i=>edge(outside[0],i)));
      else {const [a,b]=inside,[c,d]=outside;const ac=edge(a,c),ad=edge(a,d),bc=edge(b,c),bd=edge(b,d);triangle(ac,ad,bc);triangle(ad,bd,bc);}
    }
  }
  if(!positions.length)throw Error('Implicit surface is empty at this resolution');
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  g.setAttribute('normal',new THREE.Float32BufferAttribute(normals,3));g.computeBoundingSphere();
  // Quantized welding is diagnostic only; it does not modify render geometry.
  const verts=new Map(),edges=new Map(),ids=[];
  for(let i=0;i<positions.length;i+=3) {
    const key=positions.slice(i,i+3).map(v=>Math.round(v*1e9)).join(',');
    if(!verts.has(key))verts.set(key,verts.size);ids.push(verts.get(key));
  }
  for(let i=0;i<ids.length;i+=3)for(const [a,b] of [[ids[i],ids[i+1]],[ids[i+1],ids[i+2]],[ids[i+2],ids[i]]]) {
    const key=a<b?`${a},${b}`:`${b},${a}`;edges.set(key,(edges.get(key)??0)+1);
  }
  g.userData.topology={vertices:verts.size,edges:edges.size,faces:ids.length/3,
    euler:verts.size-edges.size+ids.length/3,nonmanifold_edges:[...edges.values()].filter(n=>n!==2).length,
    quantization:1e-9,grid:n};
  return g;
}
