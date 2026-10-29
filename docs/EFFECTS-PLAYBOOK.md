# Effects playbook

Everything OpenKatana can do to make an edit feel finished: motion and camera,
light, texture, colour, text and graphics, and interface scenes, with how a
78-second launch film used each technique. Agents read this before planning an
edit so they know every option they have.

None of it is compulsory. Choose what serves the user's brief, the source
material and the user's accessibility preferences. A quiet edit may use almost
none of it; a high-energy edit may use all of it. The user's instructions take
precedence over anything here.

The **high-energy launch-film style** is one way to combine everything below.
Use the whole style when the user asks for a high-energy, aura-farm or
launch-film edit, or says "use the high-energy launch-film preset."

Frame numbers in the reference refer to the original 24 fps edit. Pixel values
refer to a 1920×1080 canvas; brightness values use a 0–255 scale.

## Suggested workflow for a high-energy edit

### 1. Inspect the reference at an appropriate rate

Start at the source frame rate or a sampling rate suited to the edit. Inspect
fast motion and cut boundaries frame by frame when useful. A 60 fps source may
benefit from 60 fps inspection; resampling a 24 fps source to 60 fps repeats
frames and does not reveal additional motion.

### 2. Identify assets the edit needs

After the analysis, list everything the reference relies on that you do not have. Ask for missing material when it affects the brief:

- fonts
- textures and overlays (dust, scratches, light leaks, film burns, paper, grunge)
- music and sound effects
- effects and presets
- stock inserts
- logos and brand colours
- interface captures

Use supplied or generated material according to the user's preferences and rights.

### 3. Work as in After Effects

OpenKatana is an environment like After Effects. Edits in this style are built from:

- **Easy ease and keyframes.**
  - Consider eased keyframes where appropriate for position,
    scale, rotation, opacity, blur, zoom and glow.
  - Camera zooms take eases (`in3`, `out3`, `inout3`, `outback`), plus crash, pulse and
    drift moves.
  - Hook items take per-key eases (`[frame, value, 'io']`).
- **Slow motion.**
  - Use speed ramps (`speed` to `speed1`) and freezes.
  - Use optical-flow slow motion (`analyze_clip` operation `retime`), which renders real
    in-between frames instead of blending. Keep it inside one take.
- **The core eight effects.** Choose from this palette; an edit need not use all eight:
  1. **Turbulence and displacement.** The imperfections of the original use them to bend
     objects and effects (section 21).
  2. **Glow and deep glow.** They sit around buttons and lights, and edits use them a
     lot. Pay attention to where each glow sits and when it starts (section 8).
  3. **3D camera and object blur** (section 4).
  4. **Opacity**, for text, effects, textures and everything else in the edit. The
     percentage differs from scene to scene (section 18).
  5. **Colour invert**, whether of a colour, a texture, an opacity or the whole frame.
     In one reference scene everything was inverted: what was light became dark, and what
     was dark became light (section 17).
  6. **Textures.** They change the depth of an edit massively, so consider layering them
     (section 12).
  7. **Noise, grain and colour grading** (sections 11 and 16).
  8. **Flicker**, of lights, effects or anything else (section 9).

### 4. Also pay attention to

**Story and order**
- Know what each scene says before cutting it.
- The hero is your story's hero: in a win, aura-farm the winner, not the loser.
- Show the key moment itself: the win with both people in frame, not a close-up of the
  winner alone.
- Keep the story order the user asks for.

**Sound first**
- Settle the soundtrack before the picture.
- Cut the picture to the music's beats through one shared clock, so a sound and its shot
  cannot drift apart.
- One shot per beat while tension builds.

**Words**
- Use few, only the ones that land a beat.
- Never use the reference's words.
- Words can sit at low opacity so the shot reads through them, or act as coloured windows
  into an inverted frame (section 17).

**Footage**
- Never stretch or repeat footage to fill time. Use each take once, at its own speed.
- Respect hard cuts inside source clips.

**Brand**
- Use one brand colour on every switch, badge and mark, including inside screen captures
  of other apps.
- A switch glows only once it is on.
- A badge shares its label's tilt and italic skew.

