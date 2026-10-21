# Responsive compositions, shaped text and plugins

OpenKatana now has an original composition document and plugin API. CSS Flexbox,
Grid and Chromium text layout handle responsive motion graphics and complex text.
The output is a lossless PNG plate usable by the existing timeline, plus optional
MP4. Extensions use the OpenKatana JavaScript API, not a native binary ABI.
Existing timeline text/hooks continue working; use this composition route for
contextual scripts, responsive layout and reusable parameterized components.

## Agent and CLI workflow

Read `read_guide(topic="composition")`. Six operations share CLI/MCP signatures:

| Operation | Purpose |
| --- | --- |
| `create_composition` | Create an original title composition; returns document, path and revision. |
| `save_composition` | Validate the schema and save with a revision guard, writer lock and previous-version history. Null revision creates only. |
| `inspect_composition` | Render a preview at a requested width/height/frame; inspect actual rectangles, overflow, fonts, grapheme ranges and coverage warnings. Executes declared trusted plugins. |
| `render_composition` | Render PNG frames/MP4; verify backwards seek and fresh mount samples; return `clip` and receipt. |
| `list_plugins` | Execute trusted manifest entries and report their real components, effects, operators and typed parameters. Always includes original `core`. |
| `run_plugin_operator` | Run a deterministic operation on a copy, validate the returned composition/timeline, and return a proposal. Does not save. |

The CLI has the same operations through `openkatana tools` / `openkatana call`.
Standalone composition commands also work:

```powershell
openkatana composition init work/title --width 1280 --height 720 --frames 90
openkatana composition check work/title/composition.json --width 720 --height 1280
openkatana composition render work/title/composition.json --out work/title/render
```

`--project` sets the asset root when the document lives in a subdirectory.
Use new output directories. A full render returns a project-relative `clip`:
put it in timeline `clips`, reference it from a shot, and use normal preview,
audio, transitions, export and review tools. Alpha is preserved in PNG plates;
the optional H.264 MP4 has no alpha. Save/re-render the composition after an
operator or component-parameter change; the prior plate remains an immutable
render, rather than a hidden live dependency. Odd output dimensions need PNG-only
mode (`--no-video` / `video=false`); H.264 output requires even dimensions.

## Document contract

Unknown and inapplicable fields fail. The top level accepts only `schema` (1),
`canvas` (`w`, `h`, `fps`, `frames`), `fonts`, `plugins`, `root`, `tracks`.
Canvas width/height: 16..7680 integer pixels; fps: 1..120; frames: 1..36000.
Paths are relative to the project and must remain inside it. No remote assets.

A font face has `family` (simple alias), exactly one of `bundled` or `src`, and
optional CSS FontFace `weight` and `style` strings. `bundled` is an exact filename
from the installed font manifest; `src` is a local TTF/OTF/WOFF/WOFF2. A variable
face can declare `weight: "100 900"`. Files are loaded and awaited before capture.
No font download occurs at render time. Inspection reports missing character-map
coverage and system/unknown fallback; this does not identify final glyph IDs.
For portable results, supply all script coverage, rather than relying on OS fonts.

Each node needs a unique `id` and one of these `type` values:

| Type | Additional fields |
| --- | --- |
| `box` | `children` node array |
| `text` | Exactly one of `text` or `runs`; each run has `text`, optional typographic `style`, `lang`, `dir` |
| `image` | `src`: local PNG/JPEG/WebP; use CSS object-fit/object-position |
| `component` | `component`: `plugin/name`; `params` object, expanded before validation/layout |

All nodes accept `style`, `responsive`, `lang`, `dir` and `effects`. Direction is
`auto`, `ltr` or `rtl`. Text uses DOM text nodes, never injected HTML. Runs support
font/text/word/letter properties and color, line-height, white-space, direction,
unicode-bidi and vertical-align. Keep layout on their parent text node.
Limits: 1000 expanded nodes, depth 24, 10000 characters per run, 256 runs per node.

`responsive` is an ordered array of `{min_width, max_width, style}` rules, using
inclusive viewport width bounds (defaults 0..7680). Matching later rules override
earlier styles. Component parameters regenerate their node subtree for the target
canvas; IDs of built-in children are stable (`title-heading`, `title-subtitle`,
`name-name`, `name-role`). Author responsive behavior with Flexbox/Grid, intrinsic
sizes, min/max dimensions, wrapping, percentages, `vw`/`vh`, `clamp()` and `calc()`.
Unsupported CSS values fail in the actual browser, not silently disappear.

