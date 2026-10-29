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
