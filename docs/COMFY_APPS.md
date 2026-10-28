# OpenKatana in ComfyUI Apps

Run OpenKatana locally from ComfyUI's Apps panel. The integration offers every
shared AgentAPI tool (currently 72), plus the existing three tensor utilities and
seven convenience/media nodes (82 nodes total). Studio, CLI and MCP continue to use the same project
files and revision checks. ComfyUI Apps is an additional entry point.

No hosted server, account, cloud credits or model download is needed for editing
and WebGL rendering. Model-dependent operations still require their installed
local models and nodes. This adapter rejects paid/cloud execution; it does not
change the separate CLI's authorized cloud capabilities. It is a trusted local
integration, not a public multi-user service or a sandbox for untrusted scripts.

## Install

Download the OpenKatana source release or use a checkout. Run the ordinary
[setup](SETUP.md) first, then use its reported Python interpreter:

```sh
python scripts/install_comfy_nodes.py --comfy-root PATH_TO_COMFYUI
```

`PATH_TO_COMFYUI` is the data folder containing `custom_nodes`, `user`, `input`
and `output`. `--python PATH_TO_OPENKATANA_PYTHON` selects another installed
OpenKatana environment; `--workspace PATH_TO_PROJECTS` selects an existing shared
workspace. The default is `ComfyUI/output/OpenKatana`. The script links the node
pack, writes `user/openkatana/config.json`, and installs six App workflows under
`user/default/workflows/OpenKatana`. It does not pip-install into ComfyUI or
download dependencies. Existing edited Apps and differing configuration are
preserved. Stop active work, restart ComfyUI once and refresh its interface.

On Windows, automatic discovery supports the older Desktop configuration;
passing `--comfy-root` also works with newer Desktop installations. Other ComfyUI
profiles can import the supplied `.app.json` files from
`comfy_nodes/example_workflows`. `--remove` removes only the node link; your Apps,
configuration and projects remain yours. Do not move/remove the OpenKatana
installation while its link is in use.

A Manager **Install via Git URL** clone into `custom_nodes/OpenKatana` now loads
through the root entry point. Run `python scripts/setup.py` there, then the node
installer with that environment's Python. It detects the existing root install
and does not create a duplicate link. Installing the node pack alone does not
install the editor's separate runtime. Missing configuration gives setup guidance.

The installer records detected Chrome/Chromium in its local config. If none is
installed, explicitly run `python -m playwright install chromium` with OpenKatana's
Python, then run the installer again. The renderer also discovers installed
Playwright Chromium automatically; it never downloads a browser at render time.

## The six Apps

**Full workflow** puts every App below into one graph. One **Project ID** node feeds
Open Studio, **Import media → Make edit → Render to video**, the 3D starter and the
tools node, in four groups: *Your project and Studio*, *Video to edit*, *3D starter*
and *Every tool*. Its App form shows all of their inputs. Choose a video, keep
`seconds` within its length, and Run: it opens Studio, renders the edit, starts a 3D
scene and returns the tool result together. Switch to the node graph to see or
rewire the whole workflow. The five single-purpose Apps:

1. **Open Studio:** choose a simple project ID and display name; Run creates or
   reopens it and starts a loopback Studio. Open the returned URL. Its setup data
   gives your agent the exact workspace, project ID, Python and skill. Reopening
   preserves your timeline and reuses the Studio process.
2. **All tools:** select a tool and supply the same JSON arguments used by the
   CLI/MCP. The project field is added only to tools accepting `project_id`;
   conflicting IDs are rejected. Start with `get_capabilities`, then
   `read_guide` with `{"topic":"comfy-apps"}` or a feature guide. Every tool is
   also a separately searchable node under **OpenKatana / Tools**, with its
   description and parameter signature. The full Studio catalog supplies guides.
3. **Make a 3D scene:** select product, morph or physics, dimensions, frames and
   fps. Run creates a new editable scene and renders PNGs and MP4 locally. These
   are starting examples; your agent can edit their JSON and rerender through
   `render_scene3d`. No Blender or generation model is needed for this App.
4. **Background job:** paste a job ID to read its result. It never resubmits work.
5. **Video to edit:** upload a video and set the same project ID on Import media,
   Make edit and Render to video. Choose a recipe; Run imports, saves and renders.
   Existing timelines are protected unless `replace_existing` is explicitly enabled.
   Source audio is imported separately and passed to the recipe. A silent source
   requires a silent preset such as ramp-freeze (beat-montage requires music).

Example: select `create_project`, set project ID `film`, and arguments
`{"name":"My film"}`. For an existing project use `get_project` with `{}`.
For font discovery use `list_fonts` with `{}`. Structured scene/timeline/plugin
documents use the existing guides and JSON contracts; the node adapter does not
invent a second set of parameters.

