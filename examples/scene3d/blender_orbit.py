"""Original editable Blender example; run through OpenKatana's trusted-script route."""
import bpy
from mathutils import Vector

bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.render.resolution_x=320;scene.render.resolution_y=180;scene.render.resolution_percentage=100
scene.render.fps=12;scene.frame_start=1;scene.frame_end=3
scene.world.color=(.15,.15,.15)
bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=16,location=(0,0,1))
hero=bpy.context.object;hero.name='Original sphere'
mat=bpy.data.materials.new('Copper');mat.diffuse_color=(.8,.2,.05,1);mat.use_nodes=True
shader=mat.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(.8,.2,.05,1)
shader.inputs['Metallic'].default_value=.6;shader.inputs['Roughness'].default_value=.25;hero.data.materials.append(mat)
hero.location.x=-.3;hero.keyframe_insert(data_path='location',frame=1)
hero.location.x=.3;hero.keyframe_insert(data_path='location',frame=3)
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,0))
bpy.ops.object.light_add(type='AREA',location=(2,-2,5));light=bpy.context.object;light.data.energy=1000;light.data.shape='DISK';light.data.size=5
light.rotation_euler=(Vector((0,0,1))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(4,-5,3));scene.camera=bpy.context.object
scene.camera.rotation_euler=(Vector((0,0,1))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
