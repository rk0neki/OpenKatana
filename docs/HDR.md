# HDR finishing

`import_hdr_media` keeps a copy of the original and registers a tone-mapped SDR
proxy for ordinary editing. It returns a separate HDR finishing document.
`render_hdr` and `openkatana hdr render` use original media through FFmpeg/libzimg
and float32 linear BT.2020 compositing, with 1.0 representing 100 nits. They do
not route HDR pictures through the 8-bit Canvas renderer.

Requires separately installed FFmpeg with `zscale`, `tonemap`, `libx265`, `ffv1`
and `libx264`. No additional Python dependencies, downloaded models or services.

```json
{
  "schema": "openkatana.hdr/1",
  "canvas": {"width": 1920, "height": 1080, "fps": 30, "frames": 90},
  "output": {"transfer": "pq", "peak_nits": 1000},
  "clips": [
    {"source": "media/original.mkv", "start": 0, "frames": 90,
     "trim_seconds": 0, "exposure": 0}
  ]
}
```

Paths are project-relative and cannot escape the project. Source color tags must
be present; if absent or known incorrect, explicitly declare `source_color` as
`pq`, `hlg`, `bt709` or `srgb` after inspecting the media. Overrides are recorded.
PQ/HLG use BT.2020; BT.709 and sRGB plates are converted into the working gamut.
Rotation must be conformed explicitly. Dolby Vision is rejected.

Clips play in list order, later clips over earlier clips, with black underneath.
`start`/`frames` use output frames; `trim_seconds` is the source trim. Output rate
is explicitly conformed with FFmpeg's fps filter. This does not synthesize new
motion. Scaling currently fills the entire canvas; prepare the desired crop first.
`exposure` is stops, `opacity` is 0..1. `fade_in` and `fade_out` are frame counts,
with zero and one at the endpoints. For a dissolve, overlap the incoming clip and
fade it in over the outgoing clip; do not also fade the outgoing clip to black.
An unexpectedly short source fails instead of repeating its final frame.

Optional `overlays` are full-canvas sRGB RGBA PNGs (or a directory of `%05d.png` animation frames) with `source`, `start`, `frames`,
`opacity`, `fade_in`, `fade_out` and `white_nits` (default 203), and optional `source_start` frame index for a sequence. Alpha is composited
in linear light. Supplied typography/composition plates retain their SDR origin;
setting a paper-white level does not create additional highlight detail.
Optional `audio` is a project-relative soundtrack, padded/trimmed to the export.

Output files:

- `master.mkv`: FFV1 lossless encoding of **16-bit PQ/HLG 4:4:4 samples**. The
  float-to-16-bit/color conversion itself is not mathematically lossless.
- `video.mp4`: HEVC Main 10, BT.2020 PQ or HLG, limited range.
- `preview-sdr.mp4`: silent BT.709 viewing derivative with explicit Mobius tone
  mapping. Use the HDR output for delivery; do not judge HDR highlights on this proxy.
- `manifest.json`: input/output hashes, color assumptions, clipping fraction,
  measured maximum RGB and frame-average maximum RGB luminance. PQ export includes
  measured content-light metadata. No invented mastering-display metadata.

Pixels outside 0..`peak_nits` are clipped and counted. Inspect this statistic and
adjust exposure/peak deliberately. Linear working pictures occupy a temporary
float file (12 bytes/pixel/frame); allow enough disk space. It is removed after
success or failure. Outputs use a new directory and never replace source media.

Boundaries: no Dolby Vision/HDR10+ dynamic metadata, automatic HDR reconstruction,
or native HDR versions of every Canvas effect. Browser/3D plates remain SDR unless
provided through a separately color-managed source. Those effects are not silently
applied to an HDR source with lost precision. Validate HDR delivery on an HDR
display; numeric checks establish signal handling, not display calibration.

Tests use original float ramps, PQ/HLG round trips, >256 levels, highlights above
100 nits, linear blending/exposure, output tags/frame counts and short-input failure.
Color transforms use the documented [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html#zscale).
