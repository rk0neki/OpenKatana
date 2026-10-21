# Validation

Tests distinguish contract correctness, actual rendering and human creative
review. Use a new output directory for each integration run. The recorded local
platform is Windows; browser, FFmpeg and optional Blender/models are installed
separately.

## Repeatable checks

```sh
python -m unittest discover -s tests -q
python scripts/test_studio_live.py --out work/check-studio
python scripts/test_release_features.py --out work/check-release
python scripts/test_scene3d_live.py --out work/check-scene3d
python scripts/test_composition_live.py --out work/check-composition
python scripts/test_animation_live.py --out work/check-animation
python scripts/test_webgl_live.py --out work/check-webgl
```

The suite checks supported contracts, revision conflicts, malformed inputs,
frame scheduling, rendering, audio processing and network boundaries. Studio's
walkthrough exercises setup/guide clipboard actions, fixed guide controls,
import/edit/save/render, external agent saves, unsaved human edit protection and
390px layouts. These checks use synthetic inputs and no paid models.

Each feature's JSON validation summary records the scope of its last fixture
run; those are dated results, not proof every later source tree is identical.
The current release review is summarized in [RELEASE-READINESS.md](RELEASE-READINESS.md).

## Optional integrations

Local Comfy and model scripts require the relevant running service, nodes and
licensed weights. They are explicit tests, never an automatic cloud fallback.
Recorded adapter checks include Qwen/H3 references, SeedVR2, RIFE interpolation
and image upscaling. Model identity, motion quality and all parameter combinations
are not certified by a successful small inference.

MCP scripts exercise the same tool API through stdio. CLI does not need MCP.
Blender tests require an installed executable. Test outputs record actual
dependencies and receipts; do not call a missing integration a pass.

## Release packaging

Build an allowlisted source bundle with `scripts/release_bundle.py`, build a wheel
from that source, install it separately, and verify bundled guides, skill,
licenses, browser assets and a local render. CI configuration covers Windows
and Linux, but only completed CI runs establish results for a release commit.

Technical passes do not establish human approval, legal clearance, general
model fidelity or quality on arbitrary creative briefs.
# ComfyUI Apps integration â€” 2026-10-21

All 72 AgentAPI operations are exposed by the local Comfy adapter, plus four
convenience nodes and the three existing tensor nodes (79 total). See
[ComfyUI Apps](COMFY_APPS.md) and `comfy-apps-validation.json` for scope.

On Windows, the final regression suite ran 265 tests with no failures and one
optional Torch-dependent skip. Real ComfyUI 0.41.0 / frontend 1.55.18 prompts
created and reopened a shared Studio, rendered a moving WebGL morph and exported
a timeline. CLI and a real stdio MCP client read the same revision. Stale saves
and paid execution were rejected. An EmptyImage workflow submitted through the
official SDK and a temporary local proxy was collected by the background adapter
while Comfy's queue remained available. No model weights or paid services were
used. This is a queue/transport test, not a new quality test of every model.

Browser verification covered saved Apps discovery, App Mode input controls,
text-result display/download controls, Studio linking and a 640Ã—360 product video
preview. An isolated wheel loaded its 72-tool catalog, four App workflows, frontend
extension and guide. Linux integration with a running ComfyUI was not exercised
in this round; the ordinary platform CI remains applicable to shared code.

# Pre-launch review — 2026-10-21

See `prelaunch-validation.json` for the updated scope. An isolated Windows ComfyUI
root install registered 82 nodes. IMAGE batches passed through subprocess optical
flow, import, a saved timeline and VIDEO/IMAGE output. A second import preserved
the VIDEO frames and soundtrack. The fifth saved App's controls loaded in App Mode.
Root-package chroma matte and point helpers also ran in ComfyUI's own Python.
The original eight-second quick-edit example rendered with its soundtrack.
LTX's 12-node example passed schema/link checks only; no new model inference ran.

For public receipts, use `python scripts/export_validation.py receipt.json --root
PATH_TO_LOCAL_WORKSPACE --out docs/report.json`. It removes explicitly mapped roots
and rejects unknown personal paths. Keep full paths in private project receipts.
The release manifest scanner also rejects JSON-escaped Windows user paths.
