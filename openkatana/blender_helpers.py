"""Reusable procedural Blender geometry and materials.
Run inside installed Blender. Z-up, front -Y; no project paths or brand defaults.
SPDX-License-Identifier: MIT
"""
import math
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector



# ----------------------------------------------------------------- colours
def srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin(hexstr, a=1.0):
    h = hexstr.lstrip('#')
    return tuple(srgb_to_linear(int(h[i:i + 2], 16)) for i in (0, 2, 4)) + (a,)


def mix_hex(a, b, t):
    la, lb = lin(a), lin(b)
    return tuple(la[i] * (1 - t) + lb[i] * t for i in range(3)) + (1.0,)


# ----------------------------------------------------------------- collections
def collection(name, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    par = parent or bpy.context.scene.collection
    if c.name not in [x.name for x in par.children]:
        par.children.link(c)
    return c


def link(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def empty(name, coll, loc=(0, 0, 0), parent=None, size=0.05):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = size
    e.location = loc
    coll.objects.link(e)
    if parent:
        e.parent = parent
    return e


def mesh_obj(name, verts, faces, coll, mat=None, smooth=True, parent=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.validate(clean_customdata=False)
    if smooth:
        me.shade_smooth()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    if mat:
        o.data.materials.append(mat)
    if parent:
        o.parent = parent
    return o


def set_mat(o, mat):
    o.data.materials.clear()
    o.data.materials.append(mat)
    return o


# ----------------------------------------------------------------- materials
_MATS = {}


def _bsdf(m):
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes.get('Principled BSDF')
    return nt, b


def principled(name, color, metallic=0.0, rough=0.5, coat=0.0, coat_rough=0.04, aniso=0.0,
               transmission=0.0, ior=1.45, spec=0.5, emission=None, estrength=0.0, sheen=0.0):
    m = bpy.data.materials.new(name)
    nt, b = _bsdf(m)
    b.inputs['Base Color'].default_value = lin(color) if isinstance(color, str) else color
    b.inputs['Metallic'].default_value = metallic
    b.inputs['Roughness'].default_value = rough
    b.inputs['Coat Weight'].default_value = coat
    b.inputs['Coat Roughness'].default_value = coat_rough
    b.inputs['Anisotropic'].default_value = aniso
    b.inputs['Transmission Weight'].default_value = transmission
    b.inputs['IOR'].default_value = ior
    b.inputs['Specular IOR Level'].default_value = spec
    b.inputs['Sheen Weight'].default_value = sheen
    if emission:
        b.inputs['Emission Color'].default_value = lin(emission)
        b.inputs['Emission Strength'].default_value = estrength
    if transmission > 0:
        for attr, val in (('use_raytrace_refraction', True), ('surface_render_method', 'DITHERED')):
            if hasattr(m, attr):
                setattr(m, attr, val)
    m.diffuse_color = lin(color) if isinstance(color, str) else color
    _MATS[name] = m
    return m


def add_bump(m, kind='brushed', scale=80.0, strength=0.06, distance=0.0004, stretch=(1.0, 1.0, 40.0)):
    """Fine procedural surface detail (seeded by fixed coordinates; deterministic)."""
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = stretch
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    if kind == 'brushed':
        tx = nt.nodes.new('ShaderNodeTexNoise')
        tx.inputs['Scale'].default_value = scale
        tx.inputs['Detail'].default_value = 6.0
        out = tx.outputs['Fac']
    elif kind == 'braid':
        tx = nt.nodes.new('ShaderNodeTexWave')
        tx.wave_type = 'BANDS'
        tx.bands_direction = 'DIAGONAL'
        tx.inputs['Scale'].default_value = scale
        tx.inputs['Distortion'].default_value = 1.5
        tx.inputs['Detail'].default_value = 2.0
        out = tx.outputs['Fac']
    else:  # satin / grain
        tx = nt.nodes.new('ShaderNodeTexNoise')
        tx.inputs['Scale'].default_value = scale
        tx.inputs['Detail'].default_value = 3.0
        out = tx.outputs['Fac']
    nt.links.new(mp.outputs['Vector'], tx.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = strength
    bump.inputs['Distance'].default_value = distance
    nt.links.new(out, bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    if 'Coat Normal' in b.inputs and kind != 'brushed':
        pass
    return m


def emissive(name, color, strength):
    m = bpy.data.materials.new(name)
    nt, b = _bsdf(m)
    b.inputs['Base Color'].default_value = lin('#101010')
    b.inputs['Roughness'].default_value = 0.35
    b.inputs['Emission Color'].default_value = lin(color)
    b.inputs['Emission Strength'].default_value = strength
    _MATS[name] = m
    return m


def led_material(name, atlas_path, cols, rows, tiles, frame_driver=None,
                 colors=('#FFFFFF', '#FF8040', '#40BFFF'), strength=1.25,
                 off_level=0.06, static=False, master_strength_key=None):
    """Sample an RGB channel-mask atlas on dot_grid geometry; key FRAME deterministically.

    atlas_path is explicit; tiles is [columns, rows]. Colors are RGB-channel colors.
    frame_driver receives the Value node and must key every master-frame index.
    """
    if len(colors) != 3 or len(tiles) != 2 or min(tiles) < 1:
        raise ValueError('Supply three channel colors and positive atlas dimensions')
    if not static and frame_driver is None:
        raise ValueError('Animated display needs a frame_driver')
    m = bpy.data.materials.new(name)
    nt, b = _bsdf(m)
    N, L = nt.nodes, nt.links
    b.inputs['Base Color'].default_value = lin('#181818')
    b.inputs['Roughness'].default_value = 0.34
    b.inputs['Coat Weight'].default_value = 0.3
    b.inputs['Coat Roughness'].default_value = 0.12
    uvn = N.new('ShaderNodeUVMap'); uvn.uv_map = 'dotuv'
    sep = N.new('ShaderNodeSeparateXYZ'); L.new(uvn.outputs['UV'], sep.inputs['Vector'])

    def math(op, a, bval=None):
        n = N.new('ShaderNodeMath'); n.operation = op
        for k, v in enumerate((a, bval)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[k].default_value = float(v)
            else:
                L.new(v, n.inputs[k])
        return n.outputs[0]

    if static:
        u = math('DIVIDE', sep.outputs['X'], float(cols))
        v = math('SUBTRACT', 1.0, math('DIVIDE', sep.outputs['Y'], float(rows)))
    else:
        fv = N.new('ShaderNodeValue'); fv.name = 'FRAME'; fv.label = 'FRAME'
        fv.outputs[0].default_value = 0.0
        frame_driver(fv)  # caller keys the value with the scene frame
        fr = math('ROUND', fv.outputs[0])
        tx = math('MODULO', fr, float(tiles[0]))
        ty = math('FLOOR', math('DIVIDE', fr, float(tiles[0])))
        u = math('DIVIDE', math('ADD', math('MULTIPLY', tx, float(cols)), sep.outputs['X']), float(cols * tiles[0]))
        v = math('SUBTRACT', 1.0, math('DIVIDE', math('ADD', math('MULTIPLY', ty, float(rows)), sep.outputs['Y']), float(rows * tiles[1])))
    comb = N.new('ShaderNodeCombineXYZ')
    L.new(u, comb.inputs['X']); L.new(v, comb.inputs['Y'])
    img = N.new('ShaderNodeTexImage')
    img.image = bpy.data.images.load(str(Path(atlas_path).resolve()), check_existing=True)
    img.image.colorspace_settings.name = 'Non-Color'
    img.interpolation = 'Closest'
    img.extension = 'CLIP'
    L.new(comb.outputs['Vector'], img.inputs['Vector'])
    sepc = N.new('ShaderNodeSeparateColor'); L.new(img.outputs['Color'], sepc.inputs['Color'])
    acc = None
    for ch, channel_color in zip(('Red', 'Green', 'Blue'), colors):
        mul = N.new('ShaderNodeVectorMath'); mul.operation = 'SCALE'
        mul.inputs[0].default_value = lin(channel_color)[:3]
        L.new(sepc.outputs[ch], mul.inputs['Scale'])
        if acc is None:
            acc = mul.outputs[0]
        else:
            add = N.new('ShaderNodeVectorMath'); add.operation = 'ADD'
            L.new(acc, add.inputs[0]); L.new(mul.outputs[0], add.inputs[1]); acc = add.outputs[0]
    # faint "off" dot glow so the grid reads as a physical display
    offc = N.new('ShaderNodeVectorMath'); offc.operation = 'ADD'
    L.new(acc, offc.inputs[0])
    offc.inputs[1].default_value = tuple(x * off_level for x in lin(colors[0])[:3])
    L.new(offc.outputs[0], b.inputs['Emission Color'])
    sv = N.new('ShaderNodeValue'); sv.name = 'STRENGTH'; sv.label = 'STRENGTH'
    sv.outputs[0].default_value = strength
    L.new(sv.outputs[0], b.inputs['Emission Strength'])
    if master_strength_key:
        master_strength_key(sv)
    return m


# ----------------------------------------------------------------- primitive builders
def rounded_box(name, size, coll, mat, bevel=0.01, segments=5, parent=None, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    o.location = loc
    if parent:
        o.parent = parent
    if mat:
        o.data.materials.append(mat)
    if bevel > 0:
        bv = o.modifiers.new('Bevel', 'BEVEL')
        bv.width = bevel
        bv.segments = segments
        bv.limit_method = 'NONE'
        bv.harden_normals = False
    me.shade_smooth()
    return o


def outline_stadium(w, h, n=24):
    r = h / 2
    pts = []
    for k in range(n + 1):
        a = -math.pi / 2 + math.pi * k / n
        pts.append((w / 2 - r + r * math.cos(a), r * math.sin(a)))
    for k in range(n + 1):
        a = math.pi / 2 + math.pi * k / n
        pts.append((-w / 2 + r + r * math.cos(a), r * math.sin(a)))
    return pts


def outline_rrect(w, h, r, n=8):
    pts = []
    cs = [(w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)]
    for cx, cy, a0 in cs:
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def prism(name, outline, depth, coll, mat, bevel=0.003, segments=3, parent=None, loc=(0, 0, 0), plane='XZ'):
    """Extrude a 2D outline (x, y) along local Y (plane XZ) by depth, centred."""
    verts, faces = [], []
    n = len(outline)
    for yy in (-depth / 2, depth / 2):
        for (x, y) in outline:
            verts.append((x, yy, y) if plane == 'XZ' else (x, y, yy))
    faces.append(list(range(n))[::-1] if plane == 'XZ' else list(range(n)))
    faces.append([n + k for k in range(n)] if plane == 'XZ' else [n + k for k in range(n)][::-1])
    for k in range(n):
        k2 = (k + 1) % n
        faces.append([k, k2, n + k2, n + k])
    o = mesh_obj(name, verts, faces, coll, mat, smooth=False, parent=parent)
    bm = bmesh.new(); bm.from_mesh(o.data); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(o.data); bm.free()
    o.location = loc
    if bevel > 0:
        bv = o.modifiers.new('Bevel', 'BEVEL')
        bv.width = bevel; bv.segments = segments; bv.limit_method = 'ANGLE'
        bv.angle_limit = math.radians(40)
    o.data.shade_smooth()
    try:
        o.data.set_sharp_from_angle(angle=math.radians(35))
    except Exception:
        pass
    return o


def ring_prism(name, outer, inner, depth, coll, mat, bevel=0.0015, parent=None, loc=(0, 0, 0)):
    """Frame between two outlines with equal point counts, extruded along Y."""
    if len(outer) != len(inner) or len(outer) < 3:
        raise ValueError('Ring outlines require equal counts of at least three points')
    n = len(outer)
    verts = []
    for yy in (-depth / 2, depth / 2):
        for (x, y) in outer:
            verts.append((x, yy, y))
        for (x, y) in inner:
            verts.append((x, yy, y))
    def idx(side, ring, k):
        return side * 2 * n + ring * n + (k % n)
    faces = []
    for k in range(n):
        faces.append([idx(0, 0, k), idx(0, 0, k + 1), idx(0, 1, k + 1), idx(0, 1, k)])          # front
        faces.append([idx(1, 0, k), idx(1, 1, k), idx(1, 1, k + 1), idx(1, 0, k + 1)])          # back
        faces.append([idx(0, 0, k + 1), idx(0, 0, k), idx(1, 0, k), idx(1, 0, k + 1)])          # outer wall
        faces.append([idx(0, 1, k), idx(0, 1, k + 1), idx(1, 1, k + 1), idx(1, 1, k)])          # inner wall
    o = mesh_obj(name, verts, faces, coll, mat, smooth=False, parent=parent)
    o.location = loc
    me = o.data
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    if bevel > 0:
        bv = o.modifiers.new('Bevel', 'BEVEL')
        bv.width = bevel; bv.segments = 2; bv.limit_method = 'ANGLE'; bv.angle_limit = math.radians(40)
    me.shade_smooth()
    try:
        me.set_sharp_from_angle(angle=math.radians(35))
    except Exception:
        pass
    return o


def lathe(name, profile, coll, mat, segments=48, parent=None, loc=(0, 0, 0), angular=None, cap_top=False, cap_bottom=False):
    """Surface of revolution about local +Z from profile [(r, z), ...].
    angular(theta, r, z) -> dz optional modulation (ridges)."""
    verts, faces = [], []
    P = len(profile)
    for s in range(segments):
        t = 2 * math.pi * s / segments
        for (r, z) in profile:
            dz = angular(t, r, z) if angular else 0.0
            verts.append((r * math.cos(t), r * math.sin(t), z + dz))
    for s in range(segments):
        s2 = (s + 1) % segments
        for p in range(P - 1):
            faces.append([s * P + p, s2 * P + p, s2 * P + p + 1, s * P + p + 1])
    if cap_bottom:
        c = len(verts); verts.append((0, 0, profile[0][1]))
        for s in range(segments):
            faces.append([c, ((s + 1) % segments) * P, s * P])
    if cap_top:
        c = len(verts); verts.append((0, 0, profile[-1][1]))
        for s in range(segments):
            faces.append([c, s * P + P - 1, ((s + 1) % segments) * P + P - 1])
    o = mesh_obj(name, verts, faces, coll, mat, smooth=True, parent=parent)
    o.location = loc
    me = o.data
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bm.to_mesh(me); bm.free()
    me.shade_smooth()
    return o


def tube_curve(name, points, radius, coll, mat, parent=None, resolution=6, closed=False, smooth=True, kind='POLY',
               tilt=None, bevel_object=None):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.resolution_u = 12
    cu.bevel_mode = 'ROUND'
    cu.bevel_depth = radius
    cu.bevel_resolution = resolution
    cu.use_fill_caps = True
    if bevel_object is not None:
        cu.bevel_mode = 'OBJECT'
        cu.bevel_object = bevel_object
    if kind == 'BEZIER':
        sp = cu.splines.new('BEZIER')
        sp.bezier_points.add(len(points) - 1)
        for k, p in enumerate(points):
            bp = sp.bezier_points[k]
            bp.co = p
            bp.handle_left_type = bp.handle_right_type = 'AUTO'
            if tilt:
                bp.tilt = tilt[k]
    else:
        sp = cu.splines.new('POLY')
        sp.points.add(len(points) - 1)
        for k, p in enumerate(points):
            sp.points[k].co = (p[0], p[1], p[2], 1.0)
            if tilt:
                sp.points[k].tilt = tilt[k]
    sp.use_cyclic_u = closed
    sp.use_smooth = smooth
    o = bpy.data.objects.new(name, cu)
    coll.objects.link(o)
    if mat:
        o.data.materials.append(mat)
    if parent:
        o.parent = parent
    return o


def cylinder_between(name, a, b, radius, coll, mat, segments=24, parent=None, bevel=0.0):
    a, b = Vector(a), Vector(b)
    L = (b - a).length
    o = lathe(name, [(0.0, 0.0), (radius, 0.0), (radius, L), (0.0, L)], coll, mat, segments)
    d = (b - a).normalized()
    o.matrix_world = Matrix.Translation(a) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    if parent:
        mw = o.matrix_world.copy(); o.parent = parent; o.matrix_world = mw
    if bevel:
        bv = o.modifiers.new('Bevel', 'BEVEL'); bv.width = bevel; bv.segments = 2
        bv.limit_method = 'ANGLE'
    try:
        o.data.set_sharp_from_angle(angle=math.radians(50))
    except Exception:
        pass
    return o


def orient(o, loc, forward, up=(0, 0, 1)):
    """Place object so its local -Y (front) faces `forward` and local Z ~ up."""
    f = Vector(forward).normalized()
    y = -f
    x = y.cross(Vector(up))
    if x.length < 1e-6:
        x = Vector((1, 0, 0))
    x.normalize()
    z = x.cross(y).normalized()
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(loc)
    o.matrix_world = m
    return o


def add_bevel(o, width, segments=3, angle=None):
    bv = o.modifiers.new('Bevel' + ('A' if angle else ''), 'BEVEL')
    bv.width = width
    bv.segments = segments
    if angle:
        bv.limit_method = 'ANGLE'
        bv.angle_limit = math.radians(angle)
    else:
        bv.limit_method = 'NONE'
    return bv


# ----------------------------------------------------------------- LED dot grids
def _dome_template(rd, h, seg=8):
    v = []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        v.append((rd * math.cos(a), rd * math.sin(a), 0.0))
    for k in range(seg):
        a = 2 * math.pi * (k + 0.5) / seg
        v.append((0.72 * rd * math.cos(a), 0.72 * rd * math.sin(a), 0.62 * h))
    v.append((0, 0, h))
    f = []
    for k in range(seg):
        k2 = (k + 1) % seg
        f.append((k, k2, seg + k))
        f.append((k2, seg + k2, seg + k))
        f.append((seg + k, seg + k2, 2 * seg))
    return np.array(v, np.float64), f


def dot_grid(name, cols, rows, pitch, coll, mat, parent=None, surface='flat', radius=None,
             rd_ratio=0.40, h_ratio=0.22):
    """LED dots centred on local origin. flat: plane XZ facing -Y. cyl: column i at
    angle around a vertical axis at (0, +radius, 0) (convex toward -Y)."""
    tv, tf = _dome_template(rd_ratio * pitch, h_ratio * pitch)
    nv = len(tv)
    V, F, UV = [], [], []
    for j in range(rows):
        for i in range(cols):
            x = (i - (cols - 1) / 2) * pitch
            z = ((rows - 1) / 2 - j) * pitch
            if surface == 'flat':
                c = np.array([x, 0.0, z]); n = np.array([0.0, -1.0, 0.0]); t = np.array([1.0, 0.0, 0.0])
            else:
                ang = x / radius
                c = np.array([radius * math.sin(ang), radius - radius * math.cos(ang), z])
                n = np.array([math.sin(ang), -math.cos(ang), 0.0])
                t = np.array([math.cos(ang), math.sin(ang), 0.0])
            up = np.cross(n, t) * -1  # local z of dot frame: up
            up = np.array([0.0, 0.0, 1.0])
            # template: x->t, y->up, z->n
            base = len(V)
            V.extend((c + tv[:, 0:1] * t + tv[:, 1:2] * up + tv[:, 2:3] * n).tolist())
            F.extend([(a + base, b + base, cc + base) for a, b, cc in tf])
            UV.append((i + 0.5, j + 0.5))
    o = mesh_obj(name, V, F, coll, mat, smooth=True, parent=parent)
    me = o.data
    uvl = me.uv_layers.new(name='dotuv')
    per_vert = np.repeat(np.array(UV, np.float32), nv, axis=0)
    loop_v = np.zeros(len(me.loops), np.int32)
    me.loops.foreach_get('vertex_index', loop_v)
    uvl.data.foreach_set('uv', per_vert[loop_v].ravel())
    return o


# ----------------------------------------------------------------- text labels
def label(name, text, font_path, size, coll, mat, parent=None, extrude=0.0002, align='CENTER',
          loc=(0, 0, 0), rot=(math.pi / 2, 0, 0), spacing=1.0):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = text
    cu.font = bpy.data.fonts.load(str(font_path), check_existing=True)
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    cu.align_y = 'CENTER'
    cu.space_character = spacing
    o = bpy.data.objects.new(name, cu)
    coll.objects.link(o)
    o.data.materials.append(mat)
    if parent:
        o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    return o


# ----------------------------------------------------------------- boolean helper
def boolean_cut(target, cutters, coll_hidden, name):
    """Join cutter objects into one hidden mesh parented to the target (so the cut
    stays rigidly attached during animation) and subtract it with a live modifier."""
    bpy.context.view_layer.update()
    inv = target.matrix_world.inverted()
    bm = bmesh.new()
    for c in cutters:
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(c.evaluated_get(dg))
        me.transform(inv @ c.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        bpy.data.objects.remove(c)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    cut = bpy.data.objects.new(name, me)
    coll_hidden.objects.link(cut)
    cut.parent = target
    cut.hide_render = True
    cut.hide_viewport = True
    cut.display_type = 'WIRE'
    mod = target.modifiers.new('Cut_' + name, 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = cut
    return cut


# ----------------------------------------------------------------- keyframe helpers
def key_values(obj_or_id, path, values, index=-1, interp='LINEAR', frames=None):
    """Insert one key per frame (deterministic baked animation)."""
    frames = range(len(values)) if frames is None else frames
    target = obj_or_id
    for f, val in zip(frames, values):
        if index >= 0:
            arr = getattr(target, path)
            arr[index] = val
        else:
            setattr(target, path, val)
        target.keyframe_insert(data_path=path, index=index, frame=f)
    ad = target.animation_data if hasattr(target, 'animation_data') else None
    set_interp(target, interp, paths={path})


def set_interp(idblock, interp='LINEAR', paths=None):
    ad = getattr(idblock, 'animation_data', None)
    if not ad or not ad.action:
        return
    for fc in iter_fcurves(ad.action):
        if paths is not None and fc.data_path not in paths:
            continue
        for kp in fc.keyframe_points:
            kp.interpolation = interp


def iter_fcurves(action):
    # Blender 5 layered actions
    if hasattr(action, 'layers') and len(action.layers):
        for layer in action.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    for fc in cb.fcurves:
                        yield fc
    elif hasattr(action, 'fcurves'):
        for fc in action.fcurves:
            yield fc


def bake_camera(segments, fps, schedule_fps, frames, name='Camera', sensor_width=36.0, fstop=4.0):
    """Bake position/aim/lens/aperture and cut-safe subframes; returns (camera, target).

    Segment coordinates use schedule_fps. All masters are sampled at fps; there is
    no frame interpolation model. Cut boundaries must land on a whole master frame.
    Use a centered shutter <= 1 frame. Simulations must be baked separately.
    """
    from .camera_path import CameraTrack
    from .contracts import ContractError, number
    for v, k in ((fps,'fps'),(schedule_fps,'schedule_fps')): number(v,k,1,240)
    number(frames,'frames',2,36000,integer=True)
    scale = fps / schedule_fps
    track = CameraTrack(segments, step=1/scale)
    if segments[0]['f0'] != 0 or segments[-1]['f1'] < (frames-1)/scale:
        raise ContractError('Camera schedule must cover the whole master')
    cuts = []
    for c in track.cuts():
        master = c*scale
        if abs(master-round(master)) > 1e-7: raise ContractError('Cut does not land on a master frame')
        if 0 < master < frames: cuts.append(round(master))
    coll = bpy.context.scene.collection
    data = bpy.data.cameras.new(name); data.sensor_width = sensor_width
    cam = bpy.data.objects.new(name,data); coll.objects.link(cam)
    target = empty(name+'_aim',coll)
    constraint = cam.constraints.new('TRACK_TO'); constraint.target = target
    constraint.track_axis = 'TRACK_NEGATIVE_Z'; constraint.up_axis = 'UP_Y'
    data.dof.use_dof = True; data.dof.focus_object = target
    bpy.context.scene.camera = cam
    def put(frame,sample):
        cam.location = sample['pos']; cam.keyframe_insert('location',frame=frame)
        target.location = sample['tgt']; target.keyframe_insert('location',frame=frame)
        data.lens = sample['lens']; data.keyframe_insert('lens',frame=frame)
        data.dof.aperture_fstop = sample['fstop'] or fstop
        data.dof.keyframe_insert('aperture_fstop',frame=frame)
    for frame in range(frames): put(frame,track.sample(frame/scale))
    for cut in cuts: put(cut-.5,track.sample(cut/scale))
    for owner in (cam,target,data):
        for curve in iter_fcurves(owner.animation_data.action):
            for key in curve.keyframe_points:
                at = float(key.co.x)
                key.interpolation = 'CONSTANT' if abs(at-round(at))<1e-7 and round(at)+1 in cuts else 'LINEAR'
            curve.update()
    cam['openkatana_cuts'] = cuts
    return cam,target


def track_target(target, subject, weights, name='follow'):
    """Add a weighted tracking constraint without changing any location/cut keys.

    weights are [(master_frame, influence), ...]. Smooth sudden subject movement
    with camera_path.spring_follow on a proxy before attaching this constraint.
    """
    from .contracts import ContractError,number
    if not weights: raise ContractError('Tracking requires weight keys')
    last = -1
    for frame,value in weights:
        number(frame,'frame',0);number(value,'influence',0,1)
        if frame<=last: raise ContractError('Tracking frames must increase')
        last=frame
    c=target.constraints.new('COPY_LOCATION');c.name=name;c.target=subject
    for frame,value in weights:
        c.influence=value;c.keyframe_insert('influence',frame=frame)
    set_interp(target, 'LINEAR', paths={c.path_from_id('influence')})
    return c


def camera_samples(scene=None, cuts=None):
    """Measure evaluated camera including constraints at every frame and shutter edge.

    Horizontal field of view comes from Blender's actual projection (aspect/sensor
    fit included). Does not render or mutate scene animation; restores current time.
    """
    scene=scene or bpy.context.scene
    cam=scene.camera
    if cam is None or cam.data.type!='PERSP': raise ValueError('Select a perspective camera')
    shutter=scene.render.motion_blur_shutter
    position=getattr(scene.render,'motion_blur_position','CENTER')
    offsets={'CENTER':(-shutter/2,shutter/2),'START':(0,shutter),'END':(-shutter,0)}
    if position not in offsets: raise ValueError('Unsupported shutter position')
    old=(scene.frame_current,scene.frame_subframe);rows=[]
    try:
        for frame in range(scene.frame_start,scene.frame_end+1):
            rec={'f':frame}
            for tag,offset in (('',0),('_open',offsets[position][0]),('_close',offsets[position][1])):
                at=frame+offset;whole=math.floor(at);scene.frame_set(whole,subframe=at-whole)
                evaluated=cam.evaluated_get(bpy.context.evaluated_depsgraph_get());m=evaluated.matrix_world
                rec['pos'+tag]=list(m.translation);rec['fwd'+tag]=list((-m.col[2].to_3d()).normalized())
                if not tag:
                    rec['lens']=evaluated.data.lens
                    corners=evaluated.data.view_frame(scene=scene)
                    xs=[p.x/-p.z for p in corners]
                    rec['hfov_deg']=math.degrees(math.atan(max(xs))-math.atan(min(xs)))
            rows.append(rec)
    finally: scene.frame_set(old[0],subframe=old[1])
    return {'fps':scene.render.fps/scene.render.fps_base,'width':scene.render.resolution_x*scene.render.resolution_percentage//100,
            'height':scene.render.resolution_y*scene.render.resolution_percentage//100,
            'shutter':shutter,'cuts':list(cuts if cuts is not None else cam.get('openkatana_cuts',[])), 'rows':rows}
