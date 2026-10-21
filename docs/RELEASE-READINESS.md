# Release readiness

**0.1.0rc2 is a release candidate.** The package includes the local Studio,
72 shared MCP/CLI operations, agent skill, editable rendering templates and
licensed browser/font/model assets. FFmpeg, Chromium, optional Blender and
generative weights are separate installations.

The public setup uses the GitHub repository and one CLI bootstrap for all
agents. It preserves existing projects and customized skills and reports
missing runtime dependencies. The Studio guide keeps Copy and Close visible
while its content scrolls.

Current checks and artifact hashes are recorded in `public-release-validation.json`.
These checks cover the release preparation changes, not every optional inference
model. Feature-level fixtures and reproducible commands are in [VALIDATION.md](VALIDATION.md).

Before declaring a final release, review actual CI results, installation on the
intended systems, the UI and final demo output. Automated tests are not human
creative approval. Read [limits](CAPABILITY-GAPS.md) and
[licensing](LICENSING.md) before redistribution.
