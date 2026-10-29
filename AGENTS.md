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
`skills/openkatana-video/SKILL.md`. Follow the user's brief, source timing and
accessibility preferences. `docs/MUST-USE-EFFECTS.md` is an optional high-energy
launch-film preset, used only when the user selects it. Its effects, slow motion
and reference sampling choices are not requirements for other edits.
