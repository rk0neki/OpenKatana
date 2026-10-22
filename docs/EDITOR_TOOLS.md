# Editor tools and reference matching

OpenKatana has 72 shared MCP/CLI operations; [TOOLS.md](TOOLS.md) lists all of
them by area. Use the CLI catalog for exact signatures and check runtime
readiness before invoking optional workflows.

| Editor need | Available surface | Important limit |
|---|---|---|
| Inspect footage | inspect_media, preview_source, source_contact_sheet | Up to 96 timestamped frames per sheet request; inspect adjacent frames for boundaries |
| Find reference events | analyze_reference | Scene-change and audio-energy candidates; flashes can look like cuts; no OCR/transcription or semantic beat detection |
| Measure reference energy | analyze_energy | Cuts, white/black flashes, shake bursts, pans, motion hits with ready timeline entries, per-second rates, 0.5 s curve, chart; `reference` adds a per-second check of a render; fast camera moves can still read as cuts, inspect frames |
| Plan cuts to music | plan_music_edit | Beat-aligned cut list (tempo-aware pace per level section, half-beat burst after a drop), suggested specials/punch/shake, optional draft timeline from imported clips; a starting point, nothing saved |
| Cut to music | analyze_audio | BPM + octave candidates, constant beat grid fitted to onsets, downbeats, onsets, level sections, silence, EBU R128 loudness, timeline image; estimates (constant tempo assumed), confirm by listening |
| Custom motion graphics | render_page | A project HTML/CSS/SVG/Canvas page with `window.openkatanaPage = {width, height, fps, frames, render(t, f)}` rendered to a PNG clip after a forward/reverse determinism check; same-origin sandbox, blocked requests listed |
| Sound effects | list_sfx + timeline `audio.cues` | OpenKatana's own synthesised hits, impacts, whooshes, risers, clicks, slaps, pops, glitches, dings, shutters (4 variants each) at category levels; not recordings |
| Transcribe speech | transcribe_audio | Word timings from faster-whisper (optional extra) with a Whisper model already in the local cache (never downloaded); CPU fallback when the CUDA runtime is missing; machine output, check words, names and timings |
| Captions from word timings | make_captions | Groups a words JSON (e.g. from transcribe_audio) or SRT/VTT into caption events (clean, bold_pop, karaoke, lower_third, title_card) + SRT/VTT; timings must be checked against the audio |
| Choose the actual font | list_fonts, preview_fonts, import_media | 26 bundled SIL OFL fonts (listed first, licence and copyright; import copies the licence into the project) plus metadata/specimens of local font files; no automatic font identification, licensing clearance for other fonts, or downloads |
| Match typography | Supplied fonts, weight/style, size, placement, parts, tracking, scale_x/y, hollow fill, glow, typewriter, flicker | Original graffiti shapes deliberately differ; font choice still requires visual verification |
| Match cuts and retiming | Timeline f0/f1 or t0/t1, src/srcf, speed and ramps, stutter, two-shot transitions; analyze_clip interpolate builds a higher-fps clip; analyze_clip retime builds an exact-frame slow-motion plate | Full supported fields are in TIMELINE.md; no arbitrary unsupported field is accepted. For slow motion prefer retime (one new picture per output frame, used at speed 1): an interpolated clip re-sampled at speed < 1 is blended again and stutters on baked repeats |
| Match effects and cameras | Timeline cam/fx/layers/look/post plus workflows | Parameters must be measured; a similar effect name does not establish parity |
| Avoid slow repeated imports | import_media_batch | One source hash per batch; partial outcomes recorded and never blindly repeated |
| Author/save | get_project, plan_edit, validate_timeline, save_timeline | Recipe is optional; it does not recover a reference edit |
| Recipe families and presets | build_recipe | Original starting timelines for beat_cut_punch, xerox_ink, mono_noir, cutout_collage, speed_ramp_freeze, facelock_strobe, timed_type, glitch_hits from imported clips (music drives beat families), or one of 12 OpenKatana presets (a family plus a look and finishing; get_capabilities presets); validated, not saved |
| Storyboard before footage | plan_storyboard, fill_storyboard | Music-planned slots with briefs (part, role, shot, subject, camera, seconds needed) and slate pictures; filling checks footage length; verdict "GAPS storyboard: k of n slots still to fill" / FILLED, and a storyboard_gaps validation warning while slates remain |
| Motion revision | revise_motion | Renders the saved timeline, measures cuts/flashes/shake/jitter/camera movement/motion energy per second against a reference, then up to 4 bounded camera-only revisions on unlocked shots (best kept, saved only if better); cut/flash shortfalls and measures that do not respond to camera edits are reported for the editor; feeds the optional `require_motion` review gate |
| Matte review | review_mask | Sheets of the source every 0.25 s plus the last frame with the background tinted, the matte edge outlined and coverage per frame (flags empty/full mattes and coverage jumps); records accept/reject; strict mode blocks matte-dependent renders until the current matte is accepted. `analyze_clip masks` mode `refine` grows/shrinks, fills holes, smooths over frames and feathers an existing matte. No point-prompted segmentation model is installed |
| Identity references | bind_reference, inspect_identity | Named references (identity, style, product, location) with asset hashes; a face-crop comparison sheet of an asset against them (visual only, no biometric score) with an accept/reject decision; strict mode refuses generated (Comfy-imported) clips until accepted against every identity reference |
| Enforce a reference specification | save_reference_plan, audit_reference_plan | Checks the authored specification; the agent must first verify that specification against the reference |
| Review frames and playback | preview_timeline, compare_reference, preview_segment | Client/model must support actual video/audio review; creation of previews is not review |
| Optional strict gates | set_review_policy | With strict on, start_render needs every timeline source inspected (preview_source/source_contact_sheet) and the current revision previewed (preview_timeline); records are not proof of human review |
| Render and review | start_render, get_render, review_render | Agent approval is not user approval; keep MCP connected while rendering |
| Masks/face tracks/flow | analyze_clip | Face tracks use the bundled YuNet model (box, eyes, nose tip, mouth corners) or the OpenCV cascades (eyes); masks are local heuristics; all need visual checks; semantic weights are separate |
| Comfy | build/check/submit/collect/import_workflow_output/process_clip | Explicit local SDK execution; model availability varies. process_clip kind cutout: point-click subject cut-out (clicks on the first frame, SAM2 video model already installed, one job per clip); OpenKatana's nodes link into custom_nodes with scripts/install_comfy_nodes.py |

