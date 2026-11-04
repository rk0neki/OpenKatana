// Light effects as an OpenKatana effect pack (Deep Glow, Lens Flare, Light Rays, Light Sweep). Parameters
// and defaults are documented in docs/TIMELINE.md; validation is in openkatana/fx_light.py. Shared helpers:
// OpenKatanaLocal.util. Each effect builds its light on a small float buffer (or with gradients) and adds it over the
// frame (lighter or screen), so a frame with nothing bright enough, or an amount of 0, comes out bit-identical.
(() => {
  const {register, util} = OpenKatanaLocal;
  const {clamp, buffer, keyedT, perlin, shape, rng} = util;
  const hex = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16) / 255);
  const tintOf = v => (typeof v === 'string' && v[0] === '#' ? hex(v) : null);
  const rgba = (c, a) => `rgba(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)},${clamp(a)})`;
  const mixC = (a, b, u) => a.map((x, i) => x + (b[i] - x) * u);

  // the frame scaled to w x h (RGBA bytes)
  function grab(ctx, w, h) {
    const b = buffer(w, h), g = b.getContext('2d');
    g.imageSmoothingQuality = 'high'; g.drawImage(ctx.canvas, 0, 0, w, h);
    return g.getImageData(0, 0, w, h).data;
  }
  // the parts brighter than `th` (Rec. 709 luma, 0..1): colour x clamp((luma - th) / (1 - th)) ** knee as float RGB; null
  // when nothing passes (the effect then leaves the frame untouched)
  function bright(d, n, th, knee = 1) {
    const out = new Float32Array(n * 3), span = Math.max(1e-3, 1 - th);
    let any = false;
    for (let i = 0; i < n; i++) {
      const r = d[4 * i] / 255, g = d[4 * i + 1] / 255, b = d[4 * i + 2] / 255, l = .2126 * r + .7152 * g + .0722 * b;
      if (l <= th) continue;
      const m = Math.min(1, (l - th) / span) ** knee;
      out[3 * i] = r * m; out[3 * i + 1] = g * m; out[3 * i + 2] = b * m; any = true;
    }
    return any ? out : null;
  }
  // separable box blur of float RGB (edges extended); three passes approximate a gaussian of sigma^2 = b^2 + b
  function boxPass(src, dst, w, h, b, horizontal) {
    const n = horizontal ? w : h, lines = horizontal ? h : w, step = horizontal ? 3 : 3 * w, k = 1 / (2 * b + 1);
    for (let l = 0; l < lines; l++) {
      const base = horizontal ? l * w * 3 : l * 3;
      for (let c = 0; c < 3; c++) {
        const o = base + c;
        let s = 0;
        for (let i = -b; i <= b; i++) s += src[o + step * Math.min(n - 1, Math.max(0, i))];
        for (let i = 0; i < n; i++) {
          dst[o + step * i] = s * k;
          s += src[o + step * Math.min(n - 1, i + b + 1)] - src[o + step * Math.max(0, i - b)];
        }
      }
    }
  }
  function gauss(buf, w, h, sigma) {
    const b = Math.max(1, Math.round(Math.sqrt(sigma * sigma + .25) - .5)), tmp = new Float32Array(buf.length);
    for (let i = 0; i < 3; i++) { boxPass(buf, tmp, w, h, b, true); boxPass(tmp, buf, w, h, b, false); }
  }
  function half(src, w, h) {   // 2 x 2 average down to ceil(w/2) x ceil(h/2)
    const hw = Math.ceil(w / 2), hh = Math.ceil(h / 2), out = new Float32Array(hw * hh * 3);
    for (let y = 0; y < hh; y++) for (let x = 0; x < hw; x++) {
      const x0 = 2 * x, y0 = 2 * y, x1 = Math.min(w - 1, x0 + 1), y1 = Math.min(h - 1, y0 + 1);
      for (let c = 0; c < 3; c++) out[(y * hw + x) * 3 + c] = (src[(y0 * w + x0) * 3 + c] + src[(y0 * w + x1) * 3 + c] + src[(y1 * w + x0) * 3 + c] + src[(y1 * w + x1) * 3 + c]) / 4;
    }
    return {d: out, w: hw, h: hh};
  }
  // acc (w x h) += weight x lv (lw x lh) bilinearly upsampled
  function addUp(acc, w, h, lv, lw, lh, weight) {
    if (lw === w && lh === h) { for (let i = 0; i < acc.length; i++) acc[i] += lv[i] * weight; return; }
    const fx = lw / w, fy = lh / h;
    for (let y = 0; y < h; y++) {
      const sy = Math.min(lh - 1, Math.max(0, (y + .5) * fy - .5)), y0 = Math.floor(sy), y1 = Math.min(lh - 1, y0 + 1), uy = sy - y0;
      for (let x = 0; x < w; x++) {
        const sx = Math.min(lw - 1, Math.max(0, (x + .5) * fx - .5)), x0 = Math.floor(sx), x1 = Math.min(lw - 1, x0 + 1), ux = sx - x0;
        const a = (y0 * lw + x0) * 3, b = (y0 * lw + x1) * 3, c = (y1 * lw + x0) * 3, d = (y1 * lw + x1) * 3, o = (y * w + x) * 3;
        for (let ch = 0; ch < 3; ch++) acc[o + ch] += weight * ((lv[a + ch] * (1 - ux) + lv[b + ch] * ux) * (1 - uy) + (lv[c + ch] * (1 - ux) + lv[d + ch] * ux) * uy);
      }
    }
  }
  // float RGB light (w x h) -> a canvas, with gain, tint (the light's luma times the colour, its brightest channel kept)
  // and saturation; then added over the frame (lighter) or screened
  function lay(ctx, s, light, w, h, gain, tint, sat, blend) {
    const c = buffer(w, h), g = c.getContext('2d'), img = g.createImageData(w, h), d = img.data, tn = tint && tint.map(x => x / Math.max(1e-3, ...tint));
    for (let i = 0, n = w * h; i < n; i++) {
      let r = light[3 * i] * gain, gg = light[3 * i + 1] * gain, b = light[3 * i + 2] * gain;
      if (tn) { const l = .2126 * r + .7152 * gg + .0722 * b; r = l * tn[0]; gg = l * tn[1]; b = l * tn[2]; }
      if (sat !== 1) { const m = .2126 * r + .7152 * gg + .0722 * b; r = m + (r - m) * sat; gg = m + (gg - m) * sat; b = m + (b - m) * sat; }
      d[4 * i] = clamp(r) * 255 + .5; d[4 * i + 1] = clamp(gg) * 255 + .5; d[4 * i + 2] = clamp(b) * 255 + .5; d[4 * i + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    ctx.globalCompositeOperation = blend === 'screen' ? 'screen' : 'lighter';
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(c, 0, 0, s.W, s.H);
    ctx.globalCompositeOperation = 'source-over';
  }

  // local_deep_glow: a deep, layered glow. Parts brighter than `threshold` (luma 0..1, soft above it)
  // (squared above it, so parts just over the threshold glow faintly) are blurred `layers` times with radii doubling up to
  // `radius` (px at 1080) and summed with weights growing by sqrt 2 per layer and adding up to 1: exposure 1 adds the
  // thresholded picture once over a flat area (a standard glow at intensity 1), and a point of light falls off about
  // as r^-1.5, a tight core and a wide tail. `exposure` scales the sum; `tint` colours it, `saturation` scales its
  // colourfulness; `blend` add (default) or screen. Built at most 540 px high.
  register('local_deep_glow', {order: 80, draw(ctx, p, s) {
    const {W, H} = s, t = s.elapsed - (p.at ?? 0);
    if (t < 0) return;
    const E = keyedT(p.exposure, t, 1);
    if (!(E > 0)) return;
    const th = clamp(keyedT(p.threshold, t, .6)), L = clamp(Math.round(p.layers ?? 6), 2, 8);
    const sc = Math.min(1, 540 / H), w = Math.max(1, Math.round(W * sc)), h = Math.max(1, Math.round(H * sc));
    const R = Math.max(.5, keyedT(p.radius, t, 120) * H / 1080 * sc);
    const src = bright(grab(ctx, w, h), w * h, th, 2);
    if (!src) return;
    const wsum = (2 ** (L / 2) - 1) / (Math.SQRT2 - 1);   // sum of sqrt 2 ** i, i < L
    const acc = new Float32Array(w * h * 3), levels = [{d: src, w, h}];
    for (let i = 0; i < L; i++) {
      const sigma = R / 2 ** (L - 1 - i) / 2;   // the radius is about two sigma
      let lv = 0;   // blur on a pyramid level where sigma stays a few px (fast at any radius)
      while (sigma / 2 ** (lv + 1) >= 2 && Math.min(levels[lv].w, levels[lv].h) >= 16) {
        if (!levels[lv + 1]) levels.push(half(levels[lv].d, levels[lv].w, levels[lv].h));
        lv++;
      }
      const {d, w: lw, h: lh} = levels[lv], buf = Float32Array.from(d);
      gauss(buf, lw, lh, sigma / 2 ** lv);
      addUp(acc, w, h, buf, lw, lh, Math.SQRT2 ** i / wsum);
    }
    lay(ctx, s, acc, w, h, E, tintOf(p.tint), keyedT(p.saturation, t, 1), p.blend);
  }});

  // local_lens_flare: a lens flare, drawn with gradients. A hot core at
  // `position` ([x, y] fractions, may sit off frame), a halo, a faint rainbow ring and a lens's own set of ghosts along
  // the line from the light through the frame centre (t 1 = the centre, 2 = the mirror point). `lens` picks the set:
  // 50_300mm_zoom (many small hexagonal ghosts), 35mm_prime (big soft ghosts and star rays), 105mm_prime (a tight core,
  // small bright ghosts, a strong ring). `brightness` 0..3, `streak` 0..1 an anamorphic horizontal streak, `tint`
  // colours it all, `flicker` 0..1 a seeded flutter of the brightness.
  const LENSES = {   // ghosts: [t, radius px at 1080, alpha, colour, kind]
    '50_300mm_zoom': {core: 70, glow: 330, halo: [.22, .035, .10], ring: [.42, .05, .07], rays: 0, ghosts: [
      [.22, 16, .30, '#ff9a3c', 'disc'], [.42, 36, .13, '#7cff7a', 'hex'], [.58, 8, .40, '#ffd27a', 'disc'],
      [.8, 64, .09, '#5a9cff', 'hex'], [1.1, 24, .20, '#b37aff', 'hex'], [1.28, 100, .07, '#3cffb0', 'ring'],
      [1.42, 12, .34, '#ff6a3c', 'disc'], [1.6, 50, .13, '#4a7dff', 'hex'], [1.85, 140, .07, '#ffb15a', 'hex'],
      [2.05, 32, .22, '#9aff5a', 'disc'], [2.3, 76, .11, '#5ad1ff', 'ring']]},
    '35mm_prime': {core: 90, glow: 480, halo: [.3, .08, .07], ring: [.55, .07, .05], rays: 14, ghosts: [
      [.45, 60, .10, '#ffe0a0', 'glow'], [.9, 26, .16, '#ffb070', 'disc'], [1.35, 120, .08, '#a0c8ff', 'glow'],
      [1.7, 44, .13, '#ffd090', 'disc'], [2.1, 190, .06, '#c0a0ff', 'ring']]},
    '105mm_prime': {core: 45, glow: 220, halo: [.14, .025, .12], ring: [.3, .03, .12], rays: 0, ghosts: [
      [.55, 7, .55, '#ffffff', 'disc'], [.75, 15, .28, '#ffcc66', 'disc'], [1.2, 11, .38, '#88aaff', 'disc'],
      [1.5, 30, .16, '#ff9966', 'ring'], [1.9, 19, .26, '#aaffcc', 'disc'], [2.2, 9, .4, '#ffd0ff', 'disc']]},
  };
  function blob(ctx, x, y, r, col, a, kind) {
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    if (kind === 'ring') { g.addColorStop(0, rgba(col, 0)); g.addColorStop(.72, rgba(col, a * .25)); g.addColorStop(.9, rgba(col, a)); g.addColorStop(1, rgba(col, 0)); }
    else if (kind === 'glow') { g.addColorStop(0, rgba(col, a)); g.addColorStop(.5, rgba(col, a * .35)); g.addColorStop(1, rgba(col, 0)); }
    else { g.addColorStop(0, rgba(col, a * .7)); g.addColorStop(.8, rgba(col, a)); g.addColorStop(.92, rgba(col, a * .6)); g.addColorStop(1, rgba(col, 0)); }
    ctx.fillStyle = g; ctx.beginPath();
    if (kind === 'hex') for (let i = 0; i < 6; i++) { const q = Math.PI / 3 * i + .26; ctx[i ? 'lineTo' : 'moveTo'](x + r * Math.cos(q), y + r * Math.sin(q)); }
    else ctx.arc(x, y, r, 0, 2 * Math.PI);
    ctx.fill();
  }
  register('local_lens_flare', {order: 82, draw(ctx, p, s) {
    const {W, H} = s, t = s.elapsed - (p.at ?? 0);
    if (t < 0) return;
    let B = keyedT(p.brightness, t, 1);
    if (p.flicker) B *= 1 - clamp(p.flicker) * .8 * (.5 + .5 * perlin(p.seed ?? 1)(t * 7, .5, .25));
    if (!(B > .001)) return;
    const k = H / 1080, lens = LENSES[p.lens ?? '50_300mm_zoom'], tint = tintOf(p.tint), pos = keyedT(p.position, t, [.3, .3]);
    const lx = pos[0] * W, ly = pos[1] * H, vx = W / 2 - lx, vy = H / 2 - ly, col = c => (tint ? mixC(hex(c), tint, .6) : hex(c));
    const warm = tint ?? [1, .78, .55], streak = clamp(keyedT(p.streak, t, 0));
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    // the glow round the light and its hot core
    let g = ctx.createRadialGradient(lx, ly, 0, lx, ly, lens.glow * k * Math.sqrt(B));
    g.addColorStop(0, rgba(warm, .55 * B)); g.addColorStop(.12, rgba(warm, .22 * B)); g.addColorStop(.4, rgba(warm, .06 * B)); g.addColorStop(1, rgba(warm, 0));
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    const cr = lens.core * k * Math.sqrt(B);
    g = ctx.createRadialGradient(lx, ly, 0, lx, ly, cr);
    g.addColorStop(0, rgba([1, 1, 1], Math.min(1, B))); g.addColorStop(.25, rgba([1, 1, 1], .8 * B)); g.addColorStop(.6, rgba(mixC([1, 1, 1], warm, .5), .25 * B)); g.addColorStop(1, rgba(warm, 0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(lx, ly, cr, 0, 2 * Math.PI); ctx.fill();
    // halo and rainbow ring round the light
    const [hr, hw, ha] = lens.halo, Rh = hr * H;
    g = ctx.createRadialGradient(lx, ly, Math.max(0, Rh - hw * H), lx, ly, Rh + hw * H);
    g.addColorStop(0, rgba(warm, 0)); g.addColorStop(.5, rgba(mixC(warm, [.6, .8, 1], .4), ha * B)); g.addColorStop(1, rgba(warm, 0));
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    const [rr, rw, ra] = lens.ring, Rr = rr * H;
    g = ctx.createRadialGradient(lx, ly, Math.max(0, Rr - rw * H), lx, ly, Rr + rw * H);
    const bow = tint ? [tint, tint, tint, tint, tint] : [[.9, .2, .9], [.2, .4, 1], [.2, 1, .4], [1, 1, .2], [1, .3, .1]];
    g.addColorStop(0, rgba(bow[0], 0)); bow.forEach((c, i) => g.addColorStop(.15 + .7 * i / 4, rgba(c, ra * B))); g.addColorStop(1, rgba(bow[4], 0));
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    // star rays (35mm prime)
    if (lens.rays) {
      const r = rng(p.seed ?? 1);
      for (let i = 0; i < lens.rays; i++) {
        const q = 2 * Math.PI * (i + .5 * r()) / lens.rays, len = (.25 + .45 * r()) * H * Math.sqrt(B), wd = (1.5 + 2.5 * r()) * k;
        ctx.setTransform(Math.cos(q), Math.sin(q), -Math.sin(q), Math.cos(q), lx, ly);
        const lg = ctx.createLinearGradient(0, 0, len, 0);
        lg.addColorStop(0, rgba(warm, .35 * B)); lg.addColorStop(1, rgba(warm, 0));
        ctx.fillStyle = lg; ctx.beginPath(); ctx.moveTo(0, -wd); ctx.lineTo(len, 0); ctx.lineTo(0, wd); ctx.fill();
      }
      ctx.resetTransform();
    }
    // ghosts along the line from the light through the centre
    for (const [gt, gr, ga, gc, kind] of lens.ghosts) blob(ctx, lx + vx * gt, ly + vy * gt, gr * k, col(gc), ga * B, kind);
    // the anamorphic streak: a flattened glow and a thin hot line through the light
    if (streak > 0) {
      const sc = tint ?? [.45, .65, 1], len = W * (.35 + .65 * streak);
      ctx.setTransform(len / (40 * k), 0, 0, 1, lx, ly);
      g = ctx.createRadialGradient(0, 0, 0, 0, 0, 40 * k);
      g.addColorStop(0, rgba(sc, .5 * streak * B)); g.addColorStop(.3, rgba(sc, .15 * streak * B)); g.addColorStop(1, rgba(sc, 0));
      ctx.fillStyle = g; ctx.fillRect(-40 * k, -40 * k, 80 * k, 80 * k);
      ctx.resetTransform();
      const lg = ctx.createLinearGradient(lx - len, 0, lx + len, 0);
      lg.addColorStop(0, rgba(sc, 0)); lg.addColorStop(.5, rgba(mixC(sc, [1, 1, 1], .6), .9 * streak * B)); lg.addColorStop(1, rgba(sc, 0));
      ctx.fillStyle = lg; ctx.fillRect(lx - len, ly - 1.5 * k, 2 * len, 3 * k);
    }
    ctx.restore();
  }});

  // local_light_rays: CC Light Rays / volumetric rays. Parts brighter than `threshold` streak away from `center` ([x, y]
  // fractions, keyframable): every pixel averages the bright picture along the line back toward the centre over
  // `length` (0..1) of the way, nearer samples weighing more, so rays fade out. `intensity` scales them, `tint` colours
  // them, `blend` add (default) or screen. Built at most 270 px high.
  register('local_light_rays', {order: 81, draw(ctx, p, s) {
    const {W, H} = s, t = s.elapsed - (p.at ?? 0);
    if (t < 0) return;
    const I = keyedT(p.intensity, t, 1), len = clamp(keyedT(p.length, t, .4));
    if (!(I > 0) || len < .005) return;
    const th = clamp(keyedT(p.threshold, t, .5)), c = keyedT(p.center, t, [.5, .5]);
    const sc = Math.min(1, 270 / H), w = Math.max(1, Math.round(W * sc)), h = Math.max(1, Math.round(H * sc));
    const src = bright(grab(ctx, w, h), w * h, th);
    if (!src) return;
    const cx = c[0] * w - .5, cy = c[1] * h - .5, far = Math.max(Math.hypot(cx, cy), Math.hypot(w - cx, cy), Math.hypot(cx, h - cy), Math.hypot(w - cx, h - cy));
    const N = Math.max(8, Math.min(192, Math.ceil(far * len / 1.2))), U = new Float32Array(N), Wt = new Float32Array(N);
    gauss(src, w, h, clamp(far * len / N * .4, .8, 4));   // fills between samples (wider when they lie far apart)
    let wsum = 0;
    for (let i = 0; i < N; i++) { U[i] = 1 - len * i / N; Wt[i] = 1 - i / N; wsum += Wt[i]; }
    for (let i = 0; i < N; i++) Wt[i] /= wsum;
    const out = new Float32Array(w * h * 3), du = len / N;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const dx = x - cx, dy = y - cy, o = (y * w + x) * 3;
      // a fixed per-pixel jitter of the samples along the ray (interleaved gradient noise): no stamped copies between them
      const j = du * ((52.9829189 * ((.06711056 * x + .00583715 * y) % 1)) % 1);
      let r = 0, g = 0, b = 0;
      for (let i = 0; i < N; i++) {
        const sx = cx + dx * (U[i] - j), sy = cy + dy * (U[i] - j);
        if (sx < 0 || sy < 0 || sx > w - 1 || sy > h - 1) continue;
        const x0 = Math.floor(sx), y0 = Math.floor(sy), x1 = Math.min(w - 1, x0 + 1), y1 = Math.min(h - 1, y0 + 1), ux = sx - x0, uy = sy - y0;
        const a = (y0 * w + x0) * 3, bb = (y0 * w + x1) * 3, cc = (y1 * w + x0) * 3, dd = (y1 * w + x1) * 3, wt = Wt[i];
        const w00 = (1 - ux) * (1 - uy) * wt, w10 = ux * (1 - uy) * wt, w01 = (1 - ux) * uy * wt, w11 = ux * uy * wt;
        r += src[a] * w00 + src[bb] * w10 + src[cc] * w01 + src[dd] * w11;
        g += src[a + 1] * w00 + src[bb + 1] * w10 + src[cc + 1] * w01 + src[dd + 1] * w11;
        b += src[a + 2] * w00 + src[bb + 2] * w10 + src[cc + 2] * w01 + src[dd + 2] * w11;
      }
      out[o] = r; out[o + 1] = g; out[o + 2] = b;
    }
    lay(ctx, s, out, w, h, I * 2, tintOf(p.tint), 1, p.blend);
  }});

  // local_light_sweep: CC Light Sweep, a shine passing over a logo or text. A band `width` px (at 1080) wide, tilted
  // `angle` degrees from vertical (0: an upright band moving left to right; 30 leans it like "/"), with `softness` 0..1
  // of it fading at the edges, `intensity` and `color`. Without `position` it crosses the whole frame over `d` seconds
  // from `at` (eased by `ease`, inout by default), entering and leaving clean; `position` (0..1, keyframable) instead
  // puts the band's centre at that fraction of the frame along the sweep. `reception` add (everywhere) or luma (scaled
  // by the picture's own brightness, so it shines on light text and logos and leaves dark ground alone).
  register('local_light_sweep', {order: 83, draw(ctx, p, s) {
    const {W, H} = s, t = s.elapsed - (p.at ?? 0);
    if (t < 0) return;
    const I = keyedT(p.intensity, t, 1);
    if (!(I > 0)) return;
    const k = H / 1080, a = keyedT(p.angle, t, 30) * Math.PI / 180, nx = Math.cos(a), ny = Math.sin(a);
    // at least 1.5 px each side so a thin band still lands on pixels without shimmering; a narrower one keeps its energy
    const hw0 = keyedT(p.width, t, 80) * k / 2, hw = Math.max(1.5, hw0), thin = Math.min(1, hw0 / hw), soft = clamp(keyedT(p.softness, t, .5));
    const proj = [0, W * nx, H * ny, W * nx + H * ny], lo = Math.min(...proj), hi = Math.max(...proj);
    let c;
    if (p.position != null) c = lo + keyedT(p.position, t, 0) * (hi - lo);
    else {
      const d = p.d ?? 1;
      if (t >= d) return;
      c = lo - hw + shape(clamp(t / d), p.ease ?? 'inout') * (hi - lo + 2 * hw);
    }
    const col = hex(p.color ?? '#ffffff'), g = ctx.createLinearGradient(nx * (c - hw), ny * (c - hw), nx * (c + hw), ny * (c + hw));
    const ramp = Math.max(.001, soft / 2), smooth = u => u * u * (3 - 2 * u);
    for (let i = 0; i <= 4; i++) {   // smoothstep shoulders, a flat core
      const u = i / 4, v = smooth(u);
      g.addColorStop(ramp * u, rgba(col, v * thin)); g.addColorStop(1 - ramp * u, rgba(col, v * thin));
    }
    const band = buffer(W, H), bx = band.getContext('2d');   // the band's light on black (adds nothing elsewhere)
    bx.fillStyle = '#000000'; bx.fillRect(0, 0, W, H); bx.fillStyle = g; bx.fillRect(0, 0, W, H);
    if (p.reception === 'luma') { bx.globalCompositeOperation = 'multiply'; bx.filter = 'grayscale(1)'; bx.drawImage(ctx.canvas, 0, 0); bx.filter = 'none'; }
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    for (let r = I; r > 0; r -= 1) { ctx.globalAlpha = Math.min(1, r); ctx.drawImage(band, 0, 0); }
    ctx.restore();
  }});
})();
