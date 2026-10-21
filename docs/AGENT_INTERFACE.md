# Editing with an agent: CLI and optional MCP

Your agent makes the creative decisions. OpenKatana supplies the local tools,
and Studio supports human direction, adjustment and review.

Start with [SETUP.md](SETUP.md) and `python scripts/setup.py`. The same prompt
and CLI workflow apply to every agent. Studio’s Brief & media step exports briefs
with project context; Tools exposes the operation catalog and guides. External
saves refresh when the human has no unsaved edits. Read the latest revision
before saving. See [Studio](STUDIO.md).

## Optional MCP setup

Install with `python -m pip install -e ".[mcp,vision]"` in an isolated environment.
FFmpeg, FFprobe and Chrome/Edge are also required. `openkatana doctor` checks them.
The MCP extra uses the official Python SDK's supported v1 maintenance line,
bounded below version 2. The stdio server opens no network listener.

Start it with:

```powershell
openkatana mcp --workspace PATH_TO_YOUR_EDIT_PROJECTS
```

To connect an MCP client, register a stdio server that runs the environment's
Python executable by absolute path:

```powershell
PATH_TO_PYTHON -m openkatana mcp --workspace PATH_TO_YOUR_EDIT_PROJECTS
```

`mcp.example.json` shows the portable configuration shape. A local `.mcp.json`
contains machine-specific paths and is ignored by Git. Your client may ask you to
trust the newly configured server; that is a client setting. Do not disable
client permissions globally.

## Agent workflow

1. Call `get_capabilities`, then `read_guide` for `agent`, `timeline` and `effects`.
   Report missing dependencies and unsupported requested features honestly.
2. Create a project. Inspect the user-selected existing video using `inspect_media`
   and `preview_source`. Use actual returned pictures when choosing source ranges.
3. Import selected excerpts with `import_media`. `start`, `duration` and optional
   `max_width` are explicit preparation choices. Use `audio_only:true` to extract a
   video's soundtrack. Original source files are never changed. Imported video
   excerpts omit audio; import the soundtrack separately when needed.
4. Read `get_project` for media IDs. Author the complete timeline, including cuts,
   camera, typography, masks/effects and audio. `plan_edit` and `build_recipe` are only
   optional starting points; Your agent is responsible for creative decisions. For music, use
   `analyze_audio` (tempo, beat grid, sections) and `plan_music_edit` (beat-aligned cuts);
   `transcribe_audio` writes word timings locally (faster-whisper with a Whisper model already
   in the local cache; never downloaded) and `make_captions` turns word timings into caption
   events. `plan_storyboard` plans a music edit as slots with briefs and slate pictures before
   footage exists; `fill_storyboard` puts imported clips into slots and reports the verdict
   ("GAPS storyboard: k of n slots still to fill" or "FILLED"). `build_recipe` also takes one of
   12 OpenKatana presets (`get_capabilities` presets). `process_clip` kind `cutout` makes a
   point-click subject cut-out through ComfyUI (SAM2 video model, already installed). `list_sfx` lists the
   synthesised sound effects for `audio.cues`; `render_page` turns a deterministic HTML page
   into a clip. With a reference video, `analyze_energy` measures its cuts/flashes/shake and
   `revise_motion` checks (and boundedly revises) the edit's camera energy against it.
   Review mattes with `review_mask` and generated material with `bind_reference` /
   `inspect_identity`; `set_review_policy` can make these reviews (and source inspection and
   previews) required before `start_render`.
5. Validate, then `save_timeline` with the current revision (null for a first save).
   A stale save is rejected. Earlier versions remain in the project history.
6. Use `preview_timeline` at opening, cut boundaries, text entrances and endings.
   MCP includes up to four actual JPEG preview images plus structured metadata.
   Up to twelve images can be saved per call; use `view_image` for further images.
   CLI previews return file paths for the agent's image-reading tool.
7. Call `start_render` with a stable request ID such as `first-cut-v1`. It returns
   a job immediately. Poll `get_render`; a repeated request ID reuses the job.
   A changed timeline needs a new request ID. A failed/interrupted job is never
   automatically restarted under the old ID.
8. Inspect the resulting video and its audio where the client supports playback,
   plus selected full-quality output frames. Record an honest `review_render`:
   agent approval is not human approval. Revise and render with a new request ID
   as necessary. Deliver the local MP4 and brief editing/validation notes.

Do not claim that a silent frame preview verifies audio, or that metadata checks
establish aesthetic quality. Use the selected project and installed OpenKatana runtime.
Do not publish, upload, download models or submit paid/hosted jobs automatically.

## Same tools through the CLI

`openkatana tools` lists the same 72 named operations and arguments as MCP (unknown arguments are rejected on both).
Every operation can be called without an MCP connection:

```powershell
openkatana call get_capabilities --workspace projects
openkatana call create_project --workspace projects --arguments create.json
openkatana call save_timeline --workspace projects --arguments edit.json
openkatana call start_render --workspace projects --arguments render.json
openkatana call get_render --workspace projects --arguments status.json
```

Argument files are UTF-8 JSON objects matching the tool parameters. For example:

```json
{"project_id":"first-edit","request_id":"first-cut-v1"}
```