**Interfaces**
- Keep UI captures vector-sharp. Never blur a UI page with a look; motion blur belongs on
  the camera whips only.
- Pace UI scenes so they can be read.

**Real over generated**
- Real footage, real recordings and real stock beat drawn graphics and synthesised
  sounds.
- Use generated voice lines only when they truly add something.

**Licences**
- Record every source.
- Credit CC BY material.
- Clear stock and music licences before release. Free music-generator plans are often
  non-commercial.

**Delivery**
- Check the final encode, not only the render.
- The AAC encoder can overshoot on sharp transients. Low-pass at about 17.5 kHz and keep
  the true peak at or below −1 dBTP.
- Verify the frame count.

**Review**
- Check every cut, not only the shot list.
- Preview frames at full size.
- Compare against the reference at the same frames.

## How to work

1. **Measure, then build.** Measure each frame: cut points, camera motion, sharpness,
   brightness, saturation, grain, vignette, letterbox, and text size and position.
   Build from the numbers.
2. **Compare at the same frames.** Before showing a render, place it beside the
   reference at the same frames, and compare the measurements section by section.
3. **Too much is as wrong as too little.** Apply an effect where the reference has it,
   at its strength, and nowhere else.
4. **Copy the craft, not the content.** Rebuild what the reference does and why, with
   the user's own story, words, footage and brand. Stop copying frame for frame where it
   fights that story; what matters is what you and the tool can make together.

## Motion and camera

### 1. Cut rhythm and time remapping

- The cut rate rises through the edit. The cold open is one take with stepped zooms.
  The logo section cuts 0.9 times per second, the punch burst 1.4, the interface scene
  3.9, the vehicle montage 4.7 and the gym 5.4. One-frame shots are common.
- Shots play at their own speeds: 0.82× in the cold open, 1.5× through a fall, with
  ramps and holds inside shots.
- **OpenKatana:** frame-accurate `shots` with `src`/`srcf`, `speed` and `speed1`.
  One-frame shots are valid.

### 2. Camera shake

- Shakes are crisp. Frames with a shake jolt are as sharp as their neighbours; the
  jolt carries no motion blur.
- Measure camera-only motion. Run phase correlation on a 4×3 grid of patches, and accept
  a frame only when at least 6 of the 12 patches agree within 15 px. Whole-frame
  correlation mistakes word stacks, moving cars, animals and falling objects for shake.
  It also misses cuts in dark footage.
- Reference shake (90th percentile of the high-pass-filtered camera path):

  | Section | Shake |
  |---|---|
  | Cold open | 1.8 px |
  | Logo and switch | 16.8 px, with hard jolts while the switch is on screen |
  | Punch burst | 13 px |
  | Dial intro | 6.8 px |
  | Vehicle montage | 1.7 px |
  | Gym | 1.9 px, with jolts only on the final scream |

- To transfer shake, replace each shot's high-frequency camera path with the
  reference's: offset = reference path − own path. Use one cover zoom per shot so that
  no edges show.
- **OpenKatana:** `cam.shake` (hits, amplitude, decay), the studio `shake` effect, and
  per-frame offsets from a project hook.

### 3. Motion blur, whips and smears

- Blur comes on its own beats: frames where the reference goes soft against its
  neighbours. There are 12 such frames in the logo section, 11 in the punch burst, 27 in
  the vehicle montage and 13 in the gym. Whip frames smear along the travel, for example
  a 4-frame horizontal smear of 60 → 220 px.
- Graphics shown over soft video must be soft as well. Through the switch segment, the
  reference's sharpness is 8–67, against 280 for crisp vector art.
- **OpenKatana:** `cam.shutter`; the studio `dirblur`, `smear`, `zoomblur` and
  `defocus` effects; and the `whip`, `push` and `slide` transitions.

### 4. 3D camera and object blur

- Interface elements move in 3D:
  - A video card flies in, tilted, with motion blur (frame 431).
  - A link pill is thrown in perspective (1256).
  - The chat card bends as it unfolds (268).
