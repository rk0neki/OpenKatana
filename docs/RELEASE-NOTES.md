# OpenKatana 0.1.3

After Effects' Distort, Light and Time effects, written as code, and a ComfyUI node to preview any effect. 75 shared
tools (new: `preview_effect`) and 88 Comfy nodes.

## Effects

- **Distort pack**: Wave Warp, Ripple, Shockwave, Twirl, Bulge, Polar Coordinates, Kaleidoscope (CC Kaleida) and
  Mirror (`local_wave_warp` ... `local_mirror`), with After Effects' parameter names, eased keyframes on the main
  amounts, region and feather, reflect/clamp/wrap edges and antialiased high quality. A pinch (negative bulge) never
  folds the picture.
- **Light pack**: `local_deep_glow` (a multi-layer, energy-conserving bloom above a threshold, with tint and
  saturation), `local_lens_flare` (procedural flares with the 50-300mm zoom, 35mm and 105mm prime ghost sets, halo,
  rainbow ring, anamorphic streak and flicker), `local_light_rays` (CC Light Rays-style rays from bright areas) and
  `local_light_sweep` (a CC Light Sweep shine). Nothing changes where nothing is bright enough.
- **Time pack**: After Effects' Echo (all seven operators), Time Displacement (horizontal, vertical, radial, self or
  clip maps, for slit-scan and time-ripple looks), Posterize Time and frame blending. Each reads other frames of its
  own shot through a nested render that stops at the effect, so text and grades placed later are drawn once, on top;
  posterize time followed by echo gives a stop-motion trail.
- **Effect packs**: effects can now ship as packs (`web/fx_*.js` with a Python validator); the engine awaits them and
  gives time effects the shot at other frames.

## ComfyUI and agents

- **`preview_effect`**: a short MP4 and a six-frame contact sheet of any shot effect, the packs included, on a moving
  test card (grid, shapes, text, a light spot, a bouncing ball, a frame counter), a project image or a video excerpt.
  Text effects use the project's fonts or a bundled OFL font. In ComfyUI it is the **OpenKatana · Preview effect** node.

## Docs

- The README says why OpenKatana is different and shows the new effects; the Koji clip credits its Suno music.

# OpenKatana 0.1.2

After Effects-grade displacement, texture overlays and frame-level reference matching. 74 shared tools (two new:
`shot_sheet` and `eye_sheet`) and 87 Comfy nodes.

## Effects

- **`local_turbulent_displace`**: After Effects' Turbulent Displace for plates,
  graphics and type, with its controls: turbulent, bulge and twist (each with a
  smoother mode), horizontal, vertical and cross displacement; amount, size,
  complexity (fractional, 1-10), evolution and offset with keyframes and eases (Easy
  Ease, hold, cubic-bezier); Cycle Evolution for seamless loops; pinning including the
  locked pins; antialiased high quality; edge reflect, clamp or wrap. Beyond After
  Effects: a stepped boil, drift and a feathered region for one word.
- **`local_displacement_map`**: After Effects' Displacement Map. Another clip's red,
  green, blue, alpha, luminance, hue, lightness or saturation (or full / half / off)
  moves the picture, with separate horizontal and vertical amounts, stretch, centre or
  tile fit and wrap-around edges, so real heat-haze, glass and water plates bend the
  footage.
- **Timeline `overlays`**: texture plates (dust, scratches, light leaks) with 13 blend
  modes, keyframed opacity, their own picture rate (24p on a 60-fps canvas), black
  floor, tint and fit; and **adjustment layers** that grade everything beneath them at
  a partial strength.
- **`local_curve`**: a cut transition given frame by frame (scale, offset, blur, glow,
  exposure), as measured from a reference.
- Hooks declare the images they need with `prepare()`; each is recorded with its
  SHA-256 in the input manifest and the receipt.

## Reference analysis

- Every reference is analysed at **60 fps**, never lower, so every motion is caught.
  `analyze_reference` `measure` runs on a 60-fps clock and returns cuts versus
  exposure dips, picture cadence, look per shot, texture speck rate and the median cut
  transition as `local_curve` arrays.
- `compare_reference` adds a side-by-side video and a look comparison; `shot_sheet`
  numbers the shots of a render or reference; `eye_sheet` crops the eyes across a take.
