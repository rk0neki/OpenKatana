# Local and paid Comfy models

The agent remains the editor. It chooses an operation and calls OpenKatana, which uses
the official Comfy SDK to run the workflow and collect outputs. The SDK is a transport;
model quality and workflow compatibility still require testing.

## Execution choices

- Local (default): installed models/nodes through the local Comfy API proxy.
  Existing workflow builders, model checks, segmentation and clip processing remain local.
  No automatic model downloads or fallback to a paid service.
- Cloud (explicit): an API-format workflow supported by Comfy Cloud, including
  supported partner model nodes. Requires a Comfy account with API access, credits
  as applicable and COMFY_API_KEY configured in the environment of the MCP/CLI process.
  No credential is requested as a tool argument or written to a receipt by the bridge.

This release supports https://cloud.comfy.org only for cloud jobs. Direct provider APIs,
Comfy Router, paid partner nodes executed on local ComfyUI and custom hosted deployment
addresses are not implemented. Local recipes are not automatically converted to cloud
recipes. Export a working Comfy Cloud workflow in API format and keep it inside the
OpenKatana project; verify node/model availability on the service. Cloud structural
validation is not proof of model availability or permission to use a model.

## Agent use

### Model-independent imported workflows

The presets are conveniences, not the execution interface's model catalogue.
An editor may author or import any compatible API-format Comfy workflow JSON into
the project, then use the same check/submit/collect/import operations. Image, video,
audio and processing workflows use this same transport. UI graphs must first be
converted to API format. Model-specific prompting, tensors and resource requirements
still belong to that workflow; OpenKatana cannot make incompatible models interchangeable.

For local node classes outside the built-in set, pass `reviewed_local_nodes` as a
list of exact class names to both `check_workflow` and `submit_workflow` (direct CLI:
repeat `--reviewed-local-node CLASS`). Before adding a class, the agent must inspect
its live schema and implementation, confirm it executes locally without network/API
calls or automatic downloads, and record the evidence in the project. Check every
required weight/dependency is installed, including non-enumerated custom loaders.
Do not infer safety solely from a name, an `api_node:false` flag or the presence of
a model dropdown. Uncertain or unguarded download-capable nodes remain blocked.

This is a per-workflow extension, not a global wildcard: default allowlisting remains
in force. Preflight still rejects missing nodes, hosted API nodes and unavailable
enumerated models (including supplied optional model inputs). Named download nodes
cannot be generically added; they need a dedicated installed-file guard such as SAM2's.
This review is an agent engineering responsibility, not permission to spend or download.
Custom Python nodes are trusted local code, not sandboxed by OpenKatana; this mechanism
does not certify arbitrary third-party code. The extension is included in the job
receipt and request signature, so changing it requires a new request ID.

Generic cloud transport remains separately authorized as described above. A newly
imported workflow is supported only after its dependencies and actual execution are
verified; the application does not claim every installed or future model already works.

Read this guide through read_guide(topic="comfy-models") in MCP/CLI.

Use submit_workflow with the existing project_id, workflow, assets and stable request_id,
plus execution=cloud, endpoint=https://cloud.comfy.org, allow_paid=true. The user must
first authorize the selected paid job and uploading its source media. A model should not
set this flag merely because a local workflow failed. Get current pricing for the chosen
workflow before proposing it; no price estimator or hard spending cap is implemented.

The same request ID with the same inputs returns its existing receipt. Changing inputs
requires a new request ID and, for paid work, appropriate user authorization. An unknown
submission outcome is recorded, never blindly retried. Collect by the existing directory
and job ID with collect_workflow. Collection does not authorize another generation.

import_workflow_output imports image frames or source-aligned masks as before. It can
also import one generated video or audio file, preserving job provenance and pending
review. If a job returns mixed outputs, specify output_file exactly as listed in its
receipt. Generated video still participates in the identity review mechanism.

## CLI

### Local MiniMax H3

`build_workflow(kind="h3-generation", parameters={...})` builds a local FL2V
turbo workflow with explicit installed `model`, `encoder`, `vae`, `audio_vae`
and `lora` filenames. It uses native H3 conditioning, local sampling, video/audio
VAE decoding and SaveVideo. No partner node is permitted by this adapter.

