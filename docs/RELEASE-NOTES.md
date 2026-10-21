# OpenKatana 0.1.0

Turn photos, footage and music into an editable film through Studio, CLI/MCP or
ComfyUI Apps. This release provides 72 shared tools, five Apps and 82 Comfy nodes.

- Typed IMAGE, VIDEO and AUDIO import, recipe editing, full VIDEO export and
  bounded IMAGE previews connect model outputs to the editor.
- Optical flow runs in OpenKatana's environment; ComfyUI does not need OpenCV.
- Manager Git-URL installs load the repository root. Installer configuration
  carries the browser path, including installed Playwright Chromium.
- A bundled eight-second example produces a real edit without an agent or models.
- Font sources are pinned upstream; public validation receipts omit local paths.
- The hosted pilot remains experimental and undeployed. No hosting or model
  generation is started by installation.

See [validation](VALIDATION.md), [setup](SETUP.md) and [limits](CAPABILITY-GAPS.md).
Generative weights, FFmpeg and Chromium are not bundled. macOS is untested.
LTX's example graph is supplied for installed weights; it is not a claim of a
completed LTX inference or competition bonus eligibility.