Style values are CSS strings, including numbers such as `"0.5"`. URLs, !important,
rule blocks, CSS animations/transitions and arbitrary properties are rejected.
The allowed properties are listed below; arbitrary raw CSS/HTML belongs in the
separate trusted `render_page` route, not this declarative contract.

`align-content`, `align-items`, `align-self`, `aspect-ratio`, `background-color`, `border`, `border-color`, `border-radius`, `border-style`, `border-width`, `bottom`, `box-shadow`, `box-sizing`, `color`, `column-gap`, `direction`, `display`, `filter`, `flex`, `flex-basis`, `flex-direction`, `flex-grow`, `flex-shrink`, `flex-wrap`, `font-family`, `font-feature-settings`, `font-kerning`, `font-optical-sizing`, `font-size`, `font-stretch`, `font-style`, `font-variant-caps`, `font-variant-east-asian`, `font-variant-ligatures`, `font-variant-numeric`, `font-variation-settings`, `font-weight`, `gap`, `grid-area`, `grid-auto-columns`, `grid-auto-flow`, `grid-auto-rows`, `grid-column`, `grid-row`, `grid-template-areas`, `grid-template-columns`, `grid-template-rows`, `height`, `hyphens`, `inset`, `isolation`, `justify-content`, `justify-items`, `justify-self`, `left`, `letter-spacing`, `line-height`, `margin`, `margin-bottom`, `margin-left`, `margin-right`, `margin-top`, `max-height`, `max-width`, `min-height`, `min-width`, `mix-blend-mode`, `object-fit`, `object-position`, `opacity`, `order`, `overflow`, `overflow-wrap`, `overflow-x`, `overflow-y`, `padding`, `padding-bottom`, `padding-left`, `padding-right`, `padding-top`, `position`, `right`, `row-gap`, `text-align`, `text-align-last`, `text-decoration`, `text-indent`, `text-orientation`, `text-overflow`, `text-shadow`, `text-transform`, `top`, `transform`, `transform-origin`, `unicode-bidi`, `vertical-align`, `visibility`, `white-space`, `width`, `word-break`, `word-spacing`, `writing-mode`, `z-index`.

Tracks have `node`, `property`, nonempty increasing `[frame, value]` pairs in `keys`, and
optional `easing` (`linear`, `smooth`, `step`). Frame indices start at 0 and must
stay within the composition. Properties: `opacity` (0..1), `reveal` (0..1),
`translateX`/`translateY` (pixels), `rotate` (degrees), `scale` (multiplier).
Only one track per node/property. Values are evaluated from absolute frame time;
no accumulated motion. CSS transforms are preserved before animated transforms.

Text reveal masks the intact shaped run using Unicode grapheme ranges from
`Intl.Segmenter` and DOM Range rectangles. Arabic joins, Indic conjuncts and
combining marks are not split into separately drawn canvas letters. Mixed bidi
runs, language tags, kerning, ligatures, OpenType features, variable-font axes,
vertical writing and fallback stacks are available through browser standards.
The mask is logical grapheme order, not a glyph-outline animation: ligatures can
share geometry, and decorations extending outside a range box may be clipped.
Font/style changes at run boundaries can intentionally change shaping. Review
actual frames, especially for ornate fonts, vertical text and mixed directions.

## Original plugin API 1

A project lists local `plugin.json` paths in `plugins`. Each manifest declares:

```json
{
  "api": 1,
  "id": "kinetic",
  "version": "1.0.0",
  "entry": "kinetic.js",
  "files": ["kinetic.js", "LICENSE.txt"],
  "license": "MIT"
}
```

Every referenced plugin file must be inside the plugin folder and listed; keep
the actual upstream notices. A license label is provenance, not verification of
ownership. API/version mismatches, duplicate/reserved IDs and missing files fail.
The entry registers exactly once with `OpenKatanaComposition.register({...})`.
See the MIT original example `examples/plugins/kinetic/` (also in the installed
package under `share/openkatana/examples/plugins/kinetic`). Copy this entire folder
into your project and retain applicable license notices.

