# Studio and processing expansion

These tools extend the local timeline with graphics, analysis and workflow processing.

## Original lettering

`openkatana/web/letterforms.js` contains the new Switchback alphabet: original
eight-unit-grid paths with angular bowls, open joins and low crossbars. The
paths are rendered directly and can be styled with the controls below.

Existing graffiti fields remain available: hold, static, write and slam; per-letter
absolute keys; duration; regions; multiline fitting; per-line rotation, offsets and
scales; underlining; long A crossbars; ink, halo and echo; seeds, nib and bounce.
Different letter widths intentionally change exact spacing and fitting results.

## Local studio

```powershell
openkatana project-init my-edit --name "My edit"
openkatana studio my-edit
```

Open the printed local URL. Import media, select clips, choose an original edit
recipe, adjust shots, save and render. The Comfy image-workflow panel checks setup, submits/collects jobs and imports outputs.
Whole-clip processing remains available through the sequence command.
The canvas preview is silent; soundtrack
playback is available in the rendered video. Browser uploads are limited to 64 MB;
use `openkatana project-import my-edit path/to/large-video.mp4` for larger sources.

The original recipes are Pulse, Drift, Cutline and Afterglow. They are structured
editing starting points, not a copied Studio preset catalog. The planner follows
selected asset order and available source duration; it does not analyze a song or
interpret unrestricted natural-language briefs. An agent can author a full timeline
through the documented JSON contract and use the same render/review loop.

Timeline saves retain prior versions in `history/` and reject stale revisions.
Renders use saved snapshots, preserve outputs and expose success/failure. Reviews
bind to the timeline, source hashes and output. A review is not a publication action.
The server listens only on loopback and rejects foreign-host/origin writes.

## Additional renderer controls

Effects use `shot.fx`, top-level `post`, or explicit `shot.layers`. Layers retain
phase/order controls. The advanced timeline editor accepts the same JSON as the CLI.

