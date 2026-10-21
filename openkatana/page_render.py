"""Deterministic HTML/CSS/SVG/Canvas page rendering (audit F-RT-001). A project page defines
`window.openkatanaPage = {width, height, fps, frames, render(t, f)}`; frame f is drawn by `render(f / fps, f)` and captured
as PNG. Before capture, sample frames are rendered forward and then in reverse and must match (the page must not
depend on call order or wall-clock time). The page runs in the headless render browser with a same-origin CSP
(inline scripts allowed for the page itself), every request outside the loopback project server is aborted, and
Math.random is seeded per frame. The result is a clip (frames_dir, n, fps, w, h) to use in a timeline."""
import json
import threading
from functools import partial
from .http_runtime import LocalHTTPServer
from pathlib import Path

from .contracts import ContractError, local_path, number
from .render import Handler, chrome_path, digest, guard_page, write_json

PAGE_CSP = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; media-src 'self'"
SEED = """() => { let a = 0x9E3779B9; window.__okSeed = f => { a = (f * 2654435761 + 97) >>> 0; };
  Math.random = () => { a = (a + 0x6D2B79F5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  window.__okViolations = []; document.addEventListener('securitypolicyviolation', e => window.__okViolations.push(`${e.violatedDirective}: ${String(e.blockedURI).slice(0, 200)}`)); }"""


class PageHandler(Handler):
    def end_headers(self):
        self.send_header('Content-Security-Policy', PAGE_CSP)
        super(Handler, self).end_headers()


def render_page(root, page, out, frames=None, fps=None, sample=5):
    root = Path(root).resolve()
    src = local_path(root, page)
    if src.suffix.lower() not in ('.html', '.htm') or not src.is_file():
        raise ContractError('page: an existing .html file inside the project')
    from .render import playwright
    sync_playwright = playwright()
    out.mkdir(parents=True, exist_ok=False); (out / 'frames').mkdir()
    server = LocalHTTPServer(('127.0.0.1', 0), partial(PageHandler, project=root))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    rel = src.relative_to(root).as_posix()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chrome_path(), headless=True, args=['--disable-gpu'])
            try:
                page_ = browser.new_page(viewport={'width': 64, 'height': 64})
                blocked = guard_page(page_, server.server_port)
                page_.add_init_script(f'({SEED})()')
                page_.goto(f'http://127.0.0.1:{server.server_port}/project/{rel}')
                info = page_.evaluate("""() => { const p = window.openkatanaPage ?? window.hfPage; window.openkatanaPage = p; if (!p || typeof p.render !== 'function') return null;
                    return {width: p.width, height: p.height, fps: p.fps, frames: p.frames}; }""")
                if not info:
                    raise ContractError(f'{rel}: the page must define window.openkatanaPage = {{width, height, fps, frames, render(t, f)}}')
                W, H = int(info['width'] or 0), int(info['height'] or 0)
                fps = fps or info['fps']; frames = frames or info['frames']
                number(W, 'openkatanaPage.width', 16, 7680, integer=True); number(H, 'openkatanaPage.height', 16, 7680, integer=True)
                number(fps, 'fps', 1, 240); number(frames, 'frames', 1, 36000, integer=True)
                page_.set_viewport_size({'width': W, 'height': H})

                def shot(f):
                    page_.evaluate('([t, f]) => { window.__okSeed(f); return window.openkatanaPage.render(t, f); }', [f / fps, f])
                    return page_.screenshot(clip={'x': 0, 'y': 0, 'width': W, 'height': H}, animations='disabled')

                picks = sorted({round(k * (frames - 1) / max(1, sample - 1)) for k in range(sample)})
                forward = {f: digest_bytes(shot(f)) for f in picks}
                reverse = {f: digest_bytes(shot(f)) for f in reversed(picks)}
                bad = [f for f in picks if forward[f] != reverse[f]]
                if bad:
                    raise ContractError(f'{rel}: not deterministic â€” frames {bad} differ when rendered in reverse order')
                for f in range(frames):
                    (out / 'frames' / f'{f:05d}.png').write_bytes(shot(f))
                blocked += page_.evaluate('() => window.__okViolations || []')
            finally:
                browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join()
    clip = {'frames_dir': (out / 'frames').relative_to(root).as_posix(), 'pattern': '%05d.png', 'n': frames, 'fps': fps, 'w': W, 'h': H}
    receipt = {'page': rel, 'page_sha256': digest(src), 'clip': clip, 'determinism_sample': picks, 'blocked_requests': blocked,
               'time_basis': 'render(t = f / fps, f)'}
    write_json(out / 'page-render.json', receipt)
    return receipt


def digest_bytes(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()
