# Developing OpenKatana

Read AGENTS.md and docs/LICENSING.md. Submit original code or explicitly licensed
components with their notices and pinned source information. Contributions are
accepted under Apache-2.0 unless explicitly stated otherwise. Do not include
private projects, credentials or assets without redistribution permission.

Use Python 3.11+, FFmpeg and Chrome/Chromium:

```sh
python scripts/setup.py
# Activate .venv for your shell, or use its Python executable directly.
python -m unittest discover -s tests -q
python scripts/test_release_features.py --out work/release-features
python scripts/test_composition_live.py --out work/compositions
python scripts/test_scene3d_live.py --out work/scenes
python scripts/test_studio_live.py --out work/studio
```

Each integration output directory must be new. These checks use synthetic local
inputs and no paid services. Live Comfy/model tests are separate explicit scripts.
Select a browser with `OPENKATANA_CHROME` and optional Blender with
`OPENKATANA_BLENDER`. Trusted authoring scripts execute local code.

GitHub Actions defines Windows/Linux build/test jobs. Check the actual results
for your commit; a workflow file alone is not a successful cross-platform test.
See docs/VALIDATION.md for the tested scope.

Create a source bundle with `python scripts/release_bundle.py --out work/release-candidate`.
It includes a SHA-256 manifest and excludes private handoffs, local configuration,
projects, recordings and Git metadata. Build a wheel from the staged source and
test it in a separate environment before publishing. External binaries and model
weights are not bundled. Retain NOTICE and all applicable third-party licenses.
