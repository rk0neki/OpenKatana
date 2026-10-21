# Reusable animation production

For the alternate code-authored browser renderer, read [WEBGL.md](WEBGL.md).
Camera schedules and display atlases can be used by both paths; account for
Three.js Y-up versus Blender Z-up coordinates. `assemble_render_clips` accepts
both renderers; the existing `assemble_blender_clips` name remains compatible.

These reusable production utilities ship with OpenKatana.
Use them selectively for product films, explainers, title sequences and other
authored animation. They are building blocks, not a universal creative template.

## Choose the route

- Ordinary footage edits: the existing timeline, effects and audio tools.
- Responsive layouts and shaped multilingual text: compositions.
- Declarative 3D: `create_scene3d` and the bundled Three.js renderer.
- Procedural curves, detailed geometry, dynamic displays and Blender features:
  `create_animation_kit`, then `render_blender` with trusted original scene code.

The Blender route uses a **separately installed Blender**, not an OpenKatana-owned
3D renderer or a remote machine. The recorded local tests used Blender 5.1.2 EEVEE.
The bridge exposes this installed OpenKatana package to Blender's Python, so
`from openkatana import blender_helpers` works without personal path edits.
Blender installation is optional and never downloaded automatically. Arbitrary
trusted authoring scripts execute with local process permissions, not a sandbox.

## Six shared CLI/MCP operations

Discover exact signatures with `openkatana tools`. Submit UTF-8 JSON arguments via
`openkatana call TOOL --workspace work/projects --arguments arguments.json`.

| Tool | Input and result |
|---|---|
| `create_animation_kit` | Existing `project_id`, new `directory` (default `animation`), width/height/fps/frames. Creates editable `scene.py`, `config.json`, display recipe/atlas and score recipe. Does not render. Never overwrites an existing kit. |
| `build_display_atlas` | `project_id`, `document` below. Returns deterministic RGB channel masks, tile dimensions and a receipt. |
| `synthesize_score` | `project_id`, explicit note `document` below. Returns stereo WAV, recipe/hash and `preview_audio`. Local synthesis, no AI model. |
| `assemble_blender_clips` | `project_id`, ordered project-relative `receipts`, `contiguous` (default true). Checks frame files, dimensions, fps, source ranges, hashes inputs, and returns a timeline **proposal**. Use preview/revision-guarded save separately. |
| `analyze_render_motion` | `project_id`, absolute local video `source`, optional `cuts`, `work_width`, `moving`, `ratio`, `stall`. Measures optical flow and possible stalls/judder; requires the vision extra. |
| `analyze_camera_motion` | `project_id`, evaluated camera `document` from the helper below, optional `jolt_threshold`/`jolt_ratio`. Returns speed, aim acceleration and estimated rotational shutter streaks. |

The first tool is a small replaceable example, not a fixed film. Edit its scene,
objects, material palette, display copy, lights, animation and camera to meet the
brief. The example is self-contained; no logo, music recording, font download,
reference model or paid service is required. Keep creative assets in the project.

## Camera paths and fixes

`openkatana.camera_path.CameraTrack(segments, step=1)` is pure Python. A segment
has `f0`, `f1`, `type`, `poses`, optional `cut`, `name`, and `ease:[x1,x2]`.
Segments are ordered with shared boundaries (`previous.f1 == next.f0`). Each pose
has `pos:[x,y,z]`, `tgt:[x,y,z]`, `lens`, and optional `fstop` on all poses or none.
Timing types are `whip`, `snap`, `push`, `hold`, `accel`; position/target paths use
arc-length sampled Catmull-Rom curves. Curves can overshoot between distinct
waypoints; inspect the actual camera path. Near-identical consecutive waypoints
are merged to avoid the demonstrated loop-back at landings.

`track.sample(schedule_frame)` returns pose/lens/aperture for random access.
When the next segment is a cut, the prior move reaches its endpoint on the last
displayed frame, not on the first frame of the next shot. Use
`step=schedule_fps/output_fps`. Continuous segments match at the same schedule
time across output frame rates. A cut must land on a whole output frame.

Inside Blender, use:

```python
from openkatana import blender_helpers as H
camera, aim = H.bake_camera(segments, fps=60, schedule_fps=30, frames=240)
H.track_target(aim, subject, [(0, 0.0), (60, 0.4), (239, 0.0)])
```

`bake_camera` keys position, target, lens and aperture at every output frame.
For a centered shutter of at most one frame, it places the cut step at `cut-0.5`
and preserves CONSTANT keys before it. `track_target` changes **only its own
constraint-influence curves**. Changing cut keys to LINEAR while adding tracking
can cause cross-cut streaks.
Do not subsequently linearize all target curves. `set_interp(..., paths={...})`
restricts changes to specific data paths; an unrestricted call deliberately edits
all curves. Use explicit camera segments for intended cuts, not enormous whips.

`spring_follow(values, fps, hz=4, damping=.8, cuts=[])` creates deterministic
scalar/vector samples for a tracking proxy. It smooths the camera's reaction to
mechanical snaps and resets at cuts. Cache the returned array and key it by master
frame for reliable seeking. It is not a live simulation or automatic retargeting.

