# One home: a complete edit without an agent

After the normal setup, activate OpenKatana's environment and run from the repository:

```sh
python examples/quick-edit/render.py
```

The command creates a new project under `work/quick-edit`, imports the bundled
photos, video and original score, estimates beats, builds a `beat-montage`, adds
titles, previews, and renders an eight-second 960 × 540 MP4 with sound.
It prints the output path. Repeating the command creates another project.
Use `--width 640 --height 360` for a smaller render. FFmpeg and Chromium are
required; no model, network, paid service or AI account is needed after setup.

The imagery is NASA public-domain media under NASA's media-use policy, **not
CC0**. The original synthesized score and example code are Apache-2.0; no
sample pack or external music is used. See [asset credits](assets/sources.json).
The example and derived README preview do not imply NASA endorsement.
`make_score.py` reproduces the soundtrack from a fixed seed.

This is a reproducible editing example. It does not demonstrate generative model
inference; the separate [model-to-edit example](../comfy/README.md) covers that path.
