// After Effects' Stylize effects as an OpenKatana effect pack (RGB Split, Motion Tile, Find Edges, Emboss, Mosaic, Scatter); orders 60-67. Parameters and defaults are
// documented in docs/TIMELINE.md; validation is in openkatana/fx_stylize.py. Shared helpers: OpenKatanaLocal.util.
// Every effect starts at `at` (seconds into the shot) and can be confined to `region` [x0, y0, x1, y1] (0..1) with a
// `feather` (a fraction of the height, .02 by default); an amount of zero leaves the frame bit-identical.
(() => {
  const {register, util} = OpenKatanaLocal;
  const {clamp, keyedT, inBox, buffer, copy, EDGES} = util;
  const RAD = Math.PI / 180;
  // the effect's own clock: seconds since `at` (null before it starts)
  const clock = (p, s) => { const t = s.elapsed - (p.at ?? 0); return t < 0 ? null : t; };
  const regionBox = (p, s) => (p.region ? inBox(p.region, (p.feather ?? .02) * s.H, s.W, s.H) : null);

  // run `fn` (which rewrites the frame), then put the untouched frame back outside `region`, mixing across the feather
  function confined(ctx, p, s, fn) {
    const box = regionBox(p, s);
    if (!box) { fn(); return; }
    const {W: w, H: h} = s, b = ctx.getImageData(0, 0, w, h).data;
    fn();
    const after = ctx.getImageData(0, 0, w, h), a = after.data;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const g = box.still(x, y) ? 0 : box.weight(x, y);
      if (g >= 1) continue;
      const o = (y * w + x) * 4;
      for (let c = 0; c < 4; c++) a[o + c] = b[o + c] + (a[o + c] - b[o + c]) * g;
    }
    ctx.putImageData(after, 0, 0);
  }

  // local_rgb_split: chromatic aberration / RGB separation. Red and blue move `amount` px (at 1080, keyframable) in
  // opposite directions and green stays: mode "linear" moves red along `angle` (degrees clockwise from the +x axis: 0
  // moves red right and blue left, 90 red down), mode "radial" moves red outward from `center` and blue inward by
  // amount x the distance from the centre / the distance to the farthest corner (a lens's lateral aberration). Bilinear;
  // beyond the frame by `edges`; quality "high" averages four sub-pixel samples in radial mode only (a linear split
  // is one uniform shift, which bilinear sampling already renders exactly). Region weights the move.
  register('local_rgb_split', {order: 60, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s, A = keyedT(p.amount, t, 10) * h / 1080;
    if (!(Math.abs(A) > .002)) return;
    const radial = p.mode === 'radial', th = keyedT(p.angle, t, 0) * RAD, ux = Math.cos(th), uy = Math.sin(th);
    const c = keyedT(p.center, t, [.5, .5]), cx = c[0] * w - .5, cy = c[1] * h - .5;
    const R = Math.max(1, Math.hypot(Math.max(cx + .5, w - .5 - cx), Math.max(cy + .5, h - .5 - cy)));
    const box = regionBox(p, s), edge = EDGES[p.edges ?? 'reflect'], wrap = p.edges === 'wrap', high = radial && p.quality === 'high';
    const img = ctx.getImageData(0, 0, w, h), sd = img.data, out = new Uint8ClampedArray(sd);
    const tap = (sx, sy, ch) => {
      sx = edge(sx, w); sy = edge(sy, h);
      const x0 = Math.floor(sx), y0 = Math.floor(sy), fx = sx - x0, fy = sy - y0;
      const x1 = x0 + 1 < w ? x0 + 1 : wrap ? 0 : w - 1, y1 = y0 + 1 < h ? y0 + 1 : wrap ? 0 : h - 1;
      const r0 = y0 * w, r1 = y1 * w;
      return (sd[(r0 + x0) * 4 + ch] * (1 - fx) + sd[(r0 + x1) * 4 + ch] * fx) * (1 - fy) + (sd[(r1 + x0) * 4 + ch] * (1 - fx) + sd[(r1 + x1) * 4 + ch] * fx) * fy;
    };
    const SUB = [-.25, -.25, .25, -.25, -.25, .25, .25, .25];
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const g = box ? (box.still(x, y) ? 0 : box.weight(x, y)) : 1;
      if (g <= 0) continue;
      const o = (y * w + x) * 4;
      if (!radial) { const dx = A * ux * g, dy = A * uy * g; out[o] = tap(x - dx, y - dy, 0); out[o + 2] = tap(x + dx, y + dy, 2); continue; }
      const m = A * g / R;
      if (!high) { const dx = (x - cx) * m, dy = (y - cy) * m; out[o] = tap(x - dx, y - dy, 0); out[o + 2] = tap(x + dx, y + dy, 2); continue; }
      let r = 0, b = 0;
      for (let i = 0; i < 8; i += 2) {
        const px = x + SUB[i], py = y + SUB[i + 1], dx = (px - cx) * m, dy = (py - cy) * m;
        r += tap(px - dx, py - dy, 0); b += tap(px + dx, py + dy, 2);
      }
      out[o] = r / 4; out[o + 2] = b / 4;
    }
    ctx.putImageData(new ImageData(out, w, h), 0, 0);
  }});

  // local_motion_tile: After Effects' Motion Tile. The frame shrinks to tiles `tile_width` x `tile_height` (% of the
  // frame) repeated in every direction from the tile centred at `tile_center`; the result fills a centred output area
  // `output_width` x `output_height` (% of the frame: below 100 the rest is transparent, above 100 changes nothing on a
  // full frame). `mirror_edges` flips every other tile so the seams match; `phase` (degrees) offsets every other column
  // by phase / 360 of a tile down (every other row right with `horizontal_phase_shift`). Everything but the switches
  // takes keyframes: keyframe tile_center to scroll the tiles, phase for sliding columns.
  register('local_motion_tile', {order: 61, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s, tc = keyedT(p.tile_center, t, [.5, .5]);
    const TW = Math.max(1, keyedT(p.tile_width, t, 100) / 100 * w), TH = Math.max(1, keyedT(p.tile_height, t, 100) / 100 * h);
    const OW = keyedT(p.output_width, t, 100) / 100 * w, OH = keyedT(p.output_height, t, 100) / 100 * h;
    const x0 = tc[0] * w - TW / 2, y0 = tc[1] * h - TH / 2, shift = keyedT(p.phase, t, 0) / 360, mirror = !!p.mirror_edges, across = !!p.horizontal_phase_shift;
    const L = Math.max(0, Math.round((w - OW) / 2)), T = Math.max(0, Math.round((h - OH) / 2)), Rr = w - L, B = h - T;
    // one tile exactly over the frame (any phase moves only the columns or rows beside it): untouched
    if (Math.abs(TW - w) < 1e-6 && Math.abs(TH - h) < 1e-6 && Math.abs(x0) < 1e-6 && Math.abs(y0) < 1e-6 && L === 0 && T === 0) return;
    confined(ctx, p, s, () => {
      // the tile buffer never exceeds the frame (the pattern is resampled anyway): huge tiles stay within the
      // canvas size limits and the time budget, and the extra scale goes into the pattern matrix
      const tw = Math.max(1, Math.min(w, Math.round(TW))), th = Math.max(1, Math.min(h, Math.round(TH))), src = copy(ctx);
      const tile = buffer(tw * (mirror ? 2 : 1), th * (mirror ? 2 : 1)), g = tile.getContext('2d');
      g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
      for (const [fx, fy] of mirror ? [[0, 0], [1, 0], [0, 1], [1, 1]] : [[0, 0]]) {   // flipped copies in the right / lower halves
        g.setTransform(fx ? -1 : 1, 0, 0, fy ? -1 : 1, fx ? 2 * tw : 0, fy ? 2 * th : 0);
        g.drawImage(src, 0, 0, tw, th);
      }
      const pat = ctx.createPattern(tile, 'repeat'), sx = TW / tw, sy = TH / th;
      ctx.save(); ctx.resetTransform(); ctx.clearRect(0, 0, w, h); ctx.imageSmoothingEnabled = true;
      const fill = (rx, ry, rx1, ry1, ox, oy) => {
        if (rx1 <= rx || ry1 <= ry) return;
        pat.setTransform(new DOMMatrix([sx, 0, 0, sy, x0 + ox, y0 + oy])); ctx.fillStyle = pat; ctx.fillRect(rx, ry, rx1 - rx, ry1 - ry);
      };
      if (!(shift % 1)) fill(L, T, Rr, B, 0, 0);
      else if (!across) {   // columns: every other one moved down by phase / 360 of a tile
        for (let i = Math.floor((L - x0) / TW); x0 + i * TW < Rr; i++)
          fill(Math.max(L, Math.round(x0 + i * TW)), T, Math.min(Rr, Math.round(x0 + (i + 1) * TW)), B, 0, (i & 1) ? shift * TH : 0);
      } else {
        for (let j = Math.floor((T - y0) / TH); y0 + j * TH < B; j++)
          fill(L, Math.max(T, Math.round(y0 + j * TH)), Rr, Math.min(B, Math.round(y0 + (j + 1) * TH)), (j & 1) ? shift * TW : 0, 0);
      }
      ctx.restore();
    });
  }});

  // local_find_edges: After Effects' Find Edges. Each colour channel's Sobel gradient (a full 0-to-255 step reads 255)
  // drawn as dark lines on white, like a pencil drawing; `invert` draws bright lines on black. `blend_with_original`
  // (0..1, keyframable) mixes the original back in (1 leaves it untouched). Alpha is kept.
  register('local_find_edges', {order: 62, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const mix = clamp(keyedT(p.blend_with_original, t, 0));
    if (mix >= 1) return;
    const {W: w, H: h} = s, inv = !!p.invert;
    confined(ctx, p, s, () => {
      const img = ctx.getImageData(0, 0, w, h), d = img.data, out = new Uint8ClampedArray(d);
      for (let y = 0; y < h; y++) {
        const ru = Math.max(0, y - 1) * w, rm = y * w, rd = Math.min(h - 1, y + 1) * w;
        for (let x = 0; x < w; x++) {
          const xl = Math.max(0, x - 1), xr = Math.min(w - 1, x + 1), o = (rm + x) * 4;
          const a = (ru + xl) * 4, b = (ru + x) * 4, c = (ru + xr) * 4, l = (rm + xl) * 4, r = (rm + xr) * 4, e = (rd + xl) * 4, f = (rd + x) * 4, g = (rd + xr) * 4;
          for (let ch = 0; ch < 3; ch++) {
            const gx = d[c + ch] + 2 * d[r + ch] + d[g + ch] - d[a + ch] - 2 * d[l + ch] - d[e + ch];
            const gy = d[e + ch] + 2 * d[f + ch] + d[g + ch] - d[a + ch] - 2 * d[b + ch] - d[c + ch];
            const m = Math.min(255, Math.sqrt(gx * gx + gy * gy) / 4), v = inv ? m : 255 - m;
            out[o + ch] = v + (d[o + ch] - v) * mix;
          }
        }
      }
      ctx.putImageData(new ImageData(out, w, h), 0, 0);
    });
  }});

  // local_emboss: After Effects' Emboss. Reads the picture's luma as height and lights it from `direction` (degrees
  // clockwise from up; 45 is the top right): mid grey where flat, light on slopes facing the light, dark on the others.
  // `relief` (px at 1080) is how far apart the two height samples are, `contrast` (100 = AE's default) scales the
  // difference; `blend_with_original` (0..1) mixes the original back in. All four take keyframes. Alpha is kept.
  register('local_emboss', {order: 63, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const mix = clamp(keyedT(p.blend_with_original, t, 0));
    if (mix >= 1) return;
    const {W: w, H: h} = s, th = keyedT(p.direction, t, 45) * RAD, rel = Math.max(0, keyedT(p.relief, t, 1)) * h / 1080;
    const gain = keyedT(p.contrast, t, 100) / 100 * .5, lx = Math.sin(th) * rel, ly = -Math.cos(th) * rel;
    confined(ctx, p, s, () => {
      const img = ctx.getImageData(0, 0, w, h), d = img.data, out = new Uint8ClampedArray(d), Y = new Float32Array(w * h);
      for (let i = 0; i < w * h; i++) Y[i] = .2126 * d[4 * i] + .7152 * d[4 * i + 1] + .0722 * d[4 * i + 2];
      const at = (sx, sy) => {
        sx = Math.min(w - 1, Math.max(0, sx)); sy = Math.min(h - 1, Math.max(0, sy));
        const x0 = Math.floor(sx), y0 = Math.floor(sy), fx = sx - x0, fy = sy - y0, x1 = Math.min(w - 1, x0 + 1), y1 = Math.min(h - 1, y0 + 1);
        return (Y[y0 * w + x0] * (1 - fx) + Y[y0 * w + x1] * fx) * (1 - fy) + (Y[y1 * w + x0] * (1 - fx) + Y[y1 * w + x1] * fx) * fy;
      };
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        const o = (y * w + x) * 4, v = 128 + gain * (at(x - lx, y - ly) - at(x + lx, y + ly));
        for (let ch = 0; ch < 3; ch++) out[o + ch] = v + (d[o + ch] - v) * mix;
      }
      ctx.putImageData(new ImageData(out, w, h), 0, 0);
    });
  }});

  // local_mosaic: After Effects' Mosaic. horizontal_blocks x vertical_blocks (keyframable; rounded, at least 1) solid
  // blocks, each the average of the pixels under it, or with `sharp_colors` the colour at its centre. Block i spans
  // floor(i W / n) to floor((i + 1) W / n), so the blocks tile the frame exactly.
  register('local_mosaic', {order: 64, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s;
    const nx = Math.min(w, Math.max(1, Math.round(keyedT(p.horizontal_blocks, t, 10)))), ny = Math.min(h, Math.max(1, Math.round(keyedT(p.vertical_blocks, t, 10))));
    if (nx === w && ny === h) return;   // one pixel per block: untouched
    confined(ctx, p, s, () => {
      const img = ctx.getImageData(0, 0, w, h), d = img.data, sharp = !!p.sharp_colors;
      const start = (i, n, m) => Math.floor(i * m / n), block = (v, n, m) => { let i = Math.min(n - 1, Math.floor(v * n / m)); while (start(i, n, m) > v) i--; while (start(i + 1, n, m) <= v) i++; return i; };
      const bx = Int32Array.from({length: w}, (_, x) => block(x, nx, w)), by = Int32Array.from({length: h}, (_, y) => block(y, ny, h));
      const col = new Float64Array(nx * ny * 4);
      if (sharp) {
        for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
          const cx = Math.floor((start(i, nx, w) + start(i + 1, nx, w) - 1) / 2), cy = Math.floor((start(j, ny, h) + start(j + 1, ny, h) - 1) / 2);
          const o = (cy * w + cx) * 4;
          for (let c = 0; c < 4; c++) col[(j * nx + i) * 4 + c] = d[o + c];
        }
      } else {
        const n = new Float64Array(nx * ny);
        for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
          const b = by[y] * nx + bx[x], o = (y * w + x) * 4; n[b]++;
          for (let c = 0; c < 4; c++) col[b * 4 + c] += d[o + c];
        }
        for (let b = 0; b < nx * ny; b++) for (let c = 0; c < 4; c++) col[b * 4 + c] /= Math.max(1, n[b]);
      }
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        const b = (by[y] * nx + bx[x]) * 4, o = (y * w + x) * 4;
        d[o] = col[b]; d[o + 1] = col[b + 1]; d[o + 2] = col[b + 2]; d[o + 3] = col[b + 3];
      }
      ctx.putImageData(img, 0, 0);
    });
  }});

  // local_scatter: After Effects' Scatter. Every pixel shows a random pixel up to `scatter_amount` px (at 1080,
  // keyframable) away: grain "both", "horizontal" or "vertical". The pattern is fixed by `seed` unless
  // `randomize_every_frame` (then it boils). Edge pixels draw from inside the frame.
  const mixHash = a => { a = Math.imul(a ^ (a >>> 16), 0x7feb352d); a = Math.imul(a ^ (a >>> 15), 0x846ca68b); return (a ^ (a >>> 16)) >>> 0; };
  register('local_scatter', {order: 65, draw(ctx, p, s) {
    const t = clock(p, s); if (t === null) return;
    const {W: w, H: h} = s, A = Math.max(0, keyedT(p.scatter_amount, t, 20)) * h / 1080;
    if (!(A >= .5)) return;   // under half a pixel nothing can move
    const grain = p.grain ?? 'both', mx = grain !== 'vertical' ? A : 0, my = grain !== 'horizontal' ? A : 0;
    const salt = mixHash((Math.imul((p.seed ?? 1) | 0, 0x9e3779b1) + (p.randomize_every_frame ? Math.imul(s.frame | 0, 0x85ebca6b) : 0)) | 0) | 0;
    confined(ctx, p, s, () => {
      const img = ctx.getImageData(0, 0, w, h), d = img.data, out = new Uint8ClampedArray(d.length);
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        const i = y * w + x, r1 = mixHash((2 * i) ^ salt) / 4294967296, r2 = mixHash((2 * i + 1) ^ salt) / 4294967296;
        const sx = Math.min(w - 1, Math.max(0, Math.round(x + (2 * r1 - 1) * mx))), sy = Math.min(h - 1, Math.max(0, Math.round(y + (2 * r2 - 1) * my)));
        const o = i * 4, q = (sy * w + sx) * 4;
        out[o] = d[q]; out[o + 1] = d[q + 1]; out[o + 2] = d[q + 2]; out[o + 3] = d[q + 3];
      }
      ctx.putImageData(new ImageData(out, w, h), 0, 0);
    });
  }});
})();
