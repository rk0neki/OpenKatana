# OpenKatana 0.1.1 — early access

- Wheels include the effects playbook, complete Comfy example script,
  source media and credits, README visuals, and Comfy installer.
- Setup installs the effects playbook beside the project skill and preserves
  customized files. Agents read it to know the full palette of effects;
  creative choices follow the user's brief and nothing in it is compulsory.
- The README opens with the competition demo, and the ComfyUI section and the
  node installer point new users to the 00 Full workflow App.
- A clean-wheel check creates a fresh environment, verifies installed resources,
  renders both bundled examples and exercises Studio outside the source checkout.
- Competition hosting estimates distinguish a ten-reviewer CPU demo from optional
  model generation. The hosted pilot remains experimental and undeployed.

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
