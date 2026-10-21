# Formats and runtime compatibility

OpenKatana validates its documented timeline, composition and scene formats.
Unknown fields are rejected rather than silently discarded.

- [Timeline contract](TIMELINE.md): clip references, frame/time ranges, camera,
  effects, layers, text, audio and declared project hooks.
- [Compositions](COMPOSITIONS.md): versioned responsive layouts and API 1 plugins.
- [3D scenes](SCENE3D.md): local GLB/glTF, geometry/materials, animation and physics.
- [WebGL authoring](WEBGL.md): trusted local ES modules evaluated at absolute time.
- [Model workflows](COMFY_MODELS.md): public Comfy node schemas and official SDK
  transport; installed nodes and weights must pass preflight.

Rendering uses the installed browser and FFmpeg. Browser, font and codec versions
can affect output. Receipts retain inputs, implementation hashes and render
parameters so comparisons can be scoped to an exact environment.

Assembly checks frame order, dimensions, frame rate, renderer identity and source
ranges. It rejects incompatible chunks instead of silently conforming them.
Imports do not imply support for every codec or every glTF extension.

External plugins, proprietary project formats and native binary ABIs are not
automatically converted. Port creative intent to a supported document or plugin.
See [capability boundaries](CAPABILITY-GAPS.md) and [validation](VALIDATION.md).
