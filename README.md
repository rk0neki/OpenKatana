# OpenKatana

Create and edit videos with your AI agent, then refine and review them in a local
Studio. OpenKatana supplies the editing and rendering tools; your agent supplies
the creative direction. **0.1.0rc2 — release candidate.**

![Local renders and layout examples](docs/assets/capabilities.png)

## Start with your agent

Copy this into any agent that can work with local files and a terminal:

```text
Set up OpenKatana so we can create and edit videos together.

Clone https://github.com/rk0neki/OpenKatana.git, or reuse my existing checkout.
Read docs/SETUP.md and run python scripts/setup.py from the repository.
Use python3 if that is the Python 3.11+ command on my system.

Load the openkatana-video skill installed in the project's .agents/skills folder.
Use the environment and project reported by setup. Check the doctor and
get_capabilities output, explain missing dependencies, and open Studio.

Use the CLI for editing and local execution by default. Ask before model
downloads, paid jobs, uploads or publishing. Do not generate anything during
setup. Tell me when the CLI and skill are ready.
```

One setup flow works across agents. No OpenKatana account, OAuth connection or
embedded AI subscription is required. See [setup](docs/SETUP.md) for manual
installation, system dependencies and existing projects.

## What you can make

- **Footage edits:** retiming, ramps, freeze/reverse, camera moves, shake,
  transitions, masks, particles, vector morphs and layered typography.
- **Music-led edits:** audio trim/mix/fades/ducking, beat estimates, captions,
  synthesized effects and optional local transcription.
- **3D films:** PBR materials, lights/shadows, GLB/glTF skin animations and morph
  targets, topology-changing solids, rigid-body physics, depth of field and bloom.
  Author declarative scenes or custom Three.js modules; use installed Blender for
  its scene tools, simulations or Cycles rendering.
- **Motion graphics:** responsive Flex/Grid compositions, contextual multilingual
  text, glyph contours, reusable component/effect/operator plugins and 26 OFL fonts.
- **Model workflows:** official Comfy SDK integration, local model preflight,
  persistent jobs, output import and resumable processing. Optional paid routes
  require explicit authorization. Models are installed separately.
- **Human + agent review:** 72 shared MCP/CLI operations, revision-safe timeline
  changes, previews, render review and bounded motion revision.

Studio keeps these capabilities discoverable through Start, Studio, Tools and
Review. Agent saves appear in the editor without overwriting unsaved human edits.
The guide toolbar keeps **Copy guide** and **Close** visible while reading.

## Try local 3D

With the environment created by setup activated:

```sh
openkatana scene3d init my-scene --template morph
openkatana scene3d render my-scene/scene.json --out my-scene/render-001
```

This creates PNG frames, an MP4 and render receipts using the bundled WebGL
runtime. Other templates include `product`, `physics` and `webgl`. Custom scripts
require review and `--trusted-script`. No generation model is needed for this example.

## Documentation

- [Setup](docs/SETUP.md) · [Studio](docs/STUDIO.md) · [Agent guide](docs/AGENT_INTERFACE.md)
- [Timeline](docs/TIMELINE.md) · [Editor tools](docs/EDITOR_TOOLS.md) · [Effects](docs/EXPANSION.md)
- [3D scenes](docs/SCENE3D.md) · [WebGL](docs/WEBGL.md) · [Blender production](docs/ANIMATION.md)
- [Compositions/plugins](docs/COMPOSITIONS.md) · [HDR](docs/HDR.md) · [Comfy models](docs/COMFY_MODELS.md)
- [Capabilities](docs/CAPABILITY-MATRIX.md) · [Limits](docs/CAPABILITY-GAPS.md) · [Validation](docs/VALIDATION.md)
- [Contributing](CONTRIBUTING.md) · [Agent skill](skills/openkatana-video/SKILL.md)

Windows is the locally tested platform. CI is configured for Windows and Linux;
check the results for your release commit. Chrome/Chromium, FFmpeg, optional
Blender and model weights are separate installations. Rendering needs an agent
or CLI; Studio is not a full graphical 3D scene editor.

## License

OpenKatana is distributed under [Apache-2.0](LICENSE). Bundled dependencies retain
their own licenses and copyright notices; see [NOTICE](NOTICE) and
[third-party notices](THIRD_PARTY_NOTICES.md). External software, models and user
media have separate terms. The project license does not grant rights to them or
guarantee legal clearance. See [licensing](docs/LICENSING.md).
