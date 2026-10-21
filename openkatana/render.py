from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler
from .http_runtime import LocalHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .contracts import ContractError, local_path, validate


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def run(args):
    p = subprocess.run([str(a) for a in args], capture_output=True, text=True, encoding='utf-8', errors='replace', stdin=subprocess.DEVNULL)   # never read the MCP stdio stream
    if p.returncode:
        raise RuntimeError(f'{Path(str(args[0])).name} failed: {p.stderr[-4000:]}')
    return p.stdout


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', path]))


# ffmpeg 7.1+ tags the stream from the filtered frames' properties, so the output -color_primaries/-color_trc options
# are ignored and untagged PNGs left both "unknown" (only colorspace and range were negotiated). setparams tags the
# frames themselves; it changes no pixels, only the SPS colour description (primaries/transfer 2 -> 1).
VIDEO_ENCODE = ['-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,'
                       'setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709',
                '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
                '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709']


def encode(frames: Path, canvas: dict, movie: Path, soundtrack: Path | None = None, mixed: Path | None = None):
    """Encode the rendered PNGs to exactly canvas['frames'] H.264 frames, with a copied soundtrack or a mixed WAV.
    `-frames:v` ends the whole output at the last picture, which drops the AAC packets that run a few ms past it
    (encoder padding, e.g. 1526 -> 1525 packets), so a copied soundtrack is muxed afterwards by stream copy of both
    streams with nothing limiting either; audio validation already bounds how far it may run past the picture."""
    args = ['ffmpeg', '-v', 'error', '-framerate', str(canvas['fps']), '-start_number', '0', '-i', frames / '%05d.png']
    if mixed:
        args += ['-i', mixed]
    args += ['-map', '0:v:0']
    if mixed:
        args += ['-map', '1:a:0', '-c:a', 'aac', '-b:a', '256k']
    picture = movie.with_name(movie.stem + '.picture.mp4') if soundtrack else movie
    run(args + ['-frames:v', str(canvas['frames']), *VIDEO_ENCODE, '-movflags', '+faststart', picture])
    if soundtrack:
        run(['ffmpeg', '-v', 'error', '-i', picture, '-i', soundtrack, '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy',
             '-movflags', '+faststart', movie])
        picture.unlink()


def audio_packets(path) -> dict:
    """Packet count, summed duration and md5 of the first audio stream's packets, read without decoding."""
    packets = json.loads(run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'packet=duration_time',
                              '-of', 'json', path])).get('packets', [])
    md5 = run(['ffmpeg', '-v', 'error', '-i', path, '-map', '0:a:0', '-c', 'copy', '-f', 'md5', '-']).strip()
    return {'packets': len(packets), 'seconds': round(sum(float(p.get('duration_time', 0)) for p in packets), 6), 'md5': md5}


def soundtrack_check(source, movie):
    """Compare a copied soundtrack with its source packet for packet: (unchanged, details, problem or None)."""
    src, out = audio_packets(source), audio_packets(movie)
    details = {'source': src, 'output': out}
    if src['md5'] == out['md5']:
        return True, details, None
    lost, ms = src['packets'] - out['packets'], (src['seconds'] - out['seconds']) * 1000
    if lost > 0:
        problem = f'copied soundtrack lost {lost} of {src["packets"]} packets / {ms:.1f} ms'
    elif lost < 0:
        problem = f'copied soundtrack gained {-lost} packets / {-ms:.1f} ms over the {src["packets"]} in the source'
    else:
        problem = f'copied soundtrack changed: same {src["packets"]} packets, different bytes'
    return False, details, problem