- Depth of field softens whatever is out of focus.
- **OpenKatana:** compositions (CSS 3D `transform`, `filter: blur`), `scene3d` with
  `motion_blur {samples, shutter}`, and canvas pages with sub-frame accumulation.

### 5. Crash zooms and punch-ins

- The cold open zooms in over 22 measured steps, with per-frame factors of 1.006–1.040.
  Each step has its own motion blur.
- **OpenKatana:** per-frame shots with `cam.zoom` and `shutter`, and the `zoom`
  transition (`through` or `punch`).

### 6. Environmental motion blur

- On the drone chase, the background is heavily blurred around a sharp vehicle (radial
  blur). Side passes are blurred only mildly, and the start line not at all. Do not
  spread this blur across every vehicle shot.
- **OpenKatana:** masked directional or radial blur (project hook), and the studio
  `zoomblur` and `dirblur` effects.

## Light

### 7. Exposure flashes

- Transitions arrive blown out and recover over 1–3 frames (brightness ×3.0, ×1.5,
  ×1.08). White haze frames sit between shots.
- **OpenKatana:** the `flash` transition (`mode` exposure, screen, add or invert) and
  the studio `exposure` effect.

### 8. Glow and deep glow

- Glow hugs interface elements and type, and its placement matters:
  - A lime halo of about 20–30 px follows the rounded edge of the switch pill and its
    knob (184).
  - The send button has a soft red halo of about 60–80 px and a bright pink rim (500).
  - A large blurred lime-to-cyan bloom sits behind a chip (412).
  - A tile glows, with a magenta bloom behind it (552).
- Deep glow is several radii added together (tight, medium and wide), coloured from the
  element itself.
- **OpenKatana:** the studio `glow` effect (`radii`, `weights`, `tint`), `contour_glow`
  and `bloom`. For per-element glow, use pages or compositions (`box-shadow`,
  `filter`).

### 9. Flicker

- Light flickers inside shots:

  | Section | Brightness pulses |
  |---|---|
  | Logo section | ±7–22 |
  | Vehicle montage | ±8–14, plus single flash frames |
  | Gym | up to ±44 |
  | Fire-lit finale | up to +86 |

- Effects flicker too: glows, light leaks and words switch on and off.
- **Measure:** a frame's mean brightness minus the 5-frame median, inside one shot.
- **Transfer:** apply the reference frame's brightness ratio (frame ÷ 5-frame median) to
  the same output frame as a one-frame exposure change. Skip shots shorter than five
  frames, first frames of shots, and frames that are already flashes or negatives.
- **OpenKatana:** `film_overlay.flicker` and text `flicker`. A measured transfer runs as
  per-frame exposure keys from a project hook; a built-in transfer is a gap.

### 10. Flares and light leaks

- Sun flares with streaks across close-ups, and coloured leaks (magenta, warm) at the
  frame edges.
- **OpenKatana:** the `light_leak` effect and transition.

## Texture

### 11. Grain and noise

- Every shot carries grain, at a level set by its section. Measured grain metric:

  | Section | Grain |
  |---|---|
  | Cold open | 0.86 |
  | Logo | 0.40 |
  | Punch burst | 0.85 |
  | Interface | 0.17 |
  | Vehicle montage | 1.38 |
  | Album | 0.54 |
  | Gym | 1.92 |

- **OpenKatana:** the studio `grain` effect (`sigma` ≈ grain standard deviation ÷ 104 at
  mid grey; `size` scales with W/1080) and `film_overlay`.

### 12. Texture overlays

- Textures give the edit depth:
  - crumpled paper or marble inside letters (752)
  - speckle grain inside a word (641)
  - halftone dots in the logo burst (128)
  - grunge over a red-tinted crowd (752)
  - dust, scratches and lens dirt over bright frames
- Blend by texture type:
  - **Screen:** dust, scratches, sparks, embers, fire and leaks shot on black.
  - **Multiply:** grunge and paper.
  - **Overlay:** halftone.
- Film dust changes every two frames, with a random offset and flip each time.
- Lens textures (dust, dirt, leaks) do not shake with the picture. Scene textures
  (sparks, fire) do.
