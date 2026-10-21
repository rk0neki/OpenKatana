# External dependencies

The optional 0.1.0 interpolation/upscaling checks used separately installed RIFE
4.26 weights (MIT, including trained-model terms from Practical-RIFE) and
Real-ESRGAN general x4v3 weights (BSD-3-Clause). These weights are not included in
the source archive or wheel. Their pinned license URLs, file hashes and source
locations are recorded in docs/model-validation.json; preserve the upstream
notices when obtaining or redistributing the weights. OpenKatana never downloads
them automatically.

OpenKatana's project distribution uses Apache-2.0. Dependencies retain
their own licenses. The browser 3D dependencies listed below are vendored with
their original MIT notices; other Python/runtime dependencies are installed separately.

Package metadata observed in the tested environment:

| Dependency | Version | Declared license |
|---|---|---|
| comfy-sdk | 0.5.0 | MIT |
| comfy-api-proxy | 0.1.6 | MIT |
| Playwright | 1.64.0 | Apache-2.0 |
| NumPy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| Pillow | 12.3.0 | MIT-CMU |
| MCP Python SDK (optional) | 1.30.0 | MIT |

Transitive dependencies are listed in `requirements-lock.txt`; their notices remain
in installed distributions. ComfyUI, Chrome/Chromium and FFmpeg are separately
installed external programs. If binaries are distributed in a future installer,
review that exact build and include its required notices and source obligations.

The Switchback alphabet is OpenKatana artwork covered by the project license.

The optional `opencv-python-headless` dependency was tested at 4.14.0.94. OpenCV
has its own Apache-2.0 licensing and third-party notices. The default frontal-face
classifier is loaded from that separately installed package; its XML retains the
Intel Open Source Computer Vision license and attribution to Rainer Lienhart.
OpenKatana does not bundle that classifier. The optional custom Comfy nodes use
ComfyUI's separately installed PyTorch/OpenCV runtimes and are newly authored.

No system-font binaries, user media or private test receipts are included in the source package. The only
font binaries are the OFL fonts and the only model weights the YuNet face detector, both listed below.

# Bundled fonts (SIL Open Font License 1.1)

`openkatana/fonts/` ships the fonts below unmodified, each with its own licence text in
`openkatana/fonts/licenses/` and a provenance record (sha256, upstream source, name-table copyright) in
`openkatana/fonts/manifest.json`. The OFL permits bundling and redistribution with software provided each font keeps
its copyright notice and licence and is not sold by itself; Reserved Font Names stay with unmodified fonts only.
All 26 font files are recorded against Google Fonts commit
`5e8a3ba899557829a76cfdac30fa512bda91d7ca`; source and OFL URLs are pinned in the
manifest. `scripts/refresh_font_sources.py --download` verifies upstream bytes and
font identity before replacing files. Importing a bundled font into a project (`import_media`) copies its licence beside it. Fonts are third-party
works; OpenKatana's project licence does not apply to them.

