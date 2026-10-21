# Capabilities

Discover installed runtime readiness with `get_capabilities`. Availability of a
tool does not mean its optional software, weights or provider account is installed.

| Area | OpenKatana route | Dependencies and boundaries |
|---|---|---|
| Media inspection | Probe, frame extraction, contact sheets, cut/onset candidates | FFmpeg/Pillow; cuts and beats need editorial review |
| Footage editing | Retiming, ramps, freeze/reverse, camera moves, transitions, layered effects | SDR, constant output frame rate |
| Tracking and masks | Face tracks, supplied tracks, local mattes, optical flow | OpenCV; occlusion and multi-person scenes need review |
| Typography | Supplied fonts, opacity/flicker, captions, Switchback artwork | 26 bundled OFL fonts; per-letter timeline effects use codepoints |
| Complex text | Browser shaping, bidi, variable fonts, glyph geometry | Compositions; HarfBuzz/fontTools for glyph IDs/contours |
| Responsive graphics | CSS Flex/Grid, intrinsic sizing, responsive overrides | Browser composition rendering to clips |
| Plugins and operations | API 1 components/effects/operators, transactional JSON operations | Trusted local JavaScript; no arbitrary native binary plugin ABI |
| Declarative 3D | PBR, lights/shadows, camera hierarchy, GLB/glTF rigs and morph targets | Bundled Three.js; compressed asset extensions are limited |
| Code-authored 3D | Custom modules, geometry/display helpers, camera schedules | Trusted ES modules, bundled Three.js; see WEBGL.md |
| Solid morphs | Implicit shapes and marching-tetrahedra meshing | Numerical grid resolution affects detail and topology |
| Image morphs | ORB/RANSAC or explicit-landmark triangle warps | OpenCV; not semantic video reconstruction |
| Physics | Fixed-step rigid-body cache and deterministic seeking | Bundled cannon-es; JSON route does not simulate cloth/fluids |
| Cinematic rendering | Depth of field, bloom, linear-light shutter sampling | Browser rasterization; cost rises with samples/geometry |
| Full scene authoring | Optional Blender bridge and reusable production helpers | Separately installed Blender, trusted Python scripts |
| Audio | Trim/mix/fades/ducking/loudness, synthesized SFX, score synthesis | FFmpeg/NumPy; listen to final mix |
| Speech | Local transcription and caption assembly | Optional faster-whisper and installed model |
| Review/revision | Frame comparisons, authored reference plans, bounded motion loop | Camera-only automatic revisions; agent handles structural editing |
| HDR finishing | Float32 linear BT.2020, 16-bit FFV1, 10-bit HEVC PQ/HLG | Separate finishing contract; ordinary Canvas effects remain SDR |
| Model workflows | Qwen, H3, restoration, interpolation, upscale, custom graphs | Official Comfy SDK; separately installed models or authorized paid route |
| Human/agent collaboration | Studio, CLI, optional MCP, revision-protected saves | Local single-user project; no account synchronization |

See [limits](CAPABILITY-GAPS.md), [validation](VALIDATION.md), and each feature's
guide for precise contracts. Local rendering and authored animation do not
require a generation service. Optional models have their own licenses and costs.
