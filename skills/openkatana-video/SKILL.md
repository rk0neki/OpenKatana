---
name: openkatana-video
description: Create, edit, render and inspect videos with OpenKatana's CLI or MCP, including authored 3D animation, compositions, footage edits and audio. Use when the user asks to work with OpenKatana.
---

# OpenKatana video production

If not yet set up, read `docs/SETUP.md` in the OpenKatana checkout and run
`python scripts/setup.py`. It installs the CLI and this skill in the selected
project. Resume the reported project using its Python environment; do not create
a new project for every session. No account or platform-specific connector is
required. CLI is the default; MCP is optional.

When the user works inside **ComfyUI Apps**, read `docs/COMFY_APPS.md` (or
`read_guide(topic="comfy-apps")`). The installed Apps share the same AgentAPI and
workspace as Studio/CLI/MCP. Use the project and interpreter returned by **Open
Studio**, not a new parallel project. Local Apps reject paid/cloud execution.
Model operations may return an adapter background job: inspect its result and
the nested model receipt before calling it complete. Preserve request IDs and
collect existing jobs; do not resubmit to make a pending status disappear.

For a model-to-edit graph, connect decoded IMAGE frames or native VIDEO to
`OpenKatanaImportMedia`, its media/music IDs to `OpenKatanaMakeEdit`, and the
saved result to `OpenKatanaRenderVideo.after`. Keep all project IDs identical.
Connect only one image/video source; optional AUDIO supplies the soundtrack.
The VIDEO output contains the complete render; IMAGE is a sampled preview batch.
The fifth saved App and `examples/comfy/` show these connections. LTX's example
needs separately installed weights; a schema pass is not an inference test.

Discover the installed capabilities with `openkatana tools` / `get_capabilities`.
Read `read_guide(topic="agent")` and the relevant guide before forming arguments.
CLI and MCP share the same operations; use whichever the current agent supports.
For CLI calls, write UTF-8 JSON and use
`openkatana call TOOL --workspace WORKSPACE --arguments arguments.json`.
Create a project once, then resume it; keep real job IDs and receipts.

Choose the route from the requested output:

- Footage edits, retiming, effects and audio: `timeline` guide.
- Responsive motion graphics, multilingual text and original plugins:
  `composition` guide.
- Declarative WebGL 3D, model imports and morph geometry: `scene3d` guide.
- Code-authored WebGL films, custom geometry/displays and camera choreography:
  **`webgl` guide**, `create_webgl_kit` → `render_scene3d`. Bundled Three.js
  supports a procedural browser route without Blender or generation models.
- Detailed procedural Blender scenes, cut-safe camera movement, tracking,
  dynamic LED displays and chunk assembly: **`animation` guide**.
- Model assets: `comfy-models` guide. Local execution is the default. Paid use,
  uploads and model downloads require the user's applicable authorization.
  Do not assume a previous project's budget or image/video model choice applies.

For authored Blender work, `create_animation_kit` supplies an editable generic
scene and recipes. Replace its creative content to match the brief. Blender is
separately installed; `render_blender` is OpenKatana's bridge, not a remote
renderer. Python scene scripts require explicit `trusted_script=true` and execute
normal trusted local code. Use `openkatana.blender_helpers` from those scripts;
the bridge makes the installed package available without personal path edits.

The animation guide documents camera paths, geometry/material helpers,
`build_display_atlas`, `synthesize_score`, `assemble_blender_clips`,
`analyze_render_motion` and `analyze_camera_motion`. They are reusable functions
and operations, not a mandate to make every video a product film. Use the existing
composition/shaping routes for full text; LED dot glyphs have a limited inventory.

Choose WebGL for browser-authored rasterized scenes and Blender for existing
Blender assets, Cycles/path tracing or Blender-specific features. Both render
locally without a generation model. Do not assume every 3D brief needs Blender,
or promise identical output from different renderers. For custom WebGL, review
the local ES module, declare its dependency files and render with
`trusted_script=true`. Use absolute time, including fractional shutter samples.
`render_scene3d` supports inclusive `start`/`end` chunks; `assemble_render_clips`
validates their receipts and also accepts Blender clips. Use `contiguous=false`
only for deliberately independent shots. Both routes feed the same timeline.

Preserve these demonstrated production invariants:

- One absolute master-frame clock; native rendering at the requested fps.
  Camera schedules may use a separate explicit time base.
- Cut boundaries use protected camera steps. Adding trackers must change only
  their influence curves, not linearize every target/location key.
- Smooth a camera tracking proxy around mechanical snaps when appropriate;
  leave intentional object motion intact. Cache deterministic follower samples.
- Verify chunk order, source ranges, dimensions and fps. Assembly returns a
  proposal; retain existing audio/overlays deliberately and save with a revision.
- Render previews and inspect motion, text, edges and audio. Flow/jolt flags are
  candidates, not aesthetic verdicts. Inspect flagged frames, fix the source,
  rerender affected chunks and check the final encode. Do not claim listening
  review if the client cannot play audio.

Record actual tool calls, sources/licenses, costs, fixes and unresolved issues.
Distinguish generated reference images from pixels included in the final film.
Keep reusable code and declared dependencies in the project; avoid undeclared
private-directory dependencies. Publish only when the user requests publication;
agent review is not human approval or a guarantee of output quality.
