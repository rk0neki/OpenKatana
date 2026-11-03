/* Project hooks (audit F-NAT-011): a project may declare one script (timeline `hooks.src`) that registers custom
   layers and text types. It runs inside the headless render page: same-origin CSP, no network beyond the loopback
   project server (render.py aborts every other request), a seeded Math.random per frame, and its hash is recorded in
   the render receipt. A throwing hook stops the render with its own message. */
'use strict';
window.OpenKatanaHooks = (() => {
  const layers = {}, texts = {}, inited = new Set(), violations = [], assets = new Set();
  // the page CSP blocks off-origin requests before they reach the network; keep a record for the render receipt
  document.addEventListener('securitypolicyviolation', e => { if (violations.length < 200) violations.push(`${e.violatedDirective}: ${String(e.blockedURI).slice(0, 200)}`); });
  const name = n => { if (typeof n !== 'string' || !/^[A-Za-z_][A-Za-z0-9_-]{0,63}$/.test(n)) throw Error(`Hook name ${JSON.stringify(n)} is invalid`); return n; };
  // OpenKatana API: layer(name, {phase, order, prepare(params, info), draw(ctx, params, info)}), text(name, {init(item, index), draw(ctx, item, info, index)})
  function layer(n, spec) { if (typeof spec?.draw !== 'function') throw Error(`Hook layer ${n} needs draw()`); layers[name(n)] = spec; }
  function text(n, spec) { if (typeof spec?.draw !== 'function') throw Error(`Hook text type ${n} needs draw()`); texts[name(n)] = spec; }
  function drawLayer(n, ctx, params, info) {
    const spec = layers[n]; if (!spec) throw Error(`Hook layer "${n}" was declared but not registered by the hook script`);
    ctx.save(); try { spec.draw(ctx, params, info); } finally { ctx.restore(); }
  }
  function drawText(n, ctx, item, info, index) {
    const spec = texts[n]; if (!spec) throw Error(`Hook text type "${n}" was declared but not registered by the hook script`);
    const key = n + ':' + index; if (spec.init && !inited.has(key)) { spec.init(item, index); inited.add(key); }
    ctx.save(); try { spec.draw(ctx, item, info, index); } finally { ctx.restore(); }
  }
  // prepare(params, info) names the project images a layer needs for this frame; the engine loads and decodes them
  // before draw(), which finds them in info.images[path]. Paths are project-relative images; each one loaded is listed,
  // with its SHA-256, in the render receipt.
  const IMAGE_PATH = /^(?!.*(?:^|\/)\.\.?(?:\/|$))[A-Za-z0-9_][A-Za-z0-9_. \/-]*\.(?:png|jpe?g|webp)$/i;
  function prepare(n, params, info) {
    const spec = layers[n]; if (!spec?.prepare) return [];
    const paths = spec.prepare(params, info) ?? [];
    if (!Array.isArray(paths)) throw Error(`Hook layer ${n}: prepare() must return an array of project image paths`);
    if (paths.length > 32) throw Error(`Hook layer ${n}: prepare() may request at most 32 images per frame`);
    for (const path of paths) if (typeof path !== 'string' || !IMAGE_PATH.test(path))
      throw Error(`Hook layer ${n}: prepare() path ${JSON.stringify(path)} is not a project-relative .png/.jpg/.webp path`);
    return paths;
  }
  const record = path => { if (assets.size < 100000) assets.add(path); };
  const defaults = n => ({phase: layers[n]?.phase ?? 'over', order: layers[n]?.order});
  function missing(declared) {
    return [...(declared.layers ?? []).filter(n => !layers[n]).map(n => 'layer ' + n), ...(declared.text_types ?? []).filter(n => !texts[n]).map(n => 'text type ' + n)];
  }
  function reset() { for (const k of Object.keys(layers)) delete layers[k]; for (const k of Object.keys(texts)) delete texts[k]; inited.clear(); assets.clear(); }
  return {layer, text, prepare, record, drawLayer, drawText, defaults, missing, reset, violations: () => violations.slice(), assets: () => [...assets].sort()};
})();
