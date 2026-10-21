# A model output becomes an edit

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

Validation: all 12 LTX graph node schemas and typed connections were checked
against local ComfyUI. **LTX inference was not run**; weights are absent from the
isolated test installation. The shared IMAGE → optical flow → import → edit →
VIDEO/preview path and VIDEO re-import were executed with synthetic media.
This distinction keeps a transport test separate from model quality.