| Family | Controls |
| --- | --- |
| Transitions | `mosaic`, `blur`, `blurIn`, `blurOut`, `fin`, `fout`, `glitch`, `magenta`, `rgbsplit` |
| Transition shortcuts | `in`/`out` accept white, flash, dip, mosaic, blur (in -> blurIn, out -> blurOut), flashlight (in -> fin, out -> fout), glitch, magenta (as `out` it plays reversed) and wipe |
| Wipes | `wipe`: kind iris/stripes/torn, direction, count, stagger, seed, feather, color, center, inversion; torn edges take `amp` (amplitude, px) and `step` (px between edge points) |
| Finishing | grain, dust, vignette, light leak; explicit Canvas blend modes remain available |
| Subject graphics | contour from alpha mask; `big` text and `burst` shape behind the subject, followed by automatic subject redraw, which also adds a default outline halo (r 14, #e2b0f0) unless `fx.outline: false`; `burst.fill` colours both the star and its letters |
| Particles | deterministic rate/burst emission, lifetime, speed, gravity, drag, wobble, colors, dot/square/spark/confetti |
| Perspective | `polygon3d` projects authored points with rotation, spin, FOV, depth and near-plane clipping; points are world pixels around the canvas centre at default depth `z` 600, so normalised 0..1 points project to sub-pixel size (validation warns `polygon3d_units`) |
| Morphs | equal-length `from`/`to` arrays of normalized 2D points, easing, fill/stroke, closed/open paths |
| Looks | grade/filter with explicit CSS filters and color washes; levels, threshold, duotone, xerox (+ accent key), neg and posterize; `studio` grade + effects and 13 named studio looks; preset strings (TIMELINE.md "Native syntax") |

Perspective and morphs operate on authored vector graphics; they do not reconstruct
3D scenes or generate new viewpoints of footage. Xerox-family looks and decorative
graphics are independently authored treatments, not verified copies of all reference
presets. Block variants of glitch/burn are functional but lack exact comparisons.

Example layer:

```json
{"type":"particles","shape":"confetti","burst":40,"rate":20,"life":1,
 "gravity":200,"seed":3,"colors":["#66e7c8","#ffd23f"],"phase":"over"}
```

`big` requires `text` and a declared font `family`. `burst` requires a declared
family when `letters` is present. Setting `cut:false` disables automatic subject
redraw for that back graphic. Alpha masks still follow sampled source frames.

## Recorded audio

Unchanged `mode:copy` remains available and is hash-checked. `mode:mix` supports
multiple supplied recordings, source trim, timeline placement, duration, volume,
speed and fades. Mix-level `loudness` {`lufs` (-40..-5), `true_peak` (default -1.5 dBTP), `lra` (11)} normalises the
finished mix with two-pass ffmpeg loudnorm (before/after measurements in `audio-mix.json`), and `duck`
[{`track`, `under`, `db` (-10), `threshold_db` (-40), `attack` (0.05 s), `release` (0.3 s)}] lowers `track` by `db`
while `under` is louder than `threshold_db`. `cues` [{`sfx`, `variant` 1-4, `at` seconds, `level_db`}] adds OpenKatana's
synthesised sound effects (list them with `list_sfx`) as tracks at their category level; the generated files live in
`.openkatana/sfx/` and are hashed into the render's input manifest. `duration` is the output track duration after speed adjustment. To fill a
duration D at speed s, the source must provide D * s seconds of audio.

```json
{"mode":"mix","gain":1,"limiter":true,"tracks":[
  {"src":"media/music.wav","start":2,"at":0,"duration":6,"volume":0.7,"fade_out":0.3},
  {"src":"media/recorded-hit.wav","at":1.5,"volume":0.5}
]}
```

The mix is finite 48 kHz stereo PCM, then AAC in the export. Peak checks reject
clipping unless levels are reduced or the limiter is explicitly enabled. Receipts
record placement, duration and peak. Source-copy and mixing are separate modes;
mixing cannot promise unchanged encoded audio bytes.

## Masks, face tracks and interpolation

Install the optional local vision dependency with `pip install -e '.[vision]'`.

```powershell
openkatana masks my-edit/timeline.json --clip A --out my-edit/matte-A --mode chroma --key '#00ff00'
openkatana masks my-edit/timeline.json --clip A --out my-edit/subject-A --mode grabcut --rect 0.1 0.05 0.8 0.9
openkatana faces my-edit/timeline.json --clip A --out my-edit/faces-A
openkatana interpolate my-edit/timeline.json --clip A --out my-edit/smooth-A --multiplier 2
```

The CLI commands print clip updates; apply them to the timeline deliberately. MCP `analyze_clip` with `apply: true`
applies them and lists every change (`changes[]`); interpolation carries mattes and face tracks and rescales shot
`srcf`. GrabCut runs per frame at <= 720 px with guided-filter edge refinement. Face tracks use OpenCV's bundled
frontal/profile and eye classifiers with Lucas-Kanade gap filling (eyes per frame; no nose/mouth model). Matte
methods are chroma distance, luma threshold, existing alpha or rectangle-initialized
GrabCut. These are not a universal semantic subject detector. Face detection uses
the separately installed OpenCV frontal-face classifier (or supplied `--cascade`),
selects a face by size/continuity, records missed detections and does not infer
identity. Box-only anchors use the existing documented eye approximation. Real
footage with occlusion, profiles, motion blur and multiple people requires review.

Local interpolation uses bidirectional Farneback flow with a cut heuristic and a
held last-frame interval. It preserves duration and endpoints, but occlusions can
produce artifacts. It makes no equivalence claim for a private interpolation model.

For slow motion, `analyze_clip` operation `retime` (CLI: `openkatana call analyze_clip` with `"operation":"retime"`)
renders a plate instead of a denser clip: exactly `output_frames` pictures at `fps` (default the canvas rate) covering
the clip's source interval `start`..`start+seconds`. Output frame j shows source time start+(j+.5)*seconds/output_frames,
warped between the two neighbouring pictures with the same flow and visibility weighting, so every output frame is a
new picture at an even step and the shot uses the plate at speed 1 from src 0 (no re-sampling or frame blending).
`take_start`/`take_seconds` bound the frames that may be used (one take: a hard cut inside is refused).
`deduplicate` collapses baked repeat runs (difference <= `duplicate_threshold`, default 0.5 on 8-bit grey) - leave it
off for intentional holds. `timing`: `frame_centre` (default without deduplicate), `even` (default with deduplicate:
pictures evenly spaced over the take, for constant-rate footage conformed by repeating frames such as 24p in 30p),
`run_centre` (each picture at the centre of its repeat run, an estimate) or `motion` (pictures timed by their measured
motion relative to a 5-pair neighbourhood, which evens out uneven conversion cadences such as frame-blended 24p in
30p; it assumes locally steady motion, so review it). The receipt `retime.json` records the cadence (frame
differences, repeat runs, unique pictures per second), the picture times, held output frames (times before the first
or after the last picture) and pairs that fell back to the nearer picture. `apply` is not available: add the returned
clip under a new name. Inspect fast motion and occlusions; optical flow can still tear there.

## Comfy SDK workflows

All execution uses the official Python SDK through a local API proxy. The native
ComfyUI endpoint is separately used for installed-node and model checks. Neither
cloud fallback nor model downloading is automatic.

```powershell
openkatana comfy-capabilities --native-endpoint http://127.0.0.1:8000
openkatana comfy-build matte --out my-edit/matte-workflow.json
openkatana comfy-build interpolation --out my-edit/flow-workflow.json
openkatana comfy-build segmentation --model YOUR_INSTALLED_BIREFNET_MODEL --out my-edit/segment.json
openkatana comfy-build generation --model YOUR_INSTALLED_CHECKPOINT --prompt "Your description" --out my-edit/generate.json
openkatana comfy-build qwen-generation --model qwen_image_2.1_int8_convrot.safetensors --encoder qwen3vl_8b_int8_convrot.safetensors --vae qwen_image_2.1_vae_bf16.safetensors --prompt "Your description" --out my-edit/qwen.json
openkatana comfy-check my-edit/generate.json --native-endpoint http://127.0.0.1:8000
openkatana comfy-submit my-edit/matte-workflow.json --out my-edit/job-001 --endpoint http://127.0.0.1:8189 --native-endpoint http://127.0.0.1:8000 --asset 1.image=my-edit/source.png
openkatana comfy-collect my-edit/job-001
openkatana comfy-import my-edit/job-001 --project my-edit --kind mask --clip A
```

Matte/interpolation builders use the two original nodes in `comfy_nodes/`. Install
OpenKatana with its vision extra in ComfyUI's Python environment, place that folder
as a new `custom_nodes/openkatana_nodes` package, and restart ComfyUI when convenient.
This development run tested them in an isolated temporary instance; it did not
install them in or restart the user's usual ComfyUI instance.

For a whole clip, use the resumable sequence processor:

```powershell
openkatana comfy-process my-edit/timeline.json --clip A --kind matte --out my-edit/comfy-masks --endpoint http://127.0.0.1:8189 --native-endpoint http://127.0.0.1:8000
```

`comfy-process`/`process_clip` builds the matte with key #00ff00, tolerance 0.18, softness 0.08 and interpolation with
multiplier 2 (no overrides); build a workflow with `comfy-build`/`build_workflow` for other values. The CLI `plan`
command auto-saves a timeline from all imported image/video assets at 1280x720/30 fps, whereas MCP `plan_edit` returns
a timeline for the given asset IDs, size and fps without saving.

Run the identical command again to collect pending work and advance to the next
frame/pair. Completed outputs are checked before reuse; input changes require a new
directory. Submission with an unknown result never automatically retries. The
sequence processor also accepts segmentation with an installed BiRefNet model, or
interpolation with the local OpenKatana node. It does not silently apply the printed
clip update to an existing edit.

Standard generation requires an installed compatible checkpoint; BiRefNet needs
its separately installed node and weights. Those two paths remain unexecuted here
because their weight categories were empty. Qwen 2.1 instead uses three separate
installed components. Its builder follows ComfyUI's official Qwen 2.1 template
(25 steps, Euler/simple, CFG 1), with no prompt-enhancer model or downloads. The
local SDK -> Qwen -> image collection -> project import path passed with a 512-square
integration sample. CLI dimensions and steps are configurable; defaults are
1024-square and 25 steps. The editor exposes all three component filenames. Model and output
license review remains specific to the chosen model. Hosted developer-platform
deployment, billing and credentials remain a separate explicit setup step.