| Font | File | Copyright (font name table) |
|---|---|---|
| Anton Regular | `anton_Anton-Regular.ttf` | Copyright 2020 The Anton Project Authors (https://github.com/googlefonts/AntonFont.git) |
| Bebas Neue Regular | `bebasneue_BebasNeue-Regular.ttf` | Copyright 2019 The Bebas Neue Project Authors (https://github.com/dharmatype/Bebas-Neue) |
| Caveat Regular | `caveat_Caveat-VF.ttf` | Copyright 2014 The Caveat Project Authors (https://github.com/googlefonts/caveat) |
| Cormorant Light | `Cormorant[wght].ttf` | Copyright 2015 The Cormorant Project Authors (github.com/CatharsisFonts/Cormorant) |
| Cormorant Garamond Light | `cormorantgaramond_CormorantGaramond-VF.ttf` | Copyright 2015 The Cormorant Project Authors (github.com/CatharsisFonts/Cormorant) |
| Dela Gothic One Regular | `delagothicone_DelaGothicOne-Regular.ttf` | Copyright 2020 The Dela Gothic Project Authors (https://github.com/syakuzen/DelaGothic) |
| Fira Sans Extra Condensed Black | `firasansextracondensed_FiraSansExtraCondensed-Black.ttf` | Digitized data copyright 2012-2016, The Mozilla Foundation and Telefonica S.A. |
| Fira Sans Extra Condensed Bold | `firasansextracondensed_FiraSansExtraCondensed-Bold.ttf` | Digitized data copyright 2012-2016, The Mozilla Foundation and Telefonica S.A. |
| Fira Sans Extra Condensed ExtraBold | `firasansextracondensed_FiraSansExtraCondensed-ExtraBold.ttf` | Digitized data copyright 2012-2016, The Mozilla Foundation and Telefonica S.A. |
| Great Vibes Regular | `greatvibes_GreatVibes-Regular.ttf` | Copyright 2010 The Great Vibes Pro Project Authors (https://github.com/googlefonts/great-vibes) |
| Inter Italic | `inter_Inter-Italic-VF.ttf` | Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter) |
| Inter Regular | `Inter[opsz,wght].ttf` | Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter) |
| JetBrains Mono Regular | `jetbrainsmono_JetBrainsMono-VF.ttf` | Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono) |
| League Gothic Regular | `LeagueGothic[wdth].ttf` | Copyright 2020 The League Gothic Project Authors (https://github.com/theleagueof/league-gothic) |
| Montserrat Thin | `montserrat_Montserrat-VF.ttf` | Copyright 2011 The Montserrat Project Authors (https://github.com/JulietaUla/Montserrat) |
| Noto Sans Regular | `notosans_NotoSans-VF.ttf` | Copyright 2022 The Noto Project Authors (https://github.com/notofonts/latin-greek-cyrillic) |
| Nunito ExtraLight | `nunito_Nunito-VF.ttf` | Copyright 2014 The Nunito Project Authors (https://github.com/googlefonts/nunito) |
| Oswald Regular | `oswald_Oswald-VF.ttf` | Copyright 2016 The Oswald Project Authors (https://github.com/googlefonts/OswaldFont) |
| Playfair Display Italic | `playfairdisplay_PlayfairDisplay-Italic-VF.ttf` | Copyright 2017 The Playfair Display Project Authors (https://github.com/clauseggers/Playfair-Display), with Reserved Font Name "Playfair Display". |
| Playfair Display Regular | `playfairdisplay_PlayfairDisplay-VF.ttf` | Copyright 2017 The Playfair Display Project Authors (https://github.com/clauseggers/Playfair-Display), with Reserved Font Name "Playfair Display". |
| Press Start 2P Regular | `pressstart2p_PressStart2P-Regular.ttf` | Copyright 2012 The Press Start 2P Project Authors (cody@zone38.net), with Reserved Font Name "Press Start 2P" |
| Rubik Light | `rubik_Rubik-VF.ttf` | Copyright 2015 The Rubik Project Authors (https://github.com/googlefonts/rubik) |
| Unbounded Regular | `unbounded_Unbounded-VF.ttf` | Copyright 2022 The Unbounded Project Authors (https://github.com/googlefonts/unbounded) |
| UnifrakturMaguntia Book | `UnifrakturMaguntia-Book.ttf` | Copyright (c) 2010 j. 'mach' wust with Reserved Font Name UnifrakturMaguntia.
Copyright (c) 2009 Peter Wiegel.

This Font Software is licensed under the SIL Open Font License, Version 1.1. |

# Bundled face detection model (MIT)

`openkatana/models/face_detection_yunet_2023mar.onnx` is YuNet from the OpenCV Zoo, copyright (c) 2020 Shiqi Yu,
under the MIT licence (`openkatana/models/face_detection_yunet-LICENSE.txt`), unmodified (sha256
8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4). It runs through the separately installed
OpenCV `FaceDetectorYN` for `analyze_clip` faces (box, eyes, nose, mouth corners). It is the only model weight file
in the package.


## Bundled 3D dependencies (2026-10-20)

- Three.js 0.180.0: MIT; selected browser core and loader/postprocessing modules.
  Source: https://registry.npmjs.org/three/-/three-0.180.0.tgz
  Original notice: openkatana/web/vendor3d/three/LICENSE.
- cannon-es 0.20.0: MIT; browser rigid-body engine.
  Source: https://registry.npmjs.org/cannon-es/-/cannon-es-0.20.0.tgz
  Original notice: openkatana/web/vendor3d/cannon-es/LICENSE.

Both distributions are unmodified selected files. Archive SHA-512 integrity and
per-file SHA-256 hashes are in openkatana/web/vendor3d/manifest.json. The explicit
maintainer script scripts/vendor_scene3d.py reproduces the selection. Neither
package is downloaded at render time. The source and wheel include their notices.

Blender is an optional separately installed external program, not a vendored or
relicensed dependency. Its own GPL and third-party terms remain applicable to that
installation. OpenKatana's bridge and scene example use the project license;
user scripts/assets may have separate licenses. No Blender binary is distributed.

## Additional shaping fonts (2026-10-20)

- Noto Sans Arabic 2.012, `NotoSansArabic[wdth,wght].ttf`: Copyright 2022 The Noto
  Project Authors (https://github.com/notofonts/arabic). SIL OFL 1.1; original notice
  in `openkatana/fonts/licenses/notosansarabic-OFL.txt`.
- Noto Sans Devanagari 2.007, `NotoSansDevanagari[wdth,wght].ttf`: Copyright 2022 The
  Noto Project Authors (https://github.com/notofonts/devanagari). SIL OFL 1.1; original
  notice in `openkatana/fonts/licenses/notosansdevanagari-OFL.txt`.

These font files are unmodified upstream distributions from Google Fonts commit
47d54ca1ebb14fd864695f1d39dc734f39017c33. Exact source URLs and SHA-256 hashes for
fonts/notices are in `openkatana/fonts/manifest.json`. The font bundle now has 26
faces. Chromium is separately installed and retains its own third-party licenses;
no browser binary is redistributed. The composition integration uses the project
license; the kinetic example retains its MIT license. User-supplied plugins/fonts
need their own rights.

## Optional glyph geometry dependencies

The `text` extra installs uharfbuzz 0.56.x (Apache-2.0, including upstream HarfBuzz
notices in its distribution) and fontTools 4.67+ (MIT). No sources or binaries from
these packages are vendored into this tree. Preserve their installed distributions
and license files when redistributing dependencies. Tested versions: uharfbuzz
0.56.3, fontTools 4.67.0. Sources: https://github.com/harfbuzz/uharfbuzz and
https://github.com/fonttools/fonttools. Glyph output retains the input font hash.


HDR/model adapters in 0.1.0 are original OpenKatana code. HDR transforms call
separately installed FFmpeg/libzimg; no FFmpeg binary is distributed. The model
adapters call public ComfyUI node interfaces through the existing official SDK.
ComfyUI core (GPL-3.0) and its model weights remain separate user installations;
no ComfyUI implementation or weights are bundled by these adapters. Selected
model licenses still require independent review. Interface inspection covered
ComfyUI 0.41.0 Qwen 2.1, MiniMax H3, SeedVR2, video I/O and frame-interpolation
nodes. Reference-conditioned output is not a guarantee of model fidelity.

## Example media

The quick-edit example and derived README GIF use NASA imagery credited in
`examples/quick-edit/assets/sources.json`, with source URLs and SHA-256 hashes.
NASA media-use policy applies; the example does not imply NASA endorsement.
The original synthesized score and its generator use Apache-2.0.

The LTX-2.5 example API graph adapts Comfy Org's workflow template under MIT;
copyright (c) 2023-present Comfy Org. The complete notice is in
`licenses/Comfy-workflow-templates-MIT.txt`. The exact upstream revision and
template/license hashes are recorded in `examples/comfy/assets/sources.json`.
The bundled sample MP4 is AI-generated with Lightricks LTX-2.5 on Comfy Cloud,
with an original prompt. Its original workflow metadata is preserved. The
README GIF is a local OpenKatana edit of that sample with the bundled OFL Inter
font. Model weights are not bundled; the LTX-2.x Community License and the text
encoder's upstream terms are distinct from this project's code license.
