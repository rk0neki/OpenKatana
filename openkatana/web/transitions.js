/* OpenKatana two-shot transitions (audit F-STU-002). Independent implementations: A = outgoing shot rendered at this
   frame, B = incoming shot rendered at this frame (both full pipelines), p = progress through the window (0..1).
   The DEFAULTS literal below is JSON and is checked against openkatana/transitions.py by tests/test_audit_fixes.py. */
'use strict';
window.OpenKatanaTransitions = (() => {
  // DEFAULTS-BEGIN
  const DEFAULTS = {
    "dissolve": {"d": 0.5, "params": {"curve": "linear"}},
    "fade": {"d": 0.52, "params": {"color": "#000000", "out": 0.24, "hold": 0, "in": 0.28, "mode": "dip"}},
    "dip": {"d": 0.44, "params": {"color": "#000000", "out": 0.16, "hold": 0.04, "in": 0.24, "mode": "dip"}},
    "flash": {"d": null, "params": {"color": "#ffffff", "mode": "solid", "pre_frames": 0, "pre": [0.35, 0.65], "peak_frames": 1, "tau": 0.06, "cutoff": 0.05}},
    "glitch": {"d": 0.3, "params": {"streaks": "vertical", "split": 0.5, "intensity": 0.8, "seed": 0}},
    "lens": {"d": 0.43, "params": {"mode": "bulge", "split": 0.46, "strength": 0.6, "center": [0.5, 0.5], "radius": 1.0, "chroma": 0.04, "vignette": 0.25}},
    "light_leak": {"d": 0.7, "params": {"anchor": "right", "palette": "amber", "peak": 1.3, "size": 0.95, "blend": "add", "split": 0.45, "seed": 0}},
    "liquid": {"d": 0.6, "params": {"mode": "blob", "wobble": 0.04, "rim_width": 0.015, "rim_glow": 0.7, "rim_color": "#ffd9a0", "softness": 0.06, "ease": "outCubic", "seed": 0}},
    "luma": {"d": 0.6, "params": {"source": "A", "order": "dark_first", "softness": 0.08, "noise": 0.15, "seed": 0}},
    "pixel_sort": {"d": 0.37, "params": {"axis": "y", "dir": "down", "mask": "bright", "split": 0.5, "work_res": 540}},
    "push": {"d": 0.4, "params": {"dir": "left", "ease": "inOutCubic", "shutter": 0.5, "divider_width": 0, "divider_color": "#000000"}},
    "slide": {"d": 0.4, "params": {"dir": "left", "ease": "inOutCubic", "shutter": 0.5, "reveal": false}},
    "spin": {"d": 0.5, "params": {"dir": "cw", "out_angle": 120, "in_angle": -120, "scale": 1.4, "center": [0.5, 0.5], "split": 0.4, "shutter": 0.75}},
    "whip": {"d": 0.3, "params": {"dir": "right", "split": 0.5, "travel": 1.2, "shutter": 0.7, "blur_max": 0.4}},
    "wipe": {"d": 0.5, "params": {"shape": "linear", "dir": "rtl", "feather": 0.02, "ease": "inOutCubic", "mode": "open", "center": [0.5, 0.5], "count": 7, "stagger": 0.5}},
    "zoom": {"d": 0.4, "params": {"mode": "through", "out_scale": 3.0, "in_scale": 0.55, "center": [0.5, 0.5], "split": 0.55, "shutter": 0.5}},
    "datamosh": {"d": 0.5, "params": {"block": 16, "drift": 0.08, "split": 0.0, "seed": 0}}
  };
  // DEFAULTS-END
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const E = {
    linear: t => t, inQuad: t => t * t, outQuad: t => 1 - (1 - t) * (1 - t), inOutQuad: t => t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2,
    inCubic: t => t * t * t, outCubic: t => 1 - Math.pow(1 - t, 3), inOutCubic: t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
    inExpo: t => t <= 0 ? 0 : Math.pow(2, 10 * t - 10), outExpo: t => t >= 1 ? 1 : 1 - Math.pow(2, -10 * t),
    inOutExpo: t => t <= 0 ? 0 : t >= 1 ? 1 : t < .5 ? Math.pow(2, 20 * t - 10) / 2 : (2 - Math.pow(2, -20 * t + 10)) / 2,
    inOutSine: t => -(Math.cos(Math.PI * t) - 1) / 2,
  };
  const ease = (name, t) => (E[name] || E.linear)(clamp(t));
  const pool = new Map();
  function scratch(key, W, H) {
    let c = pool.get(key);
    if (!c || c.width !== W || c.height !== H) { c = document.createElement('canvas'); c.width = W; c.height = H; pool.set(key, c); }
    const x = c.getContext('2d', {willReadFrequently: true}); x.setTransform(1, 0, 0, 1, 0, 0); x.globalAlpha = 1; x.globalCompositeOperation = 'source-over'; x.filter = 'none'; x.clearRect(0, 0, W, H);
    return [c, x];
  }
  function frameWindow(spec, cut, fps) {
    const q = {...DEFAULTS[spec.type].params, ...spec};
    if (spec.type === 'flash') { const tail = Math.max(1, Math.ceil(q.tau * Math.log(1 / q.cutoff) * fps - 1e-9)); return [cut - q.pre_frames, cut + q.peak_frames + tail]; }
    const n = Math.max(2, Math.floor((spec.d ?? DEFAULTS[spec.type].d) * fps + .5)), align = spec.align ?? 'center';
    const w0 = align === 'center' ? cut - Math.floor(n / 2) : align === 'start' ? cut : cut - n;
    return [w0, w0 + n];
  }
  // average n draws of `img` under transforms produced by f(k) (k = 0..1): motion blur by running average
  function smear(ctx, img, n, f) {
    n = Math.max(1, Math.round(n));
    for (let i = 0; i < n; i++) { ctx.save(); ctx.globalAlpha = 1 / (i + 1); f(n === 1 ? .5 : i / (n - 1)); ctx.drawImage(img, 0, 0); ctx.restore(); }
  }
  function overlay(ctx, color, alpha, op = 'source-over') {
    if (alpha <= 0) return; ctx.save(); ctx.globalAlpha = clamp(alpha); ctx.globalCompositeOperation = op; ctx.fillStyle = color; ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height); ctx.restore();
  }
  function lumaField(img, w, h) {   // low-resolution luma (0..1) of a canvas
    const [c, x] = scratch('luma' + w + 'x' + h, w, h); x.drawImage(img, 0, 0, w, h);
    const d = x.getImageData(0, 0, w, h).data, out = new Float32Array(w * h);
    for (let i = 0; i < w * h; i++) out[i] = (d[i * 4] * .3 + d[i * 4 + 1] * .59 + d[i * 4 + 2] * .11) / 255;
    return out;
  }
  function boxBlur(f, w, h, passes = 2) {
    let a = f, b = new Float32Array(w * h);
    for (let p = 0; p < passes; p++) {
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { let s = 0, n = 0; for (let k = -2; k <= 2; k++) { const xx = x + k; if (xx >= 0 && xx < w) { s += a[y * w + xx]; n++; } } b[y * w + x] = s / n; }
      for (let x = 0; x < w; x++) for (let y = 0; y < h; y++) { let s = 0, n = 0; for (let k = -2; k <= 2; k++) { const yy = y + k; if (yy >= 0 && yy < h) { s += b[yy * w + x]; n++; } } a[y * w + x] = s / n; }
    }
    return a;
  }
  function fbm(noise, w, h, scale, seed, octaves = 3) {   // smooth fractal value noise on a w x h grid (0..1)
    const out = new Float32Array(w * h), sm = t => t * t * (3 - 2 * t);
    let total = 0;
    for (let o = 0; o < octaves; o++) {
      const s = scale * (1 << o), amp = 1 / (1 << o); total += amp;
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        const u = x / w * s, v = y / h * s * h / w, ix = Math.floor(u), iy = Math.floor(v), fx = sm(u - ix), fy = sm(v - iy);
        const n00 = noise(ix, iy, seed + o), n10 = noise(ix + 1, iy, seed + o), n01 = noise(ix, iy + 1, seed + o), n11 = noise(ix + 1, iy + 1, seed + o);
        out[y * w + x] += amp * ((n00 * (1 - fx) + n10 * fx) * (1 - fy) + (n01 * (1 - fx) + n11 * fx) * fy);
      }
    }
    for (let i = 0; i < out.length; i++) out[i] /= total;
    return out;
  }
  function rankNormalize(f) {   // map values to their rank fraction so thresholds reveal evenly over time
    const idx = Array.from(f.keys()).sort((i, j) => f[i] - f[j]), out = new Float32Array(f.length);
    idx.forEach((i, r) => { out[i] = r / Math.max(1, f.length - 1); });
    return out;
  }
  function maskedDraw(ctx, base, top, maskAlpha, mw, mh, W, H) {   // draw base, then top through a low-res alpha mask
    ctx.drawImage(base, 0, 0);
    const [mc, mx] = scratch('mask', mw, mh), md = mx.createImageData(mw, mh);
    for (let i = 0; i < mw * mh; i++) { md.data[i * 4 + 3] = Math.round(clamp(maskAlpha[i]) * 255); }
    mx.putImageData(md, 0, 0);
    const [tc, tx] = scratch('top', W, H); tx.drawImage(top, 0, 0); tx.globalCompositeOperation = 'destination-in'; tx.imageSmoothingQuality = 'high'; tx.drawImage(mc, 0, 0, W, H);
    ctx.drawImage(tc, 0, 0);
  }
  const PALETTES = {amber: [[255, 222, 150], [255, 128, 44], [255, 64, 24]], rose: [[255, 210, 220], [255, 90, 140], [200, 30, 90]],
                    teal: [[200, 255, 245], [60, 220, 210], [20, 120, 160]], white: [[255, 255, 255], [255, 245, 230], [255, 230, 210]]};
  const IMPL = {
    dissolve(ctx, A, B, p, q) { ctx.drawImage(A, 0, 0); ctx.globalAlpha = ease(q.curve, p); ctx.drawImage(B, 0, 0); },
    fade(ctx, A, B, p, q, info) {
      if (q.mode === 'in') { ctx.drawImage(B, 0, 0); overlay(ctx, q.color, 1 - p); return; }
      if (q.mode === 'out') { if (p < info.split) { ctx.drawImage(A, 0, 0); overlay(ctx, q.color, p / Math.max(1e-6, info.split)); } else ctx.drawImage(B, 0, 0); return; }
      const total = Math.max(1e-6, q.out + q.hold + q.in), o = q.out / total, h = q.hold / total;
      if (p < o) { ctx.drawImage(A, 0, 0); overlay(ctx, q.color, p / o); }
      else if (p < o + h) overlay(ctx, q.color, 1);
      else { ctx.drawImage(B, 0, 0); overlay(ctx, q.color, 1 - (p - o - h) / Math.max(1e-6, 1 - o - h)); }
    },
    dip(...a) { IMPL.fade(...a); },
    flash(ctx, A, B, p, q, info) {
      const rel = info.frame - info.cut; let base = B, a;
      if (rel < 0) { base = A; a = q.pre[0] + (q.pre[1] - q.pre[0]) * ((rel + q.pre_frames + .5) / Math.max(1, q.pre_frames)); }
      else if (rel < q.peak_frames) a = 1;
      else { a = Math.exp(-((rel - q.peak_frames + .5) / info.fps) / q.tau); if (a < q.cutoff) a = 0; }
      if (q.mode === 'exposure') { ctx.filter = `brightness(${1 + 3 * a})`; ctx.drawImage(base, 0, 0); ctx.filter = 'none'; return; }
      ctx.drawImage(base, 0, 0);
      if (q.mode === 'black') overlay(ctx, '#000000', a);
      else if (q.mode === 'invert') overlay(ctx, '#ffffff', a, 'difference');
      else overlay(ctx, q.color, a, q.mode === 'add' ? 'lighter' : q.mode === 'screen' ? 'screen' : 'source-over');
    },
    glitch(ctx, A, B, p, q, info) {
      const {W, H, noise} = info, vertical = q.streaks !== 'horizontal', n = 48, sp = Math.max(1e-3, q.split);
      ctx.drawImage(B, 0, 0);
      if (p < sp) {   // A drips away in columns (or rows), each with its own delay
        const cell = Math.ceil((vertical ? W : H) / n);
        for (let j = 0; j < n; j++) {
          const delay = noise(j, q.seed, 7) * .6, u = clamp((p / sp - delay) / (1 - delay)), off = ease('inQuad', u) * (vertical ? H : W) * (.6 + .4 * noise(j, q.seed, 8));
          if (vertical) ctx.drawImage(A, j * cell, 0, cell, H, j * cell, off, cell, H); else ctx.drawImage(A, 0, j * cell, W, cell, off, j * cell, W, cell);
        }
      }
      const env = clamp(1 - Math.abs(p - sp) / .22) * q.intensity;   // glitch states around the switch
      if (env > 0) {
        const [cc, cx] = scratch('glitch', W, H); cx.drawImage(ctx.canvas, 0, 0);
        for (let k = 0; k < 10; k++) {
          const y = Math.floor(noise(k, info.frame, q.seed + 11) * H), h = Math.ceil((.01 + .06 * noise(k, info.frame, q.seed + 12)) * H), dx = (noise(k, info.frame, q.seed + 13) - .5) * .25 * W * env;
          ctx.drawImage(cc, 0, y, W, h, dx, y, W, h);
        }
        const d = ctx.getImageData(0, 0, W, H), s = cx.getImageData(0, 0, W, H).data, shift = Math.round(.012 * W * env) * 4;
        for (let i = 0; i < d.data.length; i += 4) { if (i + shift < s.length) d.data[i] = s[i + shift]; if (i - shift >= 0) d.data[i + 2] = s[i - shift + 2]; }
        ctx.putImageData(d, 0, 0);
      }
    },
    lens(ctx, A, B, p, q, info) {
      const {W, H} = info, sp = clamp(q.split, .01, .99), src = p < sp ? A : B;
      const k = q.strength * (p < sp ? ease('inQuad', p / sp) : 1 - ease('outQuad', (p - sp) / (1 - sp)));
      const sx = src.getContext('2d').getImageData(0, 0, W, H).data, out = ctx.createImageData(W, H), o = out.data;
      const cx = q.center[0] * W, cy = q.center[1] * H, R = q.radius * Math.hypot(W, H) / 2;
      const mirror = (v, m) => { v = Math.abs(v); const period = 2 * (m - 1); v = v % period; return v > m - 1 ? period - v : v; };
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
        let dx = x - cx, dy = y - cy, r = Math.hypot(dx, dy) / R, s = 1, ang = 0;
        if (q.mode === 'bulge') s = r < 1 ? 1 - k * .7 * (1 - r) * (1 - r) : 1;
        else if (q.mode === 'pinch') s = r < 1 ? 1 + k * .7 * (1 - r) * (1 - r) : 1;
        else if (q.mode === 'barrel') s = 1 + k * .45 * r * r;
        else if (q.mode === 'pincushion') s = 1 / (1 + k * .45 * r * r);
        else ang = r < 1 ? k * Math.PI * (1 - r) * (1 - r) : 0;
        const ca = Math.cos(ang), sa = Math.sin(ang), rx = (dx * ca - dy * sa) * s, ry = (dx * sa + dy * ca) * s, vig = 1 - q.vignette * k * r * r, j = (y * W + x) * 4;
        for (let c = 0; c < 3; c++) {
          const cs = 1 + (c - 1) * q.chroma * k, xx = Math.round(mirror(cx + rx * cs, W)), yy = Math.round(mirror(cy + ry * cs, H));
          o[j + c] = sx[(yy * W + xx) * 4 + c] * vig;
        }
        o[j + 3] = 255;
      }
      ctx.putImageData(out, 0, 0);
    },
    light_leak(ctx, A, B, p, q, info) {
      const {W, H, noise} = info, sp = clamp(q.split, .01, .99);
      ctx.drawImage(p < sp ? A : B, 0, 0);
      const env = (p < sp ? ease('inQuad', p / sp) : 1 - ease('outQuad', (p - sp) / (1 - sp))) * q.peak;
      const anchor = {left: [-.05, .5], right: [1.05, .5], top: [.5, -.05], bottom: [.5, 1.05], center: [.5, .5]}[q.anchor];
      const jx = (noise(q.seed, 1, 21) - .5) * .2, jy = (noise(q.seed, 2, 21) - .5) * .3, R = q.size * Math.max(W, H) * (.6 + .4 * env);
      const g = ctx.createRadialGradient((anchor[0] + jx) * W, (anchor[1] + jy) * H, 0, (anchor[0] + jx) * W, (anchor[1] + jy) * H, R), pal = PALETTES[q.palette];
      g.addColorStop(0, `rgb(${pal[0]})`); g.addColorStop(.35, `rgb(${pal[1]})`); g.addColorStop(1, `rgba(${pal[2]},0)`);
      ctx.save(); ctx.globalCompositeOperation = q.blend === 'screen' ? 'screen' : 'lighter';
      for (let left = env; left > 0; left -= 1) { ctx.globalAlpha = Math.min(1, left); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H); }
      ctx.restore();
    },
    liquid(ctx, A, B, p, q, info) {
      const {W, H, noise} = info, mw = 128, mh = Math.max(8, Math.round(128 * H / W)), t = ease(q.ease, p);
      if (q.mode === 'melt') {   // glassy ripple while crossfading
        const amp = .02 * Math.sin(Math.PI * p) * W, rows = 6;
        for (const [img, alpha] of [[A, 1], [B, t]]) {
          ctx.save(); ctx.globalAlpha = alpha;
          for (let y = 0; y < H; y += rows) ctx.drawImage(img, 0, y, W, rows, Math.sin(y / H * 18 + p * 9 + q.seed) * amp, y, W, rows);
          ctx.restore();
        }
        return;
      }
      // blobs: blurred luma of A mixed with smooth clouds; the edge wobbles with a finer, frame-varying cloud layer
      const lum = boxBlur(lumaField(A, mw, mh), mw, mh, 3), clouds = fbm(noise, mw, mh, 3, q.seed + 31), wob = fbm(noise, mw, mh, 9, q.seed + 37 + info.frame, 2);
      let f = new Float32Array(mw * mh);
      for (let i = 0; i < f.length; i++) f[i] = .55 * lum[i] + .45 * clouds[i] + q.wobble * 2 * (wob[i] - .5);
      f = rankNormalize(boxBlur(f, mw, mh, 2));
      const soft = Math.max(1e-3, q.softness), th = -soft + t * (1 + 2 * soft), alpha = new Float32Array(f.length);
      for (let i = 0; i < f.length; i++) alpha[i] = clamp((th - f[i]) / soft);
      maskedDraw(ctx, A, B, alpha, mw, mh, W, H);
      if (q.rim_glow > 0 && p > 0 && p < 1) {   // glowing rim along the blob edge
        const rim = new Float32Array(f.length), wdt = Math.max(1e-3, q.rim_width * 8), env = clamp(Math.min(p, 1 - p) * 5);   // rim fades in/out at the window edges
        for (let i = 0; i < f.length; i++) rim[i] = clamp(1 - Math.abs(th - f[i]) / wdt) * q.rim_glow * env;
        const [rc, rx] = scratch('rim', mw, mh), rd = rx.createImageData(mw, mh), col = [1, 3, 5].map(i => parseInt(q.rim_color.slice(i, i + 2), 16));
        for (let i = 0; i < f.length; i++) { rd.data[i * 4] = col[0]; rd.data[i * 4 + 1] = col[1]; rd.data[i * 4 + 2] = col[2]; rd.data[i * 4 + 3] = Math.round(clamp(rim[i]) * 255); }
        rx.putImageData(rd, 0, 0); ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.filter = `blur(${Math.max(1, W / 400)}px)`; ctx.drawImage(rc, 0, 0, W, H); ctx.restore();
      }
    },
    luma(ctx, A, B, p, q, info) {
      const {W, H, noise} = info, mw = 160, mh = Math.max(8, Math.round(160 * H / W));
      // source noise = smooth fractal clouds; `noise` breaks up flat luma areas with the same clouds
      let f = q.source === 'noise' ? fbm(noise, mw, mh, 4, q.seed + 41) : lumaField(q.source === 'B' ? B : A, mw, mh);
      if (q.order === 'light_first') f = f.map(v => 1 - v);
      if (q.noise > 0 && q.source !== 'noise') { const c = fbm(noise, mw, mh, 6, q.seed + 42); f = f.map((v, i) => v + q.noise * (c[i] - .5)); }
      let lo = Infinity, hi = -Infinity; for (const v of f) { if (v < lo) lo = v; if (v > hi) hi = v; }
      const soft = Math.max(1e-3, q.softness) * (hi - lo || 1), th = lo - soft + p * (hi - lo + 2 * soft);
      maskedDraw(ctx, A, B, f.map(v => clamp((th - v) / soft)), mw, mh, W, H);
    },
    pixel_sort(ctx, A, B, p, q, info) {
      const {W, H} = info, sp = clamp(q.split, .01, .99), src = p < sp ? A : B, amount = p < sp ? p / sp : 1 - (p - sp) / (1 - sp);
      ctx.drawImage(src, 0, 0); if (amount <= 0) return;
      const scale = Math.min(1, q.work_res / H), w = Math.max(1, Math.round(W * scale)), h = Math.max(1, Math.round(H * scale));
      const [c, x] = scratch('sort', w, h); x.drawImage(src, 0, 0, w, h);
      const img = x.getImageData(0, 0, w, h), d = img.data, bright = i => d[i] * .3 + d[i + 1] * .59 + d[i + 2] * .11;
      const lines = q.axis === 'y' ? w : h, len = q.axis === 'y' ? h : w, at = (l, k) => (q.axis === 'y' ? k * w + l : l * w + k) * 4;
      const thr = 255 * (1 - amount);
      for (let l = 0; l < lines; l++) {
        let k = 0;
        while (k < len) {
          const keep = i => q.mask === 'all' ? true : q.mask === 'dark' ? bright(i) < 255 - thr : bright(i) > thr;
          while (k < len && !keep(at(l, k))) k++;
          const start = k; while (k < len && keep(at(l, k))) k++;
          if (k - start > 1) {
            const run = []; for (let m = start; m < k; m++) { const i = at(l, m); run.push([bright(i), d[i], d[i + 1], d[i + 2]]); }
            run.sort((a, b) => q.dir === 'down' ? a[0] - b[0] : b[0] - a[0]);
            run.forEach((v, m) => { const i = at(l, start + m); d[i] = v[1]; d[i + 1] = v[2]; d[i + 2] = v[3]; });
          }
        }
      }
      x.putImageData(img, 0, 0); ctx.imageSmoothingEnabled = true; ctx.drawImage(c, 0, 0, W, H);
    },
    push(ctx, A, B, p, q, info) {
      const {W, H} = info, e = ease(q.ease, p), v = Math.abs(ease(q.ease, p + .5 / info.n) - ease(q.ease, p - .5 / info.n));
      const [ux, uy] = {left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1]}[q.dir], blur = q.shutter * v, n = 1 + Math.ceil(blur * 24);
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
      for (const [img, base] of [[A, 0], [B, -1]]) smear(ctx, img, n, k => { const o = e + base + (k - .5) * blur; ctx.translate(ux * o * W, uy * o * H); });
      if (q.divider_width > 0) {   // bar on the seam between the two frames
        const dw = q.divider_width * (ux ? W : H), seam = (ux || uy) > 0 ? e : 1 - e; ctx.fillStyle = q.divider_color;
        if (ux) ctx.fillRect(seam * W - dw / 2, 0, dw, H); else ctx.fillRect(0, seam * H - dw / 2, W, dw);
      }
    },
    slide(ctx, A, B, p, q, info) {
      const {W, H} = info, e = ease(q.ease, p), v = Math.abs(ease(q.ease, p + .5 / info.n) - ease(q.ease, p - .5 / info.n));
      const [ux, uy] = {left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1]}[q.dir], blur = q.shutter * v, n = 1 + Math.ceil(blur * 24);
      if (!q.reveal) { ctx.drawImage(A, 0, 0); smear(ctx, B, n, k => { const o = 1 - e + (k - .5) * blur; ctx.translate(-ux * o * W, -uy * o * H); }); }
      else { ctx.drawImage(B, 0, 0); smear(ctx, A, n, k => { const o = e + (k - .5) * blur; ctx.translate(ux * o * W, uy * o * H); }); }
    },
    spin(ctx, A, B, p, q, info) {
      const {W, H} = info, sp = clamp(q.split, .01, .99), sign = q.dir === 'ccw' ? -1 : 1, cx = q.center[0] * W, cy = q.center[1] * H;
      const state = t => t < sp ? [A, q.out_angle * ease('inCubic', t / sp), 1 + (q.scale - 1) * ease('inCubic', t / sp)]
                                 : [B, q.in_angle * (1 - ease('outCubic', (t - sp) / (1 - sp))), q.scale + (1 - q.scale) * ease('outCubic', (t - sp) / (1 - sp))];
      const [img, ang, sc] = state(p), [, ang2] = state(clamp(p + 1 / info.n)), dAng = (ang2 - ang) * q.shutter * (img === state(clamp(p + 1 / info.n))[0] ? 1 : 0);
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
      smear(ctx, img, 1 + Math.ceil(Math.abs(dAng) / 2), k => { ctx.translate(cx, cy); ctx.rotate(sign * (ang + (k - .5) * dAng) * Math.PI / 180); ctx.scale(sc, sc); ctx.translate(-cx, -cy); });
    },
    whip(ctx, A, B, p, q, info) {
      const {W, H} = info, sp = clamp(q.split, .01, .99), [ux, uy] = {right: [1, 0], left: [-1, 0], up: [0, -1], down: [0, 1]}[q.dir];
      let img, off, blur;
      if (p < sp) { const u = ease('inExpo', p / sp); img = A; off = -q.travel * u; blur = q.blur_max * u; }
      else { const u = 1 - ease('outExpo', (p - sp) / (1 - sp)); img = B; off = q.travel * u; blur = q.blur_max * u; }
      // every smear sample is drawn as two wrapped tiles, so any travel keeps the frame filled
      const n = 1 + Math.ceil(blur * 40 * q.shutter), wrapTo = (v, m) => ((v % m) + m) % m;
      for (let i = 0; i < n; i++) {
        const k = n === 1 ? .5 : i / (n - 1), o = off + (k - .5) * blur * q.shutter;
        const x = ux ? wrapTo(ux * o * W, W) : 0, y = uy ? wrapTo(uy * o * H, H) : 0;
        ctx.save(); ctx.globalAlpha = 1 / (i + 1); ctx.drawImage(img, x, y); ctx.drawImage(img, ux ? x - W : 0, uy ? y - H : 0); ctx.restore();
      }
    },
    wipe(ctx, A, B, p, q, info) {
      // open: the shape grows and shows B inside it; close: the shape shrinks around A and B shows outside it
      const t = q.mode === 'close' ? 1 - p : p, e = ease(q.ease, t), [mc, mx] = scratch('wipe', info.W, info.H), {W, H} = info;
      const cx = q.center[0] * W, cy = q.center[1] * H, R = Math.hypot(W, H);
      mx.fillStyle = '#fff'; mx.beginPath();
      if (q.shape === 'linear') { const r = {rtl: [W * (1 - e), 0, W * e + 1, H], ltr: [0, 0, W * e, H], ttb: [0, 0, W, H * e], btt: [0, H * (1 - e), W, H * e + 1]}[q.dir]; mx.rect(...r); }
      else if (q.shape === 'circle') mx.arc(cx, cy, e * R / 2 * 1.02, 0, Math.PI * 2);
      else if (q.shape === 'diamond') { const r = e * (W + H) / 2; mx.moveTo(cx, cy - r); mx.lineTo(cx + r, cy); mx.lineTo(cx, cy + r); mx.lineTo(cx - r, cy); mx.closePath(); }
      else if (q.shape === 'box') { const hw = e * W / 2 * 1.01, hh = e * H / 2 * 1.01; mx.rect(cx - hw, cy - hh, 2 * hw, 2 * hh); }
      else if (q.shape === 'star') { const r = e * R * .9; for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, rr = i % 2 ? r * .45 : r; mx.lineTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr); } mx.closePath(); }
      else if (q.shape === 'clock') { mx.moveTo(cx, cy); mx.arc(cx, cy, R, -Math.PI / 2, -Math.PI / 2 + e * Math.PI * 2); mx.closePath(); }
      else if (q.shape === 'barn') { mx.rect(cx - e * W / 2, 0, e * W, H); }
      else { const sw = W / q.count; for (let i = 0; i < q.count; i++) { const delay = (i / Math.max(1, q.count - 1)) * q.stagger, u = clamp((t - delay) / Math.max(1e-3, 1 - q.stagger)); mx.rect(i * sw, 0, sw + .5, H * ease(q.ease, u)); } }
      mx.fill();
      if (q.mode === 'close') { mx.globalCompositeOperation = 'xor'; mx.fillRect(0, 0, W, H); }
      const [fc, fx] = scratch('wipe-f', W, H);
      if (q.feather > 0) fx.filter = `blur(${q.feather * Math.min(W, H) / 2}px)`; fx.drawImage(mc, 0, 0);
      const [tc, tx] = scratch('wipe-t', W, H); tx.drawImage(B, 0, 0); tx.globalCompositeOperation = 'destination-in'; tx.drawImage(fc, 0, 0);
      ctx.drawImage(A, 0, 0); ctx.drawImage(tc, 0, 0);
    },
    zoom(ctx, A, B, p, q, info) {
      const {W, H} = info, sp = clamp(q.split, .01, .99), cx = q.center[0] * W, cy = q.center[1] * H;
      const state = t => t < sp ? [A, 1 + (q.out_scale - 1) * ease('inExpo', t / sp)]
        : [B, q.mode === 'punch' ? q.out_scale + (1 - q.out_scale) * ease('outExpo', (t - sp) / (1 - sp)) : q.in_scale + (1 - q.in_scale) * ease('outExpo', (t - sp) / (1 - sp))];
      const [img, s] = state(p), [img2, s2] = state(clamp(p + 1 / info.n)), ds = img === img2 ? (s2 - s) * q.shutter : 0;
      if (s < 1) { ctx.save(); ctx.filter = `blur(${W / 60}px)`; ctx.translate(cx, cy); ctx.scale(1.15, 1.15); ctx.translate(-cx, -cy); ctx.drawImage(img, 0, 0); ctx.restore(); }
      smear(ctx, img, 1 + Math.ceil(Math.abs(ds) * 12), k => { const sc = s + (k - .5) * ds; ctx.translate(cx, cy); ctx.scale(sc, sc); ctx.translate(-cx, -cy); });
    },
    datamosh(ctx, A, B, p, q, info) {   // approximation: no codec motion vectors; blocks of A drift, then refresh to B
      const {W, H, noise} = info, b = Math.max(2, q.block), nx = Math.ceil(W / b), ny = Math.ceil(H / b);
      ctx.drawImage(B, 0, 0);
      for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
        const refresh = q.split + (1 - q.split) * Math.sqrt(noise(i, j, q.seed + 51));
        if (p >= refresh) continue;
        const ang = noise(i, j, q.seed + 52) * Math.PI * 2, dist = q.drift * Math.min(W, H) * p * (.5 + noise(i, j, q.seed + 53));
        ctx.drawImage(A, i * b, j * b, b, b, i * b + Math.cos(ang) * dist, j * b + Math.sin(ang) * dist, b, b);
      }
    },
  };
  function draw(ctx, spec, A, B, p, info) {
    const q = {...DEFAULTS[spec.type].params, ...spec};
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none';
    ctx.clearRect(0, 0, info.W, info.H);
    try { IMPL[spec.type](ctx, A, B, clamp(p), q, info); } finally { ctx.restore(); }
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalCompositeOperation = 'destination-over'; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, info.W, info.H); ctx.restore();
  }
  return {DEFAULTS, frameWindow, draw};
})();