- **OpenKatana:** `local_halftone` and `film_overlay` (dust, scratch, weave). A project
  hook can draw image textures:
  - Load each texture synchronously on first use, so every frame has it and renders
    stay deterministic.
  - Draw it with an opacity and a blend mode.
  - Inside letters, mask the texture to the glyphs and multiply it over their paint.

  A built-in texture layer is a gap.

### 13. VHS/CRT degradation and scanlines

- Green-black monochrome, low resolution, heavy noise and lifted blacks. Fine CRT
  scanlines (2 px period) run with a horizontally stretched glitch over a close-up
  (860–880).
- **OpenKatana:** the studio `tape` effect (`res`, `vres`, `chroma_shift`, `noise`,
  `head`). Scanlines are a gap.

### 14. Period looks (1970s soft-focus sepia)

- A warm yellow cast, faded blacks, glowing highlights, soft focus and coarse grain
  (975–991).
- **OpenKatana:** a grade (`temp`, `split`, `fade`) with `bloom`, `blur` and `grain`.
  The `film_print` and `golden_hour` presets are close.

### 15. Particles, speed lines and illustrated footage

- Sparks, embers, smoke and fire over the footage; manga speed lines on slashes; and
  2D cel-shaded footage in the finale.
- **OpenKatana:** `local_speed_lines`. Particles come from overlay clips or a particle
  hook. Cel-shaded footage comes from generation.

## Colour

### 16. Grading per shot

- Each section has its own look, and single shots break it: mono, red and sepia
  duotones, deep red, a navy frame, blown "hot" frames, pale frames and teal frames.
- Measured targets:

  | Section | Median brightness | Saturation | Vignette (corner/centre) |
  |---|---|---|---|
  | Cold open | 93 | 58 | none |
  | Logo | 38 | 116 | 0.20 |
  | Punch burst | 49 | 49 | 0.17 |
  | Vehicle montage | 51 | 60 | 0.82 |
  | Gym | 21 | 27 | 0.67 |

- **OpenKatana:** the studio `grade` and `duotone`, `vignette`, and the presets.

### 17. Colour invert

- Single negative frames punctuate cuts: 677, 1503, 1514 and 1568, and ten more in the
  podcast and basketball sections. A whole scene runs inverted, with black type over it
  (1557–1567). Inversion also applies to single elements: a texture, a word or a glow.
- Words can be windows (1558–1568). The frame is inverted in one colour, and the letters
  show the real picture duotoned in another colour, at the word's opacity.
- **Measure:** a frame that correlates with the negative of its neighbours, and not with
  the neighbours themselves.
- **OpenKatana:** the studio `invert` effect (with `amt`) and the `flash` transition with
  `mode: invert`. A word window is built in a project hook:
  - mask the duotoned frame to the glyphs;
  - draw the mask over the inverted frame.

  A built-in word window is a gap.

### 18. Opacity

- Every element has its own opacity, and it changes per scene:
  - A ghosted word goes 25% → 50% → 100% over three frames (659–662).
  - A word fades in 35% → 75% → 100% (219–221).
  - A giant word sits behind the subject at about 70% (1538–1555).
  - A word fades 100% → 0% while blurring 0 → 14 px (568–575).
  - Red letters sit at about 60–75% over the footage (640–642).
  - Textures and glows run at partial strength.
- **OpenKatana:** text `opacity_keys` and `letter_opacity_keys`, the `amt` of every
  studio effect, and composition `opacity`.

### 19. Letterbox

- Bars ease in over 16 frames to 133 px, hold, then retract over 6 frames.
- The letterbox can be a mode. In the finale it eases in while a mode switch flips
  (1643–1669) and settles at 232 px. It opens to 134 px for one wide shot
  (1709–1721) and closes again (1747–1763). At the end it closes to a 228 px strip
  over 18 frames before the end card (1801–1818).
- **OpenKatana:** an animated bars layer, keyed per frame.

## Text and graphics

### 20. Word slams

- Heavy, extended italic type (about 0.21 slant), with a chrome or white fill. Words
  slam in from 1.15–1.18× scale over 2 frames. Stacks of three lines sit at measured
  heights, with cap height about 0.185–0.2 of the frame.

