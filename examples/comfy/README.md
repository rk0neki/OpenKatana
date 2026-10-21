# A model output becomes an edit

## Tested LTX-2.5 generation and local edit

`ltx25-generate.api.json` is the exact API graph from a successful Comfy Cloud
run on 2026-10-22. It adapts Comfy's MIT-licensed **LTX-2.5: Text to Video**
template with an original copper-ribbon product prompt, five seconds at 24 fps,
0.2 megapixels and prompt enhancement disabled. All generation nodes are
open-weight Comfy nodes; there are no Partner/API generation nodes.

The run produced **121 frames, 576 × 320, H.264 + 48 kHz AAC**, in 7.65 seconds.
The selector displayed 608 × 352; the two-stage latent pipeline actually decoded
576 × 320. Use the probed output dimensions. The displayed account balance fell
by approximately two credits; the exact fractional debit was not exposed in the
activity panel. This was one authorized run, with no automatic retries.

The API graph is adapted from Comfy's template under
[MIT](../../licenses/Comfy-workflow-templates-MIT.txt). Source revisions, hashes,
model filenames and license links are in [assets/sources.json](assets/sources.json).
LTX-2.5 weights have the **LTX-2.x Community License**, not OpenKatana's Apache
license. The model's Gemma text encoder has its own upstream terms. Weights and
ComfyUI itself are not bundled. Check the exact model license before use.

To repeat the local stage after OpenKatana setup:

```sh
python examples/comfy/render_ltx_edit.py
```

This imports the bundled AI-generated clip and its audio, creates a five-second
speed-ramp/freeze edit with typography, saves it with a revision check, renders
and measures motion. It makes **zero model/network calls**. It prints the MP4 path
and keeps the project, timeline, preview frames and `example-result.json` receipt.
The hold from frame 66 is intentional. Motion measurements are diagnostic, not
an aesthetic verdict. Review source rights and the edit before publication.

Use `--source PATH_TO_VIDEO --workspace PATH_TO_PROJECTS --model-label MODEL_NAME`
for another downloaded video with audio and at least five seconds of footage.
Supply its actual model name; other inputs default to a generic label.
This small example uses
the same shared API exposed by CLI/MCP; it is not a separate renderer.

To generate new footage, open `ltx25-generate.api.json` in a compatible ComfyUI
installation or use the current official LTX-2.5 template. Select installed
filenames and review the prompt, model terms and cost before running. Cloud GPU
time costs credits even when model weights are open; local execution requires
your own compatible hardware and models. Prompt enhancement is off, so its
optional Gemma model branch is not executed. Preserve the job ID on submission
uncertainty instead of submitting again.

This validation used the Cloud browser and downloaded its completed MP4, then
the local shared API. It **does not validate Cloud SDK submission, an all-in-one
Cloud OpenKatana graph, or local LTX-2.5 inference**. OpenKatana custom nodes are
not assumed installed on Comfy Cloud. The local **Video to edit** App can import
the downloaded video, or accept a local generator's VIDEO output directly.
Prize eligibility and the final demo's model disclosure still need review.

## Legacy LTX-Video v1 wiring example

`ltx-to-edit.api.json` is an original API-format graph for the stock ComfyUI
LTX-Video v1 nodes. It samples 49 frames, decodes them, imports the IMAGE batch
into OpenKatana and renders a two-second ramp/freeze edit. No paid API node is used.
This is a generation-to-edit wiring example, not a tuned quality preset or proof
of prize eligibility.

1. Install the OpenKatana runtime and node pack as described in
   [ComfyUI Apps](../../docs/COMFY_APPS.md).
2. Install a compatible LTX-Video v1 checkpoint with VAE and a T5XXL text encoder
   following the [model author's instructions](https://github.com/Lightricks/LTX-Video).
   Check the license for the **exact weights** you choose. Models are not bundled,
   and OpenKatana will not download them. This graph is not an LTX-2 workflow.
3. Open the API JSON in ComfyUI and select actual installed filenames for
   `ckpt_name` and `clip_name`. Keep `type=ltxv`. The conspicuous placeholders
   intentionally fail validation until replaced; they are not downloadable IDs.
4. Set the same new `project_id` on all three OpenKatana nodes. Review the prompt,
   settings and source rights, then Run. Checkpoint choice can require different
   sampling settings, precision and more memory than this small example.
5. Inspect the VIDEO and preview frames. Open the same project in Studio or
   through CLI/MCP to refine the saved timeline. For music, connect a LoadAudio
   output to Import media's AUDIO port and its music ID to Make edit, then choose
   `beat-montage`. Keep the media ID connection as well.

The supplied **Video to edit** saved App is the model-free entry point: upload
an existing clip, or replace LoadVideo with your model's VIDEO output. A decoder's
IMAGE output connects to `images` instead. Connect only one of IMAGE or VIDEO.

Legacy validation: all 12 v1 graph node schemas and typed connections were checked
against local ComfyUI. **LTX inference was not run**; weights are absent from the
isolated test installation. The shared IMAGE → optical flow → import → edit →
VIDEO/preview path and VIDEO re-import were executed with synthetic media.
This distinction keeps a transport test separate from model quality.
