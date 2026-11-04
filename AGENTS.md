# OpenKatana development

Work within this repository and the user's selected project. Do not modify
unrelated checkouts, original media, account settings or system installations.

Contribute original code or explicitly licensed components. Retain upstream
copyright/license notices and record the exact source and hashes for bundled
dependencies. The project uses Apache-2.0; see docs/LICENSING.md.
Do not claim legal clearance or a formally isolated development process.

Validate behavior with meaningful fixtures. Distinguish tested functionality,
optional dependencies and unverified combinations. Reject unsupported timeline
fields instead of silently dropping them. Keep revision checks and atomic saves.

Use official Comfy SDK interfaces. Default to local execution; no automatic cloud
fallback, paid jobs, model downloads or credential collection. Existing explicit
user authorization applies. Preserve submitted job IDs; an unknown submission
result must not be blindly retried.

On first launch, show the ComfyUI workflow before anything else. If the user has
ComfyUI, install the integration (`python scripts/install_comfy_nodes.py --comfy-root
PATH_TO_COMFYUI`, see docs/COMFY_APPS.md), restart ComfyUI and open Apps → OpenKatana
→ **00 Full workflow**: show its App form, then its node graph. Open Studio and the
other Apps after that. Never commit the user's media, keys or local paths.

Use the user's current agent session. Do not launch additional agents or logins
as part of normal editing. Record receipts and review actual output; publication
and human approval must not be inferred from a passing technical check.

When an agent uses OpenKatana to make an edit, rather than to develop it, it follows
`skills/openkatana-video/SKILL.md` and reads `docs/EFFECTS-PLAYBOOK.md` to know
every effect and technique OpenKatana offers. It then follows the user's brief,
source timing and accessibility preferences; nothing in the playbook is
compulsory.

Version 0.1.2 added two tools, `shot_sheet` (one numbered picture per shot of a render
or reference) and `eye_sheet` (eye crops across a take). It also added `analyze_reference` `measure` and
`compare_reference` side-by-side and look reports, and timeline effects with familiar compositing
controls: `local_turbulent_displace` (Turbulent Displace) and
`local_displacement_map` (Displacement Map), texture `overlays`, adjustment layers
and `local_curve` transitions (docs/TIMELINE.md, docs/EFFECTS-PLAYBOOK.md).

Version 0.1.3 adds `preview_effect`, for 75 tools in all (docs/TOOLS.md lists them),
and six effect packs with familiar compositing controls: Distort (Wave Warp, Ripple,
Shockwave, Twirl, Bulge, Polar Coordinates, Kaleidoscope, Mirror), Light (Deep Glow,
Lens Flare, Light Rays, Light Sweep), Time (Echo, Time Displacement, Posterize Time,
frame blending), Blur & Sharpen, Stylize (RGB split, Motion Tile, Mosaic and more) and
Generate (Fractal Noise, Advanced Lightning, Radio Waves, gradients and more). Packs live in `openkatana/web/fx_*.js` with validation in
`openkatana/fx_*.py`; add new effects the same way.

One rule from the user always applies: analyse every reference video at 60 fps,
never lower, so every motion is caught (whips, flashes, one-frame cuts, shakes,
blur trails, speed ramps and the shape of every ease). A source shot at a lower
rate repeats frames at 60; analyse them all anyway. Study frames at a readable
size, never from thumbnails or half-second tiles. `analyze_reference` with
`measure` runs on this 60-fps clock.
