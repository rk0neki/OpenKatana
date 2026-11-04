// Time effects as an OpenKatana effect pack (Echo, Time Displacement, Posterize Time, frame blending).
// Parameters and defaults are documented in docs/TIMELINE.md; validation is in openkatana/fx_time.py. Shared helpers:
// OpenKatanaLocal.util. Each effect reads other frames of its own shot through s.shotAt(frame): the shot rendered at
// that frame up to (not including) this effect, so an echo holds exactly what the effect sees on its own frame.
(() => {
  const {register, util} = OpenKatanaLocal;
  const {clamp, buffer, copy, keyedT} = util;
  const pixelsOf = (pic, w, h) => {   // RGBA bytes of a canvas or bitmap at w x h
    if (pic.getContext && pic.width === w && pic.height === h) return pic.getContext('2d').getImageData(0, 0, w, h).data;
    const b = buffer(w, h), x = b.getContext('2d'); x.drawImage(pic, 0, 0, w, h); return x.getImageData(0, 0, w, h).data;
  };
  // the picture `offset` frames away (0: the picture as it stands, no nested render)
  const frameAt = (s, here, offset) => (offset === 0 ? here : s.shotAt(s.frame + offset));

  // local_echo: Echo. Image k (k = 0 the frame itself, 1..number_of_echoes the frames echo_time seconds
  // apart; negative looks back) has intensity starting_intensity x decay^k, and the images are combined by `operator`:
  // add, maximum, minimum, screen, blend (intensity-weighted mean), composite_back (echoes behind the frame, the newest
  // on top) or composite_front (echoes over it, the oldest on top), over black. Echo times outside the edit, or where the
  // shot has no source frame (before its source starts or after it ends, no loop), add nothing.
  async function echo(ctx, p, s) {
    const {W: w, H: h, fps} = s, t = s.elapsed - (p.at ?? 0);
    if (t < 0) return;
    const step = (p.echo_time ?? -1 / fps) * fps, n = Math.round(p.number_of_echoes ?? 1);
    const I0 = clamp(p.starting_intensity ?? 1), decay = clamp(p.decay ?? 1), op = p.operator ?? 'add';
    const here = copy(ctx), images = [];
    for (let k = 0; k <= n; k++) {
      const I = I0 * decay ** k, f = s.frame + Math.round(k * step);
      if (f < 0 || f >= (s.frames ?? Infinity)) continue;   // before the edit starts or after it ends: nothing to echo
      if (k && s.hasFrame && !s.hasFrame(f)) continue;     // before the shot's source starts or after it ends: likewise
      if (I > 1 / 512 || op === 'minimum') images.push([I, await frameAt(s, here, f - s.frame)]);
    }
    if (op === 'composite_back' || op === 'composite_front') {   // alpha-over, drawn back to front
      const order = op === 'composite_back' ? images.slice().reverse() : images;
      ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1; ctx.fillStyle = '#000000'; ctx.fillRect(0, 0, w, h);
      for (const [I, pic] of order) { ctx.globalAlpha = I; ctx.drawImage(pic, 0, 0, w, h); }
      ctx.globalAlpha = 1;
      return;
    }
    if (images.length === 1 && images[0][0] >= 1 && op !== 'minimum') return;   // the frame alone at full intensity
    const N = w * h * 4, acc = new Float32Array(N);
    let wsum = 0;
    if (op === 'minimum') acc.fill(Infinity);
    for (const [I, pic] of images) {
      const d = pixelsOf(pic, w, h);
      if (op === 'add' || op === 'blend') for (let i = 0; i < N; i++) acc[i] += I * d[i];
      else if (op === 'maximum') for (let i = 0; i < N; i++) { const v = I * d[i]; if (v > acc[i]) acc[i] = v; }
      else if (op === 'minimum') for (let i = 0; i < N; i++) { const v = I * d[i]; if (v < acc[i]) acc[i] = v; }
      else if (op === 'screen') for (let i = 0; i < N; i++) acc[i] = 255 - (255 - acc[i]) * (255 - I * d[i]) / 255;
      wsum += I;
    }
    const im = ctx.getImageData(0, 0, w, h), o = im.data, k = op === 'blend' ? (wsum > 0 ? 1 / wsum : 0) : 1;
    for (let i = 0; i < N; i += 4) { o[i] = acc[i] * k; o[i + 1] = acc[i + 1] * k; o[i + 2] = acc[i + 2] * k; o[i + 3] = 255; }
    ctx.putImageData(im, 0, 0);
  }

  // local_posterize_time: Posterize Time. The shot shows frames held at `fps`: each frame shows the frame
  // at the start of its step (steps counted from the shot start, or `at`).
  async function posterizeTime(ctx, p, s) {
    const t = s.elapsed - (p.at ?? 0), r = p.fps ?? 12;
    if (t < 0 || r >= s.fps) return;
    const back = Math.floor((t - Math.floor(t * r + 1e-6) / r) * s.fps + 1e-6);
    if (back <= 0) return;
    const pic = await s.shotAt(s.frame - back);
    ctx.globalCompositeOperation = 'copy'; ctx.globalAlpha = 1; ctx.drawImage(pic, 0, 0, s.W, s.H);
    ctx.globalCompositeOperation = 'source-over';
  }

  // local_time_displacement: Time Displacement. A map's brightness picks, pixel by pixel, the time shown:
  // white max_displacement seconds ahead, black as far back, mid grey now (`invert` swaps them). The span is cut into
  // `levels` time slices (whole frames) and each pixel blends the two nearest. map: horizontal / vertical (gradients,
  // black at the left / top), radial (black at `center`, white at the farthest corner), self (the picture's own luma) or
  // clip (`clip`'s frame at this time, stretched over the frame; src / speed / loop as local_displacement_map).
  async function timeDisplace(ctx, p, s) {
    const {W: w, H: h, fps} = s, t = s.elapsed - (p.at ?? 0);
    if (t < 0) return;
    const max = keyedT(p.max_displacement, t, 1), L = Math.round(p.levels ?? 8);
    const offs = Array.from({length: L}, (_, k) => Math.round((-1 + 2 * k / (L - 1)) * max * fps));
    if (offs.every(o => o === 0)) return;
    const map = new Float32Array(w * h), kind = p.map ?? (p.clip ? 'clip' : 'horizontal');
    if (kind === 'horizontal') { for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) map[y * w + x] = w > 1 ? x / (w - 1) : .5; }
    else if (kind === 'vertical') { for (let y = 0; y < h; y++) map.fill(h > 1 ? y / (h - 1) : .5, y * w, (y + 1) * w); }
    else if (kind === 'radial') {
      const c = p.center ?? [.5, .5], cx = c[0] * w, cy = c[1] * h;
      const R = Math.max(...[[0, 0], [w, 0], [0, h], [w, h]].map(([x, y]) => Math.hypot(x - cx, y - cy))) || 1;
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) map[y * w + x] = Math.min(1, Math.hypot(x + .5 - cx, y + .5 - cy) / R);
    } else {
      let d;
      if (kind === 'self') d = ctx.getImageData(0, 0, w, h).data;
      else {
        const mc = s.clips?.[p.clip], i = mc ? OpenKatanaLocal.mapFrame(p, mc, s.elapsed) : null;
        if (i === null) return;
        d = pixelsOf(await s.image(p.clip, i), w, h);
      }
      for (let i = 0, j = 0; i < map.length; i++, j += 4) map[i] = (.2126 * d[j] + .7152 * d[j + 1] + .0722 * d[j + 2]) / 255;
    }
    if (p.invert) for (let i = 0; i < map.length; i++) map[i] = 1 - map[i];
    const used = new Uint8Array(L);   // which slices any pixel uses, so unused ones are never rendered
    for (let i = 0; i < map.length; i++) { const u = map[i] * (L - 1), a = Math.floor(u); used[a] = 1; if (u > a) used[Math.min(L - 1, a + 1)] = 1; }
    const here = copy(ctx), slices = [];
    for (let k = 0; k < L; k++) slices.push(used[k] ? pixelsOf(await frameAt(s, here, offs[k]), w, h) : null);
    const im = ctx.getImageData(0, 0, w, h), o = im.data;
    for (let i = 0, j = 0; i < map.length; i++, j += 4) {
      const u = map[i] * (L - 1), a = Math.min(L - 1, Math.floor(u)), f = u - a, A = slices[a];
      if (f <= 0 || a === L - 1) { o[j] = A[j]; o[j + 1] = A[j + 1]; o[j + 2] = A[j + 2]; }
      else { const B = slices[a + 1]; o[j] = A[j] + (B[j] - A[j]) * f; o[j + 1] = A[j + 1] + (B[j + 1] - A[j + 1]) * f; o[j + 2] = A[j + 2] + (B[j + 2] - A[j + 2]) * f; }
      o[j + 3] = 255;
    }
    ctx.putImageData(im, 0, 0);
  }

  // local_frame_blend: frame blending looking back over earlier frames, with sub-frame spacing. `samples`
  // images spread evenly over the last shutter x (samples - 1) frames are averaged (a sample between two frames mixes
  // them), smearing motion into a trail the way a longer shutter would; shutter 0 leaves the frame alone.
  async function frameBlend(ctx, p, s) {
    const {W: w, H: h} = s, t = s.elapsed - (p.at ?? 0);
    if (t < 0) return;
    const n = Math.round(p.samples ?? 4), reach = clamp(p.shutter ?? .5) * (n - 1);
    if (reach < 1e-3) return;
    const weights = new Map();   // frame offset -> weight
    for (let i = 0; i < n; i++) {
      const x = -reach * i / (n - 1), a = Math.floor(x + 1e-9), f = x - a;
      weights.set(a, (weights.get(a) ?? 0) + (1 - f) / n);
      if (f > 1e-9) weights.set(a + 1, (weights.get(a + 1) ?? 0) + f / n);
    }
    const here = copy(ctx), N = w * h * 4, acc = new Float32Array(N);
    for (const [off, wt] of weights) {
      if (wt <= 1e-6) continue;
      const d = pixelsOf(await frameAt(s, here, off), w, h);
      for (let i = 0; i < N; i++) acc[i] += wt * d[i];
    }
    const im = ctx.getImageData(0, 0, w, h), o = im.data;
    for (let i = 0; i < N; i += 4) { o[i] = acc[i]; o[i + 1] = acc[i + 1]; o[i + 2] = acc[i + 2]; o[i + 3] = 255; }
    ctx.putImageData(im, 0, 0);
  }

  // post-phase orders 1..4: time effects come first in a stack
  register('local_posterize_time', {order: 1, time: true, draw: posterizeTime});
  register('local_time_displacement', {order: 2, time: true, draw: timeDisplace});
  register('local_frame_blend', {order: 3, time: true, draw: frameBlend});
  register('local_echo', {order: 4, time: true, draw: echo});
})();
