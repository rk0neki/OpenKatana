# Tool reference

OpenKatana has 72 tools, shared by the CLI, the MCP server and the ComfyUI
nodes. This page is generated from the tool catalog by
`python scripts/build_tools_doc.py`; do not edit it by hand.

For exact signatures and types, run `openkatana tools`. Each section links to the
guide with details and limits. Parameters ending in `?` are optional.

| Area | Tools | Guide |
|---|---|---|
| [Start and discover](#start-and-discover) | 4 | [Agent guide](AGENT_INTERFACE.md) |
| [Bring in and inspect media](#bring-in-and-inspect-media) | 8 | [Editor tools](EDITOR_TOOLS.md) |
| [Author the timeline](#author-the-timeline) | 6 | [Timeline](TIMELINE.md), [Release tools](RELEASE-TOOLS.md) |
| [Music, sound and captions](#music-sound-and-captions) | 7 | [Editor tools](EDITOR_TOOLS.md) |
| [Analysis and effects](#analysis-and-effects) | 5 | [Effects](EXPANSION.md) |
| [Match a reference](#match-a-reference) | 6 | [Editor tools](EDITOR_TOOLS.md) |
| [Fonts and text shaping](#fonts-and-text-shaping) | 3 | [Editor tools](EDITOR_TOOLS.md), [Release tools](RELEASE-TOOLS.md) |
| [Compositions and plugins](#compositions-and-plugins) | 6 | [Compositions](COMPOSITIONS.md) |
| [3D scenes and WebGL](#3d-scenes-and-webgl) | 7 | [3D](SCENE3D.md), [WebGL](WEBGL.md) |
| [Blender and authored animation](#blender-and-authored-animation) | 6 | [Animation](ANIMATION.md) |
| [Render and review](#render-and-review) | 5 | [Editor tools](EDITOR_TOOLS.md), [Validation](VALIDATION.md) |
| [ComfyUI models](#comfyui-models) | 7 | [Models](COMFY_MODELS.md) |
| [HDR](#hdr) | 2 | [HDR](HDR.md) |

## Start and discover

Guide: [Agent guide](AGENT_INTERFACE.md)

| Tool | What it does | Parameters |
|---|---|---|
| `get_capabilities` | Discover actual tools, supported workflows, runtime readiness and limits before editing. | — |
| `read_guide` | Read the exact supported timeline contract and editing workflow; do not guess parameters. | `topic?` |
| `create_project` | Create a fresh editing project. | `name`, `project_id?` |
| `get_project` | Read media IDs, the current timeline and its revision for conflict-safe saving. | `project_id` |

## Bring in and inspect media

Guide: [Editor tools](EDITOR_TOOLS.md)

| Tool | What it does | Parameters |
|---|---|---|
| `inspect_media` | Inspect a local media file's duration, dimensions, rates and streams without changing it. | `source` |
| `preview_source` | See source frames at explicit times BEFORE choosing shots. | `project_id`, `source`, `times` |
| `source_contact_sheet` | Inspect up to 96 timestamped source frames as contact sheets. | `project_id`, `source`, `start?`, `end?`, `step?`, `columns?` |
| `view_image` | View a saved image or matte inside the project. | `project_id`, `path` |
| `preview_segment` | Create a playable video excerpt (up to 15s) and an audio preview for clients supporting audio input. | `project_id`, `source`, `start?`, `duration?`, `max_width?` |
| `import_media` | Import media, optionally a trimmed/resized video excerpt or its audio. | `project_id`, `source`, `rights?`, `start?`, `duration?`, `max_width?`, `audio_only?` |
| `import_media_batch` | Import 1..32 excerpts, hashing a large source once. | `project_id`, `source`, `excerpts`, `request_id`, `rights?` |
| `set_review_policy` | Optional strict mode: start_render then refuses until every source used by the timeline was inspected (preview_source / source_contact_sheet) and the current revision was previewed (preview_timeline); with require_motion also until revise_motion measured the current revision against a reference. | `project_id`, `strict`, `require_motion?` |

## Author the timeline

Guide: [Timeline](TIMELINE.md) · [Release tools](RELEASE-TOOLS.md)

| Tool | What it does | Parameters |
|---|---|---|
| `plan_edit` | Optional original recipe starting point. | `project_id`, `asset_ids`, `recipe?`, `seconds?`, `width?`, `height?`, `fps?`, `caption?` |
| `build_recipe` | Starting-point timeline for one of 8 recipe families (beat_cut_punch, xerox_ink, mono_noir, cutout_collage, speed_ramp_freeze, facelock_strobe, timed_type, glitch_hits) from imported assets; music (an imported audio asset) drives beat-based families. | `project_id`, `family`, `asset_ids`, `music_asset_id?`, `text?`, `font_family?`, `font_file?`, `seconds?`, `width?`, `height?`, `fps?` |
| `validate_timeline` | Check a complete timeline against real local assets before saving or rendering. | `project_id`, `timeline` |
| `save_timeline` | Save the agent's authored timeline; pass the revision from get_project (null for first save). | `project_id`, `timeline`, `revision` |
| `edit_timeline` | Propose or atomically save RFC 6902 timeline operations against an exact revision. | `project_id`, `operations`, `revision`, `save?` |
| `preview_timeline` | See actual rendered frames of the saved timeline, including text/masks/camera/effects. | `project_id`, `frames` |

## Music, sound and captions

Guide: [Editor tools](EDITOR_TOOLS.md)

| Tool | What it does | Parameters |
|---|---|---|
| `analyze_audio` | Measure music for cutting: BPM with octave candidates, a constant beat grid fitted to onsets, downbeats, onsets (all/strong/low), level-based sections, silence and EBU R128 loudness, plus a timeline image. | `project_id`, `source`, `start?`, `duration?`, `fps?`, `beats_per_bar?` |
| `plan_music_edit` | Plan cuts to music: analyse the track, then return a beat-aligned cut list (tempo-aware pace per level section: the smallest of 1/2/4/8 beats lasting >= 0.5 s loud, 1 s mid, 2 s quiet; half-beat burst after a drop), shot spans, suggested specials/punch/shake entries and, with asset_ids, a draft timeline (clips assigned in order; the track is included when it lives in the project). | `project_id`, `source`, `asset_ids?`, `start?`, `duration?`, `fps?`, `width?`, `height?`, `pace?`, `min_shot?`, `burst?` |
| `plan_storyboard` | Storyboard mode: plan a music edit as slots to fill before footage exists. | `project_id`, `source`, `start?`, `duration?`, `fps?`, `width?`, `height?`, `pace?`, `subject?`, `camera?`, `save?` |
| `fill_storyboard` | Put imported footage into storyboard slots of the saved timeline (fills: [{slot, asset_id, srcf?}]; each slot's other shot settings are kept) and save a new revision. | `project_id`, `storyboard_id`, `fills?` |
| `list_sfx` | Browse OpenKatana's own synthesised sound effects (no recordings or licences involved): name, category, variants, duration and default level. | `category?` |
| `transcribe_audio` | Transcribe speech locally with word timings (faster-whisper; a Whisper model already in the local cache, see get_capabilities transcription; never downloaded). | `project_id`, `source`, `model?`, `language?`, `start?`, `duration?` |
| `make_captions` | Turn supplied word timings (words JSON or SRT/VTT; no transcription) into caption text events for the timeline, grouped for reading (max_chars/max_words/max_gap/max_duration, sentence ends), in a style (clean, bold_pop, karaoke with per-word highlight, lower_third, title_card), plus SRT and WebVTT files. | `project_id`, `words`, `family`, `fps?`, `style?`, `size?`, `height?`, `offset?`, `highlight?`, `karaoke_mode?`, `max_chars?`, `max_words?`, `max_gap?`, `max_duration?` |

## Analysis and effects

Guide: [Effects](EXPANSION.md)

| Tool | What it does | Parameters |
|---|---|---|
| `analyze_clip` | Run local source analysis. | `project_id`, `clip_id`, `operation`, `options?`, `apply?` |
| `analyze_energy` | Measure a video's energy: cuts, white/black flashes, shake bursts, pans and motion hits (each with a ready timeline entry: specials / cam.shake / cam.pan / cam.punch), per-second rates and a 0.5 s energy curve, plus a chart image. | `project_id`, `source`, `reference?`, `start?`, `duration?`, `canvas_w?`, `floor?` |
| `review_mask` | Review a clip's matte: sheets of the source every `step` s plus the last frame with the background tinted, the matte edge outlined and coverage per frame; flags empty/full mattes and coverage jumps. | `project_id`, `clip_id`, `step?`, `accept?`, `note?` |
| `morph_images` | Morph two local images using geometric ORB correspondence or explicit normalized landmarks. | `project_id`, `source`, `target`, `width?`, `height?`, `fps?`, `frames?`, `points?` |
| `render_page` | Render a project HTML/CSS/SVG/Canvas page that defines window.openkatanaPage = {width, height, fps, frames, render(t, f)} into PNG frames (render(f/fps, f) per frame) after a forward/reverse determinism check; returns a clip to add to the timeline. | `project_id`, `page`, `frames?`, `fps?` |

## Match a reference

Guide: [Editor tools](EDITOR_TOOLS.md)

| Tool | What it does | Parameters |
|---|---|---|
| `analyze_reference` | Find scene-change and audio energy-rise candidates in up to 120 seconds. | `project_id`, `source`, `start?`, `duration?`, `scene_threshold?` |
| `compare_reference` | See paired reference/render pictures at the same requested times (render time = reference time + offset). | `project_id`, `reference`, `rendered`, `times`, `render_offset?` |
| `save_reference_plan` | Record verified reference timing/text/font/effect requirements. | `project_id`, `plan` |
| `audit_reference_plan` | Check saved timeline against exact cut frames, literal timed text, font file hashes and specified shot settings. | `project_id` |
| `bind_reference` | Record a named reference (role identity, style, product or location) from imported assets, with their hashes. | `project_id`, `name`, `asset_ids`, `role?`, `subject_type?`, `description?` |
| `inspect_identity` | Compare an asset with bound references: a sheet of the largest detected face (or the centre) in each reference and in the chosen frames of the asset. | `project_id`, `asset_id`, `references?`, `frames?`, `accept?`, `note?` |

## Fonts and text shaping

Guide: [Editor tools](EDITOR_TOOLS.md) · [Release tools](RELEASE-TOOLS.md)

| Tool | What it does | Parameters |
|---|---|---|
| `list_fonts` | List actual local font family/style/path metadata. | `directory?`, `query?`, `limit?`, `text?` |
| `preview_fonts` | See side-by-side specimens and exact hashes of up to eight local TTF/OTF/TTC font files before choosing one (TTC: first face, as browsers load it). | `project_id`, `sources`, `text?` |
| `shape_text` | Export one shaped text run as glyph IDs, clusters, positions, contours and SVG. | `project_id`, `font`, `text`, `size?`, `direction?`, `language?`, `script?`, `features?`, `variations?`, `radius?` |

## Compositions and plugins

Guide: [Compositions](COMPOSITIONS.md)

| Tool | What it does | Parameters |
|---|---|---|
| `create_composition` | Create an original responsive composition. | `project_id`, `name?`, `width?`, `height?`, `fps?`, `frames?` |
| `save_composition` | Validate/save a composition with a revision guard and history. | `project_id`, `path`, `document`, `revision` |
| `inspect_composition` | Preview actual layout, font loading, grapheme ranges and overflow at a viewport size. | `project_id`, `path`, `frame?`, `width?`, `height?` |
| `render_composition` | Render a responsive composition offline with deterministic seeking checks. | `project_id`, `path`, `width?`, `height?`, `video?` |
| `list_plugins` | Load trusted project plugin manifests; list actual components, effects, operators and parameter contracts. | `project_id`, `manifests?` |
| `run_plugin_operator` | Run an original plugin operation as a validated, deterministic proposal; never saves. | `project_id`, `operator`, `document`, `parameters?`, `manifests?`, `kind?` |

## 3D scenes and WebGL

Guide: [3D](SCENE3D.md) · [WebGL](WEBGL.md)

| Tool | What it does | Parameters |
|---|---|---|
| `create_scene3d` | Create an editable 3D scene, never overwrite one. | `project_id`, `name?`, `template?`, `scene?` |
| `inspect_model3d` | Inspect a supplied local GLB/glTF model's clips, skins, morph targets and dependencies. | `source` |
| `import_model3d` | Copy a supplied GLB/glTF and its local dependencies into a NEW project-relative folder, normally scenes/NAME/assets/MODEL. | `project_id`, `source`, `destination` |
| `check_scene3d` | Validate scene JSON, animation targets, local model dependencies and supported fields before rendering. | `project_id`, `scene` |
| `render_scene3d` | Render WebGL 3D locally with reverse-seek checks. | `project_id`, `scene`, `preview_frames?`, `video?`, `start?`, `end?`, `trusted_script?` |
| `create_webgl_kit` | Create an original editable JavaScript/Three.js scene, cut-safe camera schedule and animated display atlas. | `project_id`, `directory?`, `width?`, `height?`, `fps?`, `frames?` |
| `assemble_render_clips` | Assemble ordered WebGL or Blender receipt paths into a validated timeline proposal. | `project_id`, `receipts`, `contiguous?` |

## Blender and authored animation

Guide: [Animation](ANIMATION.md)

| Tool | What it does | Parameters |
|---|---|---|
| `render_blender` | Render a project .blend or explicitly trusted .py scene script using separately installed Blender. | `project_id`, `source`, `engine?`, `start?`, `end?`, `trusted_script?` |
| `create_animation_kit` | Create an editable original Blender animation starter and display atlas. | `project_id`, `directory?`, `width?`, `height?`, `fps?`, `frames?` |
| `build_display_atlas` | Create frame-indexed RGB LED masks from text cues (animation guide). | `project_id`, `document` |
| `synthesize_score` | Render an original deterministic local oscillator/noise score from explicit notes. | `project_id`, `document` |
| `assemble_blender_clips` | Validate ordered project-relative Blender receipts and return a timeline proposal with frame hashes. | `project_id`, `receipts`, `contiguous?` |
| `analyze_camera_motion` | Analyze evaluated camera_samples from blender_helpers: speed, aim jolts and rotational shutter streak estimates. | `project_id`, `document`, `jolt_threshold?`, `jolt_ratio?` |

## Render and review

Guide: [Editor tools](EDITOR_TOOLS.md) · [Validation](VALIDATION.md)

| Tool | What it does | Parameters |
|---|---|---|
| `start_render` | Render a saved timeline asynchronously. | `project_id`, `request_id` |
| `get_render` | Read a recorded render status and output path, also after MCP reconnects. | `project_id`, `job_id` |
| `review_render` | Record the agent's review against rendered source/timeline hashes. | `project_id`, `job_id`, `decision`, `notes` |
| `revise_motion` | Bounded motion revision loop: render the saved timeline, measure per-second cuts, flashes, shake frames, jitter, camera movement and motion energy against a reference video (analyze_energy measures), then up to max_revisions (0-4) times propose camera-only edits on unlocked shots (shake bursts, pans, punch hits at the reference's event times; amplitude scaling bounded 0.5-2x per step), re-render and re-measure; the best attempt is kept. | `project_id`, `reference`, `max_revisions?`, `locked_shots?`, `floor?`, `reference_start?`, `reference_duration?`, `apply?`, `ceiling?` |
| `analyze_render_motion` | Measure decoded-frame optical flow and candidate judder/stalls, excluding planned cuts. | `project_id`, `source`, `cuts?`, `work_width?`, `moving?`, `ratio?`, `stall?` |

## ComfyUI models

Guide: [Models](COMFY_MODELS.md)

| Tool | What it does | Parameters |
|---|---|---|
| `build_workflow` | Build an audited LOCAL workflow with explicit installed model names; returns a project-relative file. | `project_id`, `kind`, `parameters?` |
| `check_workflow` | Check local nodes/models without execution. | `project_id`, `workflow`, `native_endpoint?`, `reviewed_local_nodes?` |
| `submit_workflow` | Submit through official Comfy SDK. | `project_id`, `workflow`, `request_id`, `assets?`, `endpoint?`, `native_endpoint?`, `execution?`, `allow_paid?`, `reviewed_local_nodes?` |
| `collect_workflow` | Collect the previously submitted Comfy job; never submit a replacement. | `project_id`, `directory` |
| `import_workflow_output` | Import collected images/masks or one video/audio output. | `project_id`, `directory`, `kind?`, `clip_id?`, `fps?`, `output_file?` |
| `process_clip` | Advance a resumable whole-clip Comfy sequence. | `project_id`, `clip_id`, `kind`, `directory`, `endpoint?`, `native_endpoint?`, `model?`, `points?`, `negative_points?` |
| `run_model_workflow` | Build, check, submit or collect an installed LOCAL model workflow with stable request ID. | `project_id`, `kind`, `parameters`, `assets`, `request_id`, `endpoint?`, `native_endpoint?` |

## HDR

Guide: [HDR](HDR.md)

| Tool | What it does | Parameters |
|---|---|---|
| `import_hdr_media` | Keep an original HDR source and import an explicitly tone-mapped SDR editing proxy. | `project_id`, `source`, `source_color?`, `fps?`, `start?`, `duration?`, `peak_nits?`, `rights?` |
| `render_hdr` | Finish HDR clips in float32 linear BT.2020; export 16-bit FFV1, 10-bit HEVC and SDR preview. | `project_id`, `document` |