Registration accepts `api`, `id`, `version`, `components`, `operators`, `effects`,
optional async `setup({api})` and `teardown()`. Each named extension has
`description`, `params` and these callbacks:

| Extension | Callbacks |
| --- | --- |
| Component | `build(params, {id, canvas})` returns a node subtree. Expansion is recursively bounded and schema-validated. |
| Operator | `kinds: ["composition", "timeline"]` (choose supported kinds), `run(documentCopy, params, {kind})` returns a full document. |
| Effect | Optional `mount(element, params, {canvas,id})` returns private state; `render(element, params, {frame,t,canvas,id}, state)`; optional `dispose(element,state)`. |

Parameter declarations map each name to `{type, required, default, min, max, enum}`.
Types: string, number, integer, boolean, object, array. Bounds apply to numeric
values; enums use JSON values. Unknown parameters and wrong types fail. Nested
object/array semantics belong to the extension and final document validator.
No hooks into a private ABI, native shared-library loader, automatic registry
downloads or built-in proprietary plugin catalogue are supplied.

Effects run after declarative styles/tracks each frame. A node lists
`effects: [{"use":"kinetic/float","params":{"pixels":8,"hz":1}}]`.
Use absolute `frame` or `t`, not wall-clock time or state accumulated across calls.
Mount/dispose occurs on remount and completion; lifecycle events are recorded.
The deterministic checks sample forward, backwards and after a fresh mount.
They detect tested state/order problems, not prove arbitrary code deterministic
for every frame or protect against malicious JavaScript.

Plugins are trusted project code in an ephemeral browser context. Network requests
outside the local server, popups and CSP violations fail. Project HTTP reads are
restricted to declared plugin files, validated images and font files. There is no
host Python/shell API. This is not an OS security sandbox; do not run untrusted
plugins. A synchronous infinite loop can still require terminating the browser.

## Editing operations and revision safety

`core/batch` accepts `params.ops` with JSON Pointer operations: `add`, `replace`,
`remove`, `copy`, `move`, `test`. Example proposal:

```json
{
  "ops": [
    {"op":"test", "path":"/canvas/w", "value":1280},
    {"op":"replace", "path":"/canvas/w", "value":720},
    {"op":"replace", "path":"/canvas/h", "value":1280}
  ]
}
```

Use `kind="composition"` or `kind="timeline"`. Pointer escaping is `~1` for `/`
and `~0` for `~`; array `-` appends. Missing paths, unknown operations/fields,
out-of-range indices, prototype keys and moves into descendants fail. Root
replacement is deliberately unsupported. Operations apply to a copy; a failed
batch changes no project document. The complete result is validated and checked
for repeatability before it is returned. Save separately using `before_revision`
and `save_composition` or the existing `save_timeline` revision check.

`save_composition` uses an exclusive writer lock and atomic replace, and stores
previous documents in `.openkatana/composition-history/`. A crashed writer can
leave a lock; inspect it before manually removing it. It is never blindly stolen.
These operations use the documented OpenKatana document and plugin contracts.

## Evidence and boundaries

`scripts/test_composition_live.py` uses original layouts and text, local licensed
fonts and the original example plugin. It exercises layout reflow, actual Arabic
joining and ligature metrics, grapheme handling, lifecycle, operation rollback,
network rejection, deterministic export and reuse in the normal timeline.
`tests/test_composition.py` covers contracts, provenance and save conflicts.
Exact results and package evidence are in `docs/composition-validation.json`.

Use the separate `shape_text` operation for low-level glyph IDs/outlines
(see RELEASE-TOOLS.md). Arbitrary script/font combinations need review; native
binary plugins are not supported. Host browser/font versions affect output; receipts record the versions,
source/runtime/font hashes and sampled geometry. Legacy timeline per-letter
effects retain their prior semantics; migrate complex shaped text to compositions.

The integration, API, fixtures and sample plugin were authored for OpenKatana.
The browser is separately installed; fonts are unmodified OFL distributions with
pinned hashes and notices. Public specifications used: [CSS Flexbox](https://www.w3.org/TR/css-flexbox-1/),
[CSS Grid](https://www.w3.org/TR/css-grid-2/),
[OpenType CSS controls](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Fonts/OpenType_fonts)
and [Noto licensing](https://notofonts.github.io/noto-docs/website/use/).
