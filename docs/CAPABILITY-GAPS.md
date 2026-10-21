# Capability boundaries

OpenKatana supports local editing, authored 3D, morphs, compositions, advanced
text and model-workflow integration. The following limits remain explicit:

- **Model quality:** reference conditioning is not a guarantee of identity,
  semantic reconstruction or artifact-free motion. Availability and licensing
  depend on the installed model. Paid transport has offline integration tests;
  no broad live paid-provider certification is claimed.
- **3D assets:** the GLB/glTF route is tested with skin animation and morph
  targets, but not every extension or compressed asset. Blender can handle
  additional workflows; arbitrary rig transfer, cloth/fluid bakes and scripts
  require scene-specific verification.
- **Morphs:** image morphing uses correspondences and triangle warps. Solid
  morphs use sampled implicit geometry. Neither is semantic video generation.
- **Plugins:** the supported extension format is OpenKatana API 1. Native binary
  plugin ABIs and arbitrary foreign project formats are not supported.
- **HDR:** a separate high-precision finishing route is available. Canvas
  timelines remain SDR; dynamic HDR metadata and every-effect HDR compositing
  are not supported.
- **Typography:** composition text supports contextual shaping. Legacy timeline
  letter effects use codepoints. Arbitrary script/font combinations need review;
  automatic exact font identification and OCR reconstruction are not included.
- **Automatic repair:** motion measurements are candidates for review. The
  automatic revise loop makes bounded camera changes, not general creative
  rewrites or guaranteed reference reconstruction.
- **Tracking/mattes:** fast motion, occlusion, multiple faces and complex edges
  need visual checks. Some semantic workflows require additional weights.
- **Usability:** Studio exposes all tools through its library, but advanced
  scene/composition authoring still uses an agent or CLI. It is a loopback-only,
  single-user app, with no cloud account, sync service or bundled general AI.
- **Platforms:** Windows is locally tested. Consult the actual CI result before
  claiming a Windows/Linux release passes. A clean operating-system install and
  broad real-world media corpus remain separate validation tasks.

Use [the capability table](CAPABILITY-MATRIX.md) to select the correct route.
These limitations are not solved by a tool count or a successful sample render.
