// Editable original example. Replace shapes, layout, palette and timing for your own brief.
// setup runs once; update must derive every animated value from absolute time/frame.
export async function setup({THREE:T,scene,helpers:H,assetURL,config}) {
  const group=new T.Group();group.name='authored-device';group.position.y=.85;scene.add(group);
  const body=new T.Mesh(H.roundedBox([2,.9,.55],.12),new T.MeshPhysicalMaterial({color:'#397487',metalness:.5,roughness:.25,clearcoat:.8}));
  body.castShadow=true;body.receiveShadow=true;group.add(body);
  const display=await H.atlasDisplay({assetURL});display.mesh.position.set(0,.03,.287);group.add(display.mesh);
  const cable=new T.Mesh(H.tube([[-.8,.35,0],[-1.3,1,0],[-.8,1.6,0],[.8,1.6,0],[1.3,1,0],[.8,.35,0]],{radius:.055}),
    new T.MeshStandardMaterial({color:'#e9ad57',metalness:.3,roughness:.3}));cable.castShadow=true;group.add(cable);
  const knob=new T.Mesh(H.lathe([[0,0],[.16,0],[.2,.05],[.16,.18],[0,.18]]),new T.MeshStandardMaterial({color:'#d2e4e7',metalness:.8,roughness:.2}));
  knob.position.set(.65,.45,0);knob.castShadow=true;group.add(knob);
  return {
    update(t,f){group.rotation.y=.12*Math.sin(t*2);knob.rotation.y=t*2;display.update(f);},
    state(){return {display_frame:display.tile,rotation:group.rotation.y,custom_meshes:4,
      geometry_vertices:[body,cable,knob].map(m=>m.geometry.attributes.position.count)};}
  };
}
