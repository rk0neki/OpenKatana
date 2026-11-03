// After Effects' Blur & Sharpen effects as an OpenKatana effect pack (Gaussian, Directional, Radial and Camera Lens Blur, Unsharp Mask, Channel Blur, Tilt-Shift); orders 50-57. Parameters and defaults are
// documented in docs/TIMELINE.md; validation is in openkatana/fx_blur.py. Shared helpers: OpenKatanaLocal.util.
// Blurs run on canvases: a gaussian over both axes is the canvas blur filter (on a downscaled copy when it is wide); a
// one-axis gaussian, the directional and the radial blur are built by repeated halving: the running result is drawn over
// itself moved by a doubling step at alpha 1/2, so 2^k evenly spaced copies are averaged in k draws (on half-float
// canvases, rounded to 8 bits once at the end). Edges repeat by mirroring. An amount of 0, or a time before `at`, leaves the frame bit-identical.
(() => {
  const {register, util} = OpenKatanaLocal;
  const {clamp, buffer, copy, keyedT, inBox} = util;
  const RAD = Math.PI / 180;
  const clock = (p, s) => { const t = s.elapsed - (p.at ?? 0); return t < 0 ? null : t; };
  // a canvas with half-float pixels where the browser has them (Chrome 133+): the halving's running means then keep
  // sub-level precision and nothing drifts dark; elsewhere an ordinary 8-bit canvas
  const fine = (w, h) => { const c = buffer(w, h); c.getContext('2d', {colorType: 'float16'}); return c; };

  // src (w x h) with px / py px of edge on the left / top and qx / qy on the right / bottom (px / py by default):
  // mirrored (repeat edge pixels, any width) or black
  function padded(src, w, h, px, py, repeat = true, qx = px, qy = py) {
    const c = fine(w + px + qx, h + py + qy), g = c.getContext('2d');
    if (repeat && (px || py || qx || qy)) {
      const tile = buffer(2 * w, 2 * h), t = tile.getContext('2d');
      for (const sx of [0, 1]) for (const sy of [0, 1]) {
        t.save(); t.translate(sx ? 2 * w : 0, sy ? 2 * h : 0); t.scale(sx ? -1 : 1, sy ? -1 : 1); t.drawImage(src, 0, 0, w, h); t.restore();
      }
      g.save(); g.translate(px, py); g.fillStyle = g.createPattern(tile, 'repeat'); g.fillRect(-px, -py, c.width, c.height); g.restore();
    } else { g.fillStyle = '#000000'; g.fillRect(0, 0, c.width, c.height); }
    g.drawImage(src, px, py, w, h);
    return c;
  }
  // the mean of T^i(src), i < 2^k: k draws, each laying the running result over itself moved by T^(2^j) at alpha 1/2.
  // move(g, n) sets g's transform to T^n. Where a moved copy leaves the canvas it adds nothing (the rest keep their mean).
  function halving(src, k, move) {
    let cur = src;
    for (let j = 0; j < k; j++) {
      const nxt = fine(cur.width, cur.height), g = nxt.getContext('2d');
      g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'low';
      g.drawImage(cur, 0, 0); g.globalAlpha = .5; move(g, 2 ** j); g.drawImage(cur, 0, 0);
      cur = nxt;
    }
    return cur;
  }
  // a box of length L px along unit (ux, uy) over canvas c: 2^k copies spaced L / 2^k (at most `step` px apart);
  // returns {c, off}: the result and the shift along (ux, uy) that centres it (to add when it is drawn back)
  function lineBox(c, L, ux, uy, step = .5) {
    if (!(L > .02)) return {c, off: 0};
    const k = Math.max(1, Math.ceil(Math.log2(L / step))), N = 2 ** k, d = L / N;
    return {c: halving(c, k, (g, n) => g.translate(n * d * ux, n * d * uy)), off: -(N - 1) / 2 * d};
  }
  // a gaussian blur of src (w x h): sigma sx across, sy down (either may be 0), edges mirrored or black. Separable and
  // continuous in sigma: per axis, up to 3 px the sampled gaussian itself (whole-pixel copies summed with its weights),
  // above that three boxes, each 2^k copies spaced so its variance is sigma^2 / 3 (less the 1/6 px^2 the sub-pixel
  // moves add); every copy moves only along its axis, so a one-axis blur never mixes rows (or columns). An axis whose
  // sigma is above 8 px is first shrunk by halvings along that axis only, each the symmetric [1 3 3 1] / 8 kernel
  // (pairs [1 2 1]-smoothed, then averaged), so nothing shifts; the result is stretched back (bilinear) at the end and
  // the variance the shrinking and stretching add is taken off sigma.
  function gaussian(src, w, h, sx, sy, repeat = true) {
    const out = buffer(w, h), o = out.getContext('2d');
    sx = sx > .05 ? sx : 0; sy = sy > .05 ? sy : 0;
    if (!sx && !sy) { o.drawImage(src, 0, 0); return out; }
    let c = src, sw = w, sh = h, nx = 0, ny = 0;
    const smooth = (c, ux, uy) => {   // [1 2 1] / 4 along (ux, uy): two half-alpha passes, one each way
      for (const sgn of [1, -1]) {
        const n = fine(c.width, c.height), g = n.getContext('2d');
        g.drawImage(c, 0, 0); g.globalAlpha = .5; g.drawImage(c, sgn * ux, sgn * uy); c = n;
      }
      return c;
    };
    for (;;) {
      const hx = sx * sw / w > 8, hy = sy * sh / h > 8;
      if (!hx && !hy) break;
      if (hx) c = smooth(c, 1, 0);
      if (hy) c = smooth(c, 0, 1);
      const nw = hx ? Math.max(1, Math.ceil(sw / 2)) : sw, nh = hy ? Math.max(1, Math.ceil(sh / 2)) : sh;
      const n = fine(nw, nh), g = n.getContext('2d');
      g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'low'; g.drawImage(c, 0, 0, sw, sh, 0, 0, nw, nh);
      c = n; sw = nw; sh = nh; nx += hx; ny += hy;
    }
    // sigma in shrunk px, less the shrinking's .25 (1 - 4^-n) and the stretch's 1/6 px^2
    const less = n => n ? .25 * (1 - 4 ** -n) + 1 / 6 : 0;
    const gx = sx ? Math.sqrt(Math.max(.01, (sx * sw / w) ** 2 - less(nx))) : 0, gy = sy ? Math.sqrt(Math.max(.01, (sy * sh / h) ** 2 - less(ny))) : 0;
    const px = gx ? Math.ceil(3 * gx) + 2 : 0, py = gy ? Math.ceil(3 * gy) + 2 : 0;
    c = padded(c, sw, sh, px, py, repeat);
    let ox = 0, oy = 0;
    for (const [sg, ux, uy] of [[gx, 1, 0], [gy, 0, 1]]) {
      if (!sg) continue;
      if (sg <= 3) {   // the sampled kernel: integer moves, weights summed on a half-float canvas
        const r = Math.ceil(3 * sg), wt = [];
        for (let i = -r; i <= r; i++) wt.push(Math.exp(-i * i / (2 * sg * sg)));
        // canvas alpha goes in 1/255 steps: the weights become whole 255ths summing to 255 (largest remainders)
        const tot = wt.reduce((a, b) => a + b), q = wt.map(v => v / tot * 255), iq = q.map(Math.floor);
        let left = 255 - iq.reduce((a, b) => a + b);
        for (const j of q.map((v, j) => j).sort((x, y) => (q[y] - iq[y]) - (q[x] - iq[x]))) { if (left <= 0) break; iq[j]++; left--; }
        const n = fine(c.width, c.height), g = n.getContext('2d');
        g.globalCompositeOperation = 'lighter';
        iq.forEach((v, j) => { if (v) { g.globalAlpha = v / 255; g.drawImage(c, (j - r) * ux, (j - r) * uy); } });
        c = n; continue;
      }
      const sb = Math.sqrt(sg * sg - .5), k = Math.max(1, Math.ceil(Math.log2(Math.hypot(4 * sg, 1)))), N = 2 ** k, d = 2 * sb / Math.sqrt(N * N - 1);
      for (let i = 0; i < 3; i++) c = halving(c, k, (g, n) => g.translate(n * d * ux, n * d * uy));
      ox += 3 * (N - 1) / 2 * d * ux; oy += 3 * (N - 1) / 2 * d * uy;   // each box's copies reach (N - 1) d one way
    }
    o.imageSmoothingEnabled = true; o.imageSmoothingQuality = 'low';
    o.drawImage(c, px + ox, py + oy, sw, sh, 0, 0, w, h);
    return out;
  }
  // put `out` into the frame: everywhere, or inside `region` [x0, y0, x1, y1] (0..1) fading out over `feather` (a
  // fraction of the height, .02 by default) beyond it; pixels outside keep their exact values
  function finish(ctx, out, p, s) {
    const {W: w, H: h} = s;
    if (!p.region) { ctx.globalCompositeOperation = 'copy'; ctx.drawImage(out, 0, 0); ctx.globalCompositeOperation = 'source-over'; return; }
    const box = inBox(p.region, (p.feather ?? .02) * h, w, h), im = ctx.getImageData(0, 0, w, h), d = im.data;
    const e = out.getContext('2d').getImageData(0, 0, w, h).data;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const g = box.weight(x + .5, y + .5);
      if (g <= 0) continue;
      const i = (y * w + x) * 4;
      for (let c = 0; c < 3; c++) d[i + c] = d[i + c] + (e[i + c] - d[i + c]) * g;
    }
    ctx.putImageData(im, 0, 0);
  }
  const DIMS = {both: [1, 1], horizontal: [1, 0], vertical: [0, 1]};

  // local_gaussian_blur: After Effects' Gaussian Blur. `blurriness` (px at 1080; sigma = blurriness / 2) over
  // `dimensions` both / horizontal / vertical; `repeat_edge_pixels` (true) mirrors the picture past its edges so the
  // border stays bright (false: black comes in, as AE without it over black). region / feather confine it.
  register('local_gaussian_blur', {order: 50, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const sg = Math.max(0, keyedT(p.blurriness, t, 20)) * s.H / 1080 / 2;
    if (!(sg > .05)) return;
    const [dx, dy] = DIMS[p.dimensions ?? 'both'];
    finish(ctx, gaussian(copy(ctx), s.W, s.H, sg * dx, sg * dy, p.repeat_edge_pixels ?? true), p, s);
  }});

  // local_directional_blur: After Effects' Directional Blur. Each pixel is spread evenly `blur_length` px (at 1080) both
  // ways along `direction` (degrees clockwise from up, as AE: 0 smears vertically, 90 horizontally). Edges mirror.
  register('local_directional_blur', {order: 51, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const L = Math.max(0, keyedT(p.blur_length, t, 30)) * s.H / 1080;
    if (!(L > .05)) return;
    const th = keyedT(p.direction, t, 0) * RAD, ux = Math.sin(th), uy = -Math.cos(th), {W: w, H: h} = s;
    const px = Math.ceil(L * Math.abs(ux)) + 2, py = Math.ceil(L * Math.abs(uy)) + 2;   // the centred result reads L each way
    const r = lineBox(padded(copy(ctx), w, h, px, py), 2 * L, ux, uy), out = buffer(w, h);
    out.getContext('2d').drawImage(r.c, -px + r.off * ux, -py + r.off * uy);
    finish(ctx, out, p, s);
  }});

  // local_radial_blur: After Effects' Radial Blur around `center` ([x, y] 0..1). spin: copies turned evenly over
  // `amount` degrees (half each way); zoom: as After Effects, each pixel averages the picture along its ray toward the
  // centre, over copies scaled about the centre from 1x to (1 + amount / 200)x, evenly in ratio (bright shapes streak
  // outward; nothing is read from outside the frame). `quality` low spaces copies up to 2 px apart at the far corner,
  // high .5 px. amount and center take keyframes.
  register('local_radial_blur', {order: 52, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const A = Math.max(0, keyedT(p.amount, t, 10));
    if (!(A > 1e-3)) return;
    const {W: w, H: h} = s, c = keyedT(p.center, t, [.5, .5]), cx = c[0] * w, cy = c[1] * h;
    const R = Math.max(...[[0, 0], [w, 0], [0, h], [w, h]].map(([x, y]) => Math.hypot(x - cx, y - cy)));
    const step = p.quality === 'high' ? .5 : 2, spin = (p.type ?? 'spin') === 'spin';
    const span = spin ? A * RAD : Math.log(1 + A / 200), reach = spin ? R * span : R * A / 200;
    if (reach < .05) return;
    const k = Math.max(1, Math.ceil(Math.log2(reach / step))), N = 2 ** k, d = span / (N - 1);
    // spin: the canvas holds the frame turned by every angle within half the span each way (its corners' arcs, sampled
    // finely, plus the arcs' sag between samples); zoom reads only between a pixel and the centre, inside the frame
    let l = 2, tp = 2, r = 2, b = 2;
    if (spin) {
      let x0 = 0, y0 = 0, x1 = w, y1 = h;
      for (let i = 0; i <= 256; i++) {
        const a = (i / 256 - .5) * span, co = Math.cos(a), si = Math.sin(a);
        for (const [x, y] of [[0, 0], [w, 0], [0, h], [w, h]]) {
          const X = cx + (x - cx) * co - (y - cy) * si, Y = cy + (x - cx) * si + (y - cy) * co;
          x0 = Math.min(x0, X); y0 = Math.min(y0, Y); x1 = Math.max(x1, X); y1 = Math.max(y1, Y);
        }
      }
      const sag = R * (1 - Math.cos(span / 512)) + 2;
      l = Math.ceil(-x0 + sag); tp = Math.ceil(-y0 + sag); r = Math.ceil(x1 - w + sag); b = Math.ceil(y1 - h + sag);
    }
    const ox = cx + l, oy = cy + tp, src = padded(copy(ctx), w, h, l, tp, true, r, b);
    const res = halving(src, k, spin ? (g, n) => { g.translate(ox, oy); g.rotate(n * d); g.translate(-ox, -oy); }
      : (g, n) => { const z = Math.exp(n * d); g.translate(ox, oy); g.scale(z, z); g.translate(-ox, -oy); });
    const out = buffer(w, h), g = out.getContext('2d');
    g.translate(-l, -tp);
    if (spin) { g.translate(ox, oy); g.rotate(-(N - 1) / 2 * d); g.translate(-ox, -oy); }
    g.drawImage(res, 0, 0);
    finish(ctx, out, p, s);
  }});

  // local_channel_blur: After Effects' Channel Blur. red / green / blue_blurriness (px at 1080, sigma = value / 2) blur
  // each channel on its own; `dimensions` and `repeat_edge_pixels` as Gaussian Blur. All 0 (the default) is identity.
  register('local_channel_blur', {order: 53, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const k = s.H / 1080 / 2, sg = ['red', 'green', 'blue'].map(c => Math.max(0, keyedT(p[`${c}_blurriness`], t, 0)) * k);
    if (!sg.some(v => v > .05)) return;
    const {W: w, H: h} = s, [dx, dy] = DIMS[p.dimensions ?? 'both'], src = copy(ctx), out = buffer(w, h), o = out.getContext('2d');
    o.fillStyle = '#000000'; o.fillRect(0, 0, w, h); o.globalCompositeOperation = 'lighter';
    const vals = sg.map(v => v > .05 ? v : 0);
    for (const v of new Set(vals)) {   // channels that share a value are blurred together
      const pic = v ? gaussian(src, w, h, v * dx, v * dy, p.repeat_edge_pixels ?? true) : copy(src.getContext('2d'));
      const mask = '#' + vals.map(u => u === v ? 'ff' : '00').join('');
      const g = pic.getContext('2d'); g.globalCompositeOperation = 'multiply'; g.fillStyle = mask; g.fillRect(0, 0, w, h);
      o.drawImage(pic, 0, 0);
    }
    finish(ctx, out, p, s);
  }});

  // local_unsharp_mask: After Effects' Unsharp Mask. out = in + amount% x (in - gaussian(in, sigma = radius px at
  // 1080)), per channel, where the difference is above `threshold` (0..255). amount and radius take keyframes.
  register('local_unsharp_mask', {order: 56, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const a = Math.max(0, keyedT(p.amount, t, 50)) / 100, r = Math.max(0, keyedT(p.radius, t, 1)) * s.H / 1080, th = p.threshold ?? 0;
    if (!(a > 0) || !(r > .05)) return;
    const {W: w, H: h} = s, blur = gaussian(copy(ctx), w, h, r, r).getContext('2d').getImageData(0, 0, w, h).data;
    const out = buffer(w, h), og = out.getContext('2d'), im = ctx.getImageData(0, 0, w, h), d = im.data;
    for (let i = 0; i < d.length; i += 4) for (let c = 0; c < 3; c++) {
      const v = d[i + c], diff = v - blur[i + c];
      if (Math.abs(diff) > th) d[i + c] = v + a * diff;   // the clamped array rounds and clips
    }
    og.putImageData(im, 0, 0);
    finish(ctx, out, p, s);
  }});

  // local_tilt_shift: the miniature look. A band through `center` (a y fraction, or [x, y]) at `angle` degrees,
  // `band` x the frame height across, stays sharp; beyond it the blur grows over `feather` (a fraction of the height) to
  // `blur_radius` (px at 1080, sigma = radius / 2), blended between three blur levels. `saturation` (1) scales colour
  // over the whole frame (1.2-1.5 sells the toy look). center, angle, band, blur_radius and saturation take keyframes.
  register('local_tilt_shift', {order: 55, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s, R = Math.max(0, keyedT(p.blur_radius, t, 30)) * h / 1080 / 2, sat = Math.max(0, keyedT(p.saturation, t, 1));
    if (!(R > .05) && Math.abs(sat - 1) < 1e-4) return;
    const cv = keyedT(p.center, t, .5), [cx, cy] = Array.isArray(cv) ? [cv[0] * w, cv[1] * h] : [w / 2, cv * h];
    const th = keyedT(p.angle, t, 0) * RAD, nx = -Math.sin(th), ny = Math.cos(th);
    const half = Math.max(0, keyedT(p.band, t, .25)) / 2 * h, fe = Math.max(1e-3, p.feather ?? .3) * h;
    const src = copy(ctx), levels = [ctx.getImageData(0, 0, w, h)], L = R > .05 ? 3 : 0;
    for (let i = 1; i <= L; i++) levels.push(gaussian(src, w, h, R * i / L, R * i / L).getContext('2d').getImageData(0, 0, w, h));
    const im = levels[0], d = im.data;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4, dist = Math.abs((x + .5 - cx) * nx + (y + .5 - cy) * ny);
      const m = L ? clamp((dist - half) / fe) : 0;
      if (!(m > 0) && sat === 1) continue;
      let r = d[i], g = d[i + 1], b = d[i + 2];
      if (m > 0) {
        const u = m * L, a = Math.min(L - 1, Math.floor(u)), f = u - a, A = levels[a].data, B = levels[a + 1].data;
        r = A[i] + (B[i] - A[i]) * f; g = A[i + 1] + (B[i + 1] - A[i + 1]) * f; b = A[i + 2] + (B[i + 2] - A[i + 2]) * f;
      }
      if (sat !== 1) { const l = .2126 * r + .7152 * g + .0722 * b; r = l + (r - l) * sat; g = l + (g - l) * sat; b = l + (b - l) * sat; }
      d[i] = r; d[i + 1] = g; d[i + 2] = b;
    }
    ctx.putImageData(im, 0, 0);
  }});

  // local_camera_lens_blur: After Effects' Camera Lens Blur. Each pixel becomes the iris shape (`iris_shape` polygon,
  // `iris_rotation` degrees, `iris_roundness` 0..100 % toward a circle) of radius `blur_radius` px at 1080, averaged in
  // the working (gamma) space as After Effects at 8/16 bpc, so the average brightness stays. Bright points bloom into
  // shaped bokeh through the highlights: pixels with luma above `highlight_threshold` (0..255) are boosted up to
  // 1 + highlight_gain x .4 times before the blur (gain 0..100). A blur map sets the radius per pixel:
  // `map` horizontal / vertical (black at the left / top) / radial (black at `center`) / clip (`clip`'s luma; src /
  // speed / loop as local_displacement_map); the map level `focal_distance` (0..255) is sharp and the blur grows to
  // the full radius at the far end of the map (`invert` flips it). Built on a scaled copy (radius >= 5 px there).
  const SIDES = {triangle: 3, square: 4, pentagon: 5, hexagon: 6, heptagon: 7, octagon: 8, nonagon: 9, decagon: 10};
  const pixelsOf = (pic, w, h) => { const c = buffer(w, h), g = c.getContext('2d'); g.imageSmoothingQuality = 'high'; g.drawImage(pic, 0, 0, w, h); return g.getImageData(0, 0, w, h).data; };
  async function blurMap(p, s, t) {   // the radius fraction 0..1 per frame pixel, null for a uniform blur, 'skip' for no map frame
    const kind = p.map ?? (p.clip ? 'clip' : null), {W: w, H: h} = s;
    if (!kind) return null;
    const m = new Float32Array(w * h);
    if (kind === 'horizontal') { for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) m[y * w + x] = w > 1 ? x / (w - 1) : 0; }
    else if (kind === 'vertical') { for (let y = 0; y < h; y++) m.fill(h > 1 ? y / (h - 1) : 0, y * w, (y + 1) * w); }
    else if (kind === 'radial') {
      const c = keyedT(p.center, t, [.5, .5]), cx = c[0] * w, cy = c[1] * h;
      const R = Math.max(...[[0, 0], [w, 0], [0, h], [w, h]].map(([x, y]) => Math.hypot(x - cx, y - cy))) || 1;
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) m[y * w + x] = Math.min(1, Math.hypot(x + .5 - cx, y + .5 - cy) / R);
    } else {
      const mc = s.clips?.[p.clip], i = mc ? OpenKatanaLocal.mapFrame(p, mc, s.elapsed) : null;
      if (i === null) return 'skip';
      const d = pixelsOf(await s.image(p.clip, i), w, h);
      for (let i = 0, j = 0; i < m.length; i++, j += 4) m[i] = (.2126 * d[j] + .7152 * d[j + 1] + .0722 * d[j + 2]) / 255;
    }
    const f = (p.focal_distance ?? 0) / 255, span = Math.max(f, 1 - f, 1e-3);
    for (let i = 0; i < m.length; i++) { const v = p.invert ? 1 - m[i] : m[i]; m[i] = Math.min(1, Math.abs(v - f) / span); }
    return m;
  }
  register('local_camera_lens_blur', {order: 54, async draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s, R = Math.max(0, keyedT(p.blur_radius, t, 20)) * h / 1080;
    if (!(R > .3)) return;
    const map = await blurMap(p, s, t);
    if (map === 'skip') return;
    // working scale: about 6e7 tap-pixels at most (2.5e7 with a map, whose loop is per pixel), the radius at least 5 px
    // there (3 with a map: its sharp parts come from the full-resolution picture)
    const sc = map ? Math.min(1, Math.max(Math.min(1, 3 / R), (2.5e7 / (Math.PI * w * h * R * R)) ** .25))
      : Math.min(1, Math.max(Math.min(1, 5 / R), (6e7 / (Math.PI * w * h * R * R)) ** .25));
    const ww = Math.max(1, Math.round(w * sc)), wh = Math.max(1, Math.round(h * sc)), Rw = R * ww / w;
    // the iris: taps (dx, dy) with their distance and the polygon's boundary radius in their direction (1 = circle); a
    // corner of the bokeh points up at rotation 0
    const n = SIDES[p.iris_shape ?? 'hexagon'], rot = (p.iris_rotation ?? 0) * RAD, round = clamp((p.iris_roundness ?? 0) / 100);
    const P = Math.ceil(Rw) + 1, taps = [], seg = 2 * Math.PI / n;
    for (let dy = -P; dy <= P; dy++) for (let dx = -P; dx <= P; dx++) {
      const r = Math.hypot(dx, dy), a = Math.atan2(-dy, -dx) - rot + Math.PI / 2;   // gathered: the shape is the taps mirrored
      const u = ((a % seg) + seg) % seg - seg / 2, b = (1 - round) * Math.cos(Math.PI / n) / Math.cos(u) + round;
      if (r <= Rw * b + .5) taps.push([dx, dy, r, b]);
    }
    taps.sort((x, y) => x[2] - y[2]);
    // 0..1 values, boosted highlights, edges repeated by P px
    const sd = pixelsOf(copy(ctx), ww, wh), pw = ww + 2 * P, ph = wh + 2 * P, lin = new Float32Array(pw * ph * 3);
    const gain = (p.highlight_gain ?? 0) * .4, thr = p.highlight_threshold ?? 255;
    for (let y = 0; y < ph; y++) for (let x = 0; x < pw; x++) {
      const i = (clamp(y - P, 0, wh - 1) * ww + clamp(x - P, 0, ww - 1)) * 4, o = (y * pw + x) * 3;
      const l = .2126 * sd[i] + .7152 * sd[i + 1] + .0722 * sd[i + 2], boost = gain > 0 && l > thr ? 1 + gain * Math.min(1, (l - thr) / Math.max(1, 255 - thr)) : 1;
      lin[o] = sd[i] / 255 * boost; lin[o + 1] = sd[i + 1] / 255 * boost; lin[o + 2] = sd[i + 2] / 255 * boost;
    }
    const acc = new Float32Array(ww * wh * 3), row = ww * 3;
    if (!map) {   // one kernel: tap by tap over whole rows
      let tot = 0;
      for (const [dx, dy, r, b] of taps) {
        const wt = clamp(Rw * b - r + .5); if (wt <= 0) continue; tot += wt;
        for (let y = 0; y < wh; y++) {
          const so = ((y + P + dy) * pw + P + dx) * 3, d0 = y * row;
          for (let i = 0; i < row; i++) acc[d0 + i] += wt * lin[so + i];
        }
      }
      for (let i = 0; i < acc.length; i++) acc[i] /= tot;
    } else {      // per pixel: the iris scaled by the map (taps sorted by distance, so the loop stops at the radius)
      for (let y = 0; y < wh; y++) for (let x = 0; x < ww; x++) {
        const mv = map[Math.min(h - 1, Math.floor((y + .5) * h / wh)) * w + Math.min(w - 1, Math.floor((x + .5) * w / ww))];
        const rad = mv * Rw, base = ((y + P) * pw + x + P) * 3;
        let r0 = 0, g0 = 0, b0 = 0, tot = 0;
        for (const [dx, dy, r, b] of taps) {
          if (r > rad + .5) break;
          const wt = clamp(rad * b - r + .5); if (wt <= 0) continue;
          const o = base + (dy * pw + dx) * 3; r0 += wt * lin[o]; g0 += wt * lin[o + 1]; b0 += wt * lin[o + 2]; tot += wt;
        }
        const o = (y * ww + x) * 3; acc[o] = r0 / tot; acc[o + 1] = g0 / tot; acc[o + 2] = b0 / tot;
      }
    }
    const small = buffer(ww, wh), sg = small.getContext('2d'), im = sg.createImageData(ww, wh), od = im.data;
    for (let i = 0, j = 0; i < acc.length; i += 3, j += 4) {
      od[j] = acc[i] * 255; od[j + 1] = acc[i + 1] * 255; od[j + 2] = acc[i + 2] * 255; od[j + 3] = 255;   // clamped
    }
    sg.putImageData(im, 0, 0);
    const out = buffer(w, h), og = out.getContext('2d');
    og.imageSmoothingQuality = 'high'; og.drawImage(small, 0, 0, w, h);
    if (map) {   // sharp parts keep the full-resolution picture; the scaled copy takes over once the radius is ~2 of its px
      const e = og.getImageData(0, 0, w, h), ed = e.data, d = ctx.getImageData(0, 0, w, h).data, full = 2 / sc;
      for (let i = 0, j = 0; i < map.length; i++, j += 4) {
        const a = clamp(map[i] * R / full);
        for (let c = 0; c < 3; c++) ed[j + c] = d[j + c] + (ed[j + c] - d[j + c]) * a;
      }
      og.putImageData(e, 0, 0);
    }
    finish(ctx, out, p, s);
  }});
})();