### 21. Turbulent displacement

- An imperfection that bends type and effects:
  - A placeholder line goes wavy (402–404).
  - A word sits in rippling liquid (626–633).
  - Words stretch and warp (1520–1535).
  - Letters ripple at the edges (1557–1567).
  - Logo ornaments burn (160–166).
- **For type:** slide rows sideways and columns up and down by a sum of three sine
  waves, with phases that change every frame. Use 3–22 px at 1080 and a wave size of
  0.25–0.8 of the cap height.
- **OpenKatana:** type can be displaced from a project hook. Plates and graphics need a
  built-in `turbulent_displace` effect (fractal-noise displacement with amount, size,
  complexity and evolution). The `liquid` transition (`wobble`) and `lens_warp` cover
  only part of it.

### 22. Slash cuts, glitch slices and smears on type

- A word is cut by thin dark slash lines, with the pieces offset (223–234). On some
  frames it is smeared sideways by 8–46 px; on others it gets band glitches.

### 23. 3D camera-tracked text

- Words are anchored to a ground plane, moving with the camera and hidden behind
  foreground objects (1013–1098).
- **OpenKatana:** tracking plus `scene3d` text; needs verification.

### 24. Typing, ghosting and split colour

- Type-on at measured rates (2 characters per frame), ghost letters before a word lands,
  and a word changing colour from left to right.

## Interface scenes

### 25. Real interface, built for zooms

- Use the real interface, captured or rebuilt from its HTML and CSS. Keep it
  vector-sharp, because the camera zooms 4–5× into the composer. Match:
  - glow placement
  - the cursor and typing
  - attachment cards
  - the burst on send
  - 3D card motion

## What each version missed

The rebuild went through sixteen renders. These are the misses, in order:

- **v1:** built from thumbnails and 2 fps tiles, so it read as a different video.
  Missing: fast-edit motion, textures, lights and transitions.
- **v3** (the frame-accurate rebuild), missing:
  - VHS/CRT texture
  - 1970s soft-focus sepia
  - cel shading
  - 3D tracked text
  - a scanline glitch over a close-up
  - heavy environmental motion blur
  - particles and speed lines
  - shakes and blurs
- **v4–v7:** shake was measured with whole-frame correlation, so word stacks and moving
  subjects were added as fake shake. Blur was tied to every shake, and environmental
  blur spread to shots where the reference is sharp.
- **v8–v10:** camera-only shake, blur only on soft beats, and slash type. Still missing:
  - turbulent displacement
  - glow and deep glow, with the right placement
  - 3D camera and object blur
  - opacity per element
  - colour invert
  - textures
  - grain and grading
  - flicker
- **v11–v13:** the real interface, the anime finale, stock inserts, textures, type
  displacement and flicker transfer are in. Mistakes found and fixed on the way:
  - Single negative frames came out dark. A negative is light only when its source
    frame is dark, so grade bright frames down before inverting them.
  - The switch was drawn upright with a smooth glow. The reference's is slanted, its
    mark glows, and its lime glow burns with a ragged edge.
  - A cheetah beat was missed because it sat inside a long shot; check every cut, not
    only the shot list.
- **v14:** the user's v13 review. Fixed in v14:
  - The cut ran on the reference's own soundtrack, with its unrelated words (LOSER, LOVE
    MY KIDS) on screen. v14 runs on its own soundtrack, and every word follows its voice
    lines.
  - The cold open, switch and punch burst stayed on the losing sumo. v14 aura-farms the
    grandpa, the winner.
  - The interface pages were blurred by a 1.3 px look over the whole page. The page's own
    frames were sharp. Never put a blur look on vector UI; motion blur belongs on the
    whips only.
  - The finale had too little fighting. v14 cuts a real fight (CC BY anime) shot for shot
    on a 26-hit fight track in the soundtrack.
