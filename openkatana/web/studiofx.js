/* Plate grading and effects for OpenKatana Studio looks. */
'use strict';
window.OpenKatanaStudio = (() => {
  const clamp = (x, a = 0, b = 1) => x < a ? a : x > b ? b : x;
  const pool = new Map();
  function scratch(key, W, H) {
    let c = pool.get(key);
    if (!c || c.width !== W || c.height !== H) { c = document.createElement('canvas'); c.width = W; c.height = H; pool.set(key, c); }
    const x = c.getContext('2d', {willReadFrequently: true}); x.setTransform(1, 0, 0, 1, 0, 0); x.globalAlpha = 1; x.globalCompositeOperation = 'source-over'; x.filter = 'none'; x.clearRect(0, 0, W, H);
    return [c, x];
  }
  function copyOf(ctx, key = 'copy') { const {width: W, height: H} = ctx.canvas, [c, x] = scratch(key, W, H); x.drawImage(ctx.canvas, 0, 0); return c; }
  function blurred(src, px, key = 'blur') {
    const [c, x] = scratch(key, src.width, src.height);
    if (px <= .01) { x.drawImage(src, 0, 0); return c; }
    // edge-extended blur: draw the source slightly enlarged under itself so edges do not darken
    x.filter = `blur(${px}px)`; x.drawImage(src, -px * 2, -px * 2, src.width + px * 4, src.height + px * 4); x.drawImage(src, 0, 0); x.filter = 'none';
    return c;
  }
  const hexRGB = c => c[0] === '#' ? [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16)) : c.slice(c.indexOf('(') + 1).split(',').slice(0, 3).map(Number);
  const lin = v => Math.pow(v / 255, 2.2), gam = v => 255 * Math.pow(clamp(v), 1 / 2.2);
  const LUMA = (r, g, b) => .2126 * r + .7152 * g + .0722 * b;

  // ---------------------------------------------------------------- grade
  function grade(ctx, g) {
    const {width: W, height: H} = ctx.canvas, img = ctx.getImageData(0, 0, W, H), a = img.data;
    let lo = 0, hi = 1;
    if (g.auto) {   // auto levels from the 1st / 99th luma percentiles, mixed by `auto`
      const hist = new Uint32Array(256); let n = 0;
      for (let i = 0; i < a.length; i += 16) { hist[Math.round(LUMA(a[i], a[i + 1], a[i + 2]))]++; n++; }
      let acc = 0, p1 = 0, p99 = 255;
      for (let v = 0; v < 256; v++) { acc += hist[v]; if (acc < n * .01) p1 = v; if (acc < n * .99) p99 = v; }
      lo = g.auto * p1 / 255; hi = 1 - g.auto * (1 - Math.max(p1 + 8, p99) / 255);
    }
    const mult = g.mult ?? [1, 1, 1], temp = g.temp ?? 0, tint = g.tint ?? 0, sat = g.sat ?? 1, con = g.contrast ?? 1, gm = g.gamma ?? 1;
    const black = g.black ?? 0, fade = g.fade ?? 0, gain = g.gain ?? 1, mono = g.mono ?? 0, ev = Math.pow(2, g.exposure ?? 0);
    const wb = [mult[0] * (1 + .22 * temp) * (1 + .06 * tint), mult[1] * (1 - .16 * tint), mult[2] * (1 - .22 * temp) * (1 + .06 * tint)];
    const split = g.split, sh = split ? split[0].map(v => (v - .5) * 2) : null, hl = split ? split[1].map(v => (v - .5) * 2) : null, sk = split ? split[2] ?? .5 : 0;
    for (let i = 0; i < a.length; i += 4) {
      let r = a[i] / 255, gg = a[i + 1] / 255, b = a[i + 2] / 255;
      if (lo !== 0 || hi !== 1) { const s = 1 / Math.max(1e-3, hi - lo); r = (r - lo) * s; gg = (gg - lo) * s; b = (b - lo) * s; }
      // white balance and exposure in linear light
      r = Math.pow(clamp(r), 2.2) * wb[0] * ev; gg = Math.pow(clamp(gg), 2.2) * wb[1] * ev; b = Math.pow(clamp(b), 2.2) * wb[2] * ev;
      r = Math.pow(clamp(r), 1 / 2.2); gg = Math.pow(clamp(gg), 1 / 2.2); b = Math.pow(clamp(b), 1 / 2.2);
      let L = LUMA(r, gg, b);
      const s2 = sat * (1 - mono);
      r = L + (r - L) * s2; gg = L + (gg - L) * s2; b = L + (b - L) * s2;
      r = (r - .5) * con + .5; gg = (gg - .5) * con + .5; b = (b - .5) * con + .5;
      if (gm !== 1) { r = Math.pow(clamp(r), gm); gg = Math.pow(clamp(gg), gm); b = Math.pow(clamp(b), gm); }
      if (black) { r = (r - black) / (1 - black); gg = (gg - black) / (1 - black); b = (b - black) / (1 - black); }
      if (split) {
        L = clamp(LUMA(r, gg, b)); const ws = (1 - L) * (1 - L) * sk * .25, wh = L * L * sk * .25;
        r += sh[0] * ws + hl[0] * wh; gg += sh[1] * ws + hl[1] * wh; b += sh[2] * ws + hl[2] * wh;
      }
      r = fade + clamp(r) * gain * (1 - fade); gg = fade + clamp(gg) * gain * (1 - fade); b = fade + clamp(b) * gain * (1 - fade);
      a[i] = 255 * clamp(r); a[i + 1] = 255 * clamp(gg); a[i + 2] = 255 * clamp(b);
    }
    ctx.putImageData(img, 0, 0);
  }

  // ---------------------------------------------------------------- helpers for effects
  function pixels(ctx, fn) { const {width: W, height: H} = ctx.canvas, img = ctx.getImageData(0, 0, W, H); fn(img.data, W, H); ctx.putImageData(img, 0, 0); }
  function smear(ctx, src, n, place) {   // running average of n placements of src
    for (let i = 0; i < n; i++) { ctx.save(); ctx.globalAlpha = 1 / (i + 1); place(n === 1 ? .5 : i / (n - 1)); ctx.drawImage(src, 0, 0); ctx.restore(); }
  }
  function shiftChannels(ctx, dxR, dyR, dxB, dyB) {
    const {width: W, height: H} = ctx.canvas, src = ctx.getImageData(0, 0, W, H).data;
    const mirror = (v, m) => { v = Math.abs(v); const period = 2 * (m - 1); v %= period; return v > m - 1 ? period - v : v; };
    pixels(ctx, a => {
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
        const j = (y * W + x) * 4;
        a[j] = src[(Math.round(mirror(y - dyR, H)) * W + Math.round(mirror(x - dxR, W))) * 4];
        a[j + 2] = src[(Math.round(mirror(y - dyB, H)) * W + Math.round(mirror(x - dxB, W))) * 4 + 2];
      }
    });
  }
  function highlights(ctx, thr, knee, tint, key = 'hl') {
    const {width: W, height: H} = ctx.canvas, [c, x] = scratch(key, W, H); x.drawImage(ctx.canvas, 0, 0);
    const img = x.getImageData(0, 0, W, H), a = img.data, t = tint ? hexRGB(tint) : null;
    for (let i = 0; i < a.length; i += 4) {
      const L = LUMA(a[i], a[i + 1], a[i + 2]) / 255, w = clamp((L - thr) / Math.max(1e-3, knee));
      if (t) { a[i] = (a[i] * .4 + t[0] * .6) * w; a[i + 1] = (a[i + 1] * .4 + t[1] * .6) * w; a[i + 2] = (a[i + 2] * .4 + t[2] * .6) * w; }
      else { a[i] *= w; a[i + 1] *= w; a[i + 2] *= w; }
      a[i + 3] = 255;
    }
    x.putImageData(img, 0, 0); return c;
  }
  const LEAK = {amber: [[255, 214, 140], [255, 120, 40], [200, 50, 10]], magenta: [[255, 200, 240], [240, 70, 180], [120, 20, 120]],
                gold: [[255, 236, 170], [255, 180, 60], [180, 100, 10]], peach: [[255, 225, 200], [255, 150, 120], [200, 80, 70]],
                cool: [[220, 240, 255], [90, 170, 255], [30, 60, 160]]};
  const BAYER4 = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];

  // ---------------------------------------------------------------- effects
  const FX = {
    bleach(ctx, p) { ctx.save(); ctx.globalAlpha = clamp(p.a ?? .5); ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height); ctx.restore(); },
    bloom(ctx, p, s) {
      const hl = highlights(ctx, p.thr ?? .7, .08, null), b = blurred(hl, (p.r ?? 30) * s.W / 1080, 'bloom');
      ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = clamp(p.strength ?? .6, 0, 2); ctx.drawImage(b, 0, 0); ctx.restore();
    },
    blur(ctx, p, s) { const b = blurred(copyOf(ctx), (p.r ?? 6) * s.W / 1080); ctx.drawImage(b, 0, 0); },
    chroma(ctx, p, s) { const px = (p.px ?? 6) * s.W / 1080; p.vertical ? shiftChannels(ctx, 0, px, 0, -px) : shiftChannels(ctx, px, 0, -px, 0); },
    clarity(ctx, p, s) {
      const base = copyOf(ctx, 'clar'), b = blurred(base, (p.radius ?? .02) * Math.min(s.W, s.H), 'clarb');
      const bd = b.getContext('2d').getImageData(0, 0, s.W, s.H).data, amt = p.amount ?? .4;
      pixels(ctx, a => {
        for (let i = 0; i < a.length; i += 4) {
          const L = LUMA(a[i], a[i + 1], a[i + 2]) / 255, Lb = LUMA(bd[i], bd[i + 1], bd[i + 2]) / 255, w = 4 * L * (1 - L);
          const k = L > 1e-3 ? clamp(L + amt * (L - Lb) * w * 2, 0, 1) / L : 1;
          const m = Math.max(a[i], a[i + 1], a[i + 2]) || 1, cap = 255 / m;   // never push a channel past white
          const f = Math.min(k, cap); a[i] *= f; a[i + 1] *= f; a[i + 2] *= f;
        }
      });
    },
    contour_glow(ctx, p, s) {
      if (!s.mask) return;
      const {W, H} = s, m = Math.min(W, H), [c, x] = scratch('cg', W, H);
      x.filter = `blur(${(p.radius ?? .03) * m}px)`; x.drawImage(s.mask, 0, 0); x.filter = 'none';
      x.globalCompositeOperation = 'source-in'; x.fillStyle = p.color ?? '#8a5cff'; x.fillRect(0, 0, W, H);
      x.globalCompositeOperation = 'destination-out'; x.globalAlpha = 1 - (p.inner ?? .15); x.drawImage(s.mask, 0, 0);
      ctx.save(); ctx.globalCompositeOperation = (p.blend ?? 'screen') === 'add' ? 'lighter' : 'screen'; ctx.globalAlpha = clamp(p.strength ?? .8, 0, 2); ctx.drawImage(c, 0, 0); ctx.restore();
    },
    datamosh(ctx, p, s) {   // approximation: blocks of the frame drift along seeded vectors that grow over the shot
      const src = copyOf(ctx, 'dm'), b = Math.max(2, Math.round((p.block ?? 16) * s.W / 1080)), u = clamp(s.elapsed / Math.max(1e-3, s.duration));
      const seed = p.seed ?? 0, drift = (p.drift ?? .08) * Math.min(s.W, s.H) * u;
      for (let y = 0; y < s.H; y += b) for (let x = 0; x < s.W; x += b) {
        if (s.hash(x, y, seed + 7) > (p.share ?? .5)) continue;
        const ang = s.hash(x, y, seed + 8) * Math.PI * 2, d = drift * (.5 + s.hash(x, y, seed + 9));
        ctx.drawImage(src, x, y, b, b, x + Math.cos(ang) * d, y + Math.sin(ang) * d, b, b);
      }
    },
    defocus(ctx, p, s) {
      const base = copyOf(ctx, 'df'), r = (p.amount ?? .012) * Math.min(s.W, s.H);
      const hl = highlights(ctx, .75, .2, null, 'dfh'), b = blurred(base, r, 'dfb'), bh = blurred(hl, r * .8, 'dfbh');
      ctx.drawImage(b, 0, 0); ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = clamp(((p.highlights ?? 1.5) - 1) * .6, 0, 1); ctx.drawImage(bh, 0, 0); ctx.restore();
    },
    dirblur(ctx, p, s) {
      const src = copyOf(ctx, 'db'), L = (p.len ?? .05) * s.W, a = (p.angle ?? 0) * Math.PI / 180, n = Math.max(2, Math.min(24, Math.ceil(L / 2)));
      smear(ctx, src, n, k => ctx.translate(Math.cos(a) * L * (k - .5), Math.sin(a) * L * (k - .5)));
    },
    duotone(ctx, p) {
      const sh = hexRGB(p.shadows ?? '#1c0e2f'), hl = hexRGB(p.highlights ?? '#ffd27a'), amt = clamp(p.amount ?? 1);
      pixels(ctx, a => { for (let i = 0; i < a.length; i += 4) { const L = LUMA(a[i], a[i + 1], a[i + 2]) / 255; for (let c = 0; c < 3; c++) a[i + c] += (sh[c] + (hl[c] - sh[c]) * L - a[i + c]) * amt; } });
    },
    exposure(ctx, p) { const k = Math.pow(2, p.ev ?? 0); pixels(ctx, a => { for (let i = 0; i < a.length; i += 4) for (let c = 0; c < 3; c++) a[i + c] = gam(lin(a[i + c]) * k); }); },
    film_overlay(ctx, p, s) {
      const lvl = p.level ?? 2, seed = p.seed ?? 0, f = s.frame;
      const weave = (p.weave ?? [0, .6, 1.2, 2][lvl]) * s.W / 1080;
      if (weave > 0) { const src = copyOf(ctx, 'fo'); ctx.save(); ctx.translate((s.hash(f, 1, seed) - .5) * weave * 2, (s.hash(f, 2, seed) - .5) * weave * 2); ctx.drawImage(src, 0, 0); ctx.restore(); }
      FX.grain(ctx, {sigma: p.grain ?? [0, .02, .035, .05][lvl], size: 1.8, mono: true, seed}, s);
      const flick = (p.flicker ?? [0, .015, .03, .05][lvl]) * (s.hash(f, 3, seed) - .5) * 2;
      if (flick) { ctx.save(); ctx.globalAlpha = Math.abs(flick); ctx.fillStyle = flick > 0 ? '#ffffff' : '#000000'; ctx.fillRect(0, 0, s.W, s.H); ctx.restore(); }
      ctx.save(); ctx.fillStyle = 'rgba(250,250,240,0.85)'; ctx.strokeStyle = 'rgba(20,20,20,0.6)';
      const dust = p.dust ?? [0, 3, 7, 14][lvl];
      for (let i = 0; i < dust; i++) { ctx.fillStyle = s.hash(f, i, seed + 5) > .5 ? 'rgba(250,250,240,0.8)' : 'rgba(10,10,10,0.7)'; ctx.beginPath(); ctx.arc(s.hash(f, i, seed + 6) * s.W, s.hash(f, i, seed + 7) * s.H, .5 + s.hash(f, i, seed + 8) * 2 * s.W / 1080, 0, Math.PI * 2); ctx.fill(); }
      if ((p.scratch ?? [0, 0, 1, 2][lvl]) && s.hash(Math.floor(f / 3), 9, seed) < .5) { const x = s.hash(Math.floor(f / 3), 10, seed) * s.W; ctx.lineWidth = Math.max(1, s.W / 1080); ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x + (s.hash(f, 11, seed) - .5) * 6, s.H); ctx.stroke(); }
      ctx.restore();
    },
    glow(ctx, p, s) {
      const hl = highlights(ctx, p.threshold ?? .72, p.knee ?? .1, p.tint ?? null), m = Math.min(s.W, s.H);
      ctx.save(); ctx.globalCompositeOperation = (p.blend ?? 'screen') === 'add' ? 'lighter' : 'screen';
      const radii = p.radii ?? [.004, .015, .04, .1], weights = p.weights ?? [.35, .3, .2, .15];
      radii.forEach((r, i) => { ctx.globalAlpha = clamp((p.strength ?? .3) * weights[i] * 2.5, 0, 1); ctx.drawImage(blurred(hl, r * m, 'gl' + i), 0, 0); });
      ctx.restore();
    },
    grain(ctx, p, s) {
      const sigma = (p.sigma ?? .035) * 255, size = Math.max(1, (p.size ?? 2) * s.W / 1080), seed = (p.seed ?? 0) + s.frame * 131, mono = p.mono ?? false;
      pixels(ctx, (a, W, H) => {
        const cw = Math.ceil(W / size), ch = Math.ceil(H / size), planes = mono ? 1 : 3, cell = new Float32Array(cw * ch * planes);
        for (let i = 0; i < cw * ch; i++) for (let k = 0; k < planes; k++)   // one triangular-noise value per grain cell
          cell[i * planes + k] = s.hash(i % cw, Math.floor(i / cw), seed + 2 * k) + s.hash(i % cw, Math.floor(i / cw), seed + 2 * k + 1) - 1;
        for (let y = 0; y < H; y++) { const row = Math.floor(y / size) * cw; for (let x = 0; x < W; x++) {
          const j = (y * W + x) * 4, L = LUMA(a[j], a[j + 1], a[j + 2]) / 255, w = (.35 + 2.6 * L * (1 - L)) * sigma, c = (row + Math.floor(x / size)) * planes;
          a[j] += cell[c] * w; a[j + 1] += cell[c + (planes > 1 ? 1 : 0)] * w; a[j + 2] += cell[c + (planes > 1 ? 2 : 0)] * w;
        } }
      });
    },
    invert(ctx, p) { const src = copyOf(ctx, 'inv'); ctx.save(); ctx.filter = 'invert(1)'; ctx.globalAlpha = clamp(p.amt ?? 1); ctx.drawImage(src, 0, 0); ctx.restore(); },
    lens_warp(ctx, p, s) {
      const {W, H} = s, src = ctx.getImageData(0, 0, W, H).data, k = p.strength ?? .5, mode = p.mode ?? 'bulge';
      const cx = (p.center ?? [.5, .5])[0] * W, cy = (p.center ?? [.5, .5])[1] * H, R = (p.radius ?? 1) * Math.hypot(W, H) / 2, chroma = p.chroma ?? 0, vig = p.vignette ?? 0;
      const mirror = (v, m) => { v = Math.abs(v); const period = 2 * (m - 1); v %= period; return v > m - 1 ? period - v : v; };
      pixels(ctx, a => {
        for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
          const dx = x - cx, dy = y - cy, r = Math.hypot(dx, dy) / R; let sc = 1, ang = 0;
          if (mode === 'bulge') sc = r < 1 ? 1 - k * .7 * (1 - r) * (1 - r) : 1;
          else if (mode === 'pinch') sc = r < 1 ? 1 + k * .7 * (1 - r) * (1 - r) : 1;
          else if (mode === 'barrel') sc = 1 + k * .45 * r * r;
          else if (mode === 'pincushion') sc = 1 / (1 + k * .45 * r * r);
          else if (mode === 'sphere') sc = r < 1 ? Math.sqrt(1 - Math.min(.99, r * r * k)) : 1;
          else ang = r < 1 ? k * Math.PI * (1 - r) * (1 - r) * ((p.dir ?? 'ccw') === 'cw' ? -1 : 1) : 0;
          const ca = Math.cos(ang), sa = Math.sin(ang), rx = (dx * ca - dy * sa) * sc, ry = (dx * sa + dy * ca) * sc, v = 1 - vig * r * r, j = (y * W + x) * 4;
          for (let c = 0; c < 3; c++) { const cs = 1 + (c - 1) * chroma, xx = Math.round(mirror(cx + rx * cs, W)), yy = Math.round(mirror(cy + ry * cs, H)); a[j + c] = src[(yy * W + xx) * 4 + c] * v; }
        }
      });
    },
    light_leak(ctx, p, s) {
      const {W, H} = s, pal = LEAK[p.palette ?? 'amber'], t = s.elapsed;
      const anchors = {left: [-.05, .5], right: [1.05, .5], top: [.5, -.05], bottom: [.5, 1.05], center: [.5, .5], tl: [0, 0], tr: [1, 0], bl: [0, 1], br: [1, 1]};
      const [ax, ay] = anchors[p.anchor ?? 'left'], seed = p.seed ?? 0;
      const x = (ax + Math.sin(t * .7 + seed) * .04) * W, y = (ay + Math.cos(t * .5 + seed) * .06) * H, R = (p.size ?? .32) * Math.max(W, H) * (1 + .08 * Math.sin(t * 9.4 + seed));
      const g = ctx.createRadialGradient(x, y, 0, x, y, R * 2);
      g.addColorStop(0, `rgb(${pal[0]})`); g.addColorStop(.35, `rgb(${pal[1]})`); g.addColorStop(1, `rgba(${pal[2]},0)`);
      ctx.save(); ctx.globalCompositeOperation = (p.blend ?? 'screen') === 'add' ? 'lighter' : 'screen'; ctx.globalAlpha = clamp(p.peak ?? .9); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H); ctx.restore();
    },
    pixel_art(ctx, p, s) {
      const {W, H} = s, b = Math.max(1, Math.round((p.block ?? .008) * W)), w = Math.ceil(W / b), h = Math.ceil(H / b), [c, x] = scratch('pa', w, h);
      x.imageSmoothingEnabled = true; x.drawImage(ctx.canvas, 0, 0, w, h);
      // adaptive palette: median cut of the frame's own colours, then nearest colour (optional ordered dither)
      const dither = p.dither === 'bayer4', img = x.getImageData(0, 0, w, h), a = img.data, cols = [];
      for (let i = 0; i < a.length; i += 4) cols.push([a[i], a[i + 1], a[i + 2]]);
      let boxes = [cols];
      while (boxes.length < (p.colors ?? 12)) {
        let best = -1, bi = -1, bc = 0;
        boxes.forEach((bx, i) => { if (bx.length < 2) return; for (let c = 0; c < 3; c++) { let lo = 255, hi = 0; for (const v of bx) { if (v[c] < lo) lo = v[c]; if (v[c] > hi) hi = v[c]; } if ((hi - lo) * Math.sqrt(bx.length) > best) { best = (hi - lo) * Math.sqrt(bx.length); bi = i; bc = c; } } });
        if (bi < 0 || best <= 0) break;
        const bx = boxes[bi].sort((A, B) => A[bc] - B[bc]), mid = bx.length >> 1;
        boxes.splice(bi, 1, bx.slice(0, mid), bx.slice(mid));
      }
      const pal = boxes.filter(bx => bx.length).map(bx => [0, 1, 2].map(c => bx.reduce((t, v) => t + v[c], 0) / bx.length));
      for (let yy = 0; yy < h; yy++) for (let xx = 0; xx < w; xx++) {
        const j = (yy * w + xx) * 4, d = dither ? (BAYER4[(yy % 4) * 4 + xx % 4] / 16 - .5) * 48 : 0;
        let bestD = 1e9, best = pal[0];
        for (const q of pal) { const dd = (a[j] + d - q[0]) ** 2 + (a[j + 1] + d - q[1]) ** 2 + (a[j + 2] + d - q[2]) ** 2; if (dd < bestD) { bestD = dd; best = q; } }
        a[j] = best[0]; a[j + 1] = best[1]; a[j + 2] = best[2];
      }
      x.putImageData(img, 0, 0);
      const src = copyOf(ctx, 'pa0'); ctx.save(); ctx.imageSmoothingEnabled = false; ctx.drawImage(c, 0, 0, w * b, h * b);
      ctx.globalAlpha = 1 - clamp(p.strength ?? 1); ctx.imageSmoothingEnabled = true; ctx.drawImage(src, 0, 0); ctx.restore();
    },
    pixel_sort(ctx, p, s) {
      const {W, H} = s, scale = Math.min(1, (p.work_res ?? 540) / H), w = Math.max(1, Math.round(W * scale)), h = Math.max(1, Math.round(H * scale)), [c, x] = scratch('ps', w, h);
      x.drawImage(ctx.canvas, 0, 0, w, h);
      const img = x.getImageData(0, 0, w, h), d = img.data, br = i => LUMA(d[i], d[i + 1], d[i + 2]), lo = (p.lo ?? .62) * 255, mask = p.mask ?? 'bright';
      const axis = p.axis ?? 'y', lines = axis === 'y' ? w : h, len = axis === 'y' ? h : w, at = (l, k) => (axis === 'y' ? k * w + l : l * w + k) * 4;
      const keep = i => mask === 'full' ? true : mask === 'dark' ? br(i) < 255 - lo : br(i) > lo;
      for (let l = 0; l < lines; l++) {
        let k = 0;
        while (k < len) {
          while (k < len && !keep(at(l, k))) k++;
          const st = k; while (k < len && keep(at(l, k))) k++;
          if (k - st > 1) {
            const run = []; for (let m = st; m < k; m++) { const i = at(l, m); run.push([br(i), d[i], d[i + 1], d[i + 2]]); }
            run.sort((A, B) => (p.dir ?? 'down') === 'down' ? A[0] - B[0] : B[0] - A[0]);
            run.forEach((v, m) => { const i = at(l, st + m); d[i] = v[1]; d[i + 1] = v[2]; d[i + 2] = v[3]; });
          }
        }
      }
      x.putImageData(img, 0, 0); ctx.drawImage(c, 0, 0, W, H);
    },
    pixelate(ctx, p, s) {
      const b = Math.max(2, Math.round((p.size ?? .035) * Math.min(s.W, s.H))), w = Math.max(1, Math.round(s.W / b)), h = Math.max(1, Math.round(s.H / b)), [c, x] = scratch('px', w, h);
      x.drawImage(ctx.canvas, 0, 0, w, h); ctx.save(); ctx.imageSmoothingEnabled = false; ctx.drawImage(c, 0, 0, w, h, 0, 0, s.W, s.H); ctx.restore();
    },
    posterize(ctx, p) {
      const n = Math.max(2, p.levels ?? 4), q = v => Math.round(v / 255 * (n - 1)) * 255 / (n - 1);
      pixels(ctx, a => { for (let i = 0; i < a.length; i += 4) { if ((p.mode ?? 'rgb') === 'luma') { const L = LUMA(a[i], a[i + 1], a[i + 2]), k = L > 0 ? q(L) / L : 0; a[i] *= k; a[i + 1] *= k; a[i + 2] *= k; } else for (let c = 0; c < 3; c++) a[i + c] = q(a[i + c]); } });
    },
    rgb_split(ctx, p, s) { const px = (p.px ?? 8) * s.W / 1080, a = (p.angle ?? 0) * Math.PI / 180; shiftChannels(ctx, Math.cos(a) * px, Math.sin(a) * px, -Math.cos(a) * px, -Math.sin(a) * px); },
    saturation(ctx, p) { const src = copyOf(ctx, 'sat'); ctx.save(); ctx.filter = `saturate(${Math.max(0, 1 + (p.sat ?? 0))}) hue-rotate(${p.hue ?? 0}deg)`; ctx.drawImage(src, 0, 0); ctx.restore(); },
    shake(ctx, p, s) {
      const px = (p.px ?? 12) * s.W / 1080, src = copyOf(ctx, 'sh'), k = 1 + 2 * px / Math.min(s.W, s.H);
      ctx.save(); ctx.translate(s.W / 2 + (s.hash(s.frame, 1, p.seed ?? 0) - .5) * 2 * px, s.H / 2 + (s.hash(s.frame, 2, p.seed ?? 0) - .5) * 2 * px); ctx.scale(k, k); ctx.drawImage(src, -s.W / 2, -s.H / 2); ctx.restore();
    },
    smear(ctx, p, s) { FX.dirblur(ctx, {len: (p.len ?? .25) * .3, angle: p.angle ?? 0}, s); FX.chroma(ctx, {px: p.px ?? 14}, s); FX.saturation(ctx, {sat: (p.sat ?? 1.6) - 1}, s); },
    tape(ctx, p, s) {
      const {W, H} = s, res = p.res ?? .36, w = Math.max(8, Math.round(W * res)), h = Math.max(8, Math.round(H * (p.vres ?? .6))), [c, x] = scratch('tp', w, h), seed = p.seed ?? 0;
      x.drawImage(ctx.canvas, 0, 0, w, h); ctx.save(); ctx.imageSmoothingEnabled = true; ctx.drawImage(c, 0, 0, W, H); ctx.restore();
      FX.chroma(ctx, {px: (p.chroma_shift ?? .004) * 1080}, s);
      const band = Math.floor(s.elapsed / 2.3 + seed) % 3 === 0, by = s.hash(Math.floor(s.elapsed / 2.3), 4, seed) * H, bh = .05 * H;
      pixels(ctx, a => {
        const src = a.slice(), depth = p.depth ?? .07, noise = (p.noise ?? .03) * 255;
        for (let y = 0; y < H; y++) {
          const dark = (y & 1) ? 1 - depth : 1, inBand = band && y > by && y < by + bh, shift = inBand ? Math.round((s.hash(y, s.frame, seed) - .3) * .012 * W * 4) : (y > H * (1 - (p.head ?? .02)) ? Math.round(.01 * W) : 0);
          for (let x2 = 0; x2 < W; x2++) {
            const j = (y * W + x2) * 4, sj = (y * W + Math.min(W - 1, Math.max(0, x2 - shift))) * 4, n = (s.hash(x2 >> 1, y, s.frame + seed) - .5) * noise;
            a[j] = src[sj] * dark + n; a[j + 1] = src[sj + 1] * dark + n; a[j + 2] = src[sj + 2] * dark + n;
          }
        }
      });
    },
    vignette(ctx, p, s) {
      const {W, H} = s, [cx, cy] = p.center ?? [.5, .5], R = Math.hypot(W, H) / 2, f = p.feather ?? .15;
      const g = ctx.createRadialGradient(cx * W, cy * H, R * Math.max(0, .55 - f), cx * W, cy * H, R * (1.05 + f * .5));
      g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, `rgba(0,0,0,${clamp((p.amount ?? .35) * 1.6)})`);
      ctx.save(); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H); ctx.restore();
    },
    zoomblur(ctx, p, s) {
      const src = copyOf(ctx, 'zb'), n = Math.max(2, p.n ?? 8), cx = (p.cx ?? .5) * s.W, cy = (p.cy ?? .5) * s.H, amt = p.amount ?? .12;
      smear(ctx, src, n * 2, k => { const z = 1 + amt * k; ctx.translate(cx, cy); ctx.scale(z, z); ctx.translate(-cx, -cy); });
    },
  };
  FX.glitch_blocks = FX.datamosh;

  function apply(ctx, look, info) {
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none';
    try {
      if (look.grade) grade(ctx, look.grade);
      for (const item of look.fx ?? []) {
        const {type, amt = 1, ...params} = item;
        if (amt >= 1) FX[type](ctx, params, info);
        else if (amt > 0) { const before = copyOf(ctx, 'amt'); FX[type](ctx, params, info); ctx.save(); ctx.globalAlpha = 1 - amt; ctx.drawImage(before, 0, 0); ctx.restore(); }
      }
    } finally { ctx.restore(); }
  }
  return {apply, effects: Object.keys(FX)};
})();