Advanced scene and composition routes are documented below and in their
dedicated guides. Model-dependent workflows require installed dependencies.

## Exact text controls

Set `fill:null` for hollow text. Omitted fill remains white. Set `stroke` to a
hex color and `lw` to its width. Use `render_style:"explicit"` on typewriter or
mixed-part text to honor `stroke:null`, `lw:0`, alignment and the actual supplied
weight/style during measurement. Omitted render_style preserves tested legacy
typewriter behavior, including its fixed stroke and centered layout.

`tracking` adds pixels between characters; `scale_x` and `scale_y` independently
scale the text (positive factors). Letter layout is Unicode-codepoint based, not
a general complex-script shaping engine. For contextual scripts, use the new
composition route described in COMPOSITIONS.md; legacy per-letter effects keep
their prior behavior.

`opacity_keys:[[0,1],[0.1,0],[0.2,1]]` uses step changes in seconds relative to the
text event. `letter_opacity_keys` contains one such list per Unicode character,
including spaces, for measured letter flicker. Optional deterministic `flicker`
accepts `hz`, `duty`, `min_alpha`, `seed` and `per_letter`; use explicit keys when
reproducing measured timing. Seeded flicker alone is not reference equivalence.

## Reference plan

First inspect and manually verify a reference's timings and literal text. Save a
plan with `source` (absolute media path), `fps`, `frames` (target excerpt length),
`cut_frames` (all internal cut boundaries), and optional:

- `texts`: objects with exact `text`, `f0`, `f1`, and optional `family` (matched against global text, shot text
  layers and graffiti layers, with layer timing converted from `at`/`d`).
- `fonts`: objects with timeline `family` and exact font-file `sha256`.
- `shots`: objects with zero-based `index` and `fields` containing a recursive
  subset of that shot's required camera/effect/layer settings.
- `allow_extra_text`: defaults true for additional titles; false rejects extras.
- `notes`: explain measured requirements and any user-approved adaptations.

All frames are on the target timeline's fps, and f1 is exclusive. Do not pretend
that an automatically found scene boundary or guessed lyric is verified. Plans
keep their source hash and previous versions. The audit reports precise mismatches;
the agent render operation blocks mismatches. Changing the plan to hide a failed
comparison is not a fix. It needs an explicit, documented change to the brief.

`compare_reference` pairs images at supplied times; `render_offset` is added only
to the render times. `preview_segment` returns a playable MP4 and, when audio is
present, a WAV/audio content block. If the client cannot play or hear them, report
motion/listening review as unverified.

## Batch import

Use `import_media_batch` with a stable request_id and 1..32 excerpt objects:
`{"start":3.5,"duration":1.2,"max_width":1920}`. `audio_only:true` extracts audio.
Repeated IDs return the recorded receipt, including partial/failed outcomes;
inspect recorded assets rather than re-importing them. Source stat changes during
the batch fail it. A full content hash is calculated once, not cached indefinitely.


## 2026-10-20: independent 3D expansion

Actual 3D scene rendering is now available. Read [the scene guide](SCENE3D.md)
(from the repository root: docs/SCENE3D.md) or `read_guide(topic="scene3d")`.
The added operations are `create_scene3d`, `inspect_model3d`, `import_model3d`,
`check_scene3d`, `render_scene3d` and `render_blender`. They use bundled MIT
Three.js/cannon-es or separately installed Blender. See CAPABILITY-GAPS.md
for runtime limits and unverified combinations.

## Composition and plugin expansion

`create_composition`, `save_composition`, `inspect_composition`,
`render_composition`, `list_plugins` and `run_plugin_operator` add original
responsive layout, contextual shaping, reusable components/effects and validated
editing-operation proposals. They export clips into the existing timeline. This
replaces the missing functional route, while private native syntax/ABI, glyph
binary plugin compatibility remains unsupported. See COMPOSITIONS.md.
For glyph outlines use `shape_text`; see RELEASE-TOOLS.md.
