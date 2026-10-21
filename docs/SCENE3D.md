# Real 3D scenes in OpenKatana

OpenKatana can now create and render actual 3D scenes locally. Use this route for
meshes, imported objects, animated rigs, lights, shadows and camera travel. The
older Canvas2D projection helpers remain useful for simple graphics; they are not
the limit of the application.

The browser engine is bundled **Three.js 0.180.0 (MIT)** with **cannon-es 0.20.0
(MIT)** for rigid bodies. OpenKatana's scene contract, adapters, implicit mesher,
templates and validation use local files. No external CDN, model download or
generation call is needed for authored 3D.
An optional installed Blender supplies a separate full scene/script route.

For code-authored WebGL films, custom geometry, animated displays, cut-safe
camera paths and chunked renders, read [WEBGL.md](WEBGL.md). Use
`create_webgl_kit` with the same `render_scene3d` operation; Blender is optional.

## Agent workflow

Read `read_guide(topic="scene3d")` and discover the current tools. Do not tell a
user that OpenKatana has no full 3D rendering path.

1. `create_scene3d(project_id, name, template)` makes a new editable `scenes/NAME/scene.json`.
   Templates are `product`, `morph` and `physics`. Alternatively supply a complete
   `scene` object to the same tool. Existing scenes are never overwritten by creation.
2. For supplied models, use `inspect_model3d(source)` to discover clips/skins/morphs,
   then `import_model3d(project_id, source, destination="scenes/NAME/assets/MODEL")`.
   The importer copies verified local dependencies into a new folder. Asset rights
   are not inferred from a successful import.
3. Edit the JSON through the agent's ordinary file tools. Paths inside the scene
   are relative to the scene file, such as `assets/MODEL/product.glb`.
4. `check_scene3d(project_id, scene="scenes/NAME/scene.json")` checks the contract
   and assets. `render_scene3d(..., preview_frames=[0,30,60])` renders actual stills.
5. Inspect the stills. Omit `preview_frames` for a full render. It returns PNG frames,
   a project-relative `clip`, an MP4, input/runtime hashes and diagnostic states.
6. Add the returned clip to the normal timeline, then combine it with footage,
   text, effects and audio. Use the normal preview/render/review workflow.

These operations use the same MCP and `openkatana call` CLI interfaces as other
editing tools. Restart an existing MCP server to discover the added tools.
Rendering is synchronous; keep the client connected. Each invocation makes a new
output directory. This route does not yet have the timeline render-job recovery API.

## Direct CLI

```powershell
openkatana scene3d init my-scene --template product --width 1280 --height 720 --fps 30 --frames 90
openkatana scene3d check my-scene/scene.json
openkatana scene3d render my-scene/scene.json --out my-scene/preview --stills 0,30,60,89
openkatana scene3d render my-scene/scene.json --out my-scene/final
openkatana scene3d inspect-model supplied-model.glb
openkatana scene3d import-model supplied-model.glb my-scene/assets/product
```

Outputs must be new directories. `--no-video` keeps only the PNG sequence and
receipts. The direct CLI returns an absolute clip path: convert `frames_dir` to
your timeline's project-relative path before saving it. The agent tool does this
conversion for its configured project.

## Scene contract

Schema 1 uses metres, seconds, XYZ vectors, radians for Euler rotations and
degrees for camera FOV. Unknown and inapplicable fields are errors.

| Field | Contract |
| --- | --- |
| `schema` | `1` |
| `canvas` | `width`, `height` (even, 16..4096), integer `fps` (1..120), `frames` (1..36000), optional `transparent` |
| `background` | `#RRGGBB`, default dark blue |
| `environment` | `studio` (built-in room reflections), `none`, or local Radiance `.hdr` |
| `exposure` | ACES exposure, default 1 |
| `camera` | `type`: perspective/orthographic; `position`, `target`, `fov`, `near`, `far`; orthographic `span` |
| `lights` | Unique `id`, `type`: ambient/directional/point/spot; `color`, `intensity`; applicable `position`, `target`, `shadow`, `angle`, `distance`, `decay` |
| `objects` | Unique `id`; `type`: mesh (default)/model/group; optional group `parent`, `position`, `rotation`, `scale`, `visible` |
| `tracks` | `target` ID, `property`, ordered `keys: [[seconds,value],...]`, `interpolation`: linear/smooth/step |
| `physics` | `gravity` vector and integer `substeps` per output frame (default 4) |
| `post` | `bloom`, depth-of-field `focus`, `aperture`, `max_blur` |

