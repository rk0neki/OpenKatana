# Publishing a reviewed release

Build and test before publishing. The project version is 0.1.1; that does not
mean a registry upload, public repository or GitHub release already exists.

## Build and verify

```sh
python -m unittest discover -s tests -q
python scripts/release_bundle.py --out work/release-0.1.1
python -m build
python -m twine check dist/*
```

Run the quick-edit example from the staged source and an isolated wheel install.
The repeatable wheel check creates its own fresh environment and runs both
bundled examples plus the browser workflow outside the checkout:

```sh
python scripts/test_wheel_install.py --wheel dist/openkatana-0.1.1-py3-none-any.whl --out ../openkatana-wheel-check
```

Choose a new output directory on each run. Dependencies are downloaded; FFmpeg
and a browser must already be installed. Inspect `result.json` and the logs in
that output directory. The same check runs on the Windows/Linux CI matrix.

Keep model inference results separate from synthetic transport tests. Verify the
Windows/Linux CI results for the exact release commit. The current manifest is
regenerated with `python scripts/release_bundle.py --manifest-only`.

## GitHub

Suggested description: **Agent-driven video editing with Studio, ComfyUI Apps,
CLI and MCP. Turn photos, footage and music into finished edits.**

Suggested topics: `comfyui`, `video-editing`, `ai-agents`, `open-source`,
`opensourcehiggsfield`.
Describe the competition inspiration with the README's independence statement.
Do not imply endorsement or service compatibility. A privacy-history cleanup
does not establish code provenance, copyright clearance or an isolated
development process; describe only what the source and dependency records support.
Use [release notes](RELEASE-NOTES.md) for `v0.1.1` and attach the source ZIP, wheel
and `docs/assets/quick-edit.gif`. Confirm the current source and all historical
commits are suitable for public release before changing repository visibility.
Back up refs before any history rewrite; use a lease against the known remote
tip, preserve commit dates/messages, and do not merge an old checkout back in.
Old workflow logs/artifacts need a separate review before making a private repo
public. Passing tests do not authorize deleting history or publishing.

## PyPI

Publishing needs the owner's PyPI account and trusted-publisher configuration or
a scoped upload token. Package-name availability is checked at publication time;
do not advertise `pip install openkatana` until the real upload is verified.
Use the built wheel and source distribution, not an empty placeholder package.

After explicit release approval, upload with the account's configured publishing
method and verify installation in a clean environment. Never commit an API token.
Official guide: [Packaging Python projects](https://packaging.python.org/en/latest/tutorials/packaging-projects/).

## Comfy Registry

A registry publisher ID belongs to the owner and cannot be inferred from the
GitHub username. Create or choose it in the registry first. Then add:

```toml
[tool.comfy]
PublisherId = "YOUR_CONFIRMED_PUBLISHER_ID"
DisplayName = "OpenKatana"
Icon = "YOUR_PUBLIC_ICON_URL"
```

These are documentation placeholders, not active package metadata. Supply a
public, square PNG/JPG/GIF/SVG icon of at most 400 × 400 pixels; an optional
`Banner` uses a 21:9 image. The repository root loads in Manager already; setup
still provisions the separate editor environment. Confirm that behavior in the registry-installed version before
calling it a one-click runtime installation. Run `comfy node publish` only after
the publisher and release are approved. See the official
[publishing guide](https://docs.comfy.org/registry/publishing).

No npm wrapper or placeholder package is needed for this Python application.
