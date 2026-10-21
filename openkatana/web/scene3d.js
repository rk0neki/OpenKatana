// OpenKatana's original scene adapter. MIT dependencies live in vendor3d with their notices.
import * as T from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RGBELoader } from 'three/addons/loaders/RGBELoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { BokehPass } from 'three/addons/postprocessing/BokehPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import * as C from 'cannon-es';
import { implicitGeometry } from './implicit3d.js';
import * as helpers from './webgl_helpers.js';

let config, renderer, scene, camera, composer, entities, simulations, actions, dynamic, cameraTarget, author;
const url=p=>'/project/'+p.split('/').map(encodeURIComponent).join('/');
const vec=a=>new T.Vector3(...a);
const textureLoader=new T.TextureLoader();

function geometry(g) {
  const s=g.size??[1,1,1], seg=g.radial_segments??48;
  switch(g.type) {
    case 'box':return new T.BoxGeometry(...s);
    case 'sphere':return new T.SphereGeometry(g.radius??1,seg,Math.max(8,seg/2));
    case 'torus':return new T.TorusGeometry(g.radius??.7,g.tube??.2,seg,g.tubular_segments??96);
    case 'cylinder':return new T.CylinderGeometry(g.radius??.5,g.radius??.5,g.height??1,seg);
    case 'cone':return new T.ConeGeometry(g.radius??.5,g.height??1,seg);
    case 'plane':return new T.PlaneGeometry(s[0],s[1]);
    case 'implicit':return implicitGeometry(g,g.amount??0);
    case 'extrude': {
      const shape=new T.Shape(g.points.map(p=>new T.Vector2(...p)));
      for(const ring of g.holes??[])shape.holes.push(new T.Path(ring.map(p=>new T.Vector2(...p))));
      return new T.ExtrudeGeometry(shape,{depth:g.depth??.2,bevelEnabled:(g.bevel??0)>0,bevelThickness:g.bevel??0,
        bevelSize:g.bevel??0,bevelSegments:3,steps:1,curveSegments:24});
    }
    default:throw Error(`Unknown geometry: ${g.type}`);
  }
}

async function material(d={}) {
  const m=new T.MeshPhysicalMaterial({color:d.color??'#cccccc',metalness:d.metalness??0,roughness:d.roughness??.4,
    clearcoat:d.clearcoat??0,transmission:d.transmission??0,thickness:d.thickness??.5,ior:d.ior??1.5,
    opacity:d.opacity??1,transparent:(d.opacity??1)<1,emissive:d.emissive??'#000000',emissiveIntensity:d.emissive_intensity??1,
    side:d.double_sided?T.DoubleSide:T.FrontSide});
  if(d.map){m.map=await textureLoader.loadAsync(url(d.map));m.map.colorSpace=T.SRGBColorSpace;}
  if(d.normal_map)m.normalMap=await textureLoader.loadAsync(url(d.normal_map));
  return m;
}

function materials(object,callback) {object.traverse(child=>{if(child.material)for(const m of Array.isArray(child.material)?child.material:[child.material])callback(m);});}
function morph(object,name,value) {
  let found=0;
  object.traverse(child=>{const i=child.morphTargetDictionary?.[name];if(i!==undefined){child.morphTargetInfluences[i]=value;found++;}});
  if(!found)throw Error(`Missing morph target '${name}' on ${object.name}`);
}

function keyValue(track,time) {
  const k=track.keys;
  if(time<=k[0][0])return k[0][1];
  if(time>=k[k.length-1][0])return k[k.length-1][1];
  let i=1;while(k[i][0]<time)i++;
  if(time===k[i][0])return k[i][1];
  let a=(time-k[i-1][0])/(k[i][0]-k[i-1][0]);
  if(track.interpolation==='step')a=0;
  else if(track.interpolation==='smooth')a=a*a*(3-2*a);
  const v=k[i-1][1],w=k[i][1];
  if(Array.isArray(v))return v.map((x,j)=>x+(w[j]-x)*a);
  if(track.property==='color')return new T.Color(v).lerp(new T.Color(w),a);
  if(typeof v==='boolean')return v;
  return v+(w-v)*a;
}