Meshes have a `geometry` and optional `material`, `cast_shadow`, `receive_shadow`.
Geometry types and fields:

| Type | Options |
| --- | --- |
| box, plane | `size: [x,y,z]`; plane uses x/y |
| sphere | `radius`, `radial_segments` |
| torus | `radius`, `tube`, `radial_segments`, `tubular_segments` |
| cylinder, cone | `radius`, `height`, `radial_segments` |
| extrude | Closed `points: [[x,y],...]`, optional `holes` rings, `depth`, `bevel` |
| implicit | `from`, `to`: sphere/box/torus descriptors; `amount` 0..1, `grid` 8..64, `bound` |

Implicit geometry blends signed-distance fields and remeshes with marching
tetrahedra. A sphere can become a ring with an actual hole. This is an authored
shape transformation, not an automatic semantic morph between unrelated models.
Keep the complete surface inside `[-bound,+bound]`; clipped surfaces are errors.
`states.json` records grid and quantized topology diagnostics. Singular intermediate
shapes and very thin features still require inspection; endpoint checks do not
certify every interpolated mesh.

Materials support `color`, `metalness`, `roughness`, `clearcoat`, `transmission`,
`thickness`, `ior`, `opacity`, `emissive`, `emissive_intensity`, local `map` and
`normal_map`, and `double_sided`. Imported materials are retained unless a
replacement `material` is explicitly provided. Colours are `#RRGGBB`.

Models use `model: "assets/example.glb"` and optional
`animation: {"clip":"Walk","speed":1,"offset":0,"loop":true}`. Clip can also be
a zero-based index. Existing glTF skins and morph targets render through Three.js.
`morph_weights: {"Smile":0.4}` explicitly overrides named targets. Unknown clip
or morph names fail. This does not auto-rig or retarget arbitrary characters.

Animation tracks support object `position`, `rotation`, `scale`, `visible` (step
only), material `color`, `opacity`, `metalness`, `roughness`, `emissive_intensity`,
implicit `amount`, imported `morph.NAME`, light `color`/`intensity` and applicable
light `position`/`target`, and camera `position`/`target`/perspective `fov`.
Values hold before/after the first/last key. `smooth` uses smoothstep. Rotations
interpolate Euler components; author rotations intentionally to avoid wrap surprises.
Only one track may own a given target/property. All sampling uses absolute time.

Physics objects have `body` with `shape` sphere/box/plane, `mass` (zero is static),
`radius` or full `size`, optional `velocity`, `angular_velocity`, `friction` and
`restitution`. Plane local normal is +Z, so a ground plane rotates -pi/2 about X.
Bodies must be root objects at unit scale; no conflicting transform tracks.
The whole simulation is baked at a fixed timestep before rendering, so reverse
seeks read cached poses. Discrete collisions can tunnel at high speed: increase
substeps and inspect. This route does not implement cloth, fluids or joint authoring.

## Imported model boundaries

Local `.glb` and `.gltf` support base glTF 2, textures, hierarchy, existing animation,
skins, morph targets and the material extensions accepted by `inspect_model3d`.
Remote/escaping dependencies and unsupported extensions are rejected. Draco,
Meshopt and KTX2 are not enabled in this version; export uncompressed glTF or use
Blender to convert a compatible source. Missing assets do not become silent placeholders.

