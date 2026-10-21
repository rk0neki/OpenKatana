// Decorative and face graphics layers (audit F-NAT-006 / F-NAT-007). Names, parameters, phases and orders follow
// the documented layer interface. Face points are in eye units (D = eye
// distance) in the face's rotated frame; mouth and nose come from the track's landmarks when it has them (YuNet:
// face.mu/mv, face.nu/nv), else they are estimated from the eyes.
window.OpenKatanaDecor = (() => {
  const orders = {stairs:30, glow:90, glint:25, doodles:30, face_doodles:40, doodle:41, word:57, type:59, slash:58, sparkle:45, splat:45,
                  bw:20, tag:40, border:30, cheeks:20, fangs:21, ears:32, whisk:33, blush:34, ast:56};
  const phase = {stairs:'back', glow:'subject', bw:'post', tag:'post', border:'final'};
  const FACE = ['cheeks', 'fangs', 'ears', 'whisk', 'blush', 'ast', 'face_doodles'];
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  const buffer = (w, h) => { const c = document.createElement('canvas'); c.width = Math.max(1, Math.ceil(w)); c.height = Math.max(1, Math.ceil(h)); return c; };
  function rng(seed) { let a = (Math.imul(seed | 0, 2654435761) + 0x6D2B79F5) >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  const backOut = u => { const c1 = 1.9, c3 = c1 + 1; return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2; };
  const pop = (age, d = .16) => age < 0 ? 0 : age < d ? Math.max(0, backOut(age / d)) : 1;
  const POP3 = [1.28, 1.1, 1];   // a three-frame pop for words
  const LINE = '#7d4fb3', FILL = '#ffffff', BLUSH = '#ff8fbf', INK = '#111111', ACCENT = '#b6ff1f';
  const pal = p => ({line: p.colors?.line ?? LINE, fill: p.colors?.fill ?? FILL, blush: p.colors?.blush ?? BLUSH});
  function facePt(face, ou, ov) {
    const c = Math.cos(face.a), s = Math.sin(face.a);
    return [face.x + (c * ou - s * ov) * face.D, face.y + (s * ou + c * ov) * face.D];
  }
  function fontOf(p, size, kind = p.kind ?? 'bold') {
    const style = p.style ?? (kind === 'thin' ? 'normal' : 'italic'), weight = p.weight ?? (kind === 'thin' ? 300 : kind === 'heavy' ? 900 : 800);
    return `${style} ${weight} ${Math.round(size)}px ${JSON.stringify(p.family)}`;
  }
  function shadowOf(ctx, shadow, size) {
    if (shadow === 'glow') { ctx.shadowColor = 'rgba(255,255,255,0.85)'; ctx.shadowBlur = size * .25; }
    else if (shadow === 'dark' || shadow === true) { ctx.shadowColor = 'rgba(0,0,0,0.55)'; ctx.shadowBlur = size * .12; ctx.shadowOffsetY = size * .05; }
  }
  // wobble: small per-boil-step jitter of a coordinate
  const wob = (r, s) => (r() - .5) * s;

  // --- kawaii shapes: drawn in a unit box (-.5..5), outline + fill ---------------------------------------------------
  function heartPath(x) { x.beginPath(); x.moveTo(0, .38); x.bezierCurveTo(-.55, 0, -.42, -.42, -.1, -.32); x.quadraticCurveTo(0, -.28, 0, -.18);
    x.quadraticCurveTo(0, -.28, .1, -.32); x.bezierCurveTo(.42, -.42, .55, 0, 0, .38); x.closePath(); }
  function starPath(x, n, r0, r1) { x.beginPath(); for (let i = 0; i < n * 2; i++) { const a = -Math.PI / 2 + i * Math.PI / n, r = i % 2 ? r1 : r0; i ? x.lineTo(Math.cos(a) * r, Math.sin(a) * r) : x.moveTo(Math.cos(a) * r, Math.sin(a) * r); } x.closePath(); }
  function kawaii(x, t, c, r) {
    const j = () => wob(r, .03);
    x.lineWidth = .07; x.lineJoin = 'round'; x.lineCap = 'round'; x.strokeStyle = c.line; x.fillStyle = c.fill;
    const both = () => { x.fill(); x.stroke(); };
    switch (t) {
      case 'heart': heartPath(x); both(); break;
      case 'hearto': heartPath(x); x.lineWidth = .09; x.stroke(); break;
      case 'star': starPath(x, 5, .48 + j(), .22); both(); break;
      case 'spark': starPath(x, 4, .5 + j(), .13); both(); break;
      case 'note': case 'note2': {
        const heads = t === 'note' ? [[-.12, .28]] : [[-.28, .3], [.22, .22]];
        for (const [hx, hy] of heads) { x.beginPath(); x.ellipse(hx, hy, .14, .11, -.4, 0, Math.PI * 2); x.fillStyle = c.line; x.fill(); x.beginPath(); x.moveTo(hx + .12, hy); x.lineTo(hx + .12, hy - .55); x.stroke(); }
        x.beginPath(); if (t === 'note') { x.moveTo(.0, -.27); x.quadraticCurveTo(.25, -.15, .2, .05); } else { x.moveTo(-.16, -.25); x.lineTo(.34, -.33); } x.lineWidth = .09; x.stroke(); break; }
      case 'bow': for (const s of [-1, 1]) { x.beginPath(); x.moveTo(0, 0); x.bezierCurveTo(s * .25, -.4, s * .55, -.2, s * .5, 0); x.bezierCurveTo(s * .55, .2, s * .25, .4, 0, 0); both(); }
        x.beginPath(); x.arc(0, 0, .09, 0, Math.PI * 2); x.fillStyle = c.blush; x.fill(); x.stroke(); break;
      case 'dots': for (const [dx, dy] of [[-.3, .1], [0, -.05], [.3, .1]]) { x.beginPath(); x.arc(dx + j(), dy + j(), .08, 0, Math.PI * 2); x.fillStyle = c.line; x.fill(); } break;
      case 'swirl': x.beginPath(); for (let i = 0; i <= 40; i++) { const a = i / 40 * Math.PI * 4, rr = .03 + i / 40 * .42; i ? x.lineTo(Math.cos(a) * rr, Math.sin(a) * rr) : x.moveTo(Math.cos(a) * rr, Math.sin(a) * rr); } x.stroke(); break;
      case 'squig': x.beginPath(); x.moveTo(-.45, 0); for (let i = 1; i <= 6; i++) x.quadraticCurveTo(-.45 + (i - .5) * .15, (i % 2 ? -.22 : .22) + j(), -.45 + i * .15, 0); x.stroke(); break;
      case 'arrow': x.beginPath(); x.moveTo(-.42, .25); x.quadraticCurveTo(-.05, -.35, .38, -.12); x.stroke(); x.beginPath(); x.moveTo(.2, -.28); x.lineTo(.4, -.12); x.lineTo(.2, .03); x.stroke(); break;
      case 'cross': x.lineWidth = .11; x.beginPath(); x.moveTo(0, -.38); x.lineTo(0, .38); x.moveTo(-.38, 0); x.lineTo(.38, 0); x.stroke(); break;
      case 'dash3': x.lineWidth = .09; for (const a of [-.5, 0, .5]) { x.beginPath(); x.moveTo(Math.sin(a) * .12, -Math.cos(a) * .12); x.lineTo(Math.sin(a) * .45, -Math.cos(a) * .45); x.stroke(); } break;
      case 'blush': x.beginPath(); x.ellipse(0, 0, .45, .24, 0, 0, Math.PI * 2); x.fillStyle = c.blush; x.globalAlpha *= .75; x.fill(); x.globalAlpha /= .75;
        x.lineWidth = .06; for (const dx of [-.2, 0, .2]) { x.beginPath(); x.moveTo(dx + .07, -.12); x.lineTo(dx - .07, .12); x.stroke(); } break;
      case 'ear': x.beginPath(); x.moveTo(-.42, .38); x.quadraticCurveTo(-.3, -.3, .02, -.46); x.quadraticCurveTo(.3, -.2, .42, .38); x.closePath(); both();
        x.beginPath(); x.moveTo(-.22, .3); x.quadraticCurveTo(-.12, -.12, .02, -.24); x.quadraticCurveTo(.16, -.08, .22, .3); x.closePath(); x.fillStyle = c.blush; x.fill(); break;
      case 'whisk': x.lineWidth = .09; for (const dy of [-.18, 0, .18]) { x.beginPath(); x.moveTo(-.45, dy * .6); x.quadraticCurveTo(0, dy * 1.4 - .05, .45, dy * 1.9); x.stroke(); } break;
    }
  }
  function drawKawaii(ctx, t, cx, cy, size, rot, c, r, alpha = 1) {
    if (size <= 0) return;
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot); ctx.scale(size, size); ctx.globalAlpha *= alpha; kawaii(ctx, t, c, r); ctx.restore();
  }
  // --- ink shapes (doodles): rough strokes ----------------------------------------------------------------------------
  function ink(x, t, r) {
    const j = () => wob(r, .06); x.lineWidth = .08; x.lineCap = 'round'; x.lineJoin = 'round';
    const line = pts => { x.beginPath(); pts.forEach(([a, b], i) => i ? x.lineTo(a + j(), b + j()) : x.moveTo(a + j(), b + j())); x.stroke(); };
    switch (t) {
      case 'zig': line([[-.45, .1], [-.25, -.15], [-.05, .12], [.15, -.15], [.35, .1], [.48, -.08]]); break;
      case 'scratch': for (let i = 0; i < 4; i++) line([[-.35 + i * .18, .3], [-.15 + i * .18, -.3]]); break;
      case 'splat': x.beginPath(); for (let i = 0; i <= 14; i++) { const a = i / 14 * Math.PI * 2, rr = (i % 2 ? .2 : .36) + j(); i ? x.lineTo(Math.cos(a) * rr, Math.sin(a) * rr) : x.moveTo(Math.cos(a) * rr, Math.sin(a) * rr); } x.closePath(); x.fill(); break;
      case 'rays': for (let i = 0; i < 7; i++) { const a = -Math.PI * .9 + i * Math.PI * .3; line([[Math.cos(a) * .18, Math.sin(a) * .18], [Math.cos(a) * .48, Math.sin(a) * .48]]); } break;
      case 'arrow': line([[-.45, .3], [.35, -.25]]); line([[.12, -.3], [.38, -.27], [.3, -.02]]); break;
      case 'spark': starPath(x, 4, .48, .1); x.fill(); break;
      case 'cross': line([[-.38, -.38], [.38, .38]]); line([[.38, -.38], [-.38, .38]]); break;
      case 'hatch': for (let i = -2; i <= 2; i++) { line([[-.4, i * .16], [.4, i * .16 + .1]]); line([[i * .16, -.4], [i * .16 + .1, .4]]); } break;
      case 'star': starPath(x, 5, .46, .2); x.stroke(); break;
      case 'xx': for (const dx of [-.25, .25]) { line([[dx - .18, -.18], [dx + .18, .18]]); line([[dx + .18, -.18], [dx - .18, .18]]); } break;
      case 'bolt': x.beginPath(); [[.05, -.5], [-.25, .05], [0, .05], [-.1, .5], [.28, -.1], [.03, -.1], [.15, -.5]].forEach(([a, b], i) => i ? x.lineTo(a, b) : x.moveTo(a, b)); x.closePath(); x.fill(); break;
      case 'bang': x.lineWidth = .14; line([[0, -.45], [0, .15]]); x.beginPath(); x.arc(0, .36, .08, 0, Math.PI * 2); x.fill(); break;
    }
  }
  function blob(ctx, cx, cy, rr, r, lobes = 5) {
    ctx.beginPath();
    for (let i = 0; i <= 40; i++) { const a = i / 40 * Math.PI * 2, k = 1 + .22 * Math.sin(a * lobes + r() * 6) + .1 * Math.sin(a * (lobes * 2 + 1)); i ? ctx.lineTo(cx + Math.cos(a) * rr * k, cy + Math.sin(a) * rr * k) : ctx.moveTo(cx + Math.cos(a) * rr * k, cy + Math.sin(a) * rr * k); }
    ctx.closePath(); ctx.fill();
  }
  function star4(ctx, cx, cy, r, rot, fill, line, lw) {
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot); ctx.beginPath();
    for (let i = 0; i < 8; i++) { const a = i * Math.PI / 4, rr = i % 2 ? r * .22 : r; i ? ctx.lineTo(Math.cos(a) * rr, Math.sin(a) * rr) : ctx.moveTo(Math.cos(a) * rr, Math.sin(a) * rr); }
    ctx.closePath(); ctx.fillStyle = fill; ctx.fill(); if (lw > 0) { ctx.strokeStyle = line; ctx.lineWidth = lw; ctx.lineJoin = 'round'; ctx.stroke(); } ctx.restore();
  }
  function typed(ctx, p, x, y, size, count, rot) {   // mixed-weight parts, left-to-right reveal, centred on the full line
    const parts = p.parts ?? [[p.text ?? p.v, p.kind ?? 'bold']], chars = parts.flatMap(([t, k]) => Array.from(t, ch => ({ch, k})));
    const widths = chars.map(c => { ctx.font = fontOf(p, size, c.k); return ctx.measureText(c.ch).width; }), total = widths.reduce((a, b) => a + b, 0);
    ctx.save(); ctx.translate(x, y); ctx.rotate(rot); ctx.textBaseline = 'middle'; ctx.textAlign = 'left'; ctx.lineJoin = 'round';
    let cx = -total / 2;
    for (let i = 0; i < Math.min(count, chars.length); i++) {
      ctx.font = fontOf(p, size, chars[i].k);
      if (p.stroke !== undefined || p.lw) { ctx.strokeStyle = p.stroke ?? '#1a1a1a'; ctx.lineWidth = p.lw ?? size * .1; ctx.strokeText(chars[i].ch, cx, 0); }
      ctx.save(); shadowOf(ctx, p.shadow, size); ctx.fillStyle = p.fill ?? '#ffffff'; ctx.fillText(chars[i].ch, cx, 0); ctx.restore();
      cx += widths[i];
    }
    ctx.restore();
  }

  function draw(ctx, name, p, s) {
    if (!(name in orders)) return false;
    p = p === true ? {} : p;
    const {W: w, H: h, elapsed: t, frame, face} = s, m = Math.min(w, h), step3 = Math.floor(frame / 3), r = rng(((p.seed ?? 1) * 7919 + step3 * 31 + name.length) | 0);
    if (FACE.includes(name) && !face) return true;   // face graphics need a tracked face
    ctx.save(); ctx.resetTransform();
    const D = face?.D ?? m * .12, a = face?.a ?? 0;
    switch (name) {
      case 'stairs': {
        const sz = p.size ?? m * .085, cx = (p.x ?? .3) * w, cy = (p.y ?? .32) * h, rs = rng(((p.seed ?? 3) * 131 + Math.floor(frame / 4)) | 0);
        const cells = p.cells ?? [[0, 0], [1, 0], [1, 1], [2, 1], [2, 2], [3, 2], [3, 3], [4, 3], [-1, 1], [-2, 2], [5, 4], [0, 3]];
        cells.forEach(([cx_, cy_], i) => { if (rs() < .12) return;   // ~12% dropped each boil step
          ctx.fillStyle = i % 3 === 2 ? (p.color2 ?? '#c98be0') : (p.color ?? '#ffc6e4'); ctx.globalAlpha = .9;
          ctx.fillRect(cx + cx_ * sz * 1.15 + wob(rs, sz * .12), cy + cy_ * sz * 1.15 + wob(rs, sz * .12), sz, sz); });
        break; }
      case 'glow': {
        const c = buffer(w, h), cc = c.getContext('2d'); cc.filter = `blur(${p.blur ?? 8}px)`; cc.drawImage(ctx.canvas, 0, 0);
        ctx.globalCompositeOperation = 'screen'; ctx.globalAlpha = clamp(p.amt ?? p.v ?? .35); ctx.drawImage(c, 0, 0); break; }
      case 'glint': {
        const at = p.at ?? 0, d = p.d ?? .5; if (t < at) break;
        const map = pt => p.src && s.matrix ? [s.matrix[0] * pt[0] + s.matrix[2] * pt[1] + s.matrix[4], s.matrix[1] * pt[0] + s.matrix[3] * pt[1] + s.matrix[5]] : [pt[0] * w, pt[1] * h];
        const [x0, y0] = map(p.from ?? [.22, .3]), [x1, y1] = map(p.to ?? [.5, .42]), u = clamp((t - at) / d), e = 1 - (1 - u) ** 3;
        const x = x0 + (x1 - x0) * e, y = y0 + (y1 - y0) * e, R = p.r ?? m * .42, rot = t * 1.4;
        ctx.strokeStyle = '#ffffff'; ctx.lineWidth = Math.max(1, R * .03); ctx.globalAlpha = .9;
        for (let i = 0; i < 4; i++) { const aa = rot * -.5 + i * Math.PI / 2 + Math.PI / 4; ctx.beginPath(); ctx.moveTo(x + Math.cos(aa) * R * .5, y + Math.sin(aa) * R * .5); ctx.lineTo(x + Math.cos(aa) * R * 1.7, y + Math.sin(aa) * R * 1.7); ctx.stroke(); }
        ctx.globalAlpha = 1; star4(ctx, x, y, R, rot, p.color ?? ACCENT, INK, R * .07);
        ctx.beginPath(); ctx.arc(x, y, R * .2, 0, Math.PI * 2); ctx.fillStyle = '#ffffff'; ctx.fill(); break; }
      case 'doodles': {
        const n = p.n ?? [0, 5, 10, 16][Math.round(p.v ?? 1)], types = p.types ?? ['zig', 'spark', 'cross', 'rays', 'bolt', 'bang', 'star', 'xx'];
        const cx = face ? face.x : w / 2, cy = face ? face.y + D * .6 : h / 2, R = face ? D * 2.4 : m * .32, rp = rng(((p.seed ?? 5) * 977) | 0);
        for (let i = 0; i < n + (p.scratch ?? 0); i++) {
          const ang = (i / Math.max(1, n + (p.scratch ?? 0))) * Math.PI * 2 + rp() * .5, rad = R * (.85 + rp() * .35), shape = i >= n ? 'scratch' : types[Math.floor(rp() * types.length)];
          const x = cx + Math.cos(ang) * rad * (w > h ? 1.2 : 1), y = cy + Math.sin(ang) * rad, sz = (face ? D : m * .1) * (.5 + rp() * .35);
          if (x < -sz || x > w + sz || y < -sz || y > h + sz) continue;
          ctx.save(); ctx.translate(x + wob(r, sz * .05), y + wob(r, sz * .05)); ctx.rotate(rp() * 6.28); ctx.scale(sz, sz);
          const col = p.mono ? INK : (i % 3 === 1 ? (p.color ?? ACCENT) : INK); ctx.strokeStyle = col; ctx.fillStyle = col; ink(ctx, shape, r); ctx.restore();
        }
        break; }
      case 'face_doodles': {
        const c = pal(p), rp = rng(((p.seed ?? 2) * 613) | 0);
        const auto = [[-1.45, -1.05], [1.45, -1.05], [-1.7, .25], [1.7, .25], [0, -1.85], [-1.25, 1.35], [1.25, 1.35], [-2.1, -.5], [2.1, -.5]];
        const pool = p.pool ?? ['heart', 'spark', 'star', 'note', 'bow'];
        const items = p.items ?? Array.from({length: p.n ?? 4}, (_, i) => ({t: pool[Math.floor(rp() * pool.length)], o: auto[i % auto.length], s: .55 + rp() * .2, r: (rp() - .5) * .6, at: i * .08}));
        for (const it of items) { const [x, y] = facePt(face, ...(it.o ?? [1.4, -1])); drawKawaii(ctx, it.t, x, y, D * (it.s ?? .6) * pop(t - (it.at ?? 0)), a + (it.r ?? 0) + wob(r, .08), c, r); }
        break; }
      case 'doodle': {
        const sz = (p.size ?? m * .1) * pop(t - (p.at ?? 0)), [px, py] = p.pos ?? [.5, .5];
        drawKawaii(ctx, p.t ?? 'heart', px * w, py * h, sz, (p.rot ?? 0) + wob(r, .06), pal(p), r, p.alpha ?? 1); break; }
      case 'word': {
        const age = t - (p.at ?? 0); if (age < 0) break;
        const f = Math.floor(age * s.fps + 1e-6), sc = POP3[Math.min(2, f)], k = p.k ?? 1;
        const size = clamp(D * .95 * k, (p.min ?? 28) * w / 1440, (p.max ?? 260) * w / 1440);
        const [x, y] = face ? facePt(face, p.dx ?? 0, p.dy ?? 1.7) : [w * .5, h * .6];
        ctx.translate(x, y); ctx.rotate(face ? a : 0); ctx.scale(sc, sc); ctx.font = fontOf(p, size); ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round';
        ctx.strokeStyle = p.stroke ?? '#c98be0'; ctx.lineWidth = p.lw ?? size * .16; ctx.strokeText(p.text ?? p.v, 0, 0);
        shadowOf(ctx, p.shadow, size); ctx.fillStyle = p.fill ?? '#ffffff'; ctx.fillText(p.text ?? p.v, 0, 0); break; }
      case 'type': {
        const age = t - (p.at ?? 0); if (age < 0) break;
        const count = (p.base ?? 0) + Math.floor(age / (p.dt ?? .06)) + 1, size = clamp(D * .7 * (p.k ?? 1), (p.min ?? 22) * w / 1440, (p.max ?? 200) * w / 1440);
        const [x, y] = face ? facePt(face, p.dx ?? 0, p.dy ?? 2.1) : [(p.pos?.[0] ?? .5) * w, (p.pos?.[1] ?? .8) * h];
        typed(ctx, p, x, y, size, count, face ? a : 0); break; }
      case 'slash': {
        const age = t - (p.at ?? 0); if (age < 0) break;
        const [ox, oy] = face ? facePt(face, p.dx ?? 0, p.dy ?? .4) : [w / 2, h / 2], n = p.n ?? 4, rp = rng(((p.seed ?? 4) * 389) | 0), grow = clamp(age / .22), fade = clamp(1 - (age - .5) / .4);
        ctx.globalAlpha = fade; ctx.fillStyle = p.fill ?? '#ffffff'; ctx.strokeStyle = p.stroke ?? '#c98be0'; ctx.lineWidth = Math.max(1, m * .004); ctx.lineJoin = 'round';
        for (let i = 0; i < n; i++) {
          const ang = -.32 + (rp() - .5) * .25, off = (i - (n - 1) / 2) * m * .045, L = m * (.42 + rp() * .3) * (1 - (1 - grow) ** 2), wd = m * (.012 + rp() * .01);
          const nx = -Math.sin(ang), ny = Math.cos(ang), x0 = ox + nx * off - Math.cos(ang) * L * .5, y0 = oy + ny * off - Math.sin(ang) * L * .5;
          ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + Math.cos(ang) * L * .55 + nx * wd, y0 + Math.sin(ang) * L * .55 + ny * wd);
          ctx.lineTo(x0 + Math.cos(ang) * L, y0 + Math.sin(ang) * L); ctx.lineTo(x0 + Math.cos(ang) * L * .55 - nx * wd * .4, y0 + Math.sin(ang) * L * .55 - ny * wd * .4); ctx.closePath(); ctx.fill(); ctx.stroke();
        }
        break; }
      case 'sparkle': {
        const [px, py] = p.pos ?? [.5, .5], R = p.r ?? m * .1, x = px * w, y = py * h, rp = rng(((p.seed ?? 6) * 211) | 0);
        star4(ctx, x, y, R * (1 + wob(r, .06)), step3 * .05, p.color ?? '#fff1a8', INK, Math.max(1, R * .06));
        ctx.fillStyle = INK; for (let i = 0; i < 7; i++) { const aa = rp() * 6.28, rr = R * (1.15 + rp() * .5); ctx.beginPath(); ctx.arc(x + Math.cos(aa) * rr, y + Math.sin(aa) * rr, R * (.03 + rp() * .04), 0, Math.PI * 2); ctx.fill(); }
        break; }
      case 'splat': {
        for (const [k, f] of (p.items ?? [p]).entries()) {
          const [px, py] = f.pos ?? [.5, .5], R = f.r ?? m * .12, x = px * w, y = py * h, rp = rng(((f.seed ?? p.seed ?? 8) * 307 + k) | 0);
          ctx.fillStyle = f.color ?? p.color ?? ACCENT; blob(ctx, x, y, R * .42, rp);
          for (let i = 0; i < (f.n ?? 12); i++) { const aa = rp() * 6.28, rr = R * (.45 + rp() * .6); ctx.fillStyle = rp() < .25 ? (f.color2 ?? p.color2 ?? INK) : (f.color ?? p.color ?? ACCENT); blob(ctx, x + Math.cos(aa) * rr, y + Math.sin(aa) * rr, R * (.04 + rp() * .1), rp, 3); }
        }
        break; }
      case 'bw': {
        const c = buffer(w, h), cc = c.getContext('2d'); cc.filter = p.filter ?? 'grayscale(1) contrast(1.1)'; cc.drawImage(ctx.canvas, 0, 0);
        ctx.globalCompositeOperation = 'copy'; ctx.drawImage(c, 0, 0); ctx.globalCompositeOperation = 'source-over';
        const [top, bottom] = p.bars ?? [0, 0]; ctx.fillStyle = p.color ?? '#000000'; if (top) ctx.fillRect(0, 0, w, top); if (bottom) ctx.fillRect(0, h - bottom, w, bottom); break; }
      case 'tag': {
        const size = p.size ?? h * .1, txt = p.text ?? p.v, faceRel = face && p.pos !== 'bottom';
        const x = faceRel ? face.x + (p.dx ?? 1.25) * D * 2.2 : (p.bx ?? .5) * w, y = faceRel ? face.y : (p.by ?? .9) * h;
        ctx.font = fontOf({...p, style: p.style ?? 'normal', weight: p.weight ?? 500}, size); ctx.textAlign = faceRel ? 'left' : 'center'; ctx.textBaseline = 'middle';
        ctx.shadowColor = 'rgba(0,0,0,0.7)'; ctx.shadowBlur = size * .18; ctx.shadowOffsetY = size * .06; ctx.fillStyle = p.fill ?? '#ffffff'; ctx.fillText(txt, x, y); break; }
      case 'border': {
        const lw = m * .018, rp = rng(((p.seed ?? 9) * 53 + step3) | 0); ctx.strokeStyle = p.color ?? INK; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        const edge = (x0, y0, x1, y1) => { const n = 14; ctx.beginPath(); for (let i = 0; i <= n; i++) { const u = i / n; ctx.lineTo(x0 + (x1 - x0) * u + wob(rp, lw * .8), y0 + (y1 - y0) * u + wob(rp, lw * .8)); } ctx.lineWidth = lw * (.8 + rp() * .6); ctx.stroke(); };
        const i = lw * .6; edge(i, i, w - i, i); edge(w - i, i, w - i, h - i); edge(w - i, h - i, i, h - i); edge(i, h - i, i, i);
        ctx.lineWidth = lw * .35; edge(i * 3, i * 2.2, w * .4, i * 2.6); edge(w - i * 2.4, h * .55, w - i * 2.2, h - i * 3); break; }
      case 'cheeks': {
        if (D < 30 && !p.force) break;   // too small to read
        ctx.lineWidth = Math.max(1.5, D * .07); ctx.lineJoin = 'round'; ctx.lineCap = 'round';
        for (const sx of [-1, 1]) {
          const pts = [-.25, -.08, .08, .25].map((ou, i) => facePt(face, sx * .55 + ou, .55 + (i % 2 ? .1 : -.02)));
          for (const [col, off] of [['rgba(0,0,0,0.45)', D * .03], [p.color ?? '#ff4f8b', 0]]) { ctx.strokeStyle = col; ctx.beginPath(); pts.forEach(([x, y], i) => i ? ctx.lineTo(x + off, y + off) : ctx.moveTo(x + off, y + off)); ctx.stroke(); }
        }
        break; }
      case 'fangs': {
        if (D < 30 && !p.force) break;
        const len = (p.len ?? .3) * D * .9, dy = (face.mv ?? 1.12) + (p.dy ?? 0), mx = face.mu ?? 0;   // measured mouth, else 1.12 eye units below the eyes
        ctx.fillStyle = p.color ?? '#ffffff'; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, D * .025);
        for (const sx of [-1, 1]) { const [x0, y0] = facePt(face, mx + sx * .2 - .07, dy), [x1, y1] = facePt(face, mx + sx * .2 + .07, dy), [x2, y2] = facePt(face, mx + sx * .2, dy + len / D);
          ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.lineTo(x2, y2); ctx.closePath(); ctx.fill(); ctx.stroke(); }
        break; }
      case 'ears': {
        const c = pal(p), sz = D * 1.1 * (p.size ?? 1) * pop(t - (p.at ?? 0));
        for (const sx of [-1, 1]) { let [x, y] = facePt(face, sx * .95 + (p.dx ?? 0) * sx, -1.65 + (p.dy ?? 0)); y = Math.max(y, sz * .5);   // kept inside the frame
          drawKawaii(ctx, 'ear', x, y, sz, a + sx * .25, c, r); }
        break; }
      case 'whisk': {
        const c = pal(p), sz = D * 1.05 * pop(t - (p.at ?? 0));
        for (const sx of [-1, 1]) { const [x, y] = facePt(face, sx * (1.15 + (p.dx ?? 0)), .8 + (p.dy ?? 0)); ctx.save(); ctx.translate(x, y); ctx.scale(sx, 1); drawKawaii(ctx, 'whisk', 0, 0, sz, a * sx, c, r); ctx.restore(); }
        break; }
      case 'blush': {
        const c = pal(p), sz = D * .42 * (p.size ?? 1) * pop(t - (p.at ?? 0));
        for (const sx of [-1, 1]) { const [x, y] = facePt(face, sx * (.78 + (p.dx ?? 0)), .62 + (p.dy ?? 0)); drawKawaii(ctx, 'heart', x, y, sz, a + sx * .2, {...c, fill: c.blush}, r); }
        break; }
      case 'ast': {
        const c = pal(p), sz = D * .32 * (p.size ?? 1), [x, y] = facePt(face, (face.nu ?? 0) + (p.dx ?? 0), (face.nv ?? .6) + (p.dy ?? 0));   // on the measured nose tip when tracked
        ctx.translate(x, y); ctx.rotate(t * 3); ctx.strokeStyle = c.line; ctx.lineWidth = Math.max(1.5, sz * .18); ctx.lineCap = 'round';
        for (let i = 0; i < 3; i++) { const aa = i * Math.PI / 3; ctx.beginPath(); ctx.moveTo(-Math.cos(aa) * sz, -Math.sin(aa) * sz); ctx.lineTo(Math.cos(aa) * sz, Math.sin(aa) * sz); ctx.stroke(); }
        break; }
    }
    ctx.restore();
    return true;
  }
  return {orders, phase, draw};
})();