function property(object,name,value) {
  if(['position','rotation','scale'].includes(name))object[name].fromArray(value);
  else if(name==='target'){if(object===camera)cameraTarget.fromArray(value);else if(object.target)object.target.position.fromArray(value);else throw Error(`${object.name} has no light target`);}
  else if(name==='fov'){if(!object.isPerspectiveCamera)throw Error('fov tracks require a perspective camera');object.fov=value;object.updateProjectionMatrix();}
  else if(name==='visible')object.visible=value;
  else if(name==='intensity')object.intensity=value;
  else if(name==='color'&&object.isLight)object.color.set(value);
  else if(name.startsWith('morph.'))morph(object,name.slice(6),value);
  else if(name==='amount')dynamic.find(x=>x.object===object).amount=value;
  else materials(object,m=>{
    if(name==='color')m.color.set(value);
    else {m[name==='emissive_intensity'?'emissiveIntensity':name]=value;if(name==='opacity'){m.transparent=true;m.needsUpdate=true;}}
  });
}

function bakePhysics() {
  const specs=config.objects.filter(o=>o.body);
  if(!specs.length)return [];
  const world=new C.World({gravity:new C.Vec3(...(config.physics?.gravity??[0,-9.81,0]))});
  world.solver.iterations=15;world.allowSleep=false;
  const bodies=specs.map(spec=>{
    const d=spec.body, object=entities.get(spec.id),mat=new C.Material({friction:d.friction??.3,restitution:d.restitution??.3});
    const body=new C.Body({mass:d.mass??0,material:mat,position:new C.Vec3(...object.position.toArray()),
      quaternion:new C.Quaternion(...object.quaternion.toArray()),velocity:new C.Vec3(...(d.velocity??[0,0,0])),
      angularVelocity:new C.Vec3(...(d.angular_velocity??[0,0,0]))});
    body.addShape(d.shape==='sphere'?new C.Sphere(d.radius):d.shape==='box'?new C.Box(new C.Vec3(...d.size.map(x=>x/2))):new C.Plane());
    world.addBody(body);return {id:spec.id,body};
  });
  const substeps=config.physics?.substeps??4, dt=1/config.canvas.fps/substeps,cache=[];
  for(let f=0;f<config.canvas.frames;f++) {
    cache.push(bodies.map(({id,body})=>({id,position:body.position.toArray(),quaternion:body.quaternion.toArray(),velocity:body.velocity.toArray()})));
    if(f+1<config.canvas.frames)for(let s=0;s<substeps;s++)world.step(dt);
  }
  if(cache.flat().some(x=>[...x.position,...x.quaternion].some(v=>!Number.isFinite(v))))throw Error('Non-finite physics state');
  return cache;
}

