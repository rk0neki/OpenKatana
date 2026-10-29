# Publishing a reviewed release

Build and test before publishing. Version 0.1.1 has been uploaded to the
[Comfy Registry](https://registry.comfy.org/nodes/openkatana). On 2026-10-29,
the Registry API still marked it pending review. This does not establish
availability on PyPI or the existence of a GitHub release.

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

The confirmed publisher is `rk0neki`, the permanent node ID is `openkatana`,
and the display name is **OpenKatana**. The metadata lives in `pyproject.toml`.
The icon is a public 400 × 400 PNG derived from the existing logo. Registry
icons must be square and at most 400 × 400 pixels; an optional `Banner` uses
a 21:9 image.

Publishing is manual. Merging a PR or changing the version does not publish.

1. Create a publishing key for `rk0neki` in the Registry and store it privately
   as the GitHub repository Actions secret `REGISTRY_ACCESS_TOKEN`. Never put
   the key in source, issues, chat or command output.
2. Finish the release checks for the commit on `main` and obtain the owner's
   explicit approval to publish that version.
3. Open Actions → **Publish to Comfy Registry** → Run workflow, choose `main`,
   and enter the approved version (`0.1.1` for the initial release).
   The workflow checks the publisher, node ID, version and source manifest
   before uploading. It only runs from `main`.
4. Record the Registry URL returned by the publisher and confirm the version
   is available. If an upload has an uncertain result, check the Registry
   before retrying.

For later releases, increase the semantic version, regenerate the source
manifest, merge the reviewed changes and repeat the manual publishing steps.
See the official [publishing guide](https://docs.comfy.org/registry/publishing).

### Archive contents and installation check

`.comfyignore` excludes tests, GitHub workflow files and large README MP4/GIF
demonstrations. Keep `deploy/`: the editor's Python package explicitly references
those files and cannot build without them. Keep setup scripts, skills, examples,
documentation, licensed assets and notices. The source manifest describes the
full source release; a trimmed Registry archive is not expected to pass the
full-source manifest check.

The Manager install path inspected during preparation extracts the node archive
under `custom_nodes/openkatana`, then handles `requirements.txt` and `install.py`.
This repository has neither; the editor environment is provisioned separately
with `python scripts/setup.py`. See the upstream
[Manager implementation](https://github.com/Comfy-Org/ComfyUI-Manager/blob/main/glob/manager_core.py)
and [setup instructions](COMFY_APPS.md). Confirm this with the actual published
version before advertising a one-click runtime installation.

After publishing, test Manager installation in a separate ComfyUI instance
without the development OpenKatana link. Install the pack, restart, provision
the editor environment, and run `scripts/install_comfy_nodes.py` using the
Python reported by setup. Restart again and run **00 Full workflow** with empty
media: the media steps should skip and Studio should open. Only claim Manager
installation works after this test passes. Do not install a second copy beside
an existing development link, because both copies register the same node classes.

No npm wrapper or placeholder package is needed for this Python application.