`input_mode` is `i2v` (default), `t2v` or `first-last`. For i2v, submit with
`assets={"17.image":"media/first-frame.png"}`; first-last also needs `18.image`.
Supply the actual project-relative generated keyframe paths. The t2v mode needs
no input image. Choose a FL2V model and matching turbo LoRA; this builder does not
implement the separate reference-to-video conditioning contract.

Defaults: 864x480, 107 frames at 24 fps (about 4.46 seconds), 8 steps, seed 1.
Dimensions must be multiples of 32. `length` is an exact 17k+5 frame count from
5 through 362, not seconds. The node's documented trained range starts around
124 frames; shorter previews are a deliberate test setting. Trim and assemble
multiple generated shots to reach the final timeline duration. `sage_attention`
defaults to false; enable only when the installed KJNodes/SageAttention stack
works. No automatic dependency installation or fallback is performed.

Keep the generated audio when importing a collected MP4 by importing it separately
as `audio_only:true` if the edit needs that soundtrack: ordinary video preparation
imports picture frames. A successful preflight verifies installed names/node inputs,
not GPU memory sufficiency, output quality or permission to redistribute outputs.
Inspect the first generated shot before queuing the rest.

### Direct submission

After configuring COMFY_API_KEY privately in the process environment:

```powershell
python -m openkatana comfy-submit project/paid-workflow.json --out project/jobs/paid-001 --execution cloud --endpoint https://cloud.comfy.org --allow-paid --asset 1.image=project/media/source.png
python -m openkatana comfy-collect project/jobs/paid-001
python -m openkatana comfy-import project/jobs/paid-001 --project project --output-file 000-result.mp4
```

Node/input IDs and output filenames above are placeholders: use those of the selected
workflow and actual receipt. Local commands retain their previous defaults. The Studio
has no new paid-model chooser; these options are currently exposed through MCP/CLI.

## Validation and limits

Full regression run after implementation: 155 tests, OK, one skipped for the separate
Comfy torch environment. After adding guide discovery, all eight focused integration
tests and six documentation checks also passed. Paid submission, collection, environment isolation, default rejection, duplicate request
protection and output import are covered with fake SDK jobs. No real paid job was run,
no credits spent, and no cloud output quality or individual partner model is certified.
A live job with an approved workflow and spending authorization is still required.

Official interface reference (checked 2026-10-18):
https://docs.comfy.org/development/api-development/sdks


## Reference and restoration adapters (0.1.0rc2)

The original builders now target the inspected public core interfaces in ComfyUI
0.41.0. They use installed files, never downloader nodes. Live preflight verifies
node/model choices, flattened V3 reference/codec ports, required inputs, numeric
bounds, output indices/types and dependency cycles. An incompatible installation
fails with specific errors; it is not silently upgraded.

| Builder | Purpose and required components | Upload bindings |
|---|---|---|
| `qwen-edit` | Qwen Image 2.1 instruction editing with 1–16 references; installed model, encoder and VAE | `21.image`, `22.image`, ... |
| `h3-reference` | H3 reference-to-video using pictures, motion clips and/or audio; installed **reference-compatible** model, encoder, video/audio VAEs | pictures `20.image` onward; videos `40.video` onward; audio `60.audio` onward |
| `seedvr2-restore` | Temporal restoration with core SeedVR2, tiled VAE, temporal chunk/merge and color correction; installed model and VAE | `1.file` |
| `model-interpolation` | Core RIFE/FILM interpolation with installed `frame_interpolation` model; output fps = input fps × multiplier | `1.video` |
| `image-upscale` | Installed ESRGAN-compatible image upscaler; not temporal video restoration | `1.image` |

Use `build_workflow` to get the graph and exact `asset_ports`. The CLI accepts a
JSON object via `comfy-build KIND --parameters params.json --out graph.json`.
`run_model_workflow` combines build, preflight, submit and collection using a
stable `request_id`, parameters and project-relative `assets`. Call it again with
**identical arguments** to collect the original job. Changed inputs are rejected.
Failures and uncertain submissions are never retried under the same ID. Review
collected output, then use `import_workflow_output`; select `output_file` when the
job includes both a source preview and the result. A successful job is not approval
of likeness, motion preservation, licensing or final quality.