CLI results are JSON on stdout; errors go to stderr with a nonzero exit code.
Existing direct commands (`prepare`, `validate`, `render`, `masks`, `faces`,
`interpolate`, `comfy-*`, `studio`) remain available. The shared `call` surface
adds full project inspection, revision-aware saves, previews and persistent jobs.

## Analysis and Comfy

`analyze_clip` exposes local masks, face detection and optical flow. Outputs stay
inside the project, including nested directories. `apply:false` returns an update
for inspection; `apply:true` saves a new timeline revision. Face detections can
miss glasses/profiles and produce false positives; visually inspect the track.

`build_workflow`, `check_workflow`, `submit_workflow`, `collect_workflow`,
`import_workflow_output` and `process_clip` share the official Comfy SDK bridge.
Supply installed model names explicitly. ComfyUI and the local API proxy must
already be running. Stable request IDs preserve uncertain submission receipts.
No automatic resubmission, model download, cloud fallback or publishing tool exists.

The server serializes tool dispatch to protect SDK endpoint selection and project
mutations. Renders run in separate recorded workers. Keep the MCP connection open
until completion: some hosts (including the tested Windows SDK client) terminate
child processes when disconnecting. Reconnecting recovers recorded status; a killed
worker is reported as interrupted and needs an explicit new request ID to restart.

## References

- [Official MCP Python SDK v1](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)
- [Timeline contract](TIMELINE.md), [effect/workflow guide](EXPANSION.md)

Setup guidance checked on 2026-10-17. No creative demo is implied by interface tests.

See [editor tools and reference plans](EDITOR_TOOLS.md) for the tool schemas
and typography controls. Restart an existing MCP client after a tool update
to rediscover the catalog.

## Local and paid Comfy models

See [COMFY_MODELS.md](COMFY_MODELS.md). `submit_workflow` now accepts
`execution="local"` (default) or `execution="cloud"`. Cloud requires
`endpoint="https://cloud.comfy.org"`, `allow_paid=true` and an environment
`COMFY_API_KEY`. Obtain the user's authorization for the job and source upload
before setting allow_paid; the flag records authorization, it does not obtain it.
Never invent a price or promise a spending cap: this integration does not enforce
one. Check the selected provider's current pricing before proposing a paid job.
Keep a stable request_id. `collect_workflow` resumes the recorded backend/job.
`import_workflow_output` supports images/masks and video/audio; select the exact
`output_file` from the receipt when multiple mixed media outputs are present.
`build_workflow`, `check_workflow` and `process_clip` still target local ComfyUI.


## 2026-10-20: independent 3D expansion

Actual 3D scene rendering is now available. Read [the scene guide](SCENE3D.md)
(from the repository root: docs/SCENE3D.md) or `read_guide(topic="scene3d")`.
The added operations are `create_scene3d`, `inspect_model3d`, `import_model3d`,
`check_scene3d`, `render_scene3d` and `render_blender`. They use bundled MIT
Three.js/cannon-es or separately installed Blender. See CAPABILITY-GAPS.md
for runtime limits and unverified combinations.

## Compositions and plugin operations (2026-10-20)

The current inventory is 72 operations. Read `read_guide(topic="composition")`
for responsive layouts and contextual text shaping. Use `create_composition`,
`save_composition`, `inspect_composition`, `render_composition`, `list_plugins`
and `run_plugin_operator`. Rendered compositions return normal timeline clips.
Plugin operators return proposals; save only with the revision they were based on.
This is OpenKatana's original extension API, not a private native ABI. Existing
canvas per-letter effects do not acquire complex shaping merely by updating;
choose the composition route for those text runs.

## Release additions

`shape_text` exports HarfBuzz-shaped glyph IDs, clusters, contours and SVG.
`edit_timeline` validates atomic revision-guarded timeline operation batches.
Read [release tools](RELEASE-TOOLS.md) for parameters and limits.

HDR and models: `import_hdr_media`, `render_hdr`, and `run_model_workflow` are shared CLI/MCP operations. Read `hdr` and `comfy-models` before using them. Inspect clipping and media before approving an HDR export; never describe an SDR proxy as the HDR original.

## Reusable authored-animation workflow

Read `read_guide(topic="animation")` / [ANIMATION.md](ANIMATION.md). The six new
operations are `create_animation_kit`, `build_display_atlas`, `synthesize_score`,
`assemble_blender_clips`, `analyze_render_motion` and `analyze_camera_motion`.

## WebGL or Blender authoring

Read `read_guide(topic="webgl")` before choosing an authored 3D renderer.
`create_webgl_kit` makes a portable JavaScript scene using bundled Three.js;
`render_scene3d` now supports reviewed authoring modules (`trusted_script=true`),
cut-safe camera schedules and inclusive `start`/`end` chunks. Use
`assemble_render_clips` for ordered WebGL/Blender receipts. This returns a
validated proposal, never replaces the current timeline, and rejects gaps and
source/renderer mismatches by default. Choose installed Blender for its own
scene features/Cycles rather than assuming all 3D needs it. Both routes are local.
They share this CLI/MCP interface. The existing render_blender bridge exposes
OpenKatana helpers to the installed Blender Python. These tools use original
project code with declared local dependencies.