async function boot(data) {
  config=data;entities=new Map();actions=[];dynamic=[];author=null;
  const c=config.canvas;
  renderer=new T.WebGLRenderer({antialias:true,alpha:!!c.transparent,preserveDrawingBuffer:true});
  renderer.setPixelRatio(1);renderer.setSize(c.width,c.height);document.body.appendChild(renderer.domElement);
  renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;
  renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=config.exposure??1;
  renderer.debug.onShaderError=(_gl,_program,_vs,_fs)=>{throw Error('3D shader compilation failed');};
  scene=new T.Scene();if(!c.transparent)scene.background=new T.Color(config.background??'#101820');
  const pmrem=new T.PMREMGenerator(renderer);
  if((config.environment??'studio')==='studio') {
    const room=new RoomEnvironment();scene.environment=pmrem.fromScene(room,.04).texture;room.dispose();
  } else if(config.environment!=='none') {
    const hdr=await new RGBELoader().loadAsync(url(config.environment));scene.environment=pmrem.fromEquirectangular(hdr).texture;hdr.dispose();
  }
  pmrem.dispose();
  const cam=config.camera,aspect=c.width/c.height;
  camera=cam.type==='orthographic'?new T.OrthographicCamera(-(cam.span??5)*aspect/2,(cam.span??5)*aspect/2,(cam.span??5)/2,-(cam.span??5)/2,cam.near??.01,cam.far??1000):
    new T.PerspectiveCamera(cam.fov??45,aspect,cam.near??.01,cam.far??1000);
  camera.name='camera';camera.position.fromArray(cam.position);cameraTarget=vec(cam.target??[0,0,0]);entities.set('camera',camera);
  for(const spec of config.lights??[]) {
    let l;const col=spec.color??'#ffffff',power=spec.intensity??1;
    if(spec.type==='ambient')l=new T.AmbientLight(col,power);
    if(spec.type==='directional')l=new T.DirectionalLight(col,power);
    if(spec.type==='point')l=new T.PointLight(col,power,spec.distance??0,spec.decay??2);
    if(spec.type==='spot')l=new T.SpotLight(col,power,spec.distance??0,spec.angle??Math.PI/4,.3,spec.decay??2);
    l.name=spec.id;l.position.fromArray(spec.position??[0,5,3]);
    if(l.target){l.target.position.fromArray(spec.target??[0,0,0]);scene.add(l.target);}
    if(spec.shadow&&l.shadow){l.castShadow=true;l.shadow.mapSize.set(1024,1024);l.shadow.bias=-.0002;
      if(l.isDirectionalLight)Object.assign(l.shadow.camera,{left:-6,right:6,top:6,bottom:-6,near:.01,far:100});}
    scene.add(l);entities.set(spec.id,l);
  }
  const imported=[];
  for(const spec of config.objects) {
    let object;
    if(spec.type==='model') {
      const gltf=await new GLTFLoader().loadAsync(url(spec.model));object=gltf.scene;
      if(spec.material){const m=await material(spec.material);object.traverse(child=>{if(child.isMesh)child.material=m.clone();});}
      imported.push({id:spec.id,clips:gltf.animations.map(c=>({name:c.name,duration:c.duration})),skins:0,morphs:[]});
      object.traverse(child=>{if(child.isSkinnedMesh)imported.at(-1).skins++;if(child.morphTargetDictionary)imported.at(-1).morphs.push({...child.morphTargetDictionary});});
      if(spec.animation) {
        const clip=typeof spec.animation.clip==='number'?gltf.animations[spec.animation.clip]:gltf.animations.find(a=>a.name===spec.animation.clip);
        if(!clip)throw Error(`Unknown animation ${spec.animation.clip}; available: ${gltf.animations.map(a=>a.name)}`);
        const mixer=new T.AnimationMixer(object), action=mixer.clipAction(clip);action.setLoop(T.LoopOnce,1);action.clampWhenFinished=true;action.play();
        actions.push({mixer,action,clip,settings:spec.animation});
      }
    } else if(spec.type==='group')object=new T.Group();
    else {object=new T.Mesh(geometry(spec.geometry),await material(spec.material));
      if(spec.geometry.type==='implicit')dynamic.push({object,geometry:spec.geometry,amount:spec.geometry.amount??0,last:spec.geometry.amount??0});}
    object.name=spec.id;object.position.fromArray(spec.position??[0,0,0]);object.rotation.fromArray(spec.rotation??[0,0,0]);
    object.scale.fromArray(spec.scale??[1,1,1]);object.visible=spec.visible??true;
    object.traverse(child=>{if(child.isMesh){child.castShadow=spec.cast_shadow??true;child.receiveShadow=spec.receive_shadow??true;}});
    for(const [name,weight] of Object.entries(spec.morph_weights??{}))morph(object,name,weight);
    entities.set(spec.id,object);
  }
  for(const spec of config.objects)(spec.parent?entities.get(spec.parent):scene).add(entities.get(spec.id));
  if(config.authoring) {
    const module=await import(url(config.authoring.module));
    if(typeof module.setup!=='function')throw Error('Authoring module must export setup(context)');
    author=await module.setup({THREE:T,scene,camera,renderer,entities,helpers,assetURL:url,config,
      setCamera(pose){camera.position.fromArray(pose.position);cameraTarget.fromArray(pose.target);
        if(pose.fov!==undefined){camera.fov=pose.fov;camera.updateProjectionMatrix();}}});
    if(!author||typeof author.update!=='function'||(author.state!==undefined&&typeof author.state!=='function'))
      throw Error('setup must return {update(t, frame), optional state()}');
  }
  simulations=bakePhysics();
  const post=config.post??{};
  if(post.bloom||post.aperture) {
    composer=new EffectComposer(renderer);composer.addPass(new RenderPass(scene,camera));
    if(post.aperture)composer.addPass(new BokehPass(scene,camera,{focus:post.focus??5,aperture:post.aperture,maxblur:post.max_blur??.01}));
    if(post.bloom)composer.addPass(new UnrealBloomPass(new T.Vector2(c.width,c.height),post.bloom,.4,.8));
    composer.addPass(new OutputPass());
  } else composer=null;
  return {engine:'Three.js',version:T.REVISION,physics:'cannon-es 0.20.0',objects:config.objects.length,imported,
    physics_frames:simulations.length,post:config.post??{},authoring:config.authoring?.module??null,
    camera_cuts:config._camera_cache?.cuts??[],device:renderer.getContext().getParameter(renderer.getContext().RENDERER)};
}