Qwen editing connects reference images to both its vision conditioning and VAE,
and samples the returned reference-sized latent. `resolution` is the reference
area scale (default 1024, multiples of 32; 0 keeps rounded source dimensions).
`references`, `steps` and `seed` are explicit. Width/height are deliberately not
independent overrides for this edit route.

H3 reference conditioning is distinct from first/last-frame generation. Parameters
`images` (0–9), `videos` (0–3), `audios` (0–3), and `ref_image_size` (`match`/`max`)
control the references. Use the model's `<Picture 1>`, `<Video 1>`, `<Audio 1>` tags
in the prompt. Video references are conformed to 24 fps and capped to the output
frame count; audio references are separate explicit inputs. Supply short prepared
reference clips. No FL2V turbo LoRA is attached to a reference model by default.
If supplying `lora`, verify that it is compatible with the chosen reference model.
The existing `h3-generation` first/last route can generate semantic transitions;
it does not establish deterministic geometry correspondence or exact motion transfer.

SeedVR2 keeps input fps and routes its soundtrack into `CreateVideo`; default
`scale=2` and explicit seed. It reconstructs detail rather than recovering ground
truth. RIFE/FILM returns `(N-1)*multiplier+1` pictures; the last hold interval is
shorter than a padded N×multiplier export. Review timing when synchronizing audio.
The core encoder limits this builder to 120 output fps. Model interpolation does
not replace the existing weight-free optical-flow interpolation route.

### Evidence and remaining dependencies

On the audited Windows installation, original tiny fixtures completed through the
**official SDK local proxy** for Qwen 2.1 multi-reference editing, SeedVR2 temporal
restoration and H3 picture+video+audio references. Qwen changed the synthetic
object's orange color to the supplied cyan reference while preserving its shape.
The H3 test used five frames/two steps and quantized weights: an execution check,
**not a quality benchmark**. The two user video tests are still the quality gate.

After explicit user approval, RIFE 4.26 (22.7 MB, MIT) and Real-ESRGAN general
x4v3 (4.9 MB, BSD-3-Clause) were installed separately and tested through the
fresh OpenKatana wheel. RIFE converted the original 12-frame/12-fps moving-shape
fixture into 23 frames at 24 fps, retained audio, and placed generated midpoints
within 0.015 pixels of their expected horizontal positions. The image upscaler
produced 512x512 output from 128x128 artwork, with output visibly distinct from
bicubic scaling. Both jobs were collected and their outputs inspected. FILM is an
alternative supported by the same public core interface; its weights were not run.

No weights are bundled or downloaded by OpenKatana. Reproduce these tests with
`scripts/test_restoration_models_live.py --out work/restoration-test` in the
installed package environment, after explicitly installing compatible models:

- [Comfy's RIFE 4.26 repack](https://huggingface.co/Comfy-Org/frame_interpolation/blob/219da3c9d8c357ceaf457fc1d5932c6e861b8dee/frame_interpolation/rife_v4.26.safetensors)
  in `ComfyUI/models/frame_interpolation/`. The original project explicitly applies
  its [MIT license to the trained models](https://github.com/hzwer/Practical-RIFE#trained-model).
- [Official Real-ESRGAN release](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0),
  `realesr-general-x4v3.pth` in `ComfyUI/models/upscale_models/`, under the project's
  [BSD-3-Clause license](https://github.com/xinntao/Real-ESRGAN/blob/master/LICENSE).

Exact weight/output hashes, pinned license sources and test metrics are recorded
in `model-validation.json`. The RIFE download matched its published LFS SHA-256;
the older Real-ESRGAN release does not publish a digest, so its hash is recorded
after downloading from the official release over HTTPS. Keep the license notices.

Other compatible installations can supply their own licensed weights. Identity
consistency, semantic morph quality, reconstruction and automatic rigging are
model-specific; tool availability does not establish universal model fidelity.
Model licenses/quantization belong to the selected files and must be disclosed.
