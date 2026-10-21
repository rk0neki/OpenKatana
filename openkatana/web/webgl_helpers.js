// Original OpenKatana authoring helpers, MIT. Three.js is separately licensed in vendor3d.
import * as T from 'three';

const finite=(v,name)=>{if(!Number.isFinite(v))throw Error(`${name}: expected finite number`);return v;};
const vector=(p,n=3)=>{if(!Array.isArray(p)||p.length!==n)throw Error(`Expected ${n} coordinates`);p.forEach(v=>finite(v,'coordinate'));return p;};

export function roundedBox(size=[1,1,1],radius=.1,segments=5) {
  vector(size);finite(radius,'radius');
  if(size.some(x=>x<=0)||radius<=0||radius>=Math.min(...size)/2||!Number.isInteger(segments)||segments<1||segments>32)
    throw Error('roundedBox: positive dimensions, 0 < radius < half smallest dimension, 1..32 bevel segments');
  const [x,y,z]=size.map(x=>x/2),r=radius,shape=new T.Shape();
  // A bevelled inset rectangle produces rounded surfaces on all three axes.
  shape.moveTo(-x+r,-y+r);shape.lineTo(x-r,-y+r);shape.lineTo(x-r,y-r);shape.lineTo(-x+r,y-r);shape.closePath();
  const g=new T.ExtrudeGeometry(shape,{depth:2*(z-r),bevelEnabled:true,bevelThickness:r,bevelSize:r,bevelSegments:segments,steps:1});
  g.translate(0,0,-z+r);g.computeVertexNormals();return g;
}

export function tube(points,{radius=.04,segments=64,sides=12,closed=false}={}) {
  if(!Array.isArray(points)||points.length<2||points.length>2048)throw Error('tube needs 2..2048 points');
  const p=[];for(const point of points){const v=new T.Vector3(...vector(point));if(!p.length||v.distanceTo(p.at(-1))>1e-7)p.push(v);}
  if(p.length<2||!Number.isFinite(radius)||radius<=0||!Number.isInteger(segments)||segments<2||segments>4096||!Number.isInteger(sides)||sides<3||sides>128||typeof closed!=='boolean')throw Error('Invalid tube parameters');
  const curve=new T.CatmullRomCurve3(p,closed,'centripetal');
  return new T.TubeGeometry(curve,segments,radius,sides,closed);
}

export function lathe(profile,segments=48) {
  if(!Array.isArray(profile)||profile.length<2||profile.length>2048||!Number.isInteger(segments)||segments<3||segments>512)throw Error('Invalid lathe parameters');
  const points=profile.map(p=>{vector(p,2);if(p[0]<0)throw Error('Lathe radius must be nonnegative');return new T.Vector2(...p);});
  return new T.LatheGeometry(points,segments);
}

export function sampleCamera(cache,frame) {
  if(!cache?.poses?.length)throw Error('Empty camera cache');
  const f=T.MathUtils.clamp(finite(frame,'frame'),0,cache.poses.length-1),a=Math.floor(f),b=Math.ceil(f);
  // The discontinuity lies halfway between exposed frame centres; never interpolate across it.
  if(cache.cuts.includes(b)&&a!==b)return cache.poses[f<b-.5?a:b];
  const x=cache.poses[a],y=cache.poses[b],u=f-a;
  return {position:x.position.map((v,i)=>T.MathUtils.lerp(v,y.position[i],u)),
    target:x.target.map((v,i)=>T.MathUtils.lerp(v,y.target[i],u)),fov:T.MathUtils.lerp(x.fov,y.fov,u)};
}

export async function atlasDisplay({assetURL,atlas='display/atlas.png',receipt='display/receipt.json',
    width=1.6,height=.45,pixelSize=6,colors=['#79e2ff','#ffd784','#ff8ec4']}={}) {
  if(typeof assetURL!=='function')throw Error('atlasDisplay needs the authoring context assetURL');
  const response=await fetch(assetURL(receipt));if(!response.ok)throw Error('Cannot load atlas receipt');
  const meta=await response.json(),d=meta.document;
  if(!d||!Number.isInteger(d.cols)||!Number.isInteger(d.rows)||!Number.isInteger(d.frames)||!Number.isInteger(d.tiles_x))throw Error('Invalid display atlas receipt');
  if(!Number.isInteger(pixelSize)||pixelSize<2||pixelSize>16||d.cols*pixelSize>4096||d.rows*pixelSize>4096||d.frames<1||!Number.isFinite(width)||width<=0||!Number.isFinite(height)||height<=0||!Array.isArray(colors)||colors.length!==3||colors.some(c=>!/^#[0-9a-f]{6}$/i.test(c)))throw Error('Invalid display dimensions/colours');
  const image=new Image();image.src=assetURL(atlas);await image.decode();
  if(image.width!==d.cols*d.tiles_x||image.height!==d.rows*Math.ceil(d.frames/d.tiles_x))throw Error('Atlas pixels do not match receipt');
  const source=document.createElement('canvas');source.width=image.width;source.height=image.height;
  const input=source.getContext('2d',{willReadFrequently:true});input.drawImage(image,0,0);
  const canvas=document.createElement('canvas');canvas.width=d.cols*pixelSize;canvas.height=d.rows*pixelSize;
  const ctx=canvas.getContext('2d'),texture=new T.CanvasTexture(canvas);texture.colorSpace=T.SRGBColorSpace;
  texture.minFilter=T.LinearFilter;texture.magFilter=T.LinearFilter;
  const rgb=colors.map(c=>[1,3,5].map(i=>parseInt(c.slice(i,i+2),16)));
  const material=new T.MeshBasicMaterial({map:texture,toneMapped:false});
  const mesh=new T.Mesh(new T.PlaneGeometry(width,height),material);let last=-1;
  const update=frame=>{
    const tile=T.MathUtils.clamp(Math.floor(finite(frame,'frame')+.5),0,d.frames-1);
    if(tile===last)return tile;
    const mask=input.getImageData(tile%d.tiles_x*d.cols,Math.floor(tile/d.tiles_x)*d.rows,d.cols,d.rows).data;
    ctx.fillStyle='#020608';ctx.fillRect(0,0,canvas.width,canvas.height);
    for(let y=0;y<d.rows;y++)for(let x=0;x<d.cols;x++){
      const k=(y*d.cols+x)*4,c=[0,1,2].map(j=>Math.min(255,Math.round(rgb.reduce((v,a,i)=>v+a[j]*mask[k+i]/255,0))));
      if(!c.some(v=>v))continue;
      ctx.fillStyle=`rgb(${c.join(',')})`;ctx.beginPath();ctx.arc((x+.5)*pixelSize,(y+.5)*pixelSize,pixelSize*.36,0,Math.PI*2);ctx.fill();
    }
    texture.needsUpdate=true;last=tile;return tile;
  };
  update(0);return {mesh,update,metadata:d,get tile(){return last;}};
}
