// Local layer effects; parameters and defaults are documented in docs/TIMELINE.md.
window.OpenKatanaLocal = (() => {
  const orders = {local_selective_color:6, local_posterize:7, local_halftone:8, local_frame_slices:9, local_whip:16, local_zoom_blur:17,
                  local_scramble_text:58, local_speed_lines:25, local_paper_frame:30, local_curve:95, local_turbulent_displace:18, local_displacement_map:19};
  const phase = {local_scramble_text:'over', local_speed_lines:'final', local_paper_frame:'final', local_curve:'subject'};
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
  // Improved Perlin noise in 3D (Ken Perlin, 2002) over a seeded permutation, about -1..1.
  const noises = new Map();
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
    noises.set(seed, n);
    return n;
  }
  // a number, or [[seconds, value], ...] linear between keys and held at the ends
  const keyedT = (v, t, d) => {
    if (v == null) return d;
    if (!Array.isArray(v)) return v;
    if (t <= v[0][0]) return v[0][1];
    for (let i = 1; i < v.length; i++) if (t <= v[i][0]) { const [t0, a] = v[i - 1], [t1, b] = v[i]; return a + (b - a) * (t - t0) / (t1 - t0); }
    return v[v.length - 1][1];
  };
  // local_turbulent_displace: After Effects-style Turbulent Displace. A fractal-noise field (complexity = octaves) moves
  // every pixel by up to `amount` px (at 1080): turbulent (both axes), horizontal, vertical, cross (both by one field),
  // bulge (along the noise slope: highs swell) or twist (across it: swirls). `size` is the noise feature size (px at
  // 1080); evolution moves through the noise (`speed` revolutions a second), `drift` slides it, `every` holds it for n
  // frames (a boil). Pinning fades the move to zero at the frame edges; `region` [x0, y0, x1, y1] (0..1) with `feather`
  // confines it. Output pixel x shows the source at x + d(x), bilinear, reflected at the edges.
  function turbulent(ctx, p, s) {
    const {W: w, H: h, elapsed, fps} = s, k = h / 1080, t = elapsed - (p.at ?? 0);
    if (t < 0) return;
    const A = keyedT(p.amount, t, 20) * k;
    if (!(A > .02)) return;
    const size = Math.max(1, (p.size ?? 100) * k), oct = p.complexity ?? 1, mode = p.displacement ?? 'turbulent';
    const every = p.every ?? 1, tq = Math.floor(t * fps / every + 1e-6) * every / fps;
    const z = (p.evolution ?? 0) + (p.speed ?? .5) * tq, n = perlin(p.seed ?? 1);
    const ox = ((p.offset?.[0] ?? 0) + (p.drift?.[0] ?? 0) * tq) * k, oy = ((p.offset?.[1] ?? 0) + (p.drift?.[1] ?? 0) * tq) * k;
    const fbm = (x, y, zz, salt) => { let v = 0, a = 1, f = 1, norm = 0;
      for (let o = 0; o < oct; o++) { v += a * n(x * f + salt + o * 19.19, y * f + salt * .7 + o * 7.13, zz + o * 3.7); norm += a; a *= .5; f *= 2; }
      return v / norm; };
    // the field on a grid (bilinear between grid points), a few px apart and finer than the smallest octave
    const g = Math.max(1, Math.min(8, Math.round(size / Math.pow(2, oct - 1) / 6))), gw = Math.ceil(w / g) + 2, gh = Math.ceil(h / g) + 2;
    const FX = new Float32Array(gw * gh), FY = new Float32Array(gw * gh);
    const slope = mode === 'bulge' || mode === 'twist', sw = gw + 2;
    const N = slope ? new Float32Array(sw * (gh + 2)) : null;
    if (slope) for (let j = -1; j <= gh; j++) for (let i = -1; i <= gw; i++) N[(j + 1) * sw + i + 1] = fbm((i * g + ox) / size, (j * g + oy) / size, z, 0);
    const pin = p.pin ?? 'all', pd = Math.max(2, Math.min(size, Math.min(w, h) / 4));
    const smooth = u => (u <= 0 ? 0 : u >= 1 ? 1 : u * u * (3 - 2 * u));
    const reg = p.region, fe = (p.feather ?? .02) * h;
    const [rx0, ry0, rx1, ry1] = reg ? [reg[0] * w, reg[1] * h, reg[2] * w, reg[3] * h] : [0, 0, 0, 0];
    const inside = (v, a, b) => fe > 0 ? clamp(1 - Math.max(a - v, v - b, 0) / fe) : (v >= a && v <= b ? 1 : 0);
    for (let j = 0; j < gh; j++) for (let i = 0; i < gw; i++) {
      const x = i * g, y = j * g;
      let wgt = 1;
      if (pin === 'all' || pin === 'vertical') wgt *= smooth(Math.min(x, w - 1 - x) / pd);
      if (pin === 'all' || pin === 'horizontal') wgt *= smooth(Math.min(y, h - 1 - y) / pd);
      if (reg) wgt *= inside(x, rx0, rx1) * inside(y, ry0, ry1);
      if (wgt <= 0) continue;
      let dx = 0, dy = 0;
      if (slope) {   // the noise slope per feature size, quartered: it then folds over at about the turbulent field's amount
        const c = (j + 1) * sw + i + 1, sx = (N[c + 1] - N[c - 1]) / (2 * g) * size * .25, sy = (N[c + sw] - N[c - sw]) / (2 * g) * size * .25;
        if (mode === 'bulge') { dx = sx; dy = sy; } else { dx = -sy; dy = sx; }
      } else {
        const nx = (x + ox) / size, ny = (y + oy) / size, a = fbm(nx, ny, z, 0);
        if (mode === 'turbulent') { dx = a; dy = fbm(nx, ny, z, 53.1); }
        else if (mode === 'horizontal') dx = a;
        else if (mode === 'vertical') dy = a;
        else { dx = a; dy = a; }
      }
      FX[j * gw + i] = dx * A * wgt; FY[j * gw + i] = dy * A * wgt;
    }
    const src = ctx.getImageData(0, 0, w, h), sd = src.data, out = ctx.createImageData(w, h), od = out.data;
    // pixels outside the region and its feather keep their place (the grid would otherwise bleed one cell past it)
    const [bx0, by0, bx1, by1] = reg ? [rx0 - fe, ry0 - fe, rx1 + fe, ry1 + fe] : [-1, -1, w, h];
    for (let y = 0; y < h; y++) {
      const gy = y / g, j0 = Math.floor(gy), fy = gy - j0;
      for (let x = 0; x < w; x++) {
        const gx = x / g, i0 = Math.floor(gx), fx = gx - i0, a = j0 * gw + i0, o = (y * w + x) * 4;
        const w00 = (1 - fx) * (1 - fy), w10 = fx * (1 - fy), w01 = (1 - fx) * fy, w11 = fx * fy;
        const still = x < bx0 || x > bx1 || y < by0 || y > by1;
        const dx = still ? 0 : FX[a] * w00 + FX[a + 1] * w10 + FX[a + gw] * w01 + FX[a + gw + 1] * w11;
        const dy = still ? 0 : FY[a] * w00 + FY[a + 1] * w10 + FY[a + gw] * w01 + FY[a + gw + 1] * w11;
        moveInto(od, o, sd, x, y, dx, dy, w, h);
      }
    }
    ctx.putImageData(out, 0, 0);
  }
  // out pixel (x, y) = the source at (x + dx, y + dy), bilinear and reflected at the edges; a negligible move copies
  const reflect = (v, m) => { if (m < 2) return 0; const period = 2 * (m - 1); v = Math.abs(v) % period; return v > m - 1 ? period - v : v; };
  function moveInto(od, o, sd, x, y, dx, dy, w, h) {
    if (Math.abs(dx) < .002 && Math.abs(dy) < .002) { od[o] = sd[o]; od[o + 1] = sd[o + 1]; od[o + 2] = sd[o + 2]; od[o + 3] = sd[o + 3]; return; }
    const sx = reflect(x + dx, w), sy = reflect(y + dy, h), x0 = Math.max(0, Math.min(w - 2, Math.floor(sx))), y0 = Math.max(0, Math.min(h - 2, Math.floor(sy)));
    const ux = sx - x0, uy = sy - y0, b = (y0 * w + x0) * 4, r = w * 4;
    const v00 = (1 - ux) * (1 - uy), v10 = ux * (1 - uy), v01 = (1 - ux) * uy, v11 = ux * uy;
    for (let c = 0; c < 4; c++) od[o + c] = sd[b + c] * v00 + sd[b + 4 + c] * v10 + sd[b + r + c] * v01 + sd[b + r + 4 + c] * v11;
  }
  // local_displacement_map: After Effects' Displacement Map. A frame of another clip (`s.map`, loaded by the engine and
  // stretched over the canvas, softened by `smooth` px at 1080) moves each pixel by (channel - 128) / 127 x `amount` px
  // at 1080: `x` and `y` pick the channel for each axis (red, green, blue, alpha, luma or none), so mid grey keeps a pixel
  // in place (`neutral` sets that level, or "mean" for the frame's mean). `region` [x0, y0, x1, y1] with `feather` confines
  // it. Heat haze, glass, water and ripple plates drive it.
  const CHANNEL = {red: (d, i) => d[i], green: (d, i) => d[i + 1], blue: (d, i) => d[i + 2], alpha: (d, i) => d[i + 3],
                   luma: (d, i) => .2126 * d[i] + .7152 * d[i + 1] + .0722 * d[i + 2]};
  function displaceMap(ctx, p, s) {
    const {W: w, H: h, map} = s, k = h / 1080, t = s.elapsed - (p.at ?? 0);
    if (t < 0 || !map) return;
    const A = keyedT(p.amount, t, 20) * k;
    if (!(A > .02)) return;
    const mb = buffer(w, h), mx = mb.getContext('2d'), sm = (p.smooth ?? 0) * k;
    const pad = sm > .3 ? Math.max(0, Math.min(Math.min(w, h) - 1, Math.ceil(3 * sm) + 1)) : 0;
    if (pad) { mx.filter = `blur(${sm}px)`; mx.drawImage(mirrorPad(map, w, h, pad), -pad, -pad); mx.filter = 'none'; }
    else mx.drawImage(map, 0, 0, w, h);
    const md = mx.getImageData(0, 0, w, h).data, sd = ctx.getImageData(0, 0, w, h).data, out = ctx.createImageData(w, h), od = out.data;
    const cx = CHANNEL[p.x ?? 'red'], cy = CHANNEL[p.y ?? 'green'];
    // the channel level that keeps a pixel in place: 128, a given level, or this map frame's mean ("mean": a plate shot on
    // black then moves pixels by its variation instead of shifting the whole picture one way)
    const mean = f => { let sum = 0, n = 0; for (let i = 0; i < md.length; i += 64) { sum += f(md, i); n++; } return n ? sum / n : 128; };
    const nx = cx ? (p.neutral === 'mean' ? mean(cx) : p.neutral ?? 128) : 128, ny = cy ? (p.neutral === 'mean' ? mean(cy) : p.neutral ?? 128) : 128;
    const val = (f, o, n0) => Math.max(-1, Math.min(1, (f(md, o) - n0) / 127));
    const reg = p.region, fe = (p.feather ?? .02) * h;
    const [rx0, ry0, rx1, ry1] = reg ? [reg[0] * w, reg[1] * h, reg[2] * w, reg[3] * h] : [0, 0, 0, 0];
    const inside = (v, a, b) => fe > 0 ? clamp(1 - Math.max(a - v, v - b, 0) / fe) : (v >= a && v <= b ? 1 : 0);
    for (let y = 0; y < h; y++) {
      const wy = reg ? inside(y, ry0, ry1) : 1;
      for (let x = 0; x < w; x++) {
        const o = (y * w + x) * 4, wgt = reg ? wy * inside(x, rx0, rx1) : 1;
        moveInto(od, o, sd, x, y, wgt && cx ? val(cx, o, nx) * A * wgt : 0, wgt && cy ? val(cy, o, ny) * A * wgt : 0, w, h);
      }
    }
    ctx.putImageData(out, 0, 0);
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
  return {orders, phase, draw, mapFrame};
})();
