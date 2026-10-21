# Supported timeline contract

This contract defines supported project fields. Unknown fields are rejected.
Extend it only alongside an implementation and relevant regression tests.

Example after preparing a 640x360, 30-fps, 90-frame source into `frames/`:

```json
{
  "canvas": {"w": 640, "h": 360, "fps": 60, "frames": 120, "bg": "#000000"},
  "clips": {
    "A": {"frames_dir": "frames", "pattern": "%05d.png", "n": 90, "fps": 30, "w": 640, "h": 360}
  },
  "shots": [
    {"f0": 0, "f1": 60, "clip": "A", "src": 0, "speed": 1},
    {"f0": 60, "f1": 120, "clip": "A", "src": 1, "speed": 0.5}
  ]
}
```

Paths are relative to the timeline file's folder and must remain inside it.
Sequences start at zero and use `%05d.png` or `%05d.jpg`. All declared frames must
exist. Supply real source dimensions, count and rate from preparation.
The renderer is 8-bit SDR. Preparation rejects HDR transfer tags and nonzero
rotation metadata until an explicit conversion is supplied; it does not silently
retag HDR or report unrotated dimensions for an auto-rotated source.

| Area | Supported fields |
|---|---|
| Canvas | `w`, `h` (up to 7680), `fps`, `frames`, optional `bg` (default `#ffffff`), `boil` (default 2 output frames) |
| Shots | `f0`, exclusive `f1`, `clip`, `src` seconds OR `srcf`, `speed`, `speed1`, `blend`, `loop`, `cam`, `bg`, `fx`, `in`, `out`, `layers`, `face`, `look`, `transition` (two-shot, see below), `special` (whole-frame insert instead of `clip`) |
| Camera | `fit` (cover/contain/width/height), `z`, `ax`, `ay`, `sx`, `sy`, `rot` radians, `mir`, `zoom`, `push`, `punch`, `ladder`, `pan`, `tilt`, `roll`, `handheld`, `shake`, `cover`, `crop`; face-lock fields below |
| Animated zoom | `z0` (1), `z1` (1.08), `ease` (out3; lin/in2/in3/out2/out3/inout/inout3/outback) |
| Fonts | Array of `{family,url,weight?,style?}` pointing to local font files |
| Text | `font`, `caption`, `word`, or `graffiti` events; see below |
| Faces | Clip `faces` JSON, optional `faces_size`; shot `face.box` or `face:false` |
| Mattes | Clip `mask_dir`: same-count, same-size alpha PNG frames |
| Audio | `{src,mode:"copy"}`, `{mode:"mix",tracks:[...]}` (see expansion), or omit for silence |

Canonical colors are six-digit hex (`rgba(r,g,b,a)` where a field allows
transparency: tint, text fills); the native forms below are converted first. Text `pos` is a normalized two-coordinate array; font
size is in canvas pixels. Text baseline is centered vertically. Font loading
failure is an error. Typography fixtures use the same supplied font on both sides;
the comparison does not establish matching layout for every font or writing system.

Shots must be ordered, contiguous, nonoverlapping and cover exactly the canvas
frame count. Sampling uses frame centers. Linear speed ramps integrate speed
over elapsed time. `speed:0` freezes. Negative speed runs backward. `loop` accepts
clamp, loop or pingpong. Default slow-motion blending applies at absolute speed
0.3 through less than 1; explicit `blend:true` also permits slower blending.
This blends pictures; it does not create optical-flow motion between duplicates.
Frame-based `srcf` in-points sit 0.1 microseconds inside their frame, matching the
observed reference boundary convention. Positive-speed blending does not use a
frame before the integer in-point. A reversing ramp can therefore switch to a
whole frame while returning toward its in-point; this is measured reference behavior.

## Native syntax

`validate`/`render` first rewrite these authoring forms into the canonical contract
(`openkatana/native.py`); the saved timeline keeps what you wrote, and Studio edits
the canonical form.

| Form | Meaning |
|---|---|
| `t0`/`t1` on shots, text and specials | Seconds, `"f59"` (frame start 59/fps) or `"b8"`/`"b10.75"` beats on the top-level `"beat": {"bpm", "t0"}` grid. A time maps to the first frame whose centre is at or after it: `f = ceil(t*fps - 0.5)`. A shot's `t1` defaults to the next shot's start (or the end). Use `t0/t1` or `f0/f1`, not both. Times that leave a gap or overlap between shots are rejected. |
| Colours | `"#rrggbb"`, `"rgb(...)"`, `"rgba(...)"`, `[r,g,b]`, `[r,g,b,a]`, or `"$name"` from `"palette": {...}`. Default palette: `ink #0b0b0b`, `accent #b6ff1f`, `accent2 #6fd600`, `lav #c98be0`, `magenta #ff2bd6`, `magenta2 #7a2bff`. Translucent colours are accepted only where a field supports alpha; tint replaces the colour's alpha with `v`. |
| Looks | A string is a preset (`clean`, `bw`, `kawaii`, `duo`, `neg`, `x` = xerox + accent key, `xl` = x with black 0 / white 0.5, and the 13 studio looks), a type (`"threshold"`) or a name from `"looks": {...}`; `{"preset": "duo", "grit": 0}` overrides a preset. Duotone paper defaults to `$accent`. |
| Animated numbers (looks only) | `{"from", "to", "ease": lin/in2/in3/out2/out3/inout/outback, "over": 1, "at": 0}`: progress over `over` x shot duration starting `at` seconds in. Animated values in `fx` are rejected. |
| `fx` numbers | `"fx": {"tint": 0.4}` means `{"v": 0.4}`. |
| Shot `seed` / `note` | `seed` becomes the default `seed` of the shot's seeded effects (grain, dust, leak, glitch, wipe, particles, burst, handheld); `note` is free text and dropped. |
| `xerox` `grain_every` | Frames per grit noise step (default 1). |
| `xerox` `key` | Accent key: `true` or {`channel` g, `lo` .06, `width` .09, `vmin` .16, `vw` .16} (channel dominance x value gate) or {`hue` [h0, h1] degrees, `soft` 15, `sat` .25, `val` .16}; keyed pixels (strength x `amt` above 0.5, randomised by `stoch` .8) become `dark` [10,38,0] -> `light` [196,255,52] by tone `(1-mix)*c + mix*step(c)`, `c = (luma + lift .12) * gain 1.1`, `mix` .4. The tone uses deterministic per-pixel dithering. |

