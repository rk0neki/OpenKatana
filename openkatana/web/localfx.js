// Local layer effects; parameters and defaults are documented in docs/TIMELINE.md.
window.OpenKatanaLocal = (() => {
  const orders = {local_selective_color:6, local_posterize:7, local_halftone:8, local_frame_slices:9, local_whip:16, local_zoom_blur:17,
                  local_scramble_text:58, local_speed_lines:25, local_paper_frame:30, local_curve:95, local_turbulent_displace:18, local_displacement_map:19};
  const phase = {local_scramble_text:'over', local_speed_lines:'final', local_paper_frame:'final', local_curve:'subject'};
  // Effect packs (web/fx_*.js) register their effects here: name -> {order, phase?, time?, draw(ctx, p, s)}. The engine
  // awaits a pack's draw with the canvas transform reset and p = the effect's parameters ({} for true), and passes
  // s = {W, H, elapsed, duration, frame, fps, shot, clip, image(clipId, index), shotAt(frame)}: shotAt renders this shot
  // at another frame into a canvas of its own (time effects; `time: true` marks them, and the nested renders skip them).
  const packs = {};
  function register(name, spec) { packs[name] = spec; orders[name] = spec.order; if (spec.phase) phase[name] = spec.phase; }
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  const buffer = (w, h) => { const c = document.createElement('canvas'); c.width = Math.max(1, Math.ceil(w)); c.height = Math.max(1, Math.ceil(h)); return c; };
  const copy = ctx => { const c = buffer(ctx.canvas.width, ctx.canvas.height); c.getContext('2d').drawImage(ctx.canvas, 0, 0); return c; };
  const rgb = color => color[0] === '#' ? [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16)) : color.slice(color.indexOf('(') + 1).split(',').slice(0, 3).map(Number);
  function rng(seed) { let a = (Math.imul(seed | 0, 2654435761) + 0x6D2B79F5) >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

  // Halftone tone-response table. Each entry becomes a dot radius (in cell widths) by inverting the
  // covered area of a square grid of equal circles: pi r^2 up to touching (r = 1/2), minus the shared lenses after.
  const HT_COVER = [[0,.994],[16,.985],[32,.971],[48,.949],[64,.918],[80,.885],[96,.837],[112,.770],[128,.686],[144,.603],
                    [160,.528],[176,.444],[192,.356],[208,.262],[224,.163],[240,.073],[255,0]];
  const HT_RADIUS = (() => {
    const covered = r => r <= .5 ? Math.PI * r * r : Math.PI * r * r - 2 * (2 * r * r * Math.acos(1 / (2 * r)) - .5 * Math.sqrt(4 * r * r - 1));
    const out = new Float64Array(256);
    for (let l = 0; l < 256; l++) {
      const k = HT_COVER.findIndex(([x]) => x >= l), [x1, c1] = HT_COVER[k], [x0, c0] = HT_COVER[Math.max(0, k - 1)];
      const want = x1 === x0 ? c1 : c0 + (c1 - c0) * (l - x0) / (x1 - x0);
      let lo = 0, hi = Math.SQRT1_2;
      for (let i = 0; i < 40; i++) { const mid = (lo + hi) / 2; covered(mid) < want ? lo = mid : hi = mid; }
      out[l] = (lo + hi) / 2;
    }
    return out;
  })();

  // weighted average of n shifted/scaled copies (running mean: copy i drawn at alpha w_i / (w_0 + ... + w_i));
  // equal weights unless `weight(u)` is given
  function smear(ctx, n, place, weight = () => 1) {
    const src = copy(ctx), {width: w, height: h} = ctx.canvas;
    ctx.save(); ctx.globalCompositeOperation = 'source-over';
    let total = 0;
    for (let i = 0; i < n; i++) { const u = i / (n - 1), wi = weight(u); total += wi; ctx.globalAlpha = wi / total; place(src, u, w, h); }
    ctx.restore();
  }
  function pixels(ctx, fn) {
    const {width: w, height: h} = ctx.canvas, im = ctx.getImageData(0, 0, w, h), d = im.data;
    for (let i = 0; i < d.length; i += 4) fn(d, i);
    ctx.putImageData(im, 0, 0);
  }
  function hueSat(r, g, b) {
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), c = mx - mn;
    let h = 0;
    if (c > 0) h = mx === r ? ((g - b) / c) % 6 : mx === g ? (b - r) / c + 2 : (r - g) / c + 4;
    return [(h * 60 + 360) % 360, mx ? c / mx : 0];
  }
  function deckle(ctx, x0, y0, x1, y1, amp, seed) {   // jagged rectangle path (torn paper edge)
    const r = rng(seed), pts = [], step = Math.max(4, amp * 1.6);
    const edge = (ax, ay, bx, by, nx, ny) => { const len = Math.hypot(bx - ax, by - ay), n = Math.ceil(len / step);
      for (let i = 0; i < n; i++) { const u = i / n, j = (i % 2 ? .35 + r() * .65 : -.2 * r()) * amp; pts.push([ax + (bx - ax) * u + nx * j, ay + (by - ay) * u + ny * j]); } };
    edge(x0, y0, x1, y0, 0, 1); edge(x1, y0, x1, y1, -1, 0); edge(x1, y1, x0, y1, 0, -1); edge(x0, y1, x0, y0, 1, 0);
    ctx.beginPath(); pts.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath();
  }

  // a w x h picture with p px of reflected edge on every side, so a zoom-out, slide or blur never shows a border
  function mirrorPad(src, w, h, p) {
    const c = buffer(w + 2 * p, h + 2 * p), x = c.getContext('2d');
    for (const sx of [-1, 0, 1]) for (const sy of [-1, 0, 1]) {
      x.save(); x.translate(p + sx * w + (sx ? w : 0), p + sy * h + (sy ? h : 0)); x.scale(sx ? -1 : 1, sy ? -1 : 1);
      x.drawImage(src, 0, 0, w, h); x.restore();
    }
    return c;
  }
  // exposure k: above 1 the picture is added onto itself, below 1 it darkens toward black
  function exposure(ctx, k, w, h) {
    if (Math.abs(k - 1) < .002) return;
    if (k > 1) { const src = copy(ctx); ctx.globalCompositeOperation = 'lighter';
      for (let r = k - 1; r > 0; r -= 1) { ctx.globalAlpha = Math.min(1, r); ctx.drawImage(src, 0, 0); } }
    else { ctx.globalAlpha = 1 - k; ctx.fillStyle = '#000000'; ctx.fillRect(0, 0, w, h); }
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
  }
  // local_curve: a move given frame by frame from the shot start (or `at` s): scale about the centre, offset dx/dy and
  // blur radius (fractions of the canvas height), a thresholded glow and an exposure factor. Past the end of an array its
  // value is the identity. Measured transitions (analyze_reference measure "transitions") come out in this form.
  function curve(ctx, p, s) {
    const {W: w, H: h, elapsed, fps} = s, i = Math.floor((elapsed - (p.at ?? 0)) * fps + 1e-6);
    if (i < 0) return;
    const at = (a, d) => (a && i < a.length ? a[i] : d);
    const sc = at(p.scale, 1), ox = at(p.dx, 0) * h, oy = at(p.dy, 0) * h, r = at(p.blur, 0) * h, g = at(p.glow, 0), e = at(p.exposure, 1);
    if (Math.abs(sc - 1) > 1e-4 || Math.abs(ox) > .05 || Math.abs(oy) > .05 || r > .3) {
      const src = copy(ctx), mirror = p.mirror !== false;
      const pad = mirror ? Math.max(0, Math.min(Math.min(w, h) - 1,
        Math.ceil(Math.max(w, h) / 2 * Math.max(0, 1 / sc - 1) + Math.max(Math.abs(ox), Math.abs(oy)) / sc + 3 * r / sc + 4))) : 0;
      const pic = mirror ? mirrorPad(src, w, h, pad) : src;
      ctx.fillStyle = '#000000'; ctx.fillRect(0, 0, w, h);
      ctx.filter = r > .3 ? `blur(${r}px)` : 'none';
      ctx.setTransform(sc, 0, 0, sc, w / 2 * (1 - sc) + ox, h / 2 * (1 - sc) + oy); ctx.drawImage(pic, -pad, -pad);
      ctx.resetTransform(); ctx.filter = 'none';
    }
    if (g > .002) {   // wide and soft, so built at quarter size: min(1, g x blur(contrast(brightness(picture))))
      const q = 4, sw = Math.ceil(w / q), sh = Math.ceil(h / q), R = (p.glow_radius ?? 25 / 1080) * h / q;
      const pp = Math.max(1, Math.min(Math.min(sw, sh) - 1, Math.ceil(3 * R + 2)));
      const small = buffer(sw, sh); small.getContext('2d').drawImage(ctx.canvas, 0, 0, sw, sh);
      const pad = mirrorPad(small, sw, sh, pp), glow = buffer(sw, sh), gx = glow.getContext('2d');
      gx.filter = `brightness(${p.glow_bright ?? 2.4}) contrast(${p.glow_contrast ?? 2.2}) blur(${R}px) brightness(${g})`;
      gx.drawImage(pad, -pp, -pp); gx.filter = 'none';
      ctx.globalCompositeOperation = p.glow_mode === 'add' ? 'lighter' : 'screen'; ctx.drawImage(glow, 0, 0, w, h);
      ctx.globalCompositeOperation = 'source-over';
    }
    exposure(ctx, e, w, h);
  }
  // Improved Perlin noise in 3D (Ken Perlin, 2002) over a seeded permutation, about -1..1; `.n4` is the 4-D version
  // (gradients to the 32 edge midpoints of a tesseract) that looping evolution walks a circle through.
  const noises = new Map(), G4 = new Int8Array(128);
  { let i = 0; for (const a of [-1, 1]) for (const b of [-1, 1]) for (const c of [-1, 1]) for (const v of [[0, a, b, c], [a, 0, b, c], [a, b, 0, c], [a, b, c, 0]]) G4.set(v, 4 * i++); }
  function perlin(seed) {
    if (noises.has(seed)) return noises.get(seed);
    const r = rng(seed * 7919 + 17), perm = [...Array(256).keys()], P = new Uint8Array(512);
    for (let i = 255; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [perm[i], perm[j]] = [perm[j], perm[i]]; }
    for (let i = 0; i < 512; i++) P[i] = perm[i & 255];
    const fade = t => t * t * t * (t * (t * 6 - 15) + 10), lerp = (a, b, t) => a + t * (b - a);
    const grad = (hh, x, y, z) => { hh &= 15; const u = hh < 8 ? x : y, v = hh < 4 ? y : hh === 12 || hh === 14 ? x : z;
      return ((hh & 1) ? -u : u) + ((hh & 2) ? -v : v); };
    const n = (x, y, z) => {
      const X = Math.floor(x), Y = Math.floor(y), Z = Math.floor(z); x -= X; y -= Y; z -= Z;
      const xi = X & 255, yi = Y & 255, zi = Z & 255, u = fade(x), v = fade(y), w = fade(z);
      const A = P[xi] + yi, AA = P[A] + zi, AB = P[A + 1] + zi, B = P[xi + 1] + yi, BA = P[B] + zi, BB = P[B + 1] + zi;
      return lerp(lerp(lerp(grad(P[AA], x, y, z), grad(P[BA], x - 1, y, z), u), lerp(grad(P[AB], x, y - 1, z), grad(P[BB], x - 1, y - 1, z), u), v),
                  lerp(lerp(grad(P[AA + 1], x, y, z - 1), grad(P[BA + 1], x - 1, y, z - 1), u),
                       lerp(grad(P[AB + 1], x, y - 1, z - 1), grad(P[BB + 1], x - 1, y - 1, z - 1), u), v), w);
    };
    const g4 = (hh, x, y, z, w) => { const o = (hh & 31) << 2; return G4[o] * x + G4[o + 1] * y + G4[o + 2] * z + G4[o + 3] * w; };
    n.n4 = (x, y, z, w) => {
      const X = Math.floor(x), Y = Math.floor(y), Z = Math.floor(z), Q = Math.floor(w); x -= X; y -= Y; z -= Z; w -= Q;
      const xi = X & 255, yi = Y & 255, zi = Z & 255, wi = Q & 255, u = fade(x), v = fade(y), s = fade(z), q = fade(w);
      const x1 = x - 1, y1 = y - 1, z1 = z - 1, w1 = w - 1;
      const A = P[xi] + yi, B = P[xi + 1] + yi, AA = P[A] + zi, AB = P[A + 1] + zi, BA = P[B] + zi, BB = P[B + 1] + zi;
      const AAA = P[AA] + wi, AAB = P[AA + 1] + wi, ABA = P[AB] + wi, ABB = P[AB + 1] + wi;
      const BAA = P[BA] + wi, BAB = P[BA + 1] + wi, BBA = P[BB] + wi, BBB = P[BB + 1] + wi;
      const L00 = lerp(lerp(g4(P[AAA], x, y, z, w), g4(P[BAA], x1, y, z, w), u), lerp(g4(P[ABA], x, y1, z, w), g4(P[BBA], x1, y1, z, w), u), v);
      const L10 = lerp(lerp(g4(P[AAB], x, y, z1, w), g4(P[BAB], x1, y, z1, w), u), lerp(g4(P[ABB], x, y1, z1, w), g4(P[BBB], x1, y1, z1, w), u), v);
      const L01 = lerp(lerp(g4(P[AAA + 1], x, y, z, w1), g4(P[BAA + 1], x1, y, z, w1), u), lerp(g4(P[ABA + 1], x, y1, z, w1), g4(P[BBA + 1], x1, y1, z, w1), u), v);
      const L11 = lerp(lerp(g4(P[AAB + 1], x, y, z1, w1), g4(P[BAB + 1], x1, y, z1, w1), u), lerp(g4(P[ABB + 1], x, y1, z1, w1), g4(P[BBB + 1], x1, y1, z1, w1), u), v);
      return lerp(lerp(L00, L10, s), lerp(L01, L11, s), q);
    };
    noises.set(seed, n);
    return n;
  }
  // a cubic-bezier speed curve from (0, 0) to (1, 1) through handles (x1, y1) and (x2, y2), as in a graph editor or CSS
  function bezier(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx, cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const X = s => ((ax * s + bx) * s + cx) * s, dX = s => (3 * ax * s + 2 * bx) * s + cx;
    return u => {
      let s = u;
      for (let i = 0; i < 8; i++) { const e = X(s) - u, d = dX(s); if (Math.abs(e) < 1e-7) break; if (Math.abs(d) < 1e-6) { s = NaN; break; } s -= e / d; }
      if (!(s >= 0 && s <= 1 && Math.abs(X(s) - u) < 1e-6)) {   // Newton strayed: bisect
        let lo = 0, hi = 1; s = u;
        for (let i = 0; i < 40; i++) { X(s) < u ? lo = s : hi = s; s = (lo + hi) / 2; }
      }
      return ((ay * s + by) * s + cy) * s;
    };
  }
  const EASY = bezier(.33, 0, .67, 1), beziers = new Map();   // easy ease: 33% influence on both sides
  function shape(u, e) {
    if (Array.isArray(e)) { const key = e.join(); if (!beziers.has(key)) beziers.set(key, bezier(...e)); return beziers.get(key)(u); }
    if (e === 'in2') return u * u;
    if (e === 'in3') return u * u * u;
    if (e === 'out2') return 1 - (1 - u) ** 2;
    if (e === 'out3') return 1 - (1 - u) ** 3;
    if (e === 'inout') return u * u * (3 - 2 * u);
    if (e === 'inout3') return u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
    if (e === 'outback') { const c1 = 1.70158, q = u - 1; return 1 + (c1 + 1) * q * q * q + c1 * q * q; }
    if (e === 'ease') return EASY(u);
    return u;
  }
  const mixValue = (a, b, u) => (Array.isArray(a) ? a.map((x, i) => x + (b[i] - x) * u) : a + (b - a) * u);
  // a value (a number or [x, y]), or keyframes [[seconds, value, ease?], ...]: the ease on a key shapes the move to the
  // next one (linear by default; the engine's eases, "ease" for Easy Ease, "hold", or a cubic-bezier [x1, y1, x2, y2]);
  // held before the first key and after the last
  const keyedT = (v, t, d) => {
    if (v == null) return d;
    if (!Array.isArray(v) || !Array.isArray(v[0])) return v;
    if (t <= v[0][0]) return v[0][1];
    for (let i = 1; i < v.length; i++) if (t < v[i][0]) {
      const [t0, a, e] = v[i - 1], [t1, b] = v[i];
      return e === 'hold' ? a : mixValue(a, b, shape((t - t0) / (t1 - t0), e));
    }
    return v[v.length - 1][1];
  };
  // out pixel (x, y) = the source at (x, y) + the move `at(x, y)` leaves in D: bilinear; beyond the frame by `edges`
  // (reflect, clamp or wrap). Quality "high" averages four sub-pixel samples, each moved by the field at its own place
  // (antialiased where the move squeezes the picture). A pixel that `still` keeps, or that barely moves, is copied.
  const reflect = (v, m) => { if (m < 2) return 0; const period = 2 * (m - 1); v = Math.abs(v) % period; return v > m - 1 ? period - v : v; };
  const EDGES = {reflect, clamp: (v, m) => (v < 0 ? 0 : v > m - 1 ? m - 1 : v), wrap: (v, m) => ((v % m) + m) % m};
  const SUB = [-.25, -.25, .25, -.25, -.25, .25, .25, .25];
  function remap(ctx, w, h, at, D, opt) {
    const sd = ctx.getImageData(0, 0, w, h).data, out = ctx.createImageData(w, h), od = out.data, acc = new Float64Array(4);
    const edge = EDGES[opt.edges ?? 'reflect'], wrap = opt.edges === 'wrap', high = opt.quality === 'high', still = opt.still;
    const tap = (sx, sy, k) => {
      sx = edge(sx, w); sy = edge(sy, h);
      const x0 = Math.floor(sx), y0 = Math.floor(sy), ux = sx - x0, uy = sy - y0;
      const x1 = x0 + 1 < w ? x0 + 1 : wrap ? 0 : w - 1, y1 = y0 + 1 < h ? y0 + 1 : wrap ? 0 : h - 1;
      const a = (y0 * w + x0) * 4, b = (y0 * w + x1) * 4, c = (y1 * w + x0) * 4, d = (y1 * w + x1) * 4;
      const v00 = (1 - ux) * (1 - uy) * k, v10 = ux * (1 - uy) * k, v01 = (1 - ux) * uy * k, v11 = ux * uy * k;
      for (let ch = 0; ch < 4; ch++) acc[ch] += sd[a + ch] * v00 + sd[b + ch] * v10 + sd[c + ch] * v01 + sd[d + ch] * v11;
    };
    const moves = () => Math.abs(D[0]) >= .002 || Math.abs(D[1]) >= .002;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const o = (y * w + x) * 4;
      let moved = false;
      if (!(still && still(x, y))) {
        acc.fill(0);
        if (high) for (let i = 0; i < 8; i += 2) { at(x + SUB[i], y + SUB[i + 1]); moved = moves() || moved; tap(x + SUB[i] + D[0], y + SUB[i + 1] + D[1], .25); }
        else { at(x, y); if (moves()) { moved = true; tap(x + D[0], y + D[1], 1); } }
      }
      if (moved) { od[o] = acc[0]; od[o + 1] = acc[1]; od[o + 2] = acc[2]; od[o + 3] = acc[3]; }
      else { od[o] = sd[o]; od[o + 1] = sd[o + 1]; od[o + 2] = sd[o + 2]; od[o + 3] = sd[o + 3]; }
    }
    ctx.putImageData(out, 0, 0);
  }
  const inBox = (reg, fe, w, h) => {   // weight 1 inside region [x0, y0, x1, y1] (0..1), fading to 0 over `fe` px outside
    const [rx0, ry0, rx1, ry1] = [reg[0] * w, reg[1] * h, reg[2] * w, reg[3] * h];
    const inside = (v, a, b) => fe > 0 ? clamp(1 - Math.max(a - v, v - b, 0) / fe) : (v >= a && v <= b ? 1 : 0);
    return {weight: (x, y) => inside(x, rx0, rx1) * inside(y, ry0, ry1), still: (x, y) => x < rx0 - fe || x > rx1 + fe || y < ry0 - fe || y > ry1 + fe};
  };
  // local_turbulent_displace: Turbulent Displace. A fractal-noise field (complexity = octaves; a fraction
  // weighs in the last one) moves every pixel by up to `amount` px (at 1080): turbulent (both axes), horizontal,
  // vertical, cross (both by one field), bulge (along the noise slope: highs swell) or twist (across it: swirls). The
  // "_smoother" modes compute the field twice as finely and interpolate it cubically: smoother bends, slower. `size` is
  // the feature size (px at 1080); evolution moves through the noise (`speed` revolutions a second, 0 by default when
  // evolution is keyframed) and `cycle` n loops it every n revolutions; `offset` and `drift` slide it; `every` holds it
  // for n frames (a boil). amount, size, complexity, evolution and offset take keyframes. Pinning fades the move to zero
  // at the frame edges (the "_locked" pins also never pull pixels from beyond them); `region` [x0, y0, x1, y1] (0..1)
  // with `feather` confines it. Sampling as remap: `edges`, `quality`.
  function turbulent(ctx, p, s) {
    const {W: w, H: h, elapsed, fps} = s, k = h / 1080, t = elapsed - (p.at ?? 0);
    if (t < 0) return;
    const every = p.every ?? 1, tq = Math.floor(t * fps / every + 1e-6) * every / fps, tk = every > 1 ? tq : t;
    const A = keyedT(p.amount, tk, 20) * k;
    if (!(A > .02)) return;
    const size = Math.max(1, keyedT(p.size, tk, 100) * k), C = clamp(keyedT(p.complexity, tk, 1), 1, 10);
    const oct = Math.ceil(C - 1e-9), last = C - (oct - 1);
    const kind = p.displacement ?? 'turbulent', smoother = kind.endsWith('_smoother'), mode = smoother ? kind.slice(0, -9) : kind;
    const z = keyedT(p.evolution, tk, 0) + (p.speed ?? (Array.isArray(p.evolution) ? 0 : .5)) * tq, n = perlin(p.seed ?? 1);
    const off = keyedT(p.offset, tk, [0, 0]);
    const ox = (off[0] + (p.drift?.[0] ?? 0) * tq) * k, oy = (off[1] + (p.drift?.[1] ?? 0) * tq) * k;
    // cycle n: evolution walks a circle n revolutions round through 4-D noise, so revolution n is revolution 0 again
    // (.933 matches the 4-D noise's spread to the 3-D noise's)
    const cyc = p.cycle, th = cyc ? 2 * Math.PI * z / cyc : 0, R = cyc ? cyc / (2 * Math.PI) : 0, cz = R * Math.cos(th), cw = R * Math.sin(th);
    const octave = cyc ? (x, y, o) => .933 * n.n4(x, y, cz + o * 3.7, cw + o * 5.3) : (x, y, o) => n(x, y, z + o * 3.7);
    const fbm = (x, y, salt) => { let v = 0, a = 1, f = 1, norm = 0;
      for (let o = 0; o < oct; o++) { const wo = o === oct - 1 ? a * last : a; v += wo * octave(x * f + salt + o * 19.19, y * f + salt * .7 + o * 7.13, o); norm += wo; a *= .5; f *= 2; }
      return v / norm; };
    // the field on a grid a few px apart, finer than the smallest octave; grid point (i, j) sits at ((i - M) g, (j - M) g)
    const g = Math.max(1, Math.min(smoother ? 4 : 8, Math.round(size / Math.pow(2, oct - 1) / (smoother ? 12 : 6))));
    const M = 2, gw = Math.ceil(w / g) + 2 * M + 1, gh = Math.ceil(h / g) + 2 * M + 1;
    const FX = new Float32Array(gw * gh), FY = new Float32Array(gw * gh);
    const slope = mode === 'bulge' || mode === 'twist', sw = gw + 2;
    const N = slope ? new Float32Array(sw * (gh + 2)) : null;
    if (slope) for (let j = -1; j <= gh; j++) for (let i = -1; i <= gw; i++) N[(j + 1) * sw + i + 1] = fbm(((i - M) * g + ox) / size, ((j - M) * g + oy) / size, 0);
    const pinning = p.pin ?? 'all', locked = pinning.endsWith('_locked'), pin = locked ? pinning.slice(0, -7) : pinning;
    const pd = Math.max(2, Math.min(size, Math.min(w, h) / 4)), smooth = u => (u <= 0 ? 0 : u >= 1 ? 1 : u * u * (3 - 2 * u));
    const box = p.region ? inBox(p.region, (p.feather ?? .02) * h, w, h) : null;
    for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) {
      const x = (i - M) * g, y = (j - M) * g;
      let wgt = 1;
      if (pin === 'all' || pin === 'vertical') wgt *= smooth(Math.min(x, w - 1 - x) / pd);
      if (pin === 'all' || pin === 'horizontal') wgt *= smooth(Math.min(y, h - 1 - y) / pd);
      if (box) wgt *= box.weight(x, y);
      if (wgt <= 0) continue;
      let dx = 0, dy = 0;
      if (slope) {   // the noise slope per feature size, quartered: it then folds over at about the turbulent field's amount
        const c = (j + 1) * sw + i + 1, sx = (N[c + 1] - N[c - 1]) / (2 * g) * size * .25, sy = (N[c + sw] - N[c - sw]) / (2 * g) * size * .25;
        if (mode === 'bulge') { dx = sx; dy = sy; } else { dx = -sy; dy = sx; }
      } else {
        const nx = (x + ox) / size, ny = (y + oy) / size, a = fbm(nx, ny, 0);
        if (mode === 'turbulent') { dx = a; dy = fbm(nx, ny, 53.1); }
        else if (mode === 'horizontal') dx = a;
        else if (mode === 'vertical') dy = a;
        else { dx = a; dy = a; }
      }
      FX[j * gw + i] = dx * A * wgt; FY[j * gw + i] = dy * A * wgt;
    }
    // the move at any point: bilinear between grid points, or Catmull-Rom (cubic) for the smoother modes
    const D = [0, 0], wx = new Float64Array(4), wy = new Float64Array(4);
    const cr = (u, o) => { const u2 = u * u, u3 = u2 * u; o[0] = (-u3 + 2 * u2 - u) / 2; o[1] = (3 * u3 - 5 * u2 + 2) / 2; o[2] = (-3 * u3 + 4 * u2 + u) / 2; o[3] = (u3 - u2) / 2; };
    const at = (x, y) => {
      const gx = x / g + M, gy = y / g + M, i0 = Math.floor(gx), j0 = Math.floor(gy), fx = gx - i0, fy = gy - j0;
      if (!smoother) {
        const a = j0 * gw + i0, w00 = (1 - fx) * (1 - fy), w10 = fx * (1 - fy), w01 = (1 - fx) * fy, w11 = fx * fy;
        D[0] = FX[a] * w00 + FX[a + 1] * w10 + FX[a + gw] * w01 + FX[a + gw + 1] * w11;
        D[1] = FY[a] * w00 + FY[a + 1] * w10 + FY[a + gw] * w01 + FY[a + gw + 1] * w11;
        return;
      }
      cr(fx, wx); cr(fy, wy);
      let dx = 0, dy = 0;
      for (let jj = 0; jj < 4; jj++) {
        const row = (j0 - 1 + jj) * gw + i0 - 1;
        dx += (FX[row] * wx[0] + FX[row + 1] * wx[1] + FX[row + 2] * wx[2] + FX[row + 3] * wx[3]) * wy[jj];
        dy += (FY[row] * wx[0] + FY[row + 1] * wx[1] + FY[row + 2] * wx[2] + FY[row + 3] * wx[3]) * wy[jj];
      }
      D[0] = dx; D[1] = dy;
    };
    // pixels outside the region and its feather keep their place (the grid would otherwise bleed one cell past it)
    remap(ctx, w, h, at, D, {still: box ? box.still : null, edges: locked ? 'clamp' : p.edges, quality: p.quality});
  }
  // local_displacement_map: Displacement Map. A frame of another clip (`s.map`, loaded by the engine)
  // moves each pixel by (channel - 128) / 127 x `amount` px at 1080 (`amount_x` / `amount_y` set one axis): `x` and `y`
  // pick each axis's channel (red, green, blue, alpha, luma, hue, lightness, saturation; full moves by the whole amount,
  // half and none not at all), so mid grey keeps a pixel in place (`neutral` sets that level, or "mean" for the map
  // frame's mean). `fit` stretches the map over the frame, centres it at its own size (nothing moves outside it) or tiles
  // it; `smooth` softens it (px at 1080). `region` [x0, y0, x1, y1] with `feather` confines it; sampling as remap
  // (`edges`, `quality`). Heat haze, glass, water and ripple plates drive it.
  const luma = (d, i) => .2126 * d[i] + .7152 * d[i + 1] + .0722 * d[i + 2];
  const hsl = (d, i) => { const r = d[i], g = d[i + 1], b = d[i + 2], mx = Math.max(r, g, b), mn = Math.min(r, g, b); return [mx, mn]; };
  const CHANNEL = {red: (d, i) => d[i], green: (d, i) => d[i + 1], blue: (d, i) => d[i + 2], alpha: (d, i) => d[i + 3], luma, luminance: luma,
                   hue: (d, i) => hueSat(d[i], d[i + 1], d[i + 2])[0] / 360 * 255,
                   lightness: (d, i) => { const [mx, mn] = hsl(d, i); return (mx + mn) / 2; },
                   saturation: (d, i) => { const [mx, mn] = hsl(d, i), c = mx - mn; return c ? c / (255 - Math.abs(mx + mn - 255)) * 255 : 0; },
                   full: () => 255, half: () => 128};
  const softened = (pic, pw, ph, r, tile) => {   // pic at pw x ph, blurred by r px with mirrored (or, for a tile, wrapped) edges
    const c = buffer(pw, ph), x = c.getContext('2d');
    if (!(r > .3)) { x.drawImage(pic, 0, 0, pw, ph); return c; }
    let src, pad;
    if (tile) { src = buffer(3 * pw, 3 * ph); pad = [pw, ph]; const t = src.getContext('2d'); for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) t.drawImage(pic, i * pw, j * ph, pw, ph); }
    else { const q = Math.max(0, Math.min(Math.min(pw, ph) - 1, Math.ceil(3 * r) + 1)); src = mirrorPad(pic, pw, ph, q); pad = [q, q]; }
    x.filter = `blur(${r}px)`; x.drawImage(src, -pad[0], -pad[1]); x.filter = 'none';
    return c;
  };
  function displaceMap(ctx, p, s) {
    const {W: w, H: h, map} = s, k = h / 1080, t = s.elapsed - (p.at ?? 0);
    if (t < 0 || !map) return;
    const A = keyedT(p.amount, t, 20), Ax = (p.amount_x != null ? keyedT(p.amount_x, t, 20) : A) * k, Ay = (p.amount_y != null ? keyedT(p.amount_y, t, 20) : A) * k;
    const xc = p.x ?? 'red', yc = p.y ?? 'green', cx = CHANNEL[xc], cy = CHANNEL[yc];
    if (!((cx && Ax > .02) || (cy && Ay > .02))) return;
    const mb = buffer(w, h), mx = mb.getContext('2d'), sm = (p.smooth ?? 0) * k, fit = p.fit ?? 'stretch', mw = map.width, mh = map.height;
    let rect = [0, 0, w, h];   // where the map lies; nothing moves outside it
    if (fit === 'center') {
      const x0 = Math.round((w - mw) / 2), y0 = Math.round((h - mh) / 2);
      mx.drawImage(softened(map, mw, mh, sm, false), x0, y0);
      rect = [Math.max(0, x0), Math.max(0, y0), Math.min(w, x0 + mw), Math.min(h, y0 + mh)];
    } else if (fit === 'tile') {
      mx.fillStyle = mx.createPattern(softened(map, mw, mh, sm, true), 'repeat'); mx.fillRect(0, 0, w, h);
    } else mx.drawImage(softened(map, w, h, sm, false), 0, 0);
    const md = mx.getImageData(0, 0, w, h).data;
    // the channel level that keeps a pixel in place: 128, a given level, or this map frame's mean ("mean": a plate shot on
    // black then moves pixels by its variation instead of shifting the whole picture one way); full and half are fixed
    const mean = f => { let sum = 0, n = 0;
      for (let y = rect[1]; y < rect[3]; y += 4) for (let x = rect[0]; x < rect[2]; x += 4) { sum += f(md, (y * w + x) * 4); n++; }
      return n ? sum / n : 128; };
    const level = (c, f) => (c === 'full' || c === 'half' ? 128 : p.neutral === 'mean' ? mean(f) : p.neutral ?? 128);
    const nx = cx ? level(xc, cx) : 128, ny = cy ? level(yc, cy) : 128;
    const val = (f, o, n0) => Math.max(-1, Math.min(1, (f(md, o) - n0) / 127));
    const box = p.region ? inBox(p.region, (p.feather ?? .02) * h, w, h) : null;
    const DX = new Float32Array(w * h), DY = new Float32Array(w * h);
    for (let y = rect[1]; y < rect[3]; y++) for (let x = rect[0]; x < rect[2]; x++) {
      const i = y * w + x, wgt = box ? box.weight(x, y) : 1;
      if (wgt <= 0) continue;
      if (cx) DX[i] = val(cx, i * 4, nx) * Ax * wgt;
      if (cy) DY[i] = val(cy, i * 4, ny) * Ay * wgt;
    }
    const D = [0, 0];
    const at = (x, y) => {   // a pixel's own move, or bilinear between pixels for the sub-pixel samples of quality "high"
      if (x === (x | 0) && y === (y | 0)) { D[0] = DX[y * w + x]; D[1] = DY[y * w + x]; return; }
      const sx = clamp(x, 0, w - 1), sy = clamp(y, 0, h - 1), x0 = Math.floor(sx), y0 = Math.floor(sy), ux = sx - x0, uy = sy - y0;
      const a = y0 * w + x0, b = y0 * w + Math.min(w - 1, x0 + 1), c = Math.min(h - 1, y0 + 1) * w + x0, d = Math.min(h - 1, y0 + 1) * w + Math.min(w - 1, x0 + 1);
      const v00 = (1 - ux) * (1 - uy), v10 = ux * (1 - uy), v01 = (1 - ux) * uy, v11 = ux * uy;
      D[0] = DX[a] * v00 + DX[b] * v10 + DX[c] * v01 + DX[d] * v11; D[1] = DY[a] * v00 + DY[b] * v10 + DY[c] * v01 + DY[d] * v11;
    };
    remap(ctx, w, h, at, D, {still: null, edges: p.edges, quality: p.quality});
  }
  // which frame of the map clip a local_displacement_map shows at shot time `elapsed` (null before `at`)
  function mapFrame(p, clip, elapsed) {
    const t = elapsed - (p.at ?? 0);
    if (t < 0) return null;
    const i = Math.floor(((p.src ?? 0) + (p.speed ?? 1) * t) * clip.fps + 1e-6), n = clip.n, mode = p.loop ?? 'loop';
    if (mode === 'loop') return ((i % n) + n) % n;
    if (mode === 'pingpong' && n > 1) { const period = 2 * (n - 1), q = ((i % period) + period) % period; return q < n ? q : period - q; }
    return Math.max(0, Math.min(n - 1, i));
  }
  function draw(ctx, name, p, s) {
    if (!(name in orders)) return false;
    p = p === true ? {} : p;
    const {W: w, H: h, elapsed: t, frame} = s;
    ctx.save(); ctx.resetTransform();
    if (name === 'local_whip' || name === 'local_zoom_blur') {
      const d = p.d ?? .3, age = t - (p.at ?? 0);
      if (age >= 0 && age < d) {
        const q = age / d;
        if (name === 'local_whip') {   // echoes trail one way from the frame, weighted 1 - u, reach fading as (1 - q)^2
          // Calibrated effect behavior; see the local regression fixtures.
          const amt = (p.amount ?? .3) * (1 - q) ** 2, horiz = !['up', 'down'].includes(p.dir), L = amt * (horiz ? w : h) * 1.6, sign = ['left', 'up'].includes(p.dir) ? -1 : 1;
          smear(ctx, 12, (src, u) => { const o = sign * u * L; ctx.drawImage(src, horiz ? o : 0, horiz ? 0 : o); }, u => 1 - u + 1e-3);
        } else {                       // radial: scaled copies, fading as (1 - q)^2
          const amt = (p.amount ?? .3) * (1 - q) ** 2, [cx, cy] = (p.center ?? [.5, .5]).map((v, i) => v * (i ? h : w));
          smear(ctx, 12, (src, u) => { const z = 1 + amt * u; ctx.drawImage(src, cx - cx * z, cy - cy * z, w * z, h * z); });
        }
      }
    } else if (name === 'local_halftone') {
      const sp = p.spacing ?? 8, cols = Math.ceil(w / sp), rows = Math.ceil(h / sp), small = buffer(cols, rows), sc = small.getContext('2d');
      sc.imageSmoothingQuality = 'high'; sc.drawImage(ctx.canvas, 0, 0, cols * sp, rows * sp, 0, 0, cols, rows);
      const mix = clamp(p.mix ?? 1);
      if (mix > 0) {   // mix 0 leaves the picture untouched
        const px = sc.getImageData(0, 0, cols, rows).data, out = buffer(w, h), oc = out.getContext('2d');
        // Opaque paper; each dot is drawn with opacity `mix`, so where neighbouring dots overlap the ink doubles up
        // Calibrated effect behavior; see the local regression fixtures.
        oc.fillStyle = p.paper ?? '#f4efdf'; oc.fillRect(0, 0, w, h); oc.fillStyle = p.ink ?? '#16181e'; oc.globalAlpha = mix;
        for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
          const i = (y * cols + x) * 4, r = sp * HT_RADIUS[Math.round(.2126 * px[i] + .7152 * px[i + 1] + .0722 * px[i + 2])];
          if (r > .25) { oc.beginPath(); oc.arc((x + .5) * sp, (y + .5) * sp, r, 0, Math.PI * 2); oc.fill(); }
        }
        ctx.drawImage(out, 0, 0);
      }
    } else if (name === 'local_speed_lines') {
      const every = p.every ?? 1, r = rng((p.seed ?? 5) * 7919 + Math.floor(frame / every)), n = p.count ?? 48;
      const R = Math.hypot(w, h) / 2, inner = p.inner ?? .55, lw = p.width ?? 1.5;
      ctx.fillStyle = p.color ?? '#ffffff'; ctx.globalAlpha = clamp(p.opacity ?? .5);
      for (let i = 0; i < n; i++) {
        // lines end on an ellipse of the frame's proportions (inner x half-width / half-height), plus a random reach
        const a = r() * Math.PI * 2, ca = Math.cos(a), sa = Math.sin(a), k = inner * (1 + r() * .5), wd = lw * (.5 + r());
        ctx.beginPath(); ctx.moveTo(w / 2 + ca * k * w / 2, h / 2 + sa * k * h / 2);
        ctx.lineTo(w / 2 + ca * R * 1.05 - sa * wd, h / 2 + sa * R * 1.05 + ca * wd); ctx.lineTo(w / 2 + ca * R * 1.05 + sa * wd, h / 2 + sa * R * 1.05 - ca * wd);
        ctx.closePath(); ctx.fill();
      }
    } else if (name === 'local_frame_slices') {
      const cont = p.continuous ?? true, d = p.d ?? .15;
      if (cont || t < d) {
        const r = rng((p.seed ?? 11) * 104729 + (cont ? frame : 0)), n = p.n ?? 9, src = copy(ctx), amt = p.amount ?? .1;
        const cuts = Array.from({length: n - 1}, () => r()).sort((a, b) => a - b), bounds = [0, ...cuts, 1];
        ctx.fillStyle = '#000000'; ctx.fillRect(0, 0, w, h);
        for (let i = 0; i < n; i++) {
          const y0 = Math.round(bounds[i] * h), y1 = Math.round(bounds[i + 1] * h), dx = Math.round((r() * 2 - 1) * amt * w);
          if (y1 > y0) ctx.drawImage(src, 0, y0, w, y1 - y0, dx, y0, w, y1 - y0);
        }
      }
    } else if (name === 'local_selective_color') {
      const hue = p.hue ?? 0, tol = p.tolerance ?? 25, soft = p.soft ?? 5, minSat = p.min_sat ?? .12;
      pixels(ctx, (d, i) => {
        const [r, g, b] = [d[i], d[i + 1], d[i + 2]], [hh, sat] = hueSat(r, g, b), dh = Math.min(Math.abs(hh - hue), 360 - Math.abs(hh - hue));
        const keep = sat < minSat ? 0 : (dh <= tol ? 1 : soft > 0 ? clamp(1 - (dh - tol) / soft) : 0);
        if (keep >= 1) return;
        const y = .2126 * r + .7152 * g + .0722 * b;
        d[i] = y + keep * (r - y); d[i + 1] = y + keep * (g - y); d[i + 2] = y + keep * (b - y);
      });
    } else if (name === 'local_posterize') {
      const L = (p.levels ?? 4) - 1, q = v => Math.round(Math.round(v / 255 * L) * 255 / L);
      pixels(ctx, (d, i) => { d[i] = q(d[i]); d[i + 1] = q(d[i + 1]); d[i + 2] = q(d[i + 2]); });
    } else if (name === 'local_paper_frame') {
      const src = copy(ctx);
      if ((p.mode ?? 'paper') === 'filmstrip') {
        const b = Math.round(w * .055), holeH = b * .5, holeW = b * .5, gap = holeH * 2, off = (frame * holeH * .5) % gap;
        ctx.fillStyle = '#000000'; ctx.fillRect(0, 0, w, h);
        ctx.drawImage(src, b, 0, w - 2 * b, h);
        ctx.fillStyle = p.color ?? '#f5f2ea';
        for (const x of [(b - holeW) / 2, w - b + (b - holeW) / 2]) for (let y = -gap + off; y < h; y += gap) {
          ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x, y, holeW, holeH, holeH * .2) : ctx.rect(x, y, holeW, holeH); ctx.fill();
        }
      } else {
        const m = (p.margin ?? .045) * Math.min(w, h);
        ctx.fillStyle = p.color ?? '#f2ece0'; ctx.fillRect(0, 0, w, h);
        ctx.save(); deckle(ctx, m, m, w - m, h - m, m * .7, p.seed ?? 3); ctx.clip();
        ctx.drawImage(src, m * .5, m * .5, w - m, h - m); ctx.restore();
      }
    } else if (name === 'local_curve') {
      curve(ctx, p, s);
    } else if (name === 'local_turbulent_displace') {
      turbulent(ctx, p, s);
    } else if (name === 'local_displacement_map') {
      displaceMap(ctx, p, s);
    } else if (name === 'local_scramble_text') {
      const chars = [...p.text], n = chars.length, d = p.d ?? .6, age = t - (p.at ?? 0);
      if (age >= 0) {
        const glyphs = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', step = Math.floor(frame / 2);
        const shown = chars.map((ch, i) => (ch === ' ' || age >= d * (i + 1) / n) ? ch : glyphs[Math.floor(rng((p.seed ?? 9) * 31 + i * 977 + step * 7)() * glyphs.length)]).join('');
        ctx.font = `700 ${p.size ?? Math.round(h * .12)}px "${p.family}"`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillStyle = p.fill ?? '#ffffff'; ctx.fillText(shown, (p.pos?.[0] ?? .5) * w, (p.pos?.[1] ?? .5) * h);
      }
    }
    ctx.restore();
    return true;
  }
  const util = {clamp, buffer, copy, rng, mirrorPad, exposure, hueSat, perlin, bezier, shape, keyedT, remap, inBox, reflect,
                EDGES, luma, softened};
  return {orders, phase, draw, mapFrame, register, pack: name => packs[name] ?? null, util};
})();
