# Code-authored WebGL films

Author a procedural 3D scene in JavaScript, evaluate it at absolute time, render
frames in Chromium and assemble the film locally. OpenKatana bundles
**Three.js 0.180.0 (MIT)** with its license. No generation model is required.

## Choose the renderer

| Need | Route |
| --- | --- |
| JSON-authored meshes, glTF models, rigs, morphs, physics and keyframes | `create_scene3d` → `render_scene3d`; see [SCENE3D.md](SCENE3D.md) |
| Custom procedural geometry, animated displays, arbitrary Three.js materials/shaders and code-driven choreography | `create_webgl_kit` → edit the module → `render_scene3d` |
| Existing `.blend` scenes, Cycles/path tracing, Blender-specific modifiers, rigs or simulations | `create_animation_kit` / `render_blender`; see [ANIMATION.md](ANIMATION.md) |
| Responsive layout and shaped multilingual typography | Compositions, rendered separately and placed on the timeline |

WebGL is rasterized 3D. Blender EEVEE is another rasterized option; choosing
Blender is not evidence of model generation or hosted credit costs. Both local
routes output PNG clips and MP4, need no generation credits, and can be mixed in
one timeline. Blender must be installed separately; the WebGL library is bundled.
The browser and FFmpeg still need to be installed (`openkatana doctor`).

## Agent workflow

1. Read `read_guide(topic="webgl")`. Use CLI or MCP; they expose identical tools.
2. `create_webgl_kit(project_id, directory="webgl", width=640, height=360,
   fps=30, frames=60)` creates a new editable folder. It never overwrites one.
3. Customize `scene.json`, `scene.js` and `display.json` for the brief. The starter
   is a generic technical example, not a required visual style or finished film.
4. `check_scene3d(project_id, scene="webgl/scene.json")` validates the contract
   and local dependency paths without executing the authoring module.
5. Review the JavaScript, then use `render_scene3d(..., trusted_script=true,
   preview_frames=[0,29,30,59])`. Inspect geometry, camera, texture, shadow and text.
6. Render fully by omitting `preview_frames`, or use inclusive `start`/`end`
   ranges. Render attempts use new output directories. Retain each `receipt` path.
7. `assemble_render_clips(project_id, receipts=[...])` produces a timeline
   proposal. Add audio/overlays, preview and `save_timeline` with the appropriate
   revision. The existing `assemble_blender_clips` remains compatible.
8. Inspect rendered motion; `analyze_render_motion` can flag candidate stalls or
   jolts. Correct the source and rerender affected ranges. Flags are not an
   aesthetic verdict. Native scene output is silent until audio is assembled.

For CLI calls, place arguments in a UTF-8 JSON file:

```powershell
openkatana call create_webgl_kit --workspace work/projects --arguments kit.json
openkatana call render_scene3d --workspace work/projects --arguments preview.json
```

Direct scene CLI also works without an agent project:

```powershell
openkatana scene3d init work/my-film --template webgl --frames 90 --fps 30
openkatana scene3d check work/my-film/scene.json
openkatana scene3d render work/my-film/scene.json --out work/my-preview --trusted-script --stills 0,44,45,89
openkatana scene3d render work/my-film/scene.json --out work/my-chunk --trusted-script --start 0 --end 44
```

## Authoring contract

The normal schema-1 scene gains optional `authoring` and `camera_path` fields.
The normal scene's lighting, environment, imported models, physics and post
effects remain available. The custom module can add Three.js objects directly.

```json
"authoring": {
  "module": "scene.js",
  "files": ["display/atlas.png", "display/receipt.json", "extra-module.js"]
}
```

All paths are relative to `scene.json`. Declare every local file the module
loads, including imported modules, textures, models, fonts and JSON. Requests for
undeclared files or outside services fail the render. Source/assets/runtime are
hashed in the receipt; changing them between chunks fails contiguous assembly.
Use `assetURL("relative/path")` for assets. Ordinary relative ES imports resolve
against the importing module. Import `three` or supported `three/addons/...`
modules from the bundled import map; no CDN is needed. Only the selected addons
listed in `web/vendor3d/manifest.json` are bundled; missing addons fail explicitly.

```javascript
export async function setup({THREE:T, scene, camera, renderer, entities,
                              helpers:H, assetURL, config, setCamera}) {
  const mesh = new T.Mesh(H.roundedBox([1, 1, 1], .1),
    new T.MeshPhysicalMaterial({color:'#417f96', metalness:.6, roughness:.2}));
  scene.add(mesh);
  return {
    update(t, frame) { mesh.rotation.y = t; },
    state() { return {angle: mesh.rotation.y}; }
  };
}
```

