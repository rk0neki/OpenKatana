// Sticker events (audit F-NAT-008): planned once at boot, drawn as an over-phase layer. Placement, pop-in, hard offset
// shadow and die-cut drawing are OpenKatana's own designs.
window.OpenKatanaStickers = (() => {
  let plan = [], art = [], cuts = [];
  const buffer = (w, h) => { const c = document.createElement('canvas'); c.width = Math.max(1, Math.ceil(w)); c.height = Math.max(1, Math.ceil(h)); return c; };
  function rng(seed) { let a = (Math.imul(seed | 0, 2654435761) + 0x6D2B79F5) >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  async function load(path) {
    const url = '/project/' + path.split('/').map(encodeURIComponent).join('/'), r = await fetch(url);
    if (!r.ok) throw Error(`Could not load sticker: ${path} (${r.status})`);
    return createImageBitmap(await r.blob(), {colorSpaceConversion: 'none'});
  }
  function silhouette(img, color) {   // the image's alpha filled with one colour
    const c = buffer(img.width, img.height), x = c.getContext('2d');
    x.drawImage(img, 0, 0); x.globalCompositeOperation = 'source-in'; x.fillStyle = color; x.fillRect(0, 0, c.width, c.height); return c;
  }
  function dieCut(frame, mask, clip, border, color) {
    const w = clip.w, h = clip.h, sub = buffer(w, h), sc = sub.getContext('2d');
    sc.drawImage(frame, 0, 0, w, h); sc.globalCompositeOperation = 'destination-in'; sc.drawImage(mask, 0, 0, w, h);
    const a = sc.getImageData(0, 0, w, h).data; let x0 = w, y0 = h, x1 = -1, y1 = -1;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (a[(y * w + x) * 4 + 3] > 16) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
    if (x1 < 0) throw Error('Cut-out sticker: the matte is empty at that frame');
    const cw = x1 - x0 + 1, ch = y1 - y0 + 1, crop = buffer(cw, ch);
    crop.getContext('2d').drawImage(sub, x0, y0, cw, ch, 0, 0, cw, ch);
    const out = buffer(cw + 2 * border + 2, ch + 2 * border + 2), oc = out.getContext('2d'), sil = silhouette(crop, color);
    for (let k = 0; k < 24 && border > 0; k++) { const t = k / 24 * Math.PI * 2; oc.drawImage(sil, border + 1 + Math.cos(t) * border, border + 1 + Math.sin(t) * border); }
    oc.drawImage(sil, border + 1, border + 1); oc.drawImage(crop, border + 1, border + 1);
    return out;
  }
  function inside(x, y, box) { return x >= box[0] && x <= box[2] && y >= box[1] && y <= box[3]; }
  function planEvent(ev, index, edit, faceAt) {
    const W = edit.canvas.w, H = edit.canvas.h, fps = edit.canvas.fps, n = ev.n ?? 1, r = rng((ev.seed ?? 0) * 9973 + index * 131 + 7);
    const pool = ev.kind === 'cutout' ? cuts : art, [smin, smax] = ev.size ?? (ev.kind === 'cutout' ? [W * .24, W * .3] : [W * .17, W * .24]), step = ev.step ?? .1;
    // faces on screen at the start, middle and end of the event: stickers keep clear of them
    const faces = faceAt ? [ev.f0, Math.floor((ev.f0 + ev.f1) / 2), ev.f1 - 1].map(faceAt).filter(Boolean) : [];
    const onFace = (x, y) => faces.some(f => ((x * W - f.x) / (f.D * 1.6 + smax * .5)) ** 2 + ((y * H - f.y - f.D * .6) / (f.D * 2.1 + smax * .5)) ** 2 < 1);   // head plus half a sticker
    const ids = ev.ids ? ev.ids.map(k => k - 1) : Array.from({length: n}, (_, k) => (Math.floor(r() * pool.length) + k) % pool.length);
    // candidates: a 6 x 4 grid away from the frame centre and the avoid boxes; each pick maximises distance to earlier picks
    const cand = [];
    for (let gy = 0; gy < 4; gy++) for (let gx = 0; gx < 6; gx++) {
      const x = (gx + .5) / 6, y = (gy + .5) / 4;
      if (Math.abs(x - .5) < .2 && Math.abs(y - .5) < .2) continue;
      if ((ev.avoid ?? []).some(b => inside(x, y, b)) || onFace(x, y)) continue;
      cand.push([x, y]);
    }
    const placed = [];
    for (let k = 0; k < n; k++) {
      let pos = ev.slots?.[k];
      if (!pos) {
        let best = null, score = -1;
        for (const c of cand) {
          const d = placed.length ? Math.min(...placed.map(p => Math.hypot((p[0] - c[0]) * W / H, p[1] - c[1]))) : 1;
          const s = d + r() * .15;
          if (s > score && !placed.some(p => p === c)) { score = s; best = c; }
        }
        pos = best ?? [.5, .5];
      }
      placed.push(pos);
    }
    return {f0: ev.f0, f1: ev.f1, shadow: ev.shadow ?? true, items: placed.map((pos, k) => {
      const img = pool[ids[k % ids.length]], size = smin + (smax - smin) * r(), hw = size / 2 * img.width / Math.max(img.width, img.height), hh = size / 2 * img.height / Math.max(img.width, img.height);
      // keep the whole sticker inside the frame (slots are honoured but nudged in)
      return {img, shade: null, x: Math.min(W - hw, Math.max(hw, pos[0] * W)), y: Math.min(H - hh, Math.max(hh, pos[1] * H)), size,
      rot: ((r() * 2 - 1) * (ev.rot ?? .22)), appear: ev.f0 / fps + ((ev.mode ?? 'hold') === 'burst' ? k * step : 0)}; })};
  }
  async function boot(edit, image, faceAt) {
    plan = []; art = []; cuts = [];
    const assets = edit.assets ?? {};
    art = await Promise.all((assets.stickers ?? []).map(load));
    const border = assets.cutout_border ?? Math.round(edit.canvas.w * .01), color = assets.cutout_border_color ?? '#ffffff';
    for (const c of assets.cutouts ?? []) {
      const clip = edit.clips[c.clip], idx = c.f ?? Math.round(c.t * clip.fps);
      cuts.push(dieCut(await image(clip, idx), await image({...clip, frames_dir: clip.mask_dir, pattern: '%05d.png'}, idx), clip, border, color));
    }
    plan = (edit.stickers ?? []).map((ev, i) => planEvent(ev, i, edit, faceAt));
    for (const ev of plan) for (const it of ev.items) it.shade = silhouette(it.img, 'rgba(0,0,0,0.55)');
  }
  const backOut = u => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2; };
  function draw(ctx, frame, fps, W, H) {
    for (const ev of plan) {
      if (frame < ev.f0 || frame >= ev.f1) continue;
      for (const it of ev.items) {
        const age = (frame + .5) / fps - it.appear;
        if (age < 0) continue;
        const s = age < .18 ? backOut(age / .18) : 1, k = it.size * s / Math.max(it.img.width, it.img.height);
        const w = it.img.width * k, h = it.img.height * k;
        ctx.save(); ctx.resetTransform(); ctx.translate(it.x, it.y); ctx.rotate(it.rot);
        if (ev.shadow) ctx.drawImage(it.shade, -w / 2 + W * .006, -h / 2 + W * .008, w, h);
        ctx.drawImage(it.img, -w / 2, -h / 2, w, h); ctx.restore();
      }
    }
  }
  return {boot, draw, active: frame => plan.some(ev => frame >= ev.f0 && frame < ev.f1)};
})();