- **v15:** the user's v14 review: "stop trying to copy everything 1 to 1". Each scene is now
  built for what it has to say. Fixed in v15:
  - The order now serves attention and story. The strongest scene opens as the hook,
    then how it is made, then the results; the grandpa's win closes on the brand.
  - Cuts land on the music's beats, one shot per beat while tension builds, not at the
    reference's frame numbers. The cut that was "too fast and not synced" was the
    reference timing laid over different music.
  - The win must be on screen. Show both people as the loser goes down, not a crash zoom
    on the winner alone.
  - Words as windows (reference 1558–1568, BOWLING): the frame is inverted in one colour,
    and the letters show the real picture duotoned in another, at the word's opacity.
    Shown words can also sit at low opacity so the shot reads through them.
  - Motion-design tools used: eased keyframes on every animated value; eased camera
    zooms, crashes and pulses on beats; speed ramps; optical-flow slow motion (rendered
    plates, not frame blending); two-shot whip, zoom-through, light-leak and flash
    transitions; deep glow, light leak and film weave on the aura shots; speed lines and
    frame slices.
  - Generated voice lines added nothing. Words on screen carry the story; the music and
    real effects carry the energy.
- **v16:** the user's v15 review:
  - **Keep the story order.** The cold open (the hero's win) opens and the finale closes.
    The hook is the cold open itself.
  - **Fewer words.** Keep only the words that land a beat (TOO OLD?, SPEED, GO, AURA).
    Every extra word dilutes them.
  - **Never stretch or repeat footage to fill time.** Use each take once, at its own speed.
    Cut a scene to the length its footage has.
  - **One brand colour everywhere.** The product's accent (OpenKatana red) is on every
    switch, badge and mark, including inside screen recordings of other apps.
  - **A switch glows only once it is on.** A glow while OFF reads as already on.
  - **A badge shares its label's tilt.** Use the label's own rotation and italic skew, so
    they read as one object.
  - **Real footage over drawn graphics.** A real speedometer clip beats a drawn gauge.

## Status in the launch cut (v15)

v15 adds to the table below:
- **Opacity:** low-opacity words.
- **Colour invert:** the word-window treatment.
- **Motion blur and whips:** eased camera moves and two-shot transitions.
- **Cut rhythm:** optical-flow slow motion and speed ramps.

| # | Effect | Status |
|---|---|---|
| 1 | Cut rhythm and time remapping | Done: every section is retimed onto the soundtrack through the shared map; the finale cuts on its fight track |
| 2 | Camera shake | Done; logo section at half strength to keep the switch size. Finale jolts are placed on the fight track's hits, not measured |
| 3 | Motion blur, whips, smears | Done |
| 4 | 3D camera and object blur | Partial: interface cards and the link pill move in 3D with blur; footage moves in 2D |
| 5 | Crash zooms | Done |
| 6 | Environmental motion blur | Done |
| 7 | Exposure flashes | Done |
| 8 | Glow and deep glow | Done for the switches and the interface; other elements not measured |
| 9 | Flicker | Done: transferred per frame from the reference |
| 10 | Flares and light leaks | Done: flares plus texture leaks and burns on the flashes |
| 11 | Grain and noise | Done per section |
| 12 | Texture overlays | Done: film dust and scratches, lens dirt, leaks, halftone, grunge, paper and marble in letters, sparks, embers, fire, smoke |
| 13 | VHS/CRT and scanlines | Section not in the cut |
| 14 | 1970s sepia | Section not in the cut |
| 15 | Particles, speed lines, cel shading | Done in the finale: stylised CC BY anime footage ("Koji") with its own speed streaks and ink impact frames, texture particles |
| 16 | Grading per shot | Done in the finale and on stock inserts; other sections are graded per section |
| 17 | Colour invert | Done, including the finale's red, blue and teal negatives |
| 18 | Opacity | Partial: text, textures and glows have their own opacity; not audited per scene |
| 19 | Letterbox | Done, including the finale's mode letterbox |
| 20 | Word slams | Done |
| 21 | Turbulent displacement | Done for type; plates and graphics remain an OpenKatana gap |
| 22 | Slash cuts, glitches, smears | Done |
| 23 | 3D tracked text | Section not in the cut |
| 24 | Typing, ghosting, split colour | Done |
| 25 | Real interface | Done: the chat and album scenes run on the captured Claude page, shown sharp |