`H.camera_samples(scene)` evaluates the actual camera after constraints, at every
master frame and both shutter edges. It includes the real horizontal field of
view, dimensions and cut indices. Pass that JSON to `analyze_camera_motion`.
Its pixel estimate covers rotation only; scene depth/translation require video
review. Camera diagnostics do not automatically change an animation.

## Procedural Blender helpers

Import `openkatana.blender_helpers` only inside Blender. Coordinates are Z-up,
with asset front facing local -Y. All inputs are authored values, no model weights.

| Helpers | Purpose |
|---|---|
| `collection`, `link`, `empty`, `mesh_obj`, `set_mat` | Scene organization, parenting and mesh creation |
| `lin`, `mix_hex`, `principled`, `emissive`, `add_bump` | sRGB-to-linear colors, PBR materials and procedural surface detail |
| `rounded_box`, `outline_stadium`, `outline_rrect`, `prism`, `ring_prism` | Housings, outlines, frames and extrusions |
| `lathe`, `tube_curve`, `cylinder_between`, `orient`, `add_bevel` | Turned profiles/ridges, cables/arches, connectors and finishing |
| `dot_grid`, `led_material` | Flat/curved physical dot geometry and frame-indexed RGB mask sampling |
| `label`, `boolean_cut` | Text from an explicitly supplied font and live cut-outs; keep font/license with project |
| `key_values`, `set_interp`, `iter_fcurves` | Keyframe utilities including Blender layered actions |
| `bake_camera`, `track_target`, `camera_samples` | Cut-safe camera bake, selective tracking and actual evaluated diagnostics |

These are trusted Python building blocks, not a complete declarative geometry
schema. Avoid degenerate profiles, self-intersecting outlines and incompatible
dimensions; inspect real renders. Some Blender features vary by release. Full
Blender feature parity across versions is not claimed.

## Dynamic displays

Atlas cues have an inclusive `start`, exclusive `end`, literal `text`, optional
`channel` (0/1/2), and `reveal_frames`. Overlapping masks combine by maximum.

```json
{"cols":64,"rows":9,"frames":60,"fps":30,"tiles_x":10,
 "cues":[{"start":0,"end":30,"text":"HELLO","reveal_frames":12},
         {"start":30,"end":60,"text":"PLAY","channel":1}]}
```

The original dot font supports A–Z, a small lowercase/punctuation subset, and
spaces. Unsupported glyphs and overflow are errors; it is not advanced text
shaping. For other text, use composition/shape_text and original image textures.
Atlases are capped at 64 million pixels/16384 pixels per side; split long scenes.
`led_material` takes explicit atlas path, grid dimensions, tiles and three channel
colors. Its `frame_driver` must key the FRAME value at each master frame; use
closest filtering and absolute frame indices. No stateful texture updates or
model interpolation are needed. The starter shows this complete wiring.

## Sound and chunk assembly

`synthesize_score` accepts seconds, MIDI pitches, linear gain and equal-power pan.
Events support sine, band-limited triangle, bell and seeded noise; attack/release
are seconds inside the note. At most 180 seconds/10000 events per call; output
is 16-bit stereo PCM. It reduces gain if needed to prevent clipping; subsequent
timeline loudness/limiter remains available. Audition before accepting the cue.

```json
{"duration":2,"sample_rate":48000,"seed":7,"notes":[
 {"at":0,"duration":0.4,"midi":60,"waveform":"bell","gain":0.15},
 {"at":0.5,"duration":0.6,"midi":67,"waveform":"triangle","pan":0.2}]}
```

Continue using the existing `list_sfx`, timeline `audio.cues` and `analyze_audio`
for sound effects and timing. The new score utility adds explicit synthesis;
it does not replace those tools or impose a melody/BPM on other videos.

Render shot chunks with the existing `render_blender(start=...,end=...)`; bounds
are inclusive. Each receipt describes native frames. `assemble_blender_clips`
checks contiguous ranges and matching source hashes by default. For independently
authored scenes use `contiguous=false`; fps/dimensions/missing-frame checks still
apply. Save only after merging desired audio/overlays into the returned proposal.
There is no automatic retiming, frame doubling, gap filling or silent scaling.
External texture references and arbitrary script dependencies are not automatically
bundled; archive them beside the editable source as usual.

## Inspect, revise and verify

`analyze_render_motion` examines every decoded frame (up to 36000). Planned cut
indices refer to the incoming frame and are excluded from adjacent flow tests.
Thresholds use **actual source pixels/frame**, not a hardcoded 1920-pixel canvas:
defaults `moving=1.5`, `ratio=2.2`, `stall=.25`. Adjust to the shot's resolution and
intent. It reports exact decoded duplicates separately; static holds are allowed.
Optical flow is a heuristic, especially with flashes, occlusion and large moves.

Use camera reports to locate an aim discontinuity, inspect its source curves,
correct them, rerender the affected chunk, then reassemble and inspect playback.
The existing `revise_motion` tool handles its supported timeline camera changes;
it does not rewrite arbitrary Blender scripts. Neither report implies human
approval, automatic repair or publication readiness.

Tests: `tests/test_animation.py` exercises numerical invariants and real encoded
motion. `scripts/test_animation_live.py --workspace work/NEW_DIRECTORY` renders
an original scene through installed Blender, checks cut keys after trackers,
random seeks, chunk assembly, normal timeline/audio export and both diagnostics.
See `docs/animation-validation.json` for the latest execution evidence.