`setup` runs once, may be async, and must return `update(t, frame)`. `state()` is
optional and returns JSON-serializable diagnostics for `states.json`. Both may
be async. `frame` can be fractional for shutter sampling; `t = frame/fps`.
Derive animation from absolute time or precomputed immutable caches. Do not use
incremental rotations, wall-clock time or unseeded external randomness. The host
resets its deterministic random seed per sample and checks forward/reverse
samples, but finite sample checks cannot prove an arbitrary script deterministic.

Evaluation order: imported clips and explicit tracks → cached physics → optional
camera path → custom `update` → camera look-at → render/post. `setCamera` updates
position, look-at target and optional vertical FOV; direct camera rotation is
overridden by look-at. A custom camera override deliberately takes precedence
over the scheduled path. Post settings are declared before boot; dynamic post
authoring is not part of the helper contract.

This is trusted JavaScript running in the render browser, with access to its
declared project inputs. It is not a general untrusted-code security sandbox.
`trusted_script=true` acknowledges a reviewed module, not permission to read
unrelated files or use paid services. Structural checks never execute the module.

## Reusable helpers

| Helper | Purpose |
| --- | --- |
| `H.roundedBox(size, radius, segments)` | Bevelled procedural housing geometry |
| `H.tube(points, {radius,segments,sides,closed})` | Cables, paths and curved tubes; consecutive repeated points removed |
| `H.lathe([[radius,height],...], segments)` | Knobs, vessels and other revolved profiles |
| `await H.atlasDisplay({assetURL,atlas,receipt,width,height,pixelSize,colors})` | Plane with a frame-indexed dot display; returns `mesh`, `update(frame)`, `tile` |
| `H.sampleCamera(cache, frame)` | Interpolates baked poses without blending across hard cuts |

Full bundled Three.js APIs are available for geometry/materials beyond these
conveniences. Custom objects do not automatically enter the JSON `entities` or
physics registry; author their animation directly or declare physics objects in
the scene JSON. Return custom diagnostics through `state()`.

Display atlases use `build_display_atlas` from the animation guide. Copy its PNG
and receipt into the scene folder, or keep a new output folder inside that scene,
and declare both paths. Use the same fps as the scene, or explicitly convert the
frame in `update`; the helper does not silently resample mismatched rates. During
motion blur it selects the nearest native frame. Its original dot font is limited;
use compositions or licensed font textures for full typography.

`camera_path` takes `segments`, optional `schedule_fps` and `sensor_width` (36mm
default). Its segments use the same `f0`, `f1`, `type`, `poses`, `cut` contract as
the animation guide. Pose coordinates are native Three.js **Y-up**, lens is mm,
and the horizontal sensor fit is converted to vertical FOV. No implicit Blender
Z-up conversion occurs. It must start at zero and cover the last frame; cuts
must align to output frames. It cannot coexist with camera tracks or an
orthographic camera. Lens focus/f-stop are not inferred as browser DOF settings;
set `post.focus`, `post.aperture`, `post.max_blur` explicitly.

## Chunk integrity and limits

`start` and `end` are inclusive, zero-based source frames. Each chunk's PNG files
are renumbered from `00000.png`, while `states.json` retains absolute frames.
Previews retain source frame filenames and produce no assemblable clip. Preview
indices and chunk ranges cannot be combined. Forward/reverse checks include
global samples and chunk endpoints; chunks use the full absolute scene clock.

Contiguous assembly rejects gaps, overlaps, source/renderer differences, missing
frames and dimension/fps differences. Set `contiguous=false` only to concatenate
deliberately independent shots, including WebGL and Blender clips. It does not
silently conform different frame rates or resolutions.

WebGL receipts include the declared assets and renderer implementation hashes.
Existing Blender receipts hash the authoring source; arbitrary external Blender
script dependencies/caches are not automatically inventoried. Preserve and
review them as described in the Blender guide.

WebGL uses software ANGLE/SwiftShader for the tested baseline. Complex geometry,
large atlases, shadows, post effects and shutter samples can be slow. Transparent
plates require post effects disabled. This is an SDR renderer; HDR finishing is a
separate pipeline. Arbitrary scene quality and full imported-model compatibility
require scene-specific review. Blender remains available when its
rendering or scene features fit the brief better.

Validation: `tests/test_webgl_authoring.py`, `scripts/test_webgl_live.py`, and
`webgl-validation.json` record the original fixtures and their tested scope.
