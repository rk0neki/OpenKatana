# Glyph geometry, shutter sampling and transactional edits

These OpenKatana integrations run locally without a generation model.

## Shaped text as editable geometry

From the checkout, install `python -m pip install -e '.[text]'`. HarfBuzz via uharfbuzz (Apache-2.0)
provides shaping; fontTools (MIT) provides outlines. The renderer does not download
fonts. Use a supplied TTF/OTF or an OFL font from the bundled inventory.

```powershell
openkatana shape-text path/to/font.ttf "Create in motion" --size 96 --out shaped-title
openkatana shape-text path/to/font.ttf "Create in motion" --size 96 --radius 500 --out curved-title
```

The `shape_text` agent operation takes `project_id`, `font` (local absolute path),
`text`, `size`, `direction` (`ltr`, `rtl`, `ttb`, `btt`), `language`, `script`,
`features`, `variations` and `radius`. Only the first three are required. Outputs
are `text.svg` and `glyphs.json`, containing glyph IDs, character-index clusters,
advances, offsets, origins, bounds and SVG paths. Missing characters are reported,
not silently replaced by another font. Axes outside a font's range are rejected.

Each call shapes one homogeneous script/direction run. Use browser compositions
for whole-paragraph bidi, fallback, multiline wrapping and responsive layout.
Curved placement rotates whole shaped glyphs along a circular baseline; it does
not distort contours or implement arbitrary surface deformation. SVG geometry
can be used in a custom page or plugin; the result retains the input font hash.
Only a font you may use for the intended output should be supplied.

References: [uharfbuzz API](https://uharfbuzz.readthedocs.io/reference.html),
[fontTools glyph sets](https://fonttools.readthedocs.io/en/latest/ttLib/ttFont.html),
[SVG path pen](https://fonttools.readthedocs.io/en/latest/pens/svgPathPen.html).

## Temporal motion blur in 3D

Add this top-level field to a scene document:

```json
{"motion_blur":{"samples":8,"shutter":0.5}}
```

`samples` is 1..32 (default 1); `shutter` is 0..1 of a frame interval (default
0.5). Exposure is centered on each frame and clipped at the animation's ends.
Samples are averaged in linear light with premultiplied alpha, then converted
back to sRGB. Transparent edges therefore do not acquire dark/colored halos.
Animated cameras, object tracks, morph targets and imported skin animations are
sampled at fractional times. Rigid bodies interpolate positions and quaternions
from the immutable physics cache. This is interpolation of cached simulation,
not a new collision solve at every shutter sample. Increase physics substeps for
better simulation accuracy. Rendering cost scales with sample count.

Receipts record sample times, inputs, implementation hashes and a reverse-seek
determinism check. PNG output can retain alpha; the standard H.264 MP4 is opaque,
8-bit SDR. Averaging rendered samples is not a native HDR accumulation pipeline.

## Atomic timeline editing

`edit_timeline(project_id, operations, revision, save=false)` applies original
RFC 6902 operations to a copy of the timeline. The entire result must pass the
timeline validator. The default returns a proposal; `save=true` takes an exclusive
writer lock, checks the revision again, saves history and atomically replaces the
timeline. A stale revision, bad operation, missing target or invalid timeline
leaves the saved timeline unchanged. A crashed process may leave
`timeline.json.lock`; inspect it before removing it. Locks are never stolen.

Supported operations: `add`, `replace`, `remove`, `copy`, `move`, `test`. JSON
Pointer escapes are `~0` for `~` and `~1` for `/`; `-` appends to an array. Root
replacement is accepted if the replacement is a valid complete timeline. Root
removal and moves into descendants fail. A batch contains 1..256 operations.

```json
{"project_id":"demo","revision":"revision-returned-by-get_project","save":false,
 "operations":[
   {"op":"test","path":"/shots/0/f0","value":0},
   {"op":"add","path":"/shots/0/cam","value":{"push":{"v":0.12}}}
 ]}
```

Use `openkatana call edit_timeline --workspace projects --arguments operations.json`.
Trimming, inserting/removing shots, text, motion and audio changes can be proposed
in one batch. The caller explicitly updates affected time spans; there is no
hidden ripple heuristic. Re-preview before rendering. These operations provide
an independent editing workflow, not a parser for private native command paths.