async function frame(f) {
  window.__okSeed?.(f);
  const time=f/config.canvas.fps;
  for(const {mixer,action,clip,settings} of actions) {
    const t=time*(settings.speed??1)+(settings.offset??0),local=settings.loop===false?Math.min(clip.duration,t):(clip.duration?t%clip.duration:0);
    action.reset().play();mixer.setTime(local);
  }
  // Explicit weights override animation values on every seek, never accumulated deltas.
  for(const o of config.objects)for(const [name,weight] of Object.entries(o.morph_weights??{}))morph(entities.get(o.id),name,weight);
  for(const track of config.tracks??[])property(entities.get(track.target),track.property,keyValue(track,time));
  // Interpolate the immutable integer-frame simulation cache for shutter samples.
  const lo=Math.floor(f),hi=Math.min(simulations.length-1,Math.ceil(f)),mix=f-lo;
  const physics=(simulations[lo]??[]).map((a,i)=>{const b=simulations[hi][i];
    return {...a,position:a.position.map((v,j)=>v+(b.position[j]-v)*mix),
      quaternion:new T.Quaternion(...a.quaternion).slerp(new T.Quaternion(...b.quaternion),mix).toArray()};});
  for(const state of physics) {const o=entities.get(state.id);o.position.fromArray(state.position);o.quaternion.fromArray(state.quaternion);}
  for(const d of dynamic)if(d.amount!==d.last){d.object.geometry.dispose();d.object.geometry=implicitGeometry(d.geometry,d.amount);d.last=d.amount;}
  if(config._camera_cache) {
    const p=helpers.sampleCamera(config._camera_cache,f);camera.position.fromArray(p.position);cameraTarget.fromArray(p.target);
    camera.fov=p.fov;camera.updateProjectionMatrix();
  }
  if(author)await author.update(time,f);
  camera.lookAt(cameraTarget);scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);
  if(composer)composer.render(0);else renderer.render(scene,camera);
  const state={camera:{position:camera.position.toArray(),target:cameraTarget.toArray(),fov:camera.fov},objects:{},physics,
    ...(author?.state?{authoring:await author.state()}:{} )};
  for(const o of config.objects) {
    const object=entities.get(o.id);let triangles=0,skins=0,morphs=[],deformed=[];
    object.traverse(child=>{if(child.isMesh){triangles+=(child.geometry.index?.count??child.geometry.attributes.position?.count??0)/3;if(child.isSkinnedMesh)skins++;
      if(child.morphTargetInfluences)morphs.push([...child.morphTargetInfluences]);
      if(child.isSkinnedMesh)for(let i=0;i<Math.min(4,child.geometry.attributes.position.count);i++)deformed.push(child.getVertexPosition(i,new T.Vector3()).toArray());}});
    state.objects[o.id]={position:object.position.toArray(),quaternion:object.quaternion.toArray(),triangles,skins,morphs,
      deformed,...(dynamic.find(d=>d.object===object)?{amount:dynamic.find(d=>d.object===object).amount,topology:object.geometry.userData.topology}:{} )};
  }
  return {png:renderer.domElement.toDataURL('image/png').split(',')[1],state};
}

window.OpenKatana3D={boot,frame};
