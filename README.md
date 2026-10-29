<p align="center">
  <img src="docs/assets/openkatana-wordmark.png" alt="OpenKatana logo" width="240" height="64">
</p>

# OpenKatana

OpenKatana is an independent, open-source **editing engine your AI agent drives: your photos, footage and music in, a finished edit out; cuts, transitions, motion, typography and music in one shared project, all made with code.** Inspired by Higgsfield's Katana, built with the Comfy Developer Platform, with local open-weights workflows and optional authorized API models. **Version 0.1.1** [#OpenSourceHiggsfield](https://comfy.org/open-source-higgsfield/).

[![Comfy Registry](https://img.shields.io/badge/Comfy_Registry-OpenKatana-00A67E)](https://registry.comfy.org/nodes/openkatana)
[![Release v0.1.1](https://img.shields.io/badge/release-v0.1.1-blue)](https://github.com/rk0neki/OpenKatana/releases/tag/v0.1.1)
[![CI](https://github.com/rk0neki/OpenKatana/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/rk0neki/OpenKatana/actions/workflows/ci.yml)
[![Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](docs/SETUP.md)
[![Demo](https://img.shields.io/badge/%E2%96%B6-Demo-red)](https://youtu.be/sZys4qLAprw)

## See it in motion:

### Aura Farm Koji

[![Finished Koji anime edit made with OpenKatana: cuts, effects and motion](docs/assets/koji-edit.gif)](docs/assets/koji-edit.mp4)

**[Watch the anime edit with sound](docs/assets/koji-edit.mp4)** — the finale from the OpenKatana launch film.
Source animation: [“Koji” by Ammonite & Zean](https://www.youtube.com/watch?v=61zI4eE92xM) (CC BY); edited with OpenKatana.

### Motif

[![Eight-second preview of MOTIF, made with OpenKatana and Blender; click for the full 24-second MP4](docs/assets/motif-preview.gif)](docs/assets/motif-1080p60.mp4)

**[Watch or download MOTIF — 1080p, 60 fps, with sound](docs/assets/motif-1080p60.mp4)**

A 24-second product film with procedural 3D objects, choreographed cameras, animated displays, typography and an original soundtrack. OpenKatana offers code-authored WebGL rendering for 3D scenes, with a Blender option available too. This MOTIF export used the Blender option; OpenKatana assembles and finishes the film. No video-generation model was used. The GIF shows an eight-second preview at reduced resolution and frame rate; the MP4 preserves the original 1080p/60fps export and audio. [Artwork and film credits](docs/assets/readme-visuals.json).

## Quick start

**ComfyUI Manager:** search **OpenKatana**, or run `comfy node install openkatana`
with Comfy CLI configured for your ComfyUI installation. Then complete the
[editor setup and Apps installation](docs/COMFY_APPS.md#comfy-registry-and-manager).
Registry review is pending for 0.1.1; if Manager cannot resolve it, use the source install below.

**With your agent:** copy and send the existing setup prompt:

**Copy the setup prompt**

```text
Set up OpenKatana so you can create and edit videos for me with code.

1. Download the project with:
   git clone https://github.com/rk0neki/OpenKatana.git
2. Open the downloaded OpenKatana folder, read docs/SETUP.md,
   and run python scripts/setup.py.
3. Read the openkatana-video skill that setup installs for my first project.
4. If I use ComfyUI, install the OpenKatana nodes (docs/COMFY_APPS.md) and
   open the 00 Full workflow App first. Then check the required tools,
   open Studio, and tell me when it is ready.

Use the local CLI by default. Ask before downloading models, spending credits,
uploading files or publishing. Do not generate a video during setup.
```

**Manual:**

```sh
git clone https://github.com/rk0neki/OpenKatana.git
cd OpenKatana
python scripts/setup.py
```

Python 3.11+ and Git are required. Setup prepares the Python environment, first
project and agent skill. FFmpeg and a supported browser are separate installations;
Blender and generative models are optional. Use `python3` if that is your Python
3.11+ command and follow the next commands printed by setup. There is no OpenKatana
login. [Full setup guide](docs/SETUP.md) · [Optional MCP setup](docs/AGENT_INTERFACE.md).

## Use it in ComfyUI

[![OpenKatana in ComfyUI: Full workflow, App mode, Run, then Studio opens](docs/assets/demo-comfyui.gif)](https://youtu.be/sZys4qLAprw)

[OpenKatana on the Comfy Registry](https://registry.comfy.org/nodes/openkatana)
uses node ID `openkatana` and publisher `rk0neki`. See the
[Manager installation and editor setup steps](docs/COMFY_APPS.md#comfy-registry-and-manager).
Registry review can delay version availability in Manager; the source installation
above remains available.

**Start with Apps → OpenKatana → 00 Full workflow.** It puts every App in one graph:
one project ID feeds Open Studio, your video, music and photo uploads, Make edit →
Render to video, a 3D starter and any of the 72 tools. Run it from App mode and
Studio opens in its own window.

OpenKatana includes six saved Apps: **Full workflow**, plus **Open Studio**, **All tools**, **Make a 3D scene**, **Background job**
and **Video to edit**. The integration offers 85 nodes for its tools plus project,
job and media helpers.

Connect a local model's image frames or video output to **Import media → Make edit
→ Render to video**, then open the same project in Studio to refine it.

After setup, ask your agent to follow the [ComfyUI Apps installation guide](docs/COMFY_APPS.md).
The Apps run locally; cloud and paid generation are disabled in that route.
Authorized model calls are available separately through the CLI/agent workflow.

## What can you make?

Turn a folder of photos into a story, cut footage to music, animate typography,
or build a product film from a 3D scene. Your agent writes the edit and calls the
tools; you set the direction and refine the result in Studio.

- **Edits with rhythm:** cuts, speed ramps, transitions, camera moves, beat analysis,
  audio mixing and sound effects.
- **3D films and morphs:** code-authored WebGL scenes, materials, lights, camera paths,
  rigs and morphs, with an optional Blender rendering workflow.
- **Motion graphics:** animated lettering, multilingual text shaping, responsive
  layouts, masks and reusable effects.
- **Finishing:** frame previews, motion checks, HDR workflows and video export.
  Restoration and generation adapters use separately installed or authorized models.

OpenKatana offers **72 CLI/MCP tools** ([see them all](docs/TOOLS.md)). Your agent supplies the creative
decisions; OpenKatana executes them and keeps an editable project on your machine.

![OpenKatana capabilities: 3D and morphs, type and graphics, editing and sound](docs/assets/openkatana-capabilities.png)

## How it works

1. **Bring a brief and media.** Describe the film, add footage, photos or music,
   or ask for an original scene made with code.
2. **Let your agent author it.** The agent plans shots, writes scene or animation
   code, and builds the timeline using OpenKatana's tools.
3. **Render locally.** Preview frames, render scenes and assemble the edit with
   typography, effects and sound.
4. **Review and refine.** Watch the result, give feedback, adjust it in Studio,
   and export when it is ready.

![Four-step workflow: bring your idea, your agent authors, OpenKatana renders, you review](docs/assets/openkatana-workflow.png)

Studio, ComfyUI Apps, CLI and optional MCP work with the same project. You can
move between agent instructions and hands-on review without starting over.
The two AI-generated illustrations explain the product; the films above show actual rendered output.

## Documentation and compatibility

- [Setup](docs/SETUP.md) · [Studio](docs/STUDIO.md) · [Agent guide](docs/AGENT_INTERFACE.md) · [All tools](docs/TOOLS.md)
- [Timeline](docs/TIMELINE.md) · [Editor tools](docs/EDITOR_TOOLS.md) · [Effects](docs/EXPANSION.md) · [Effects playbook](docs/EFFECTS-PLAYBOOK.md)
- [3D](docs/SCENE3D.md) · [WebGL](docs/WEBGL.md) · [Blender](docs/ANIMATION.md)
- [Compositions](docs/COMPOSITIONS.md) · [HDR](docs/HDR.md) · [Models](docs/COMFY_MODELS.md)
- [Capabilities](docs/CAPABILITY-MATRIX.md) · [Limits](docs/CAPABILITY-GAPS.md) · [Validation](docs/VALIDATION.md)
- [Contributing](CONTRIBUTING.md) · [Skill](skills/openkatana-video/SKILL.md) · [Release notes](docs/RELEASE-NOTES.md)

CI covers Windows and Linux on Python 3.11 and 3.12; check the completed runs for
the commit you install. **macOS is untested.** FFmpeg, Chromium, optional Blender
and generative weights are separate installations. Studio is not a full graphical
3D scene editor. There is no hosting bill for the local app.

<details>
<summary>Experimental hosting and remote MCP</summary>

The [hosted pilot](docs/HOSTING.md) prepares account workspaces, queued rendering
and remote MCP. It is experimental and not deployed. Production identity,
isolation, backups and model services need deployment-specific validation.
See [security](SECURITY.md) and [hosting costs](docs/HOSTING-COSTS.md).

</details>

## FAQ

**Do I need a GPU?** No dedicated GPU is required for the standard editing and
rendering workflow. Generation is optional; model and 3D workloads have their own requirements.

**Does it cost anything?** OpenKatana is free to use locally. Paid cloud models
are optional; your chosen agent provider may charge for its service.

**Which agents work?** Claude Code and Codex are tested. Use an agent that can
read local files and run commands.

**How is it different from Higgsfield's Katana?** It's open, local, edits your
own media, and contains no Higgsfield code. Built for **#OpenSourceHiggsfield**.

**Can I use it in ComfyUI without an agent?** Yes, through the Apps.

## Acknowledgments

Thanks to **Comfy** for the SDK and platform, **Lightricks** for LTX-2.5,
the [font authors](openkatana/fonts/manifest.json), and
[NASA's media sources](examples/quick-edit/assets/sources.json).
[Model and workflow credits](examples/comfy/assets/sources.json) ·
[Third-party notices](THIRD_PARTY_NOTICES.md).

## Independence

OpenKatana is inspired by Higgsfield's Katana and is not affiliated with,
endorsed by, or sponsored by Higgsfield AI. It does not connect to Higgsfield's
services. Those names identify the inspiration; their use does not imply
endorsement or trademark rights. It contains no Higgsfield code, prompts,
presets or assets. The project and its bundled dependencies have
the licenses and source records linked below.

## License

OpenKatana uses [Apache-2.0](LICENSE). Bundled components retain their own licenses
and notices; see [NOTICE](NOTICE) and [third-party notices](THIRD_PARTY_NOTICES.md).
External software, models and media have separate terms. The project license
does not grant rights to them or guarantee legal clearance. See [licensing](docs/LICENSING.md).