### Source effects

`fx.stutter {n: 3, step: 1}` loops `n` source frames from the in-point, `step`
frames apart, one per output frame regardless of speed (in-point 4, step 2:
4, 6, 8, 4, ...). `fx.trail {n: 3, step: 2, alpha: .35, op}` draws the `n` earlier
source frames (`step` apart, clamped at the clip start; also on freezes) over the
plate before the look, oldest first, ghost `j` at `alpha * (1 - (j-1)/(n+1))`.

### Specials (whole-frame inserts)

Use `"special": {...}` instead of `clip` on a shot (or clip keywords `FLASH`, `WHITE`,
`BLACK`, `COLLAGE`), or top-level `"specials": [{t0|f0, t1|f1|n|d, type, ...}]`
which override the shots beneath them (in time order, no overlap).

| Type | Fields (defaults) |
|---|---|
| `flash` | `color` ($accent), `splat` (true = $ink splats; false; or a colour), `bigsplat` |
| `white` | `color` (#ffffff), `splat` |
| `black` | `color` (#000000), `sparkle` (true) |
| `color` | `color` (required) |
| `collage` | `bg` (#ffffff), `panels` [{`clip`, `src`/`srcf`, `speed`, `loop`, `blend`, `rect` [x,y,w,h] 0..1, `cam`}], `brackets` (true), `lines` [[[x,y]..]], `look` |

All take `allow` (subset of text, stickers, dust, border; defaults per type: flash text+border, white stickers+text+dust+border, black border, color
text+stickers, collage stickers+text+dust+border) — OpenKatana draws global text
and dust; it has no stickers or border layer. A collage panel shows the full-frame
camera image of its clip clipped to the panel rectangle (measured reference
behaviour). Splats, sparkles and brackets are OpenKatana's own designs.

## Camera movement

Camera objects merge shallowly in the order top-level `cam`, clip `cam`, shot `cam`.
The shot replaces a whole effect object, not just individual parameters. The
merged camera's effect wins over the same effect in `fx`; `false` disables it.
Effects accept explicit objects, `true` for defaults, or `false`. Numeric shorthand
and string-valued effects are not supported in this contract.

| Effect | Parameters and defaults |
|---|---|
| `push` | `v` or `rate`: 0.1 scale growth per second |
| `punch` | `v` or `amt`: 0.07; `d`: 0.25 seconds; `curve`: 2; `at`: 0 or `hits`: array of shot-relative seconds |
| `ladder` | `steps` or `v`: array of positive scales, default `[1,1.12,1.24,1.36]` |
| `pan` | `dx` or `v`: 0 widths per second; `dy`: 0 heights per second |
| `tilt` | `v`: 0 heights per second |
| `roll` | `v`: 0 radians; `rate`: 0 radians per second |
| `handheld` | `amp` or `v`: 6 canvas pixels (y uses 0.8x); `hz`: 0.7; `rot`: 0.004 radians; integer `seed`: 7 |
| `shake` | `amp`: `[16,12]` canvas pixels; `d`: 0.25 seconds (0.125 if the shot starts at speed 0); `at`: 0 or `hits`: seconds array; `every`: canvas boil |

Overlapping punches use the largest active impulse. Camera operations run in
zoom, push, punch, ladder, pan, tilt, roll, handheld, shake order. Mirroring reflects the completed
camera image, including horizontal drift, rotation and off-center screen placement.
Shake uses absolute output-frame blocks, a linear decay and the strongest active
hit. A shot starting at zero speed keeps the shorter default decay even if it ramps
into motion. The noise is deterministic when frames are visited in any order.
Handheld uses smooth deterministic drift at absolute frame-center time, so cuts,
source freezes and reverse playback do not reset its phase. `hz:0` holds a fixed
offset; zero `amp` suppresses translation while `rot` remains independent.

`cover:true` enlarges and shifts the camera to keep the outer plate bounds covered
after rotation, pan and shake. `crop:[x,y]`, or a bare y coordinate, chooses a source
anchor and enables coverage. Coverage may cancel movement when no overscan is
available. `fit:cover` alone is only the initial fit and does not enable this correction.
Bars already present inside source pictures remain picture content.

```json
"cam": {"z":1.15,"cover":true,"shake":{"hits":[0,0.4],"amp":[10,8],"d":0.2}}
```

### Face-locked cameras

Select `cam.type:"facelock"` or `cam.lock:true`. Put its options directly in `cam`;
`cam.facelock` and `fx.facelock` are unsupported. The camera uses the clip's supplied,
smoothed face track at the selected source frame, including retiming and looping.

| Field | Default and meaning |
|---|---|
| `ld` | 0.12: desired eye distance as a fraction of output width |
| `lx`, `ly` | 0.5, 0.4: target eye midpoint in normalized output coordinates |
| `z0`, `z1` | 1, 1.04: zoom multiplier with out3 easing across the shot |
| `kick`, `kick_rate` | 0.035, 14: initial zoom impulse and exponential decay rate |
| `lockRot` | 1: roll correction strength, from 0 to 1 |
| `cover` | true: hide source edges; explicit false allows borders |

Face lock establishes the base scale, roll, anchor and target before other camera
effects. Base `z`, `rot`, `ax/ay`, `sx/sy` and `crop` do not override that locked
framing. Coverage can shift the face away from its requested position when the
source lacks enough margin. Mirroring applies to the completed camera.

`shot.face` overrides and `face:false` affect face-anchored graphics, not the camera's
clip track. Box-only track entries use inferred eye positions. No face detection is
performed. OpenKatana rejects face
lock without a supplied usable track, or with coincident eye coordinates, before
opening the renderer. This prevents a requested lock from silently becoming an
ordinary camera. A manual shot box alone cannot satisfy the track requirement.

```json
"cam": {"type":"facelock","ld":0.2,"ly":0.42,"handheld":{"amp":2,"rot":0.001}}
```

## Transitions and compositing

Use `fx` on a shot or top-level `post` for defaults on every shot. Shot `fx` replaces
the same global effect object; `false` disables it. Colors are six-digit hex.

| Effect | Parameters and defaults |
|---|---|
| `white` | `at`: 0; `d`: 0.067; `color`: white; `side`: in |
| `flash` | `at`: 0; `d`: 0.1; `color`: white; `amt`: 1; `side`: in |
| `dip` | `d`: 0.15; `color`: black; `side`: in |
| `tint` | `color`: `#ff78dc`; `v` or `amt`: 0.3; `op`: screen; optional `d` fades to zero |
| `invert` | `at`: 0; optional `d`, otherwise shot duration; `amt`: 1 |
| `strobe` | `every`: 2 output frames; `color`: white; `amt`: 1; optional `at`, `d` |
| `letterbox` | `top`, `bottom`, or `v`: 0.1 of canvas height; `color`: black |

An outgoing transition starts at shot duration minus `d` unless `at` is supplied (`at` is accepted on every
transition-type effect: white, flash, mosaic, blur, flashlight, glitch, magenta, wipe). Intro/outro shorthand accepts a string, object or array:
`"in":{"type":"flash","d":0.2}`. It replaces the corresponding `fx` entry.
If both `in` and `out` use the same effect name, `out` wins, as in the reference — except blur and flashlight,
which map to different effects per side (blurIn/blurOut, fin/fout), so both apply.
To keep both, use repeated layers:

```json
"layers": [
  {"type":"dip","side":"in","d":0.2},
  {"type":"dip","side":"out","d":0.3}
]
```

Layers support the seven compositing effects above, every expanded effect (EXPANSION.md), text, graffiti,
outline, cutout and declared hook layers. Compositing effects default to `post`, text/graffiti to `over`,
and outline/cutout to `subject`;
default order is `100 + array index`. Optional `phase` chooses `back`, `subject`,
`over`, `post`, or `final`; `order` sorts within that phase. Equal orders preserve
insertion order. The plate is drawn before all phases, and global text is at
`over:60`. Phase names do not add subject masks automatically in this subset.
Built-in `fx` order is invert 16, tint 51, white 60, flash 61, dip 62, strobe 63,
letterbox 70, all in `post`. The current comparison exercises screen and multiply
tint blending; other accepted Canvas blend modes have not received parity fixtures.

### Two-shot transitions

`in`/`out` above affect one shot. To blend two shots, put `transition` on the
**incoming** shot (index 1 or later):

```json
{"f0":30,"f1":60,"clip":"B","transition":{"type":"push","d":0.4,"dir":"left"}}
```

Both shots run their full pipelines (camera, look, effects, layers) inside a frame
window around the cut. The outgoing shot keeps playing past its `f1` and the
incoming shot pre-rolls before its `f0` with their own timing, so give them handle
frames (`loop`/clamp rules apply at the clip ends). Global `text` is drawn once over
the composite and does not move with pushes or slides.

Window: `n = max(2, round(d * fps))` frames; `align` `center` (default) starts at
`f0 - floor(n/2)`, `start` at `f0`, `end` at `f0 - n`. `flash` has no `d`: it spans
`pre_frames` before the cut, `peak_frames`, then an exponential tail of
`ceil(tau * ln(1/cutoff) * fps)` frames. The window must lie inside both shots and
must not overlap the previous transition; otherwise validation names the frames.
Unknown parameters and choices are rejected.

| Type | Seconds | Parameters (defaults) |
|---|---|---|
| `dissolve` | 0.5 | `curve` (linear; any ease) |
| `fade`, `dip` | 0.52, 0.44 | `color` (#000000), `out`/`hold`/`in` proportions, `mode` dip, in, out |
| `flash` | window rule | `color` (#ffffff), `mode` solid, add, screen, exposure, black, invert; `pre_frames` 0, `pre` [0.35, 0.65], `peak_frames` 1, `tau` 0.06, `cutoff` 0.05 |
| `glitch` | 0.3 | `streaks` vertical/horizontal, `split` 0.5, `intensity` 0.8, `seed` |
| `lens` | 0.43 | `mode` bulge, pinch, twirl, barrel, pincushion; `split` 0.46, `strength` 0.6, `center`, `radius` 1, `chroma` 0.04, `vignette` 0.25 |
| `light_leak` | 0.7 | `anchor` left/right/top/bottom/center, `palette` amber/rose/teal/white, `peak` 1.3, `size` 0.95, `blend` add/screen, `split` 0.45, `seed` |
| `liquid` | 0.6 | `mode` blob/melt, `wobble` 0.04, `rim_width` 0.015, `rim_glow` 0.7, `rim_color`, `softness` 0.06, `ease` outCubic, `seed` |
| `luma` | 0.6 | `source` A/B/noise, `order` dark_first/light_first, `softness` 0.08, `noise` 0.15, `seed` |
| `pixel_sort` | 0.37 | `axis` x/y, `dir` down/up, `mask` bright/dark/all, `split` 0.5, `work_res` 540 |
| `push` | 0.4 | `dir` left/right/up/down, `ease` inOutCubic, `shutter` 0.5, `divider_width` 0, `divider_color` |
| `slide` | 0.4 | `dir`, `ease`, `shutter` 0.5, `reveal` false (true: A slides away over B) |
| `spin` | 0.5 | `dir` cw/ccw, `out_angle` 120, `in_angle` -120, `scale` 1.4, `center`, `split` 0.4, `shutter` 0.75 |
| `whip` | 0.3 | `dir`, `split` 0.5, `travel` 1.2, `shutter` 0.7, `blur_max` 0.4 |
| `wipe` | 0.5 | `shape` linear, circle, diamond, box, star, clock, barn, strips; `dir` rtl/ltr/ttb/btt (linear), `feather` 0.02, `ease`, `mode` open/close, `center`, `count` 7, `stagger` 0.5 (strips) |
| `zoom` | 0.4 | `mode` through/punch, `out_scale` 3, `in_scale` 0.55, `center`, `split` 0.55, `shutter` 0.5 |
| `datamosh` | 0.5 | `block` 16, `drift` 0.08, `split` 0, `seed` — an approximation: blocks of A drift and refresh to B; there are no codec motion vectors |

Eases: linear, inQuad, outQuad, inOutQuad, inCubic, outCubic, inOutCubic, inExpo,
outExpo, inOutExpo, inOutSine. `get_capabilities` returns this vocabulary as
`shot_transitions` (defaults, choices, numeric ranges). The frame trace marks
transition frames with `{"transition":{"type","p"}}`.

## Studio looks, effects and camera moves

A look may be `{"type": "studio", "grade": {...}, "fx": [{"type": ...}, ...]}` (applied to the plate, before
graphics), or one of 13 named presets: `clean_luxe`, `cold_concrete`, `dreamy_bloom`, `film_print`, `golden_hour`, `gritty_contrast`, `home_tape`, `mono_noir`, `neon_night`, `pastel_fade`, `silver_bleach`, `teal_orange`, `vivid_pop`.
`get_capabilities().studio_looks` lists every parameter range.

Grade (in this order): `auto` (auto levels 0..1), `mult` [r,g,b], `temp`/`tint` (-1..1, linear light), `exposure`
(stops), `mono`, `sat`, `contrast` (about mid grey), `gamma` (v^gamma), `black` (crush), `split`
[[shadow r,g,b], [highlight r,g,b], strength] (0.5 = neutral), then `fade` (lift) and `gain`.

Every effect takes `amt` (0..1 mix with the picture underneath).

| Effect | Parameters |
|---|---|
| `bleach` | `a` |
| `bloom` | `thr`, `r`, `strength` |
| `blur` | `r` |
| `chroma` | `px`, `vertical` |
| `clarity` | `amount`, `radius` |
| `contour_glow` | `color`, `radius`, `strength`, `inner`, `blend` |
| `datamosh` | `block`, `drift`, `share`, `seed` |
| `defocus` | `amount`, `highlights` |
| `dirblur` | `len`, `angle` |
| `duotone` | `shadows`, `highlights`, `amount` |
| `exposure` | `ev` |
| `film_overlay` | `level`, `grain`, `dust`, `scratch`, `flicker`, `weave`, `seed` |
| `glow` | `threshold`, `knee`, `radii`, `weights`, `strength`, `tint`, `blend` |
| `grain` | `sigma`, `size`, `mono`, `seed` |
| `invert` | (none) |
| `lens_warp` | `mode`, `strength`, `center`, `radius`, `dir`, `chroma`, `vignette` |
| `light_leak` | `anchor`, `palette`, `peak`, `size`, `blend`, `seed` |
| `pixel_art` | `block`, `colors`, `dither`, `strength` |
| `pixel_sort` | `mask`, `lo`, `axis`, `dir`, `work_res` |
| `pixelate` | `size` |
| `posterize` | `levels`, `mode` |
| `rgb_split` | `px`, `angle` |
| `saturation` | `sat`, `hue` |
| `shake` | `px`, `seed` |
| `smear` | `len`, `angle`, `px`, `sat` |
| `tape` | `res`, `vres`, `chroma_shift`, `depth`, `noise`, `head`, `seed` |
| `vignette` | `amount`, `feather`, `center` |
| `zoomblur` | `amount`, `cx`, `cy`, `n` |

`contour_glow` needs a clip `mask_dir`. `datamosh` is an approximation (blocks drift over the shot; no codec
motion vectors).

Camera additions: `crash` {v, d, at, ease, center} (fast zoom toward a screen point, landing `at` seconds into the
shot), `pulse` {v, d, hits, center} (zoom in and back out on each hit), eased `roll` {from, to, ease, d}
(radians), easing `inout3`, and `shutter` (0..1 of a frame: camera motion blur from averaged sub-frame samples).
Studio move names on a shot camera are rewritten to these keys: `zoom.crash` {scale, dur, at, ease, center,
blur_shutter}, `zoom.punch` {times, scale, release, mode: bounce}, `zoom.in_out` {times, scale, center},
`shake.beat` {times, profile: impact|heavy|micro, amp}, `drift` {dx, dy (share of the frame over the shot), zoom, rot
(degrees), ease}, `handheld` {profile: calm|walk|chaos}, `roll` {angle: [from, to] degrees, dir, ease}. `times`
is a list of seconds or `beats`, `downbeats`, `1/2`, `1/8`, `offbeat`, `snare` on the top-level `beat` grid (use the
BPM and phase from `analyze_audio`). Studio eases are named `linear`, `inQuad`, `outQuad`, `inOutQuad`, `inCubic`,
`outCubic`, `inOutCubic`, `outBack`.

## Stickers

Top-level `assets` and `stickers` provide placement, pop-in, shadow and die-cut drawing:

```json
"assets": {"stickers": ["stickers/s01.png", "stickers/s02.png"],
           "cutouts": [{"clip": "A", "t": 0.3}], "cutout_border": 10, "cutout_border_color": "#ffffff"},
"stickers": [{"t0": 0.8, "t1": 1.6, "kind": "graphic", "n": 3, "mode": "burst", "step": 0.1,
              "slots": [[0.15, 0.2], [0.85, 0.2], [0.85, 0.8]], "size": [120, 180], "rot": 0.2, "shadow": true}]
```

`assets.stickers` may also be `{"dir", "n", "pattern", "start"}`. A cut-out is the clip's subject at time `t` (or
source frame `f`) through its matte (`mask_dir`, from `analyze_clip masks`) with a border. Events: `kind` graphic |
cutout, `n` (1..24), `mode` hold (all at `t0`) | burst (one every `step` seconds; default a 1/16 note on the `beat`
grid, else 0.1 s), `ids` (1-based picks), `size` [min, max] px, `slots` (else positions are chosen away from the
frame centre, the `avoid` boxes and each other), `avoid` [[x0, y0, x1, y1]], `rot` (radians, random range), `shadow`
(hard offset shadow), `seed`. They draw in the over phase (order 50); `fx.stickers: false` hides them on a shot and
specials show them when their allow list contains `stickers` (white, colour, collage).

## Authoring aliases

- Text `font`: CSS shorthand `"[style] [weight] {S}px \"Family\""` (`{S}` or `{size}` = the item's `size`, or a px
  number); sets `style`, `weight`, `size` and `family` (a declared font).
- Top-level `font_stacks` `{kind: "CSS stack"}`: a text item without `family` takes the first declared family of the
  stack for its `kind` (else `sans`). `kind` heavy = italic 900, thin = upright 300.
- Text `on_specials` (default true): false hides the event on special frames.
- Text `sfx`: a sound-effect cue at the event start (an OpenKatana synthesised sound, see `list_sfx`).
- Top-level `sfx` `{"cues": [...]}`: cues added to `audio.cues`; `auto` / `hits` true is rejected (no automatic
  placement).
- Top-level `audio_tracks` `[{asset_id | src, start, duration, at, speed, gain_db, fade_in, fade_out}]` becomes
  `audio: {"mode": "mix", "tracks": [...]}` (`gain_db` -> `volume`); `[]` is silence; not together with `audio`.
- `custom_text_types` declares hook text types (needs `hooks.src`, see Project hooks).

## Decorative and face graphics

Shot `fx` entries, timeline `post` entries or shot layers use the names, parameters, phases and
orders below. The renderer is `web/decor.js`. Eye units are the tracked eye distance; face points sit in
the face's rotated frame (mouth and nose are estimated from the eyes). `word`, `type` and `tag` need a declared font
(`family`, or `font_stacks`).

| Layer (phase:order) | Parameters | What it draws |
|---|---|---|
| `stairs` (back:30) | `seed`, `size` px, `cells` [[col,row]], `x`, `y`, `color`, `color2` | pixel squares around (x, y), re-drawn every 4 frames with ~12% dropped |
| `glow` (subject:90) | `amt` / `v`, `blur` px | screen-blended blurred copy of the frame so far |
| `glint` (over:25) | `at`, `d`, `from`, `to` (0..1, or source px with `src`), `r`, `color` | 4-point star with white core and rays sweeping from -> to, then holding |
| `doodles` (over:30) | `v` 0..3 (0/5/10/16 marks), `n`, `scratch`, `mono`, `types`, `seed`, `color` | ink marks on a ring around the face (or centre) |
| `face_doodles` (over:40) | `items` [{t, o:[x,y] eye units, s, r, at}] or `n` + `pool`, `seed`, `colors` | kawaii shapes pinned around the face, popping in |
| `doodle` (over:41) | `t`, `pos`, `size`, `rot`, `at`, `seed`, `alpha`, `colors` | one kawaii shape |
| `word` (over:57) | `text` / `v`, `at`, `dx`, `dy`, `k`, `min`, `max`, `fill`, `stroke`, `lw`, `shadow`, font keys | outlined word under the face (0, 1.7 eye units) with a 3-frame pop; (0.5W, 0.6H) without a face |
| `type` (over:59) | `parts` / `text`, `at`, `dt`, `base`, `dx`, `dy`, `k`, `min`, `max`, `pos`, `fill`, `stroke`, `shadow`, font keys | typewriter reveal under the face (0, 2.1 eye units) |
| `slash` (over:58) | `at`, `dx`, `dy`, `n` (4), `seed`, `fill`, `stroke` | tapered slashes growing from a face point or the centre |
| `sparkle` (over:45) | `pos`, `r`, `seed`, `color` | outlined 4-point sparkle with ink dots |
| `splat` (over:45) | `items` or `pos`, `r`, `n`, `seed`, `color`, `color2` | paint splat with droplets |
| `bw` (post:20) | `filter` (CSS filter functions), `bars` [top, bottom] px, `color` | re-filters the whole frame, optional bars |
| `tag` (post:40) | `text` / `v`, `pos` (bottom / face), `bx`, `by`, `dx`, `size`, `fill`, font keys | small handle text with a dark shadow |
| `border` (final:30) | `color`, `seed` | hand-inked ragged frame edge |
| `cheeks` (over:20) | `color`, `force` | zigzags under the eyes (skipped below 30 px eye distance unless `force`) |
| `fangs` (over:21) | `color`, `len` (x mouth width), `dy`, `force` | two fangs from the estimated mouth line |
| `ears` (over:32) | `at`, `size`, `dx`, `dy`, `colors` | cat ears above the head, kept inside the frame |
| `whisk` (over:33) | `at`, `dx`, `dy`, `colors` | whiskers |
| `blush` (over:34) | `at`, `dx`, `dy`, `size`, `colors` | blush hearts on the cheeks |
| `ast` (over:56) | `dx`, `dy`, `size`, `colors` | spinning asterisk on the nose |

Kawaii shapes: note, note2, heart, hearto, bow, spark, star, dots, swirl, squig, arrow, cross, dash3, blush, ear,
whisk. Ink shapes: zig, scratch, splat, rays, arrow, spark, cross, hatch, star, xx, bolt, bang. `colors` is
{line, fill, blush}.

## Local adapter layers

The effects below work as shot `fx`, timeline `post` entries or shot `layers`
(`{"type": "local_halftone", ...}`), rendered by `web/localfx.js`.

| Effect | Parameters (defaults) | Notes |
|---|---|---|
| `local_whip` | `amount` (.3), `d` (.3 s), `at` (0), `dir` (right; left/up/down) | echo smear from `at`: echoes trail in `dir` up to 1.6 x amount of the frame, weighted toward the frame, reach fading as (1 - t/d)^2 |
| `local_zoom_blur` | `amount` (.3), `d` (.3 s), `at`, `center` [.5,.5] | radial smear, fading as (1 - t/d)^2 |
| `local_halftone` | `spacing` (8 px), `mix` (1), `ink` (#16181e), `paper` (#f4efdf) | dark dots on opaque paper; the ink share of each cell follows a tone-response curve (Rec.709 luma); `mix` is the dots' opacity, so overlapping dots read darker and no picture shows through; `mix` 0 leaves the picture untouched |
| `local_speed_lines` | `count` (48), `opacity` (.5), `color`, `inner` (.55), `width` (1.5), `seed`, `every` (1 frame) | random radial lines (own layout), final phase |
| `local_frame_slices` | `amount` (.1 of the width), `continuous` (true), `n` (9), `seed`, `d` (.15 s) | horizontal bands shifted; not continuous = a burst of `d` at the shot start |
| `local_selective_color` | `hue` (deg), `tolerance` (25), `soft` (5), `min_sat` (.12) | colours within tolerance kept, others Rec.709 grey |
| `local_posterize` | `levels` (4) | per-channel rounding to levels |
| `local_paper_frame` | `mode` (paper / filmstrip), `color`, `margin` (.045), `seed` | torn paper edge or sprocket strip, final phase |
| `local_scramble_text` | `text`, `family` (a declared font, required), `size` (12% of height, bold), `pos`, `fill`, `d` (.6 s), `at`, `seed` | letters resolve left to right over `d` |

`cam.local_measured` `{f0, f1, pan_x, pan_y, zoom, roll_deg}` is a linear move over absolute frames `f0..f1-1`: pan by
`pan_x` x width and `pan_y` x height, roll by `roll_deg`, zoom by `1 + zoom`, with a constant cover margin for the
end state so the picture never uncovers. Missing keys default to 0.

## Project hooks (custom layers and text types)

For a measured mechanism the catalogue lacks, a project may declare one script:

```json
"hooks": {"src": "comp/fx.js", "layers": ["k_crown"], "text_types": ["k_text"]}
```

Declared layer names may then be used as `fx` keys (`true`, `false` or an object of parameters; `phase`/`order`
allowed) or as layer types, and declared text types as global `text` types (`custom_text_types` adds text
types). Undeclared names stay rejected, and hook names may not shadow built-in effects. The script registers what it
declared:

```js
OpenKatanaHooks.layer('k_crown', {phase: 'over', order: 22, draw(ctx, params, s) { /* draw on ctx */ }});
OpenKatanaHooks.text('k_text', {init(item, i) {}, draw(ctx, item, s, i) { /* item.t0/t1/text/params */ }});
```

`s` carries `W`, `H`, `t` (absolute seconds at the frame centre), `f`, `fps`, `lt` (seconds into the shot), `dur`,
`face` and `noise(a, b, c)`. For hooks written against the `RRC.register("LAYERS"|"TEXT", name, spec)` interface
the same calls accept the alternate argument order (`draw(S, p, x)`); `RRC.util` is not provided. Sandbox: the script
runs in the headless render page under a same-origin Content-Security-Policy; every request that is not to the
loopback project server is blocked and listed in `receipt.hooks.blocked_requests`; `Math.random` is re-seeded every
frame so renders are reproducible; the script's SHA-256 is in the input manifest and `receipt.hooks`. A hook that
throws, fails to load or does not register a declared name stops the render with a named error. There is no CPU
time limit inside a frame: an endless loop in a hook stalls that render.

## Alpha mattes and subject layers

Add `mask_dir` to a clip. It points to `%05d.png` files starting at zero, matching
the clip's count and source dimensions. Use white RGB plus an alpha channel:
transparent means background, opaque means subject, and partial alpha blends.
Grayscale RGB-only masks fail validation; they need explicit conversion to alpha.
Each mask stays tied to the whole source index, including during reverse and slow
motion; it is not interpolated with the blended plate. Mask bytes are included in
the input hash manifest. Automatic segmentation is a separate, unimplemented workflow.

`fx.cutout:true` redraws the subject over back graphics. `fx.outline` adds a matte
halo and enables subject redraw unless `cutout:false` is explicit. Outline parameters
are `r` 14, `color` `#e2b0f0`, `blur` 3, `alpha` 0.95, `dx` 16 and `dy` 6, in canvas
pixels. These effects do nothing when a clip has no matte, matching the reference.
For text behind a subject, add a text layer with `phase:"back"` and set `fx.cutout:true`.

Review a matte with `review_mask` (sheets every 0.25 s plus the last frame, coverage, region count and flags; record
`accept: true/false`). In strict review mode a timeline that renders a clip's matte (cutout, outline, contour,
contour_glow, cut-out stickers) is refused until that exact matte is accepted. `analyze_clip masks` with
`{"mode": "refine", "grow": px, "fill_holes": true, "keep_largest": true, "smooth": frames, "feather": px}` writes a
refined copy of the current matte.

## Typography

Fonts are local files declared in the top-level `fonts` list: `[{"family", "url" (project path), "weight", "style"}]`;
every text item names one of those families.
OpenKatana bundles 24 SIL OFL fonts (`openkatana/fonts`, listed in THIRD_PARTY_NOTICES.md): Anton, Bebas Neue, Caveat,
Cormorant, Cormorant Garamond, Dela Gothic One (Japanese), Fira Sans Extra Condensed (Bold, ExtraBold, Black), Great
Vibes, Inter (roman, italic), JetBrains Mono, League Gothic, Montserrat, Noto Sans, Nunito, Oswald, Playfair Display
(roman, italic), Press Start 2P, Rubik, Unbounded and UnifrakturMaguntia. `list_fonts` lists them first with
`bundled: true`, the licence and copyright; `import_media` on a bundled font's `path` copies it into the project with
its licence file (asset `license`), and its project path is the `url` to declare. Variable fonts take `weight` from the
declaration. Other fonts are your own files (OpenKatana downloads nothing). `list_fonts` with `text` reports which characters each font
lacks; `preview_fonts` reports missing glyphs per specimen; validation warns (`missing_glyphs`) when timeline text uses
characters its declared font file does not contain (the browser would draw a fallback font there).

Global events need `f0`, exclusive `f1`, `family` and `text`. `type` can be `font`,
`caption` or `word`. Shot layers use `type:"text"` and `at`/`d` in shot-relative
seconds instead. Global text is suppressed by `fx.text:false`; explicit text layers
remain independent. Text `pos` is normalized, while `size` is in canvas pixels.

| Property | Default and behavior |
|---|---|
| `size`, `weight`, `style` | 96, 800 (number 1..1000 or "normal"/"bold"), italic |
| `fill`, `stroke`, `lw` | white, `#c98be0`, 5; `stroke:null` removes the outline in ordinary text |
| `shadow` | glow; also dark, false, or `{color,blur,dx,dy}` |
| `align`, `rot`, `alpha` | center, 0 radians, 1 |
| `karaoke` | `{words: [{text, t0, t1}], highlight, mode: word|sweep}`: word times in seconds from the item start; each word (in order in `text`) takes `highlight` from its `t0` (`sweep` fills it left to right until `t1`); plain text only. `make_captions` writes these. |
| `anim` | none, pop, slam, fade, grow, type |
| `anim_d` | 0.15 seconds for fade, otherwise 0.1 |
| `pop`, `sc` | 0.18 punch amount; slam scales `[1.3,0.9,1.06,1]` |
| `dt`, `base` | Typewriter interval 0.05 seconds, initial extra character count 0 |
| `fade_out` | Optional seconds before the event ends |
| `boil`, `seed` | Jitter amount in pixels, default 0; seed 3 |

Observed reference quirks are preserved: shadow applies to the stroke, so ordinary
text with no stroke has no glow; typewriter text remains centered regardless of
`align`, and `stroke:null` falls back to the default outline in typewriter mode.
Mixed-weight `parts` and face anchors are supported as described below. Arbitrary
CSS font strings remain unsupported. Unknown fields are rejected.

Earlier OpenKatana builds used plain text defaults. To preserve that appearance,
set `weight:400`, `style:"normal"`, `stroke:null` and `shadow:false` explicitly.

### Mixed weights

Use `parts:[["NEW","bold"],[" WAVE","thin"]]` instead of, or alongside, `text`.
Parts take precedence. Kinds are `bold` (italic 800), `thin` (normal 300) and
`heavy` (italic 900); a single text event can also specify `kind`.
Every event still needs an explicitly declared local `family`.

Measured quirks: parts render as separately centered characters, ignoring `align`.
Widths are measured using each kind even when an explicit `weight`/`style` overrides
the drawing font. Typewriter/parts stroke widths are fixed at 4 for thin and 5 for
other kinds, ignoring `lw`; null stroke uses the default outline. Parts suppress
pop/slam/grow scaling but retain alpha fade and fade-out. `anim:"type"` reveals
parts over time; other animation values show all parts immediately.

### Face anchors

Set `anchor:"face"`, optional `o:[x,y]` in eye-distance units, and optional
`size_eu`, `min`, `max`. The default offset is `[0,1.05]`. Text follows the face's
roll plus `rot`; `size_eu` replaces the pixel size using eye distance. Without it,
the ordinary `size` remains. This is text placement only, not a face-locked camera.

For a manual box, add `"face":{"box":[80,30,240,170]}` to a shot. These are
source-pixel corners, not width/height. Eye positions are inferred at 30% and 70%
of box width and 42% of its height. `face:false` suppresses the track on that shot.

For moving anchors, a clip's `faces` points to a local UTF-8 JSON array with one
entry per source frame. A typical entry is:

```json
{"f":0,"box":[60,30,160,140],"eyes":[[100,75],[160,85]],"score":1,"src":"det"}
```

Here `box` is `[x,y,width,height]`; eyes are two pixel positions. Optional nose,
mouth, score and src metadata are validated. Missing faces use `null`, or an entry
with `box:null`. `faces_size:[width,height]` describes the track coordinate space;
it defaults to the prepared clip size. Track bytes are hashed in the input manifest.

`analyze_clip` faces writes such tracks. Its default detector is the bundled YuNet model (MIT, OpenCV Zoo), which
measures the box, both eyes, the nose tip `[x,y]` and both mouth corners `[[x,y],[x,y]]` on every detected frame and
tracks them through missed frames (`eyes_src` det/track; nose and mouth share it). `detector:"cascade"` keeps the
OpenCV cascades (eyes only, else `eyes_src:"estimate"`). When a track has nose/mouth points, face graphics use them:
`fangs` hang from the measured mouth and `ast` sits on the nose tip; without them both are estimated from the eyes.
The render's `frame-trace.json` face entry adds the roll `a` and the landmarks in eye units (`nu,nv` nose, `mu,mv`
mouth centre, `mw` mouth width).

The measured reference behavior fills missing entries from the nearest valid frame
(earlier wins ties), then smooths center coordinates with sigma 1.4 and distance/
roll with sigma 2.6, each within seven frames. Tracks follow the whole source frame
index during slow motion and reverse playback. Manual boxes bypass smoothing and
override a clip track. With no usable face, the reference fallback is a canvas
model centered at `(0.5W,0.42H)` with eye distance `0.1W`. No detection, automatic
tracking, identity processing or source-binding assurance is performed here;
supply coordinates belonging to your source.

### Graffiti

`type:"graffiti"` uses the Switchback letterforms (`web/letterforms.js`) and
needs no font. Layout, fitting and write/slam/hold animation use the controls below.

```json
{"type":"graffiti","word":"GO!","f0":0,"f1":48,"region":"center","mode":"write"}
```

Choose exactly one of `word`, `text` (newline-separated) or `lines`. Text becomes
uppercase. Supported glyphs are A-Z, 0-9, space and `! ? . , : - ' / + * # &`.
Modes: `hold` is stable; `write` reveals strokes; `slam` scales and shakes briefly;
omitted mode is static lettering with deterministic jitter. `wdur` controls write
duration. `wkeys` supplies one absolute time per non-space letter plus an end time;
keys must increase. `sc` sets slam steps. `seed` makes variations repeatable.

`region` accepts a normalized rectangle or center/full/left/right/top/bottom,
leftwide/rightwide, tl/tr/bl/br/tl2, lower/title. `cap` limits letter height.
`nib`, `halo`, `halo_color`, `ink`, `echo`, `under`, `rot`, `slant`, `bounce`,
`longbar`, `leading`, `line_dx`, `line_rot` and `line_scale` control treatment.
Colors are explicit hex; halo_color and echo also accept false. Per-line arrays
must match the line count. `under` accepts a bool or per-line booleans.

Shot `fx.graffiti` and `type:"graffiti"` layers use `at`/`d` seconds and default
to write mode. Explicit layers default to phase over and order 100+index; the
built-in fx uses over:61. `fx.text:false` hides global graffiti, not explicit layers.

Audio copy preserves packets and checks the output stream hash against its input.
Use an already aligned AAC/M4A soundtrack compatible with MP4 for copy mode.
Mix mode adds trimming, placement, speed, fades, gain and optional limiting; see
EXPANSION.md. Neither mode implies a listening review or a loudness target.

## Expanded contract

See [EXPANSION.md](EXPANSION.md) for looks, new effects, original graffiti, audio mixing,
source analysis, workflow processing and project UI controls. Unsupported fields still fail.

## Additional explicit typography controls

Text supports hollow `fill:null`, independent `scale_x`/`scale_y`, pixel `tracking`,
step `opacity_keys`, per-character `letter_opacity_keys` and deterministic `flicker`.
Set `render_style:"explicit"` for typewriter/parts that honor supplied font styling,
alignment, `stroke:null` and `lw:0`. Omitted render_style retains legacy typed text
defaults. Full schemas and limitations are in [EDITOR_TOOLS.md](EDITOR_TOOLS.md).