- Timelines with NaN or Infinity anywhere are rejected; previews flag flat frames.

# OpenKatana 0.1.1 — early access

Six ComfyUI Apps and 85 nodes, an effects playbook for agents and complete
installable packages. Watch the [one-minute demo](https://youtu.be/sZys4qLAprw).

## ComfyUI

- **00 Full workflow** puts every App in one graph: one project ID feeds Open
  Studio, video, music and photo uploads, Make edit → Render to video, a 3D
  starter and any of the 72 tools. New installs and agents open it first.
- Video, Music and Photo upload nodes bring the integration to 85 nodes. Empty
  media slots are skipped instead of failing the run.
- Running Open Studio opens Studio in its own app window.
- Make edit's `extra_media_ids` accepts one connected media ID as well as a
  JSON list.
- Preflight accepts autogrow ports whose template input is optional, required
  autogrow containers and V3 MatchType links, so graphs with core nodes such as
  ReferenceMultiLatent, BatchImagesNode and ComfySwitchNode pass.

## Comfy Cloud and the Comfy SDK

- Cloud submissions pass `COMFY_API_KEY` to partner (API) nodes, which
  previously failed with "Unauthorized: Please login first to use this node".
  The key is not written to job files.
- The local Comfy SDK client is built without credentials, so local and private
  endpoints do not receive the cloud API key in an Authorization header.

## Agents

- The [effects playbook](EFFECTS-PLAYBOOK.md) covers motion and camera, light,
  texture, colour, text and interface techniques, with how a launch film used
  each one. Agents read it before planning every edit so they know the full
  palette; nothing in it is compulsory and the user's brief decides. Setup
  installs a copy beside the project skill and preserves customized copies.

## Packaging and checks

- Version 0.1.1 is published on the [Comfy Registry](https://registry.comfy.org/nodes/openkatana).
  Installation of explicitly selected version 0.1.1 through Manager passed
  with a fresh editor environment. Registry review was still pending on
  2026-10-29; default/latest installation remains unverified. See the
  [installation steps](COMFY_APPS.md#comfy-registry-and-manager).
- Wheels include the effects playbook, the complete Comfy example script with
  its source media and credits, the README visuals and the ComfyUI node installer.
- A clean-wheel check creates a fresh environment, verifies installed
  resources against the source files, renders both bundled examples and exercises
  Studio outside the source checkout. It runs on the Windows and Linux CI matrix.
- The README opens with the demo, and the node installer points new users to
  00 Full workflow.
- Hosting estimates separate a ten-reviewer CPU demo from optional model
  generation. The hosted pilot remains experimental and undeployed.

FFmpeg and a browser are separate prerequisites. This is not a standalone desktop
installer. macOS and production hosting remain unverified. See [setup](SETUP.md)
and [publishing](PUBLISHING.md) for release checks and installation.

# OpenKatana 0.1.0

Turn photos, footage and music into an editable film through Studio, CLI/MCP or
ComfyUI Apps. This release provides 72 shared tools, five Apps and 82 Comfy nodes.

- Typed IMAGE, VIDEO and AUDIO import, recipe editing, full VIDEO export and
  bounded IMAGE previews connect model outputs to the editor.
- Optical flow runs in OpenKatana's environment; ComfyUI does not need OpenCV.
- Manager Git-URL installs load the repository root. Installer configuration
  carries the browser path, including installed Playwright Chromium.
- A bundled eight-second example produces a real edit without an agent or models.
- A real LTX-2.5 Cloud sample, exact MIT-licensed generation graph and local
  ramp/freeze editing example are included. Repeating the edit needs no credits.
- A generated [tool reference](TOOLS.md) lists all 72 tools by area.
- Font sources are pinned upstream; public validation receipts omit local paths.
- The hosted pilot remains experimental and undeployed. No hosting or model
  generation is started by installation.

See [validation](VALIDATION.md), [setup](SETUP.md) and [limits](CAPABILITY-GAPS.md).
Generative weights, FFmpeg and Chromium are not bundled. macOS is untested.
LTX-2.5 inference and the subsequent local edit were tested as separate stages.
OpenKatana's own Comfy Cloud submission (`comfy-submit`, then `comfy-collect`)
was tested separately with the LTX-2.5 graph; local LTX inference was not tested.
This functional smoke test does not establish competition bonus eligibility.
