// Distort effects as an OpenKatana effect pack (Wave Warp, Ripple, Shockwave, Twirl, Bulge, Polar Coordinates, Kaleidoscope, Mirror). Parameters and defaults are documented in
// docs/TIMELINE.md; validation is in openkatana/fx_distort.py. Shared helpers: OpenKatanaLocal.util.
(() => {
  const {register, util} = OpenKatanaLocal;
  const {clamp, keyedT, remap, inBox, shape, buffer, copy} = util;
  const TAU = 2 * Math.PI, RAD = Math.PI / 180;
  const smooth = u => (u <= 0 ? 0 : u >= 1 ? 1 : u * u * (3 - 2 * u));

  // Every effect here is a coordinate map: field(x, y, D) leaves in D the move from an output pixel to the source pixel it
  // shows (remap: out(x, y) = source at (x, y) + D). `region` [x0, y0, x1, y1] (0..1) with `feather` (a fraction of the
  // height, .02 by default) confines the move; `edges` and `quality` go to the resampler. `still(x, y)` marks pixels the
  // field never moves (skipped).
  function warp(ctx, p, s, field, still = null) {
    const {W: w, H: h} = s, D = [0, 0];
    const box = p.region ? inBox(p.region, (p.feather ?? .02) * h, w, h) : null;
    const at = box ? (x, y) => { const g = box.weight(x, y); if (g <= 0) { D[0] = 0; D[1] = 0; return; } field(x, y, D); D[0] *= g; D[1] *= g; }
      : (x, y) => field(x, y, D);
    const keep = box && still ? (x, y) => box.still(x, y) || still(x, y) : box ? box.still : still;
    remap(ctx, w, h, at, D, {still: keep, edges: p.edges, quality: p.quality});
  }
  // the effect's own clock: seconds since `at` (null before it starts)
  const clock = (p, s) => { const t = s.elapsed - (p.at ?? 0); return t < 0 ? null : t; };
  // a keyframable [x, y] (0..1) in pixel-index coordinates (pixel i covers i..i+1, so a fraction c sits at c * w - .5)
  const point = (v, t, d, w, h) => { const c = keyedT(v, t, d); return [c[0] * w - .5, c[1] * h - .5]; };

  // local_wave_warp: Wave Warp. Waves travel along `direction` (degrees clockwise from up: 90 travels
  // right) and move pixels across it by up to `wave_height` px (at 1080); `wave_width` is the wavelength (px at 1080),
  // `wave_speed` cycles a second, `phase` degrees. `pinning` holds edges still with a smooth fade over a quarter of the
  // smaller side (center holds the middle). wave_height and wave_width take keyframes.
  const hash = i => { const v = Math.sin(i * 127.1 + 311.7) * 43758.5453; return (v - Math.floor(v)) * 2 - 1; };
  const frac = u => u - Math.floor(u);
  const WAVES = {
    sine: u => Math.sin(TAU * u),
    square: u => (frac(u) < .5 ? 1 : -1),
    triangle: u => { const f = frac(u); return f < .25 ? 4 * f : f < .75 ? 2 - 4 * f : 4 * f - 4; },
    sawtooth: u => { const f = frac(u); return f < .5 ? 2 * f : 2 * f - 2; },
    circle: u => { const f = frac(u); return f < .5 ? Math.sqrt(Math.max(0, 1 - (4 * f - 1) ** 2)) : -Math.sqrt(Math.max(0, 1 - (4 * f - 3) ** 2)); },
    semicircle: u => 2 * Math.sqrt(Math.max(0, 1 - (2 * frac(u) - 1) ** 2)) - 1,
    uncircle: u => 1 - 2 * Math.sqrt(Math.max(0, 1 - (2 * frac(u) - 1) ** 2)),
    noise: u => { const v = u * 8, i = Math.floor(v), f = v - i; return hash(i) + (hash(i + 1) - hash(i)) * f; },
    smooth_noise: u => { const v = u * 2, i = Math.floor(v), f = v - i, g = f * f * f * (f * (f * 6 - 15) + 10); return hash(i) + (hash(i + 1) - hash(i)) * g; },
  };
  function pinWeight(pin, w, h) {
    if (!pin || pin === 'none') return null;
    const pd = Math.max(2, Math.min(w, h) / 4);
    if (pin === 'center') { const cx = (w - 1) / 2, cy = (h - 1) / 2, R = Math.min(w, h) / 2; return (x, y) => smooth(Math.hypot(x - cx, y - cy) / R); }
    const top = ['all', 'top', 'horizontal'].includes(pin), bottom = ['all', 'bottom', 'horizontal'].includes(pin);
    const left = ['all', 'left', 'vertical'].includes(pin), right = ['all', 'right', 'vertical'].includes(pin);
    return (x, y) => (top ? smooth(y / pd) : 1) * (bottom ? smooth((h - 1 - y) / pd) : 1) * (left ? smooth(x / pd) : 1) * (right ? smooth((w - 1 - x) / pd) : 1);
  }
  register('local_wave_warp', {order: 40, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const k = s.H / 1080, A = keyedT(p.wave_height, t, 10) * k, L = Math.max(1, keyedT(p.wave_width, t, 40) * k);
    if (!(Math.abs(A) > .002)) return;
    const th = (p.direction ?? 90) * RAD, tx = Math.sin(th), ty = -Math.cos(th), nx = Math.cos(th), ny = Math.sin(th);
    const wave = WAVES[p.wave_type ?? 'sine'], shift = (p.phase ?? 0) / 360 - (p.wave_speed ?? 1) * t, pin = pinWeight(p.pinning ?? 'none', s.W, s.H);
    warp(ctx, p, s, (x, y, D) => {
      const m = A * wave((x * tx + y * ty) / L + shift) * (pin ? pin(x, y) : 1);
      D[0] = -m * nx; D[1] = -m * ny;
    });
  }});

  // local_ripple: Ripple. Circular waves from `center` (wavelength px at 1080) move pixels by up to
  // `amplitude` px (at 1080), fading out at `radius` (a fraction of the frame diagonal). wave_speed: waves a second
  // (positive travel outward); phase in degrees. conversion "symmetric" moves pixels radially (refraction-like),
  // "asymmetric" (the default) moves them along one diagonal. amplitude and center take keyframes.
  register('local_ripple', {order: 41, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s, k = h / 1080, A = keyedT(p.amplitude, t, 20) * k;
    if (!(Math.abs(A) > .002)) return;
    const [cx, cy] = point(p.center, t, [.5, .5], w, h), R = (p.radius ?? .5) * Math.hypot(w, h), L = Math.max(1, (p.wavelength ?? 40) * k);
    const ph = TAU * (p.wave_speed ?? 1) * t - (p.phase ?? 0) * RAD, sym = p.conversion === 'symmetric', S = Math.SQRT1_2;
    warp(ctx, p, s, (x, y, D) => {
      const dx = x - cx, dy = y - cy, r = Math.hypot(dx, dy);
      if (r >= R) { D[0] = 0; D[1] = 0; return; }
      const m = A * Math.sin(TAU * r / L - ph) * (1 - r / R) ** 2 * smooth(r / (L * .5));
      if (sym) { D[0] = -m * dx / r; D[1] = -m * dy / r; } else { D[0] = m * S; D[1] = -m * S; }
    }, (x, y) => (x - cx) ** 2 + (y - cy) ** 2 >= R * R);
  }});

  // local_shockwave: a beat-drop ring. From `center`, starting at `at`, a
  // ring `width` px (at 1080) wide grows over `d` seconds from radius 0 to `max_radius` (a fraction of the diagonal)
  // along `ease` (out3 by default) and pushes the picture outward by up to `amount` px (at 1080; negative pulls inward),
  // fading as it grows. `split` px offsets red and blue along the push (a chromatic fringe). amount takes keyframes.
  register('local_shockwave', {order: 42, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const d = p.d ?? .6; if (t >= d) return;
    const {W: w, H: h} = s, k = h / 1080, u = t / d, fade = 1 - u;
    const A = keyedT(p.amount, t, 40) * k * fade, split = (p.split ?? 0) * k * fade;
    if (!(Math.abs(A) > .002) && !(split > .002)) return;
    const [cx, cy] = point(p.center, t, [.5, .5], w, h), Rr = shape(u, p.ease ?? 'out3') * (p.max_radius ?? .6) * Math.hypot(w, h);
    const half = Math.max(1, (p.width ?? 80) * k / 2);
    const ring = off => (x, y, D) => {
      const dx = x - cx, dy = y - cy, r = Math.hypot(dx, dy), q = (r - Rr) / half;
      if (q <= -1 || q >= 1 || r < 1e-6) { D[0] = 0; D[1] = 0; return; }
      const m = (A + off) * (1 - q * q) ** 2;
      D[0] = -m * dx / r; D[1] = -m * dy / r;
    };
    const lo = Math.max(0, Rr - half - 2), hi = Rr + half + 2;
    const still = (x, y) => { const r2 = (x - cx) ** 2 + (y - cy) ** 2; return r2 < lo * lo || r2 > hi * hi; };
    if (!(split > .002)) return warp(ctx, p, s, ring(0), still);
    const src = copy(ctx), red = buffer(w, h), rc = red.getContext('2d', {willReadFrequently: true});
    rc.drawImage(src, 0, 0); warp(rc, p, s, ring(split), still);
    const blue = buffer(w, h), bc = blue.getContext('2d', {willReadFrequently: true});
    bc.drawImage(src, 0, 0); warp(bc, p, s, ring(-split), still);
    warp(ctx, p, s, ring(0), still);
    const out = ctx.getImageData(0, 0, w, h), od = out.data, rd = rc.getImageData(0, 0, w, h).data, bd = bc.getImageData(0, 0, w, h).data;
    for (let i = 0; i < od.length; i += 4) { od[i] = rd[i]; od[i + 2] = bd[i + 2]; }
    ctx.putImageData(out, 0, 0);
  }});

  // local_twirl: Twirl. Rotates the picture round `center` by `angle` degrees (positive clockwise) at
  // the centre, easing to none at `radius` (a fraction of the smaller side). angle and center take keyframes.
  register('local_twirl', {order: 43, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s, ang = keyedT(p.angle, t, 50) * RAD;
    if (!(Math.abs(ang) > 1e-6)) return;
    const [cx, cy] = point(p.center, t, [.5, .5], w, h), R = (p.radius ?? .3) * Math.min(w, h);
    warp(ctx, p, s, (x, y, D) => {
      const dx = x - cx, dy = y - cy, r = Math.hypot(dx, dy);
      if (r >= R) { D[0] = 0; D[1] = 0; return; }
      const a = -ang * (1 - r / R) ** 2, c = Math.cos(a), sn = Math.sin(a);
      D[0] = dx * c - dy * sn - dx; D[1] = dx * sn + dy * c - dy;
    }, (x, y) => (x - cx) ** 2 + (y - cy) ** 2 >= R * R);
  }});

  // local_bulge: Bulge. Magnifies an ellipse (horizontal_radius x vertical_radius px at 1080) round
  // `center` by `height` (-4..4: 1 doubles the middle, negative pinches); `taper` (0..1) softens its edge; `pin` holds
  // the frame edges still. height and center take keyframes. A bulge samples the radius rho (0..1 across the ellipse) from
  // G(rho) = rho / (1 + height (1 - rho^2)^(1 + 2 taper)), which only grows, so it never folds; a pinch is its exact
  // inverse (looked up from a table), so it never folds either and still meets the untouched picture at the rim. Strong
  // heights squeeze the source up to (1 + 2 |height|)x, so quality defaults to 'high' above |height| 1.
  const PINCH_N = 1024;
  function pinchRatio(a, ex) {   // source / output radius for a pinch of strength a > 0, at rho = j / PINCH_N
    const M = 8 * PINCH_N, G = s => s / (1 + a * Math.pow(1 - s * s, ex)), lut = new Float64Array(PINCH_N + 1);
    lut[0] = 1 + a;
    let i = 0, g0 = 0, g1 = G(1 / M);
    for (let j = 1; j <= PINCH_N; j++) {
      const rho = j / PINCH_N;
      while (g1 < rho && i < M - 1) { i++; g0 = g1; g1 = G((i + 1) / M); }
      const src = (i + (g1 > g0 ? clamp((rho - g0) / (g1 - g0)) : 1)) / M;
      lut[j] = src / rho;
    }
    return rho => { const u = rho * PINCH_N, j = Math.min(PINCH_N - 1, Math.floor(u)), f = u - j; return lut[j] + (lut[j + 1] - lut[j]) * f; };
  }
  register('local_bulge', {order: 44, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s, k = h / 1080, hb = keyedT(p.height, t, 1);
    if (!(Math.abs(hb) > 1e-6)) return;
    const [cx, cy] = point(p.center, t, [.5, .5], w, h), rx = Math.max(1, (p.horizontal_radius ?? 300) * k), ry = Math.max(1, (p.vertical_radius ?? 300) * k);
    const ex = 1 + 2 * (p.taper ?? 0), pin = p.pin ? pinWeight('all', w, h) : null, pinch = hb < 0 ? pinchRatio(-hb, ex) : null;
    const q = {...p, quality: p.quality ?? (Math.abs(hb) > 1 ? 'high' : 'low')};
    warp(ctx, q, s, (x, y, D) => {
      const dx = x - cx, dy = y - cy, r2 = (dx / rx) ** 2 + (dy / ry) ** 2;
      if (r2 >= 1) { D[0] = 0; D[1] = 0; return; }
      const f = (pinch ? pinch(Math.sqrt(r2)) : 1 / (1 + hb * Math.pow(1 - r2, ex))) - 1, g = pin ? pin(x, y) : 1;
      D[0] = dx * f * g; D[1] = dy * f * g;
    }, (x, y) => ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 >= 1);
  }});

  // local_polar: Polar Coordinates. rect_to_polar wraps the picture round the frame centre (its top row
  // at the centre, its left edge at 12 o'clock, clockwise); polar_to_rect unrolls a circle into rows. `interpolation`
  // (0..1, keyframable) mixes from the untouched picture (0) to the full conversion (1).
  register('local_polar', {order: 45, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s, mix = clamp(keyedT(p.interpolation, t, 1));
    if (!(mix > 1e-6)) return;
    const hw = w / 2, hh = h / 2, toRect = p.conversion === 'polar_to_rect';
    warp(ctx, p, s, (x, y, D) => {
      let sx, sy;
      if (toRect) {
        const a = TAU * (x + .5) / w, rho = (y + .5) / h;
        sx = hw + rho * Math.sin(a) * hw - .5; sy = hh - rho * Math.cos(a) * hh - .5;
      } else {
        const nx = (x + .5 - hw) / hw, ny = (y + .5 - hh) / hh;
        let a = Math.atan2(nx, -ny) / TAU; if (a < 0) a += 1;
        sx = Math.min(w - 1, a * w); sy = Math.hypot(nx, ny) * h - .5;
      }
      D[0] = (sx - x) * mix; D[1] = (sy - y) * mix;
    });
  }});

  // local_kaleidoscope: CC Kaleida. Folds the picture round `center` into `segments` wedges (mirroring "on" flips every
  // other wedge so the seams match - with an odd count one seam, at the start of wedge 0, cannot match; "off" repeats one) and folds the radius every `size` px (at 1080: the cell size), so
  // the disc `size` round the centre is what is seen, tiled outward in rings. `rotation` (degrees) turns the wedge
  // that is sampled, as turning a kaleidoscope. rotation and center take keyframes.
  register('local_kaleidoscope', {order: 46, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s, k = h / 1080, n = Math.round(p.segments ?? 6), S = TAU / n, rot = keyedT(p.rotation, t, 0) * RAD;
    const [cx, cy] = point(p.center, t, [.5, .5], w, h), size = Math.max(1, (p.size ?? 360) * k), mirror = (p.mirroring ?? 'on') !== 'off';
    const base = rot - S / 2 - Math.PI / 2;   // wedge 0 is sampled from the wedge pointing up from the centre, turned by rotation
    warp(ctx, p, s, (x, y, D) => {
      const dx = x - cx, dy = y - cy, a0 = Math.atan2(dy, dx) + Math.PI / 2 + S / 2, a = a0 - TAU * Math.floor(a0 / TAU);   // 0..2pi
      let r = Math.hypot(dx, dy);
      const i = Math.min(n - 1, Math.floor(a / S)); let f = a - i * S;
      if (mirror && (i & 1)) f = S - f;
      const c = Math.floor(r / size); r -= c * size; if (c & 1) r = size - r;
      D[0] = cx + r * Math.cos(f + base) - x; D[1] = cy + r * Math.sin(f + base) - y;
    });
  }});

  // local_mirror: Mirror. Reflects the picture across the line through `reflection_center` at
  // `reflection_angle` degrees: 0 keeps the left side and mirrors it onto the right; 90 mirrors the top onto the bottom
  // (the angle turns the line clockwise). reflection_angle and reflection_center take keyframes.
  register('local_mirror', {order: 47, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s, th = keyedT(p.reflection_angle, t, 0) * RAD, nx = Math.cos(th), ny = Math.sin(th);
    const [cx, cy] = point(p.reflection_center, t, [.5, .5], w, h);
    warp(ctx, p, s, (x, y, D) => {
      const q = (x - cx) * nx + (y - cy) * ny;
      if (q <= 0) { D[0] = 0; D[1] = 0; return; }
      D[0] = -2 * q * nx; D[1] = -2 * q * ny;
    });
  }});
})();
