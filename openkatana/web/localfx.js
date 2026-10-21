// Local layer effects; parameters and defaults are documented in docs/TIMELINE.md.
window.OpenKatanaLocal = (() => {
  const orders = {local_selective_color:6, local_posterize:7, local_halftone:8, local_frame_slices:9, local_whip:16, local_zoom_blur:17,
                  local_scramble_text:58, local_speed_lines:25, local_paper_frame:30};
  const phase = {local_scramble_text:'over', local_speed_lines:'final', local_paper_frame:'final'};
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
  return {orders, phase, draw};
})();
