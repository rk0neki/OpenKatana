# Architecture

OpenKatana owns its timeline, source preparation, independent renderer, exported
files and evidence. Comfy owns execution of explicitly selected workflows.

```text
Media + authored timeline
        |
        +-- optional official Comfy SDK --> local proxy or Comfy Cloud --> workflow
        |                                      |
        |                        downloaded output + job receipt
        |                                      |
        +---------------- imported/prepared media
                                               |
                                  independent Canvas2D renderer
                                               |
                                     lossless frame sequence
                                               |
                                      FFmpeg + verification
```

Claude or another external agent chooses the edit. The MCP stdio server and CLI
share `AgentAPI`, exposing the same 59 editing operations. The local Studio supplies
interactive preview, timeline controls and review. No language model is bundled.
Projects store source provenance, timeline revisions, render receipts and reviews.
Preview tools return actual rendered images, not just descriptions of the timeline.

Render jobs run in recorded child processes. A request ID identifies one timeline
revision and prevents accidental duplicate submission. MCP dispatch is serialized;
CLI and Studio are intended for one active writer per project. Clients may stop
child processes on disconnect, so MCP users should keep the connection open until
completion. Job lookup reports interrupted workers without automatically restarting.

Browser requests are limited to local
project assets and OpenKatana's own engine. Rendering uses a temporary local server
and closes its browser and server on completion or failure.

The Comfy bridge is an SDK client, not another implementation of ComfyUI. The first
workflow surface supports an allowlist of core image operations, original local
matte/interpolation nodes and explicit model-based generation/segmentation workflows.
Local execution uses loopback. Explicit paid execution uses https://cloud.comfy.org
with environment credentials and per-submission authorization; there is no implicit cloud fallback. Model
availability and quality are recorded separately from workflow implementation.

The SDK currently reads its endpoint from an environment variable. Our context
restores the previous value after each operation. MCP serializes calls to avoid
concurrent endpoint switching. A future multi-user service must isolate workers or
use a supported per-client endpoint interface.

Official integration references, consulted 2026-10-16:

- https://github.com/Comfy-Org/comfy-python-sdk
- https://github.com/Comfy-Org/comfy-api-proxy
- https://docs.comfy.org/development/api-development/sdks

The actual installed SDK/proxy help and interfaces were checked because these APIs
are pre-1.0. Tested versions are recorded in the dependency lock and validation notes.

## Composition subsystem

`openkatana/composition.py` validates original document/plugin contracts, serves
only declared local inputs, manages ephemeral browser sessions, checks deterministic
seeking/remounts and produces normal frame clips. `web/composition.js` uses DOM/CSS
layout and browser shaping with intact text runs. `composition_builtin.js` supplies
original components, a deterministic effect and copy-based JSON Pointer batch
operations. `save_composition` guards revision/history with an exclusive writer
lock. Rendering preserves legacy timeline typography/hook semantics. Compositions
execute in the local browser; plugins use the documented JavaScript API.
