// After Effects' Generate effects as an OpenKatana effect pack (Fractal Noise, Cell Pattern, Gradient Ramp, 4-Color
// Gradient, Grid, Radio Waves, Advanced Lightning); orders 70-76. Parameters and defaults are documented in
// docs/TIMELINE.md; validation is in openkatana/fx_generate.py. Shared helpers: OpenKatanaLocal.util.
// Every generator renders onto a layer of its own and lays it over the picture with `blend` (normal, add, screen,
// multiply, overlay, soft_light, ... the canvas composite modes) at `opacity` (0..1, keyframable): opacity 0, or a time
// before `at`, leaves the frame bit-identical. Per-pixel generators compute at most 480 px wide and upscale smoothly.
(() => {
  const {register, util} = OpenKatanaLocal;
  const {clamp, buffer, keyedT, perlin, rng} = util;
  const hex = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
  const colOf = (v, d) => hex(typeof v === 'string' && v[0] === '#' ? v : d);
  const css = c => `rgb(${c[0]},${c[1]},${c[2]})`;
  const BLENDS = {normal: 'source-over', add: 'lighter', screen: 'screen', multiply: 'multiply', overlay: 'overlay',
    soft_light: 'soft-light', hard_light: 'hard-light', color_dodge: 'color-dodge', color_burn: 'color-burn',
    darken: 'darken', lighten: 'lighten', difference: 'difference', exclusion: 'exclusion', hue: 'hue',
    saturation: 'saturation', color: 'color', luminosity: 'luminosity'};

  // the generator's time and opacity: null while nothing is drawn (before `at`, or opacity 0)
  function begin(p, s) {
    const t = s.elapsed - (p.at ?? 0);
    if (t < 0) return null;
    const o = clamp(keyedT(p.opacity, t, 1));
    return o > 0 ? {t, o} : null;
  }
  // lay a layer (any size, stretched smoothly to the frame) over the picture with the blend mode and opacity
  function lay(ctx, s, layer, p, o) {
    ctx.save();
    ctx.globalCompositeOperation = BLENDS[p.blend ?? 'normal'] ?? 'source-over';
    ctx.globalAlpha = o; ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(layer, 0, 0, s.W, s.H);
    ctx.restore();
  }
  // a reduced working size (at most 480 px wide) for the per-pixel generators
  function small(s) {
    const sc = Math.min(1, 480 / s.W);
    return {w: Math.max(1, Math.round(s.W * sc)), h: Math.max(1, Math.round(s.H * sc)), sc};
  }
  // AE's Overflow: clip, soft clamp (a tanh curve of slope 1 at mid grey) or wrap back (values fold back at 0 and 1)
  const OVERFLOW = {clip: v => clamp(v), soft_clamp: v => .5 + .5 * Math.tanh(2 * (v - .5)),
    wrap: v => { v = ((v % 2) + 2) % 2; return v > 1 ? 2 - v : v; }};
  // seeded lattice hash -> -1..1
  function hash4(x, y, z, w, sd) {
    let h = Math.imul(x, 0x27d4eb2d) ^ Math.imul(y, 0x165667b1) ^ Math.imul(z, 0x9e3779b1) ^ Math.imul(w, 0x85ebca6b) ^ sd;
    h = Math.imul(h ^ (h >>> 15), 0x2c1b3c6d); h = Math.imul(h ^ (h >>> 12), 0x297a2d39); h ^= h >>> 15;
    return (h >>> 0) / 2147483647.5 - 1;
  }
  const soft = u => u * u * (3 - 2 * u);
  const INTERP = {block: () => 0, linear: u => u, soft_linear: soft};
  // value noise in x, y (interpolated by the noise type) and z (and w, for a looping evolution) interpolated softly
  function vnoise(x, y, z, w, ip, sd, four) {
    const X = Math.floor(x), Y = Math.floor(y), Z = Math.floor(z), Q = four ? Math.floor(w) : 0;
    const u = ip(x - X), v = ip(y - Y), sz = soft(z - Z), sq = four ? soft(w - Q) : 0;
    let out = 0;
    for (let dq = 0; dq <= (four ? 1 : 0); dq++) for (let dz = 0; dz <= 1; dz++) {
      const wt = (dz ? sz : 1 - sz) * (four ? (dq ? sq : 1 - sq) : 1);
      if (wt === 0) continue;
      const zz = Z + dz, qq = Q + dq, a = hash4(X, Y, zz, qq, sd);
      if (u === 0 && v === 0) { out += wt * a; continue; }
      const b = hash4(X + 1, Y, zz, qq, sd), c = hash4(X, Y + 1, zz, qq, sd), d = hash4(X + 1, Y + 1, zz, qq, sd);
      const top = a + (b - a) * u, bot = c + (d - c) * u;
      out += wt * (top + (bot - top) * v);
    }
    return out;
  }
  // two value-noise lattices half a step apart in z (and w), summed: where one is at a lattice point (still, full
  // spread) the other is midway (moving fastest, narrowest spread), so evolution runs at a steady pace and contrast
  // instead of easing in and out once a revolution
  const vnoise2 = (x, y, z, w, ip, sd, four) =>
    .7071 * (vnoise(x, y, z, w, ip, sd, four) + vnoise(x, y, z + .5, w + .5, ip, sd ^ 0x6a09e667, four));
  // the error function (Abramowitz and Stegun 7.1.26, error under 1.5e-7)
  function erf(x) {
    const q = 1 / (1 + .3275911 * Math.abs(x));
    const y = 1 - q * (.254829592 + q * (-.284496736 + q * (1.421413741 + q * (-1.453152027 + q * 1.061405429)))) * Math.exp(-x * x);
    return x < 0 ? -y : y;
  }
  const seedHash = seed => Math.imul((seed | 0) ^ 0x5bd1e995, 0x01000193) ^ 0x3c6ef372;

  // local_fractal_noise: After Effects' Fractal Noise. Octaves of noise (`complexity`, a fraction weighs in the last one),
  // each `sub_scaling` % the size of the one before, `sub_influence` % as strong and turned `sub_rotation` degrees more.
  // fractal_type basic (signed noise round mid grey), turbulent_sharp (|noise|: sharp dark creases) or turbulent_smooth
  // (a rounded |noise|: soft billows, soft creases); noise_type block, linear, soft_linear (value noise) or spline (gradient noise).
  // Then invert, contrast (%) and brightness (%) about mid grey, and overflow clip, soft_clamp or wrap. Transform:
  // rotation (degrees), scale (%, 100 = 100 px features at 1080), offset [x, y] px at 1080. evolution (revolutions) plus
  // speed (revolutions a second) moves through the noise; cycle n loops it exactly every n revolutions (a circle through
  // 4-D noise). `tint` colours it (black to the colour).
  register('local_fractal_noise', {order: 70, draw(ctx, p, s) {
    const on = begin(p, s);
    if (!on) return;
    const {t, o} = on, {W, H} = s, k = H / 1080, {w, h, sc} = small(s);
    const kind = p.fractal_type ?? 'basic', ntype = p.noise_type ?? 'soft_linear', spline = ntype === 'spline';
    const ip = INTERP[ntype] ?? soft, sd = seedHash(p.seed ?? 1), pn = perlin(p.seed ?? 1);
    const C = clamp(keyedT(p.complexity, t, 6), 1, 20), oct = Math.ceil(C - 1e-9), last = C - (oct - 1);
    const cell = Math.max(.5, keyedT(p.scale, t, 100) * k);
    const off = keyedT(p.offset, t, [0, 0]), ox = off[0] * k, oy = off[1] * k;
    const rot = keyedT(p.rotation, t, 0) * Math.PI / 180, srot = (p.sub_rotation ?? 0) * Math.PI / 180;
    const infl = (p.sub_influence ?? 70) / 100, scl = (p.sub_scaling ?? 56) / 100;
    const z = keyedT(p.evolution, t, 0) + (p.speed ?? 0) * t, cyc = p.cycle;
    const R = cyc ? cyc / (2 * Math.PI) : 0, cz = cyc ? R * Math.cos(2 * Math.PI * z / cyc) : z, cw = cyc ? R * Math.sin(2 * Math.PI * z / cyc) : 0;
    // per octave: the sampling matrix (rotate by -angle, divide by the feature size), weight and decorrelating salts
    const M = [], wts = [];
    let a = 1, f = 1 / cell, wsum = 0, w2 = 0;
    for (let i = 0; i < oct; i++) {
      // non-block octaves also turn a fixed 31 degrees each, so their lattices never line up (no grid look)
      const q = rot + srot * i + (ntype === 'block' ? 0 : .541 * i), wi = i === oct - 1 ? a * last : a;
      M.push([Math.cos(q) * f, Math.sin(q) * f, i * 19.19, i * 7.13, i * 3.7, i * 5.3]); wts.push(wi);
      wsum += wi; w2 += wi * wi; a *= infl; f /= scl;
    }
    const gain = {block: .74, linear: 1.12, spline: 1.28}[ntype] ?? 1;   // every noise type to one spread (sd .35)
    const one = (x, y, m) => gain * (spline ? (cyc ? .933 * pn.n4(x, y, cz + m[4], cw + m[5]) : pn(x, y, cz + m[4]))
      : vnoise2(x, y, cz + m[4], cw + m[5], ip, sd, !!cyc));
    const norm = kind === 'basic' ? .55 / Math.sqrt(w2) : 1 / wsum;
    const con = keyedT(p.contrast, t, 100) / 100, bri = keyedT(p.brightness, t, 0) / 100, inv = !!p.invert;
    const over = OVERFLOW[p.overflow ?? 'clip'], tint = p.tint && p.tint !== 'none' ? hex(p.tint) : [255, 255, 255];
    const layer = buffer(w, h), g = layer.getContext('2d'), img = g.createImageData(w, h), d = img.data;
    for (let y = 0; y < h; y++) {
      const dy = (y + .5) / sc - H / 2 - oy;
      for (let x = 0; x < w; x++) {
        const dx = (x + .5) / sc - W / 2 - ox;
        let v = 0;
        for (let i = 0; i < oct; i++) {
          const m = M[i], n = one(dx * m[0] + dy * m[1] + m[2], dy * m[0] - dx * m[1] + m[3], m);
          v += wts[i] * (kind === 'basic' ? n : kind === 'turbulent_sharp' ? Math.abs(n) * 1.7 : Math.sqrt(n * n + .0064) * 1.6);
        }
        v = kind === 'basic' ? .5 + v * norm : v * norm;
        if (inv) v = 1 - v;
        v = over((v - .5) * con + .5 + bri);
        const j = 4 * (y * w + x);
        d[j] = v * tint[0] + .5; d[j + 1] = v * tint[1] + .5; d[j + 2] = v * tint[2] + .5; d[j + 3] = 255;
      }
    }
    g.putImageData(img, 0, 0);
    lay(ctx, s, layer, p, o);
  }});

  // local_cell_pattern: After Effects' Cell Pattern. One feature point per `size` px cell (at 1080), scattered by
  // `disperse` (0 a square grid, 1 fully random); each point circles its place once per revolution of `evolution`
  // (plus `speed` revolutions a second), so the pattern loops every revolution. cell_pattern bubbles (round bright cells),
  // crystals (bright cells, dark seams), plates (a flat grey per cell) or tubular (bright seams). invert, contrast,
  // brightness and overflow as Fractal Noise; offset [x, y] px at 1080.
  register('local_cell_pattern', {order: 71, draw(ctx, p, s) {
    const on = begin(p, s);
    if (!on) return;
    const {t, o} = on, {W, H} = s, k = H / 1080, {w, h, sc} = small(s);
    const size = Math.max(1, keyedT(p.size, t, 60) * k), disp = clamp(keyedT(p.disperse, t, 1));
    const off = keyedT(p.offset, t, [0, 0]), ox = off[0] * k, oy = off[1] * k, sd = seedHash(p.seed ?? 1);
    const evo = keyedT(p.evolution, t, 0) + (p.speed ?? 0) * t, kind = p.cell_pattern ?? 'bubbles';
    const con = keyedT(p.contrast, t, 100) / 100, bri = keyedT(p.brightness, t, 0) / 100, inv = !!p.invert;
    const over = OVERFLOW[p.overflow ?? 'clip'], TAU = 2 * Math.PI, orbit = .18 * disp;
    const pt = (i, j, out) => {   // the feature point of cell (i, j)
      const ph = (hash4(i, j, 3, 0, sd) + 1) / 2;
      out[0] = i + .5 + .32 * disp * hash4(i, j, 1, 0, sd) + orbit * Math.cos(TAU * (evo + ph));
      out[1] = j + .5 + .32 * disp * hash4(i, j, 2, 0, sd) + orbit * Math.sin(TAU * (evo + ph));
    };
    const P = [0, 0], layer = buffer(w, h), g = layer.getContext('2d'), img = g.createImageData(w, h), d = img.data;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const px = ((x + .5) / sc - W / 2 - ox) / size, py = ((y + .5) / sc - H / 2 - oy) / size;
      const ci = Math.floor(px), cj = Math.floor(py);
      let f1 = 9, f2 = 9, id = 0;
      for (let jj = -2; jj <= 2; jj++) for (let ii = -2; ii <= 2; ii++) {   // 5 x 5: the second nearest too
        pt(ci + ii, cj + jj, P);
        const dd = Math.hypot(px - P[0], py - P[1]);
        if (dd < f1) { f2 = f1; f1 = dd; id = hash4(ci + ii, cj + jj, 4, 0, sd); } else if (dd < f2) f2 = dd;
      }
      let v = kind === 'bubbles' ? 1 - f1 * 1.35 : kind === 'crystals' ? (f2 - f1) * 1.6 : kind === 'plates' ? (id + 1) / 2
        : 1 - (f2 - f1) * 4;
      if (inv) v = 1 - v;
      v = over((v - .5) * con + .5 + bri);
      const j = 4 * (y * w + x);
      d[j] = d[j + 1] = d[j + 2] = v * 255 + .5; d[j + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    lay(ctx, s, layer, p, o);
  }});

  // grain for gradients (AE's ramp scatter / jitter): a fixed seeded per-pixel noise of +-amount x 24 levels
  function scatter(c, amount, seed) {
    if (!(amount > 0)) return;
    const g = c.getContext('2d'), img = g.getImageData(0, 0, c.width, c.height), d = img.data, r = rng(seed), A = amount * 24;
    for (let i = 0; i < d.length; i += 4) {
      const n = (r() + r() - 1) * A;
      d[i] = clamp(d[i] + n, 0, 255); d[i + 1] = clamp(d[i + 1] + n, 0, 255); d[i + 2] = clamp(d[i + 2] + n, 0, 255);
    }
    g.putImageData(img, 0, 0);
  }

  // local_gradient_ramp: After Effects' Gradient Ramp. start_color at `start`, end_color at `end` ([x, y] fractions,
  // keyframable), linear (constant along lines across start-end, held beyond both) or radial (rings round start out to
  // the distance to end). ramp_scatter 0..1 dithers it (breaks up banding).
  register('local_gradient_ramp', {order: 72, draw(ctx, p, s) {
    const on = begin(p, s);
    if (!on) return;
    const {t, o} = on, {W, H} = s, a = keyedT(p.start, t, [.5, 0]), b = keyedT(p.end, t, [.5, 1]);
    const x0 = a[0] * W, y0 = a[1] * H, x1 = b[0] * W, y1 = b[1] * H, c0 = colOf(p.start_color, '#000000'), c1 = colOf(p.end_color, '#ffffff');
    const layer = buffer(W, H), g = layer.getContext('2d'), dist = Math.hypot(x1 - x0, y1 - y0);
    let gr = null;
    if (p.shape === 'radial') gr = g.createRadialGradient(x0, y0, 0, x0, y0, Math.max(.5, dist));
    else if (dist > 1e-6) gr = g.createLinearGradient(x0, y0, x1, y1);
    if (gr) { gr.addColorStop(0, css(c0)); gr.addColorStop(1, css(c1)); g.fillStyle = gr; } else g.fillStyle = css(c1);
    g.fillRect(0, 0, W, H);
    scatter(layer, keyedT(p.ramp_scatter, t, 0), 7);
    lay(ctx, s, layer, p, o);
  }});

  // local_four_color_gradient: After Effects' 4-Color Gradient. Four colours at four points ([x, y] fractions,
  // keyframable), mixed by inverse distance: blend_amount (AE's Blend, 100) sets the falloff (lower: each colour holds
  // its own region with sharper seams; higher: softer, toward one average). jitter 0..1 dithers it.
  const FOUR = [['point_1', [.1, .1], 'color_1', '#ffff00'], ['point_2', [.9, .1], 'color_2', '#00ff00'],
    ['point_3', [.1, .9], 'color_3', '#ff00ff'], ['point_4', [.9, .9], 'color_4', '#0000ff']];
  register('local_four_color_gradient', {order: 73, draw(ctx, p, s) {
    const on = begin(p, s);
    if (!on) return;
    const {t, o} = on, {W, H} = s, {w, h, sc} = small(s);
    const pts = FOUR.map(([pk, pd, ck, cd]) => { const q = keyedT(p[pk], t, pd); return [q[0] * W, q[1] * H, colOf(p[ck], cd)]; });
    const pw = 2 * 100 / clamp(keyedT(p.blend_amount, t, 100), 1, 1000), unit = H / 4;
    const layer = buffer(w, h), g = layer.getContext('2d'), img = g.createImageData(w, h), d = img.data;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const X = (x + .5) / sc, Y = (y + .5) / sc;
      let r = 0, gg = 0, b = 0, ws = 0, hit = -1;
      for (let i = 0; i < 4; i++) {
        const dd = Math.hypot(X - pts[i][0], Y - pts[i][1]) / unit;
        if (dd < 1e-6) { hit = i; break; }
        const wt = dd ** -pw; ws += wt; r += wt * pts[i][2][0]; gg += wt * pts[i][2][1]; b += wt * pts[i][2][2];
      }
      const j = 4 * (y * w + x);
      if (hit >= 0 || !(ws > 0)) { const c = pts[Math.max(0, hit)][2]; d[j] = c[0]; d[j + 1] = c[1]; d[j + 2] = c[2]; }
      else { d[j] = r / ws + .5; d[j + 1] = gg / ws + .5; d[j + 2] = b / ws + .5; }
      d[j + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    let out = layer;
    const jit = keyedT(p.jitter, t, 0);
    if (jit > 0) { out = buffer(W, H); const ox = out.getContext('2d'); ox.imageSmoothingQuality = 'high'; ox.drawImage(layer, 0, 0, W, H); scatter(out, jit, 11); }
    lay(ctx, s, out, p, o);
  }});

  // local_grid: After Effects' Grid. Lines `border` px wide (at 1080) every `width` x `height` px (height defaults to
  // width), one crossing at `anchor` ([x, y] fractions, keyframable); `feather` px softens them, `invert` fills the
  // cells instead, `color` colours them.
  register('local_grid', {order: 74, draw(ctx, p, s) {
    const on = begin(p, s);
    if (!on) return;
    const {t, o} = on, {W, H} = s, k = H / 1080, an = keyedT(p.anchor, t, [.5, .5]), wd = keyedT(p.width, t, 100);
    const cw = Math.max(1, wd * k), ch = Math.max(1, keyedT(p.height, t, wd) * k);
    const bw = Math.max(0, keyedT(p.border, t, 3) * k), fe = Math.max(0, keyedT(p.feather, t, 0) * k);
    const layer = buffer(W, H), g = layer.getContext('2d'), ax = an[0] * W, ay = an[1] * H;
    g.fillStyle = css(colOf(p.color, '#ffffff'));
    if (p.invert) { g.fillRect(0, 0, W, H); g.globalCompositeOperation = 'destination-out'; }
    if (fe > 0) g.filter = `blur(${fe / 2}px)`;
    if (bw > 0) {
      g.beginPath();
      for (let x = ax - Math.ceil(ax / cw + 1) * cw; x <= W + cw; x += cw) g.rect(x - bw / 2, -fe - 2, bw, H + 2 * fe + 4);
      for (let y = ay - Math.ceil(ay / ch + 1) * ch; y <= H + ch; y += ch) g.rect(-fe - 2, y - bw / 2, W + 2 * fe + 4, bw);
      g.fill();
    }
    g.filter = 'none'; g.globalCompositeOperation = 'source-over';
    lay(ctx, s, layer, p, o);
  }});

  // local_radio_waves: After Effects' Radio Waves. Waves are born at `producer` ([x, y] fractions, keyframable: each
  // wave keeps the place it was born at) `frequency` times a second from `at`, grow `expansion` px a second (at 1080) and
  // live `lifespan` seconds; a stroke `start_width` px at birth to `end_width` px at death in `stroke_color`, fading in
  // over `fade_in` and out over the last `fade_out` seconds. shape circle, square or polygon (`sides`, a vertex up).
  register('local_radio_waves', {order: 75, draw(ctx, p, s) {
    const on = begin(p, s);
    if (!on) return;
    const {t, o} = on, {W, H} = s, k = H / 1080, fq = p.frequency ?? 1, ex = (p.expansion ?? 200) * k, life = p.lifespan ?? 3;
    const fin = p.fade_in ?? 0, fout = p.fade_out ?? 1, sw0 = (p.start_width ?? 5) * k, sw1 = (p.end_width ?? 5) * k;
    const shape = p.shape ?? 'circle', sides = Math.round(p.sides ?? 5), layer = buffer(W, H), g = layer.getContext('2d');
    g.strokeStyle = css(colOf(p.stroke_color, '#ffffff')); g.lineJoin = 'round';
    let drew = false;
    for (let i = Math.max(0, Math.ceil((t - life) * fq - 1e-9)); i <= Math.floor(t * fq + 1e-9); i++) {
      const tb = i / fq, age = t - tb, u = age / life;
      if (u >= 1) continue;
      const r = ex * age, lw = sw0 + (sw1 - sw0) * u;
      const a = (fin > 0 ? clamp(age / fin) : 1) * (fout > 0 ? clamp((life - age) / fout) : 1);
      if (!(r > .25) || !(lw > 0) || !(a > 0)) continue;
      const c = keyedT(p.producer, tb, [.5, .5]), cx = c[0] * W, cy = c[1] * H;
      g.globalAlpha = a; g.lineWidth = lw; g.beginPath();
      if (shape === 'square') g.rect(cx - r, cy - r, 2 * r, 2 * r);
      else if (shape === 'polygon') for (let j = 0; j < sides; j++) { const q = -Math.PI / 2 + 2 * Math.PI * j / sides; g[j ? 'lineTo' : 'moveTo'](cx + r * Math.cos(q), cy + r * Math.sin(q)); }
      else g.arc(cx, cy, r, 0, 2 * Math.PI);
      g.closePath(); g.stroke(); drew = true;
    }
    if (drew) lay(ctx, s, layer, p, o);
  }});

  // local_lightning: After Effects' Advanced Lightning. A fractal bolt from `origin` toward `direction` ([x, y]
  // fractions, keyframable): lightning_type strike (origin to the direction point), breaking (three bolts fanning
  // toward it), bouncy (wide swinging bends), omni (bolts all round the origin, as long as origin-direction) or anywhere
  // (to a point that wanders the frame as conductivity changes). `conductivity` evolves the path smoothly (keyframe it);
  // `turbulence` (1, 0..10) its jaggedness; `forking` 0..1 how often branches split off, `decay` 0..1 how fast they thin
  // and fade. A core `core_radius` px (at 1080) in core_color inside a glow `glow_radius` px in glow_color at
  // glow_opacity. `flicker` n re-seeds it every n frames (a strobing strike); `seed`.
  register('local_lightning', {order: 76, draw(ctx, p, s) {
    const on = begin(p, s);
    if (!on) return;
    const {t, o} = on, {W, H} = s, k = H / 1080;
    const fl = p.flicker ?? 0, seed = (p.seed ?? 1) + (fl > 0 ? Math.floor(t * s.fps / fl + 1e-6) * 7919 : 0);
    const n = perlin(seed), sd = seedHash(seed), cond = keyedT(p.conductivity, t, 0);
    const turb = p.turbulence ?? 1, forking = clamp(p.forking ?? .25), decay = clamp(p.decay ?? .3), type = p.lightning_type ?? 'strike';
    const A = keyedT(p.origin, t, [.3, .2]), B = keyedT(p.direction, t, [.7, .8]);
    const ax = A[0] * W, ay = A[1] * H, bx = B[0] * W, by = B[1] * H, len = Math.hypot(bx - ax, by - ay);
    const bolts = [];   // [points, width factor, alpha]
    // midpoint displacement whose offsets are smooth noise of (bolt, level, index, conductivity)
    function path(x0, y0, x1, y1, levels, id, swing) {
      let pts = [[x0, y0], [x1, y1]];
      for (let l = 0; l < levels; l++) {
        const next = [pts[0]];
        for (let i = 0; i < pts.length - 1; i++) {
          const [px, py] = pts[i], [qx, qy] = pts[i + 1], sl = Math.hypot(qx - px, qy - py) || 1;
          const amp = sl * .45 * turb * (l < 2 ? swing : 1), v = n(id * 7.31 + l * 13.17 + .5, i * 1.37 + .5, cond * 2 + id * .71);
          next.push([(px + qx) / 2 - (qy - py) / sl * amp * v, (py + qy) / 2 + (qx - px) / sl * amp * v], pts[i + 1]);
        }
        pts = next;
      }
      return pts;
    }
    function branch(pts, wf, al, depth, id) {
      bolts.push([pts, wf, al]);
      if (depth >= 2 || forking <= 0) return;
      const stride = depth ? 8 : 6;
      for (let i = stride; i < pts.length - stride; i += stride) {
        if ((hash4(id, i, depth, 9, sd) + 1) / 2 >= forking * (depth ? .6 : 1)) continue;
        const [px, py] = pts[i], [qx, qy] = pts[Math.min(pts.length - 1, i + 4)], hd = Math.atan2(qy - py, qx - px);
        const side = hash4(id, i, depth, 5, sd) > 0 ? 1 : -1, q = hd + side * (.35 + .35 * (n(id * 3.1 + i * .7, 4.2, cond * 2) + .5));
        let rest = 0;
        for (let j = i; j < pts.length - 1; j++) rest += Math.hypot(pts[j + 1][0] - pts[j][0], pts[j + 1][1] - pts[j][1]);
        const fl_ = Math.min(rest, len * 1.2) * (.25 + .2 * (hash4(id, i, depth, 6, sd) + 1));
        const sub = path(px, py, px + Math.cos(q) * fl_, py + Math.sin(q) * fl_, 5, id * 31 + i + 101, 1);
        branch(sub, wf * (1 - decay) * .7, al * (1 - decay * .8), depth + 1, id * 31 + i + 101);
      }
    }
    if (type === 'omni') {
      const m = 6 + Math.round(forking * 6);
      for (let i = 0; i < m; i++) {
        const q = 2 * Math.PI * (i + .5 * n(i * 2.3 + .5, 8.1, cond)) / m;
        branch(path(ax, ay, ax + Math.cos(q) * len, ay + Math.sin(q) * len, 6, i + 1, 1), .8, 1, 1, i + 1);
      }
    } else if (type === 'breaking') {
      for (let i = 0; i < 3; i++) {
        const sp = (i - 1) * .3 + .15 * n(i * 5.1 + .5, 2.9, cond), ex = bx - (by - ay) * sp, ey = by + (bx - ax) * sp;
        branch(path(ax, ay, ex, ey, 7, i + 1, 1.3), i === 1 ? 1 : .75, 1, i === 1 ? 0 : 1, i + 1);
      }
    } else {
      let ex = bx, ey = by;
      if (type === 'anywhere') { ex = (.5 + .9 * n(3.3, 7.7, cond * .5)) * W; ey = (.5 + .9 * n(9.1, 1.3, cond * .5)) * H; }
      branch(path(ax, ay, ex, ey, 7, 1, type === 'bouncy' ? 1.8 : 1), 1, 1, 0, 1);
    }
    const core = Math.max(0, keyedT(p.core_radius, t, 3) * k), gr = Math.max(0, keyedT(p.glow_radius, t, 50) * k);
    const go = clamp(keyedT(p.glow_opacity, t, .5)), coreC = css(colOf(p.core_color, '#ffffff')), glowC = css(colOf(p.glow_color, '#4a6cff'));
    const stroke = (g, sc, widthOf) => {
      g.lineJoin = 'round'; g.lineCap = 'round';
      for (const [pts, wf, al] of bolts) {
        g.globalAlpha = al; g.lineWidth = Math.max(.6, widthOf(wf) * sc); g.beginPath();
        pts.forEach(([x, y], i) => g[i ? 'lineTo' : 'moveTo'](x * sc, y * sc)); g.stroke();
      }
      g.globalAlpha = 1;
    };
    const layer = buffer(W, H), lg = layer.getContext('2d');
    if (gr > 0 && go > 0) {
      // the glow: the bolts drawn thick on a small buffer and blurred twice, a tight halo and a wide one, each scaled so
      // the main bolt's halo peaks at its share of glow_opacity (a blurred line loses height as the blur widens), added
      const sc = Math.min(1, 270 / H), gw = Math.ceil(W * sc), gh = Math.ceil(H * sc);
      lg.globalCompositeOperation = 'lighter'; lg.imageSmoothingQuality = 'high';
      for (const [r, share] of [[gr * .2, 1], [gr * .6, .6]]) {
        const lw = 2 * core + r, rs = Math.max(.5, r * sc), peak = erf(lw * sc / (2 * Math.SQRT2 * rs));
        const src = buffer(gw, gh), sg = src.getContext('2d');
        sg.strokeStyle = glowC; stroke(sg, sc, wf => 2 * core * wf + r);
        let gain = go * share / Math.max(peak, 1e-3), dbl = 0;
        while (gain > 1 && dbl < 6) { gain /= 2; dbl++; }
        const bl = buffer(gw, gh), bg = bl.getContext('2d');
        bg.filter = `blur(${rs}px)`; bg.globalAlpha = gain; bg.drawImage(src, 0, 0); bg.filter = 'none'; bg.globalAlpha = 1;
        bg.globalCompositeOperation = 'lighter';
        for (let i = 0; i < dbl; i++) bg.drawImage(bl, 0, 0);
        lg.drawImage(bl, 0, 0, W, H);
      }
      lg.globalCompositeOperation = 'source-over';
    }
    if (core > 0) { lg.strokeStyle = coreC; stroke(lg, 1, wf => 2 * core * wf); }
    lay(ctx, s, layer, p, o);
  }});
})();
