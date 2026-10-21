# Release readiness

**0.1.0rc2 is a release candidate.** The package includes the local Studio,
72 shared MCP/CLI operations, agent skill, editable rendering templates and
licensed browser/font/model assets. FFmpeg, Chromium, optional Blender and
generative weights are separate installations.

An authenticated hosted pilot is prepared separately; see [hosting](HOSTING.md)
and the [pre-deployment budget](HOSTING-COSTS.md). Its image includes the CPU
rendering runtimes, and its browser/MCP queue shares the local tool implementations.
It has not been deployed. Model services, actual OAuth clients, HTTPS, backup
restore and production load still need deployment-specific validation. Paid
cloud model execution remains disabled until a spending/credential broker exists.

The public setup uses the GitHub repository and one CLI bootstrap for all
agents. It preserves existing projects and customized skills and reports
missing runtime dependencies. Studio follows three numbered editing steps;
guide cards open Markdown with fixed Copy, Download and Close controls.

Current checks and artifact hashes are recorded in `public-release-validation.json`.
These checks cover the release preparation changes, not every optional inference
model. Feature-level fixtures and reproducible commands are in [VALIDATION.md](VALIDATION.md).

Before declaring a final release, review actual CI results, installation on the
intended systems, the UI and final demo output. Automated tests are not human
creative approval. Read [limits](CAPABILITY-GAPS.md) and
[licensing](LICENSING.md) before redistribution.