The browser uses WebGL2 via software ANGLE/SwiftShader for a consistent local
baseline. Performance depends on scene complexity. It is a real rasterized 3D
renderer, not a path tracer. For Cycles/path tracing, use installed Blender.
Transparent PNG plates require post effects disabled; MP4 is always opaque.

## Installed Blender

`render_blender` renders a project-relative
`.blend`, or executes a trusted `.py` authoring script and then renders its scene.
Blender's own Python API can author geometry, rigs, materials, animation and
simulations. This is a full application bridge; individual Blender features need
their own scene tests before any compatibility claim.

```powershell
openkatana scene3d blender examples/scene3d/blender_orbit.py --trusted-script --out work/blender-demo
openkatana scene3d blender my-scene.blend --engine CYCLES --start 1 --end 24 --out work/cycles-demo
```

Install Blender yourself or set `OPENKATANA_BLENDER`. No binary is bundled or
downloaded. Source scenes remain unchanged; the output includes an editable
`rendered-scene.blend` copy, frames, MP4 and receipts. Blender automatic script
execution is disabled; a supplied Python authoring script is executed only with
`trusted_script=true` / `--trusted-script`. These scripts have normal local process
access: **this is not a security sandbox**. Use trusted scripts and assets only.
Simulation runs sequentially; bake caches for reliable random-access reuse.
Textures are checked, but external simulation caches, linked libraries and arbitrary
script dependencies are not automatically packaged. Keep them with your project.

## Evidence and provenance

`scripts/test_scene3d_live.py` generates original synthetic inputs, renders product,
morph, physics and an animated/skinned glTF, checks reverse seeks, verifies sphere
and torus endpoint topology, and renders a 3D plate through the existing timeline.
`tests/test_scene3d.py` tests contracts, dependency boundaries and pinned hashes.
The Blender example is included project code; user scripts and assets need their
own redistribution rights. See THIRD_PARTY_NOTICES.md for external software.

Dependency source URLs, exact versions, archive integrity and per-file hashes are
in `openkatana/web/vendor3d/manifest.json`. Reproduce the selection using
`scripts/vendor_scene3d.py` (explicit network access; never used during rendering).
See [capability gaps](CAPABILITY-GAPS.md) for what remains unverified or missing.


## Image-pair morphs

The seventh added operation, `morph_images`, creates a geometric warp between two
local images. It uses installed OpenCV (vision extra): ORB features and RANSAC for
automatic correspondences, or explicit `points` with `source` and `target` arrays
of 3..128 paired `[x,y]` landmarks. Coordinates are normalized to the final padded
canvas and strictly inside 0..1; the four canvas corners are fixed automatically.
Inputs preserve their aspect ratio with black padding and are converted to RGB.

The output has actual triangle warping plus a colour blend, PNG plates, MP4 and a
correspondence receipt. It preserves the prepared source/target endpoint images.
Missing/rejected features require landmarks; there is no silent dissolve fallback.
Folded or collapsed triangles fail before rendering. Always inspect intermediate
frames: this is geometric matching, not semantic model-based video generation.

```powershell
openkatana morph-images first.png last.png --out work/morph --frames 60 --fps 30
openkatana morph-images first.png last.png --points landmarks.json --out work/morph-guided
```

The agent tool takes `project_id`, local absolute `source`/`target`, optional
`width`, `height`, `fps`, `frames`, and a `points` object; it returns a project-relative
clip to use in the normal timeline. No hosted service is contacted.

## Temporal shutter sampling

Set top-level `motion_blur` to `{ "samples": 8, "shutter": 0.5 }`. See
[RELEASE-TOOLS.md](RELEASE-TOOLS.md) for fractional-time sampling, alpha handling,
physics interpolation and validation evidence.

## Reusable production helpers

Read `read_guide(topic="animation")` or docs/ANIMATION.md for original procedural
geometry/materials, cut-safe camera paths and tracking, deterministic display
atlases and score synthesis, validated chunk assembly, and rendered/evaluated
motion diagnostics. These are packaged tools, not private project dependencies.
The distributable agent skill is skills/openkatana-video/SKILL.md.