def playwright():
    """The render runtime (Playwright drives the local browser); a clear error when it is not installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError('The render runtime (Playwright) is not installed in this environment; install OpenKatana with its '
                           'render dependencies and check `openkatana doctor`') from e
    return sync_playwright


ENGINE_GLOBALS = ('OpenKatana', 'OpenKatanaText', 'OpenKatanaFaces', 'OpenKatanaLetterforms', 'OpenKatanaGraffiti', 'OpenKatanaEffects',
                  'OpenKatanaTransitions', 'OpenKatanaStudio', 'OpenKatanaLocal', 'OpenKatanaStickers', 'OpenKatanaDecor', 'OpenKatanaHooks')


def open_engine(page, port, attempts=2):
    """Load the render page and make sure every engine script ran. A transient failure to serve one of the scripts
    (seen once under heavy load) would otherwise surface later as an unrelated ReferenceError; the page is reloaded once,
    then the error names what did not load."""
    problems = []
    page.on('requestfailed', lambda r: problems.append(f'{r.url}: {r.failure}') if '/app/' in r.url else None)
    page.on('response', lambda r: problems.append(f'{r.url}: HTTP {r.status}') if r.status >= 400 and '/app/' in r.url else None)
    page.on('pageerror', lambda e: problems.append(f'script error: {e}'))
    check = '() => ' + json.dumps(list(ENGINE_GLOBALS)) + '.filter(name => typeof window[name] === "undefined")'
    for attempt in range(attempts):
        problems.clear()
        page.goto(f'http://127.0.0.1:{port}/app/render.html')
        missing = page.evaluate(check)
        if not missing:
            return
    raise RuntimeError(f'The render page did not load its engine ({", ".join(missing)} undefined): ' + ('; '.join(problems[-6:]) or 'no failed request recorded'))


def chrome_path():
    options = [os.environ.get('OPENKATANA_CHROME'), shutil.which('google-chrome'), shutil.which('chromium'),
               r'C:\Program Files\Google\Chrome\Application\chrome.exe',
               r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
               '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    for name in options:
        if name and Path(name).is_file():
            return name
    raise RuntimeError('Chrome not found; set OPENKATANA_CHROME to an installed browser executable')


def guard_page(page, port):
    """Only the loopback project server is reachable from the render page (project hooks included); every other
    request is aborted and recorded."""
    blocked = []
    allowed = f'http://127.0.0.1:{port}/'
    def route(r):
        url = r.request.url
        if url.startswith(allowed) or url.startswith('data:') or url.startswith('blob:') or url == 'about:blank':
            r.continue_()
        else:
            blocked.append(url[:200]); r.abort()
    page.route('**/*', route)
    page.on('popup', lambda p: (blocked.append('popup: ' + p.url[:200]), p.close()))
    return blocked


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, project, **kwargs):
        self.project = project
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        path = unquote(urlsplit(path).path)
        if path.startswith('/app/'):
            base, relative = Path(__file__).parent / 'web', path[5:]
        elif path.startswith('/project/'):
            base, relative = self.project, path[9:]
        else:
            return str(self.project / '__not_found__')
        target = (base / relative).resolve()
        if not target.is_relative_to(base.resolve()):
            return str(self.project / '__not_found__')
        return str(target)

    def end_headers(self):
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'")
        super().end_headers()

    def log_message(self, *args):
        pass


def render(timeline: Path, output_dir: Path) -> dict:
    """Render to a new directory. Never replace an earlier result."""
    sync_playwright = playwright()

    root = timeline.resolve().parent
    edit = validate(json.loads(timeline.read_text(encoding='utf-8')), root)
    output_dir.mkdir(parents=True, exist_ok=False)
    frames = output_dir / 'frames'
    frames.mkdir()
    inputs = {str(timeline.name): digest(timeline)}
    for clip in edit['clips'].values():
        if 'faces' in clip: inputs[clip['faces']]=digest(local_path(root,clip['faces']))
        for i in range(clip['n']):
            rel = str(Path(clip['frames_dir']) / (clip.get('pattern', '%05d.png') % i))
            inputs[rel] = digest(local_path(root, rel))
        if 'mask_dir' in clip:
            for i in range(clip['n']):
                rel=str(Path(clip['mask_dir'])/f'{i:05d}.png')
                inputs[rel]=digest(local_path(root,rel))
    for f in edit.get('fonts', []):
        inputs[f['url']] = digest(local_path(root, f['url']))
    for p in (edit.get('assets') or {}).get('stickers', []):
        inputs[p] = digest(local_path(root, p))
    if edit.get('hooks'):
        inputs[edit['hooks']['src']] = digest(local_path(root, edit['hooks']['src']))
    from .audio import source_paths, mix, expanded
    for src in source_paths(expanded(edit.get('audio'), root)):
        inputs[src] = digest(local_path(root,src))
    write_json(output_dir / 'input-manifest.json', inputs)
    package = Path(__file__).parent
    implementation = {str(p.relative_to(package)): digest(p) for p in package.rglob('*') if p.suffix in ('.py', '.js', '.html')}
    write_json(output_dir / 'implementation-manifest.json', implementation)
    server = LocalHTTPServer(('127.0.0.1', 0), partial(Handler, project=root))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    trace = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chrome_path(), headless=True, args=['--disable-gpu'])
            try:
                page = browser.new_page()
                blocked = guard_page(page, server.server_port)
                open_engine(page, server.server_port)
                def browser_step(script, arg, what):
                    try:
                        return page.evaluate(script, arg)
                    except Exception as e:   # surface the renderer's own message, not the automation wrapper
                        message = str(e).split('\n')[0].replace('Page.evaluate: ', '').replace('Error: Error: ', 'Error: ')
                        raise RuntimeError(f'{what}: {message}') from e
                browser_step('(edit) => OpenKatana.boot(edit)', edit, 'Render setup failed')
                for frame in range(edit['canvas']['frames']):
                    result = browser_step('(f) => OpenKatana.render(f)', frame, f'Render failed at frame {frame}')
                    (frames / f'{frame:05d}.png').write_bytes(base64.b64decode(result['png']))
                    trace.append({'frame': frame, **result['sample'], **({'transition': result['transition']} if result.get('transition') else {}),
                                  **({'face': result['face']} if result.get('face') else {})})
                blocked += page.evaluate('() => OpenKatanaHooks.violations()')
            finally:
                browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join()
    write_json(output_dir / 'frame-trace.json', trace)
    c = edit['canvas']
    movie = output_dir / 'video.mp4'
    audio_mix=None
    if edit.get('audio',{}).get('mode')=='mix':
        audio_mix=mix(edit['audio'],root,output_dir/'audio.wav',c['frames']/c['fps'])
        write_json(output_dir/'audio-mix.json',audio_mix)
    soundtrack = local_path(root, edit['audio']['src']) if edit.get('audio',{}).get('mode')=='copy' else None
    encode(frames, c, movie, soundtrack=soundtrack, mixed=output_dir/'audio.wav' if audio_mix else None)
    info = probe(movie)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    count = int(video['nb_read_frames'])
    from fractions import Fraction
    failures = []
    if count != c['frames']:
        failures.append(f'video has {count} frames, the timeline needs {c["frames"]}')
    if (video['width'], video['height']) != (c['w'], c['h']):
        failures.append(f'video is {video["width"]}x{video["height"]}, the canvas is {c["w"]}x{c["h"]}')
    if abs(float(Fraction(video['r_frame_rate'])) - c['fps']) >= 1e-6:
        failures.append(f'video runs at {video["r_frame_rate"]} fps, the canvas is {c["fps"]}')
    audio_check = audio_copy = None
    if soundtrack:
        audio_check, audio_copy, problem = soundtrack_check(soundtrack, movie)
        if problem: failures.append(problem)
    ok = not failures
    from .warnings import timeline_warnings
    from .qa import render_qa
    qa = render_qa(edit, movie, trace, bool(edit.get('audio')))
    hooks = {**edit['hooks'], 'sha256': inputs[edit['hooks']['src']], 'blocked_requests': blocked} if edit.get('hooks') else None
    receipt = {'ok': ok, 'warnings': timeline_warnings(edit, root) + [{**w, 'source': 'render_qa'} for w in qa['warnings']], 'qa': qa, 'hooks': hooks, 'frames': count, 'width': video['width'], 'height': video['height'],
               'fps': video['r_frame_rate'], 'sha256': digest(movie), 'audio_stream_unchanged': audio_check, 'audio_copy': audio_copy,
               'contract_failures': failures, 'audio_mix':audio_mix, 'visual_review': 'not_performed', 'hosted_parity': 'not_tested', 'probe': info,
               'frame_hashes': {p.name: digest(p) for p in sorted(frames.glob('*.png'))}}
    write_json(output_dir / 'receipt.json', receipt)
    if not ok:
        raise RuntimeError('Encoded result failed its contract: ' + '; '.join(failures) + ' (see receipt.json)')
    return receipt


def prepare(source: Path, target: Path) -> dict:
    """Make lossless source frames; reject VFR rather than silently retime."""
    info = probe(source)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    from fractions import Fraction
    rotations = [float(x.get('rotation', 0)) for x in video.get('side_data_list', [])]
    rotations.append(float(video.get('tags', {}).get('rotate', 0)))
    if any(abs(angle) % 360 > .001 for angle in rotations):
        raise ContractError('Rotated source metadata needs explicit conformance before preparation')
    if video.get('color_transfer') in ('smpte2084', 'arib-std-b67'):
        raise ContractError('HDR source needs an explicit color conversion; this renderer is SDR')
    fps = float(Fraction(video['r_frame_rate']))
    pts = json.loads(run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
                         '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', source]))['frames']
    times = [float(f['best_effort_timestamp_time']) for f in pts]
    if any(abs((b-a)-1/fps) > max(.0001, .01/fps) for a,b in zip(times,times[1:])):
        raise ContractError('Variable source timing detected; explicit conformance is required')
    target.mkdir(parents=True, exist_ok=False)
    # Convert to RGB explicitly (using the source's own matrix), then clear the colour tags so the PNGs carry no
    # gAMA/cHRM/cICP chunks: browsers colour-manage tagged PNGs and would darken BT.709 footage (audit F-OK-008).
    alpha = video.get('pix_fmt', '').startswith(('yuva', 'rgba', 'bgra', 'argb', 'abgr', 'gbrap', 'ya'))
    rgb = 'rgba' if alpha else 'rgb24'
    run(['ffmpeg', '-v', 'error', '-i', source, '-map', '0:v:0', '-fps_mode', 'passthrough',
         '-vf', f'format={rgb},setparams=color_primaries=unknown:color_trc=unknown:colorspace=unknown',
         '-start_number', '0', target / '%05d.png'])
    result = {'frames_dir': target.name, 'n': len(list(target.glob('*.png'))), 'fps': fps,
              'w': video['width'], 'h': video['height'], 'pattern': '%05d.png'}
    write_json(target / 'source.json', {'source_sha256': digest(source), 'clip': result, 'pts': times})
    return result
