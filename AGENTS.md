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

Use the user's current agent session. Do not launch additional agents or logins
as part of normal editing. Record receipts and review actual output; publication
and human approval must not be inferred from a passing technical check.