OpenKatana results appear as downloadable text files; supported project image/video outputs also
appear in Comfy's preview area. Preview copies are limited to 256 MiB; full
artifacts remain in the project and Studio. The original media is never moved.
The `after` input can sequence ordinary tool nodes; it is an execution dependency,
not an automatic merge of the previous JSON into arguments.

## Model jobs and queue behavior

`process_clip`, `run_model_workflow` and `collect_workflow` run outside ComfyUI's
execution thread and return a persistent background job ID. This frees Comfy's
queue to run requested model work instead of waiting on itself. Graph mode polls
status; **Background job** is the explicit fallback in any view.

A successful adapter job means the tool call returned. Inspect the contained
model receipt: `pending`/`running` is not a finished generation, and a collected
output is not human approval. Preserve the model's `request_id` and returned
directory. Poll/collect the original job; do not blindly submit again. A stopped
worker becomes interrupted and is not automatically restarted. Background jobs
may continue after a Comfy prompt finishes or is cancelled; inspect their state
and the Comfy queue before taking further action.

Local Comfy processing uses the official Comfy SDK through a separately running
local API proxy. Read [model setup](COMFY_MODELS.md). Missing models/nodes fail
preflight; no cloud fallback is enabled. Review custom nodes and authored scripts
under the existing workflow before authorizing their execution.

## Sharing and compatibility

Saved Apps are ordinary workflow JSON with App Mode input/output bindings.
Distribute them with this node pack and the setup instructions. Recipients need
their own local ComfyUI and OpenKatana dependencies. This does not publish a free
cloud service or establish Comfy Cloud support for these custom nodes.

The integration targets the V1 custom-node API supported by current ComfyUI and
the App Mode format in frontend 1.55. Older frontends may need an update. The
exact local versions and validation scope are recorded with the test evidence.

Official references: [App Mode](https://docs.comfy.org/interface/app-mode),
[custom nodes](https://docs.comfy.org/custom-nodes/backend/server_overview).

## Development checks

```sh
python scripts/build_comfy_apps.py
python -m unittest tests.test_comfy_apps -v
python scripts/test_comfy_apps_live.py --endpoint http://127.0.0.1:8000 --workspace PATH_TO_SHARED_PROJECTS --out work/comfy-apps-check
```

Regenerate the catalog when AgentAPI signatures change. The unit test checks
that no shared operation disappears. Live checks use disposable projects and
synthetic media; they do not require paid services or generative model weights.
The live script also needs the `local-comfy`, `mcp` and `vision` package extras.
It starts and stops its own loopback API proxy and leaves receipts and test
projects available for inspection. Expected stale-revision and paid-call errors
appear as two failed prompts in Comfy's history; those are rejection tests.

On the tested frontend, App inputs use canonical graph/widget IDs and output
bindings use numeric node IDs. `extra.linearMode=true` opens the examples directly
in App Mode. Open Studio also displays a dismissible link to the shared Studio.
If another extension's image-feed bar covers Run, close that bar or
focus Run and press Enter. The OpenKatana adapter does not change other extensions.

Validation on ComfyUI 0.41.0 / frontend 1.55.18 is recorded in
[comfy-apps-validation.json](comfy-apps-validation.json).

## Typed media ports

`OpenKatanaImportMedia` accepts exactly one RGB IMAGE batch or native VIDEO,
plus optional AUDIO. IMAGE frames use the explicit fps; VIDEO keeps its timing.
Import returns `media_id`, `music_asset_id` and result JSON. AUDIO replaces the
source soundtrack when connected. `OpenKatanaMakeEdit` connects those IDs to a
recipe and saves with revision checks. `OpenKatanaRenderVideo` returns the full
native VIDEO (with audio) plus a bounded IMAGE preview, not all full-size frames.
Connect its VIDEO to downstream video nodes; preview frames are a sample only.

Model decoded IMAGE frames can replace LoadVideo in the fifth App. The original
[LTX example](../examples/comfy/README.md) supplies the complete generation-to-edit
API graph. Installed weights are required; schema validation is not inference.
The same guide now includes a separately tested LTX-2.5 Cloud generation followed
by a local shared-API edit. Download that result into the Video to edit App;
do not assume OpenKatana custom nodes are installed on Comfy Cloud.
Optical flow is classical OpenCV processing in the separate OpenKatana vision
environment. The chroma matte and point helpers need only Comfy's tensor runtime.

```sh
python -m scripts.test_comfy_typed_live --endpoint http://127.0.0.1:8188 --out work/typed-check
```
