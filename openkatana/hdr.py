"""Original high-precision finishing route; never passes HDR pictures through Canvas.

FFmpeg/libzimg performs declared color transforms. Compositing is float32 linear
BT.2020, where 1.0 is 100 cd/m2. SDR plates are explicitly expanded, not HDR detail.
"""
from __future__ import annotations

from contextlib import ExitStack
import json
import math
from pathlib import Path
import subprocess
import tempfile

import numpy as np

from .contracts import ContractError, local_path
from .render import digest, probe, run, write_json

PROFILES = {
    'pq': ('bt2020', 'smpte2084', 'bt2020nc', 'limited'),
    'hlg': ('bt2020', 'arib-std-b67', 'bt2020nc', 'limited'),
    'bt709': ('bt709', 'bt709', 'bt709', 'limited'),
    'srgb': ('bt709', 'iec61966-2-1', 'gbr', 'full'),
}


def fields(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed.split()):
        raise ContractError(f'{label}: expected an object with only {allowed}')


def numeric(value, low, high, label, integer=False):
    if type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ContractError(f'{label}: expected {"integer" if integer else "number"} in {low}..{high}')
    return value


def source_profile(path, override=None):
    streams = json.loads(run(['ffprobe','-v','error','-show_streams','-of','json',path]))['streams']
    v = next((s for s in streams if s['codec_type'] == 'video'), None)
    if not v:
        raise ContractError(f'No video stream: {path.name}')
    if any(abs(float(s.get('rotation', 0))) % 360 > .001 for s in v.get('side_data_list', [])) or abs(float(v.get('tags', {}).get('rotate', 0))) % 360 > .001:
        raise ContractError('Conform rotation explicitly before HDR finishing')
    if any('dovi' in str(s).lower() or 'dolby' in str(s).lower() for s in v.get('side_data_list', [])):
        raise ContractError('Dolby Vision dynamic metadata is not supported by this HDR route')
    if override is not None:
        if override not in PROFILES:
            raise ContractError('source_color must be pq, hlg, bt709 or srgb')
        p, t, m, r = PROFILES[override]
        # RGB still inputs have a full-range RGB matrix even if their TRC is overridden.
        if path.suffix.lower() in ('.png', '.tif', '.tiff', '.exr'):
            m, r = 'gbr', 'full'
    else:
        p, t, m, r = (v.get(k) for k in ('color_primaries', 'color_transfer', 'color_space', 'color_range'))
        r = {'tv': 'limited', 'pc': 'full'}.get(r, r)
        if p not in ('bt709', 'bt2020') or t not in ('smpte2084', 'arib-std-b67', 'bt709', 'iec61966-2-1') or m not in ('bt709', 'bt2020nc', 'gbr') or r not in ('limited', 'full'):
            raise ContractError('Missing/unsupported color tags: explicitly declare source_color after inspecting the source')
    return {'primaries': p, 'transfer': t, 'matrix': m, 'range': r,
            'width': v['width'], 'height': v['height'], 'pixel_format': v.get('pix_fmt'),
            'override': override}


def validate(document, root):
    fields(document, 'schema canvas output clips overlays audio', 'HDR document')
    if document.get('schema') != 'openkatana.hdr/1':
        raise ContractError('Expected schema openkatana.hdr/1')
    c = document.get('canvas', {})
    fields(c, 'width height fps frames', 'canvas')
    for k, lo, hi in [('width', 16, 4096), ('height', 16, 4096), ('fps', 1, 120), ('frames', 1, 72000)]:
        numeric(c.get(k), lo, hi, k, True)
    if c['width'] % 2 or c['height'] % 2:
        raise ContractError('HDR export requires even dimensions')
    o = document.get('output', {})
    fields(o, 'transfer peak_nits', 'output')
    if o.get('transfer') not in ('pq', 'hlg'):
        raise ContractError('output.transfer must be pq or hlg')
    numeric(o.get('peak_nits'), 100, 10000, 'peak_nits')
    for kind in ('clips', 'overlays'):
        items = document.get(kind, [])
        if not isinstance(items, list) or len(items) > 64:
            raise ContractError(f'{kind}: expected at most 64 layers')
        for item in items:
            allowed = 'source start frames opacity fade_in fade_out'
            fields(item, allowed + (' trim_seconds source_color exposure' if kind == 'clips' else ' white_nits source_start'), kind)
            path = local_path(root, item.get('source', ''))
            if not path.is_file() and not (kind == 'overlays' and path.is_dir()):
                raise ContractError('HDR source must be a local file within the project')
            numeric(item.get('start'), 0, c['frames']-1, 'start', True)
            numeric(item.get('frames'), 1, c['frames']-item['start'], 'frames', True)
            numeric(item.get('opacity', 1), 0, 1, 'opacity')
            for key in ('fade_in', 'fade_out'):
                numeric(item.get(key, 0), 0, item['frames'], key, True)
            if kind == 'clips':
                numeric(item.get('trim_seconds', 0), 0, 86400, 'trim_seconds')
                numeric(item.get('exposure', 0), -10, 10, 'exposure')
                source_profile(path, item.get('source_color'))
            else:
                numeric(item.get('source_start',0),0,72000,'source_start',True)
                if path.is_dir():
                    for i in range(item['frames']):
                        if not (path/f"{i+item.get('source_start',0):05d}.png").is_file():
                            raise ContractError('Overlay sequence must contain every requested %05d.png frame')
                elif path.suffix.lower() != '.png':
                    raise ContractError('Overlays are explicit full-canvas sRGB RGBA PNGs')
                numeric(item.get('white_nits', 203), 1, o['peak_nits'], 'white_nits')
    if not document.get('clips'):
        raise ContractError('At least one source clip is required')
    if 'audio' in document and not local_path(root, document['audio']).is_file():
        raise ContractError('audio must be a local file')
    return document


def decode_filter(profile, canvas):
    p = profile
    return (f"fps={canvas['fps']},zscale=pin={p['primaries']}:tin={p['transfer']}:min={p['matrix']}:rin={p['range']}:"
            f"p=bt2020:t=linear:m=gbr:r=full:npl=100:w={canvas['width']}:h={canvas['height']}:filter=bilinear,"
            'format=gbrpf32le,setsar=1')


class Decoder:
    def __init__(self, path, profile, canvas, trim=0, frames=None):
        self.size = canvas['width'] * canvas['height'] * 3 * 4
        self.shape = (3, canvas['height'], canvas['width'])
        self.errors = tempfile.TemporaryFile()
        cmd = ['ffmpeg', '-v', 'error', '-nostdin', '-noautorotate', '-ss', str(trim), '-i', str(path), '-an',
               '-vf', decode_filter(profile, canvas)]
        if frames is not None:
            cmd += ['-frames:v', str(frames)]
        self.proc = subprocess.Popen(cmd + ['-f', 'rawvideo', '-pix_fmt', 'gbrpf32le', '-'], stdout=subprocess.PIPE, stderr=self.errors, stdin=subprocess.DEVNULL)

    def read(self):
        raw = bytearray()
        while len(raw) < self.size:
            block = self.proc.stdout.read(self.size-len(raw))
            if not block:
                self.errors.seek(0)
                raise ContractError('Source ended before the requested frame count: ' + self.errors.read()[-2000:].decode(errors='replace'))
            raw.extend(block)
        # GBR planar -> RGB interleaved.
        return np.frombuffer(raw, dtype='<f4').reshape(self.shape)[[2, 0, 1]].transpose(1, 2, 0).copy()

    def close(self):
        # A caller may stop before consuming every frame. Close the read end
        # first so FFmpeg cannot remain blocked writing into a full POSIX pipe.
        try:
            self.proc.stdout.close()
            if self.proc.poll() is None:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        finally:
            self.errors.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def output_filter(transfer, pixel_format):
    trc = PROFILES[transfer][1]
    return ('zscale=pin=bt2020:tin=linear:min=gbr:rin=full:p=bt2020:'
            f't={trc}:m=bt2020nc:r=limited:npl=100:dither=error_diffusion,format={pixel_format},'
            f'setparams=color_primaries=bt2020:color_trc={trc}:colorspace=bt2020nc:range=limited')


def encode_linear(raw, canvas, output, transfer, lossless=False, max_cll=None):
    trc = PROFILES[transfer][1]
    args = ['ffmpeg', '-v', 'error', '-nostdin', '-f', 'rawvideo', '-pixel_format', 'gbrpf32le',
            '-video_size', f"{canvas['width']}x{canvas['height']}", '-framerate', str(canvas['fps']), '-i', raw,
            '-frames:v', str(canvas['frames']), '-vf', output_filter(transfer, 'yuv444p16le' if lossless else 'yuv420p10le')]
    if lossless:
        args += ['-c:v', 'ffv1', '-level', '3', '-coder', '1', '-context', '1', '-g', '1']
    else:
        params = 'pools=2:frame-threads=2:log-level=error'
        if transfer == 'pq' and max_cll:
            params += f":hdr10=1:max-cll={max_cll[0]},{max_cll[1]}"
        args += ['-c:v', 'libx265', '-preset', 'medium', '-crf', '16', '-x265-params', params, '-tag:v', 'hvc1', '-movflags', '+faststart']
    run(args + ['-color_primaries', 'bt2020', '-color_trc', trc, '-colorspace', 'bt2020nc', output])


def opacity(layer, frame):
    i, n = frame-layer['start'], layer['frames']
    value = float(layer.get('opacity', 1))
    if layer.get('fade_in', 0):
        value *= min(1, i/max(1, layer['fade_in']-1))
    if layer.get('fade_out', 0):
        value *= min(1, (n-1-i)/max(1, layer['fade_out']-1))
    return value


def overlay_pixels(path, canvas, white_nits):
    from PIL import Image
    with Image.open(path) as im:
        if im.size != (canvas['width'], canvas['height']):
            raise ContractError('Overlay PNG must match the canvas dimensions (no implicit resizing)')
        rgba = np.asarray(im.convert('RGBA'), dtype=np.float32)/255
    rgb = rgba[..., :3]
    rgb = np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)
    # BT.709 D65 -> BT.2020 D65; independently calculated standard primary matrix.
    matrix = np.array([[.627403896, .329283038, .043313066], [.069097289, .919540395, .011362316], [.016391439, .088013308, .895595253]], dtype=np.float32)
    return (rgb @ matrix.T)*(white_nits/100), rgba[..., 3:4]


def render(document, root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    validate(document, root)
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    c, output = document['canvas'], document['output']
    raw = out/'linear.gbrpf32'
    sources = []
    overlays = []
    for v in document.get('overlays', []):
        path=local_path(root,v['source'])
        files=[path/f"{i+v.get('source_start',0):05d}.png" for i in range(v['frames'])] if path.is_dir() else [path]
        # Resolve each frame too: a symlink inside a sequence cannot escape the project.
        for f in files:local_path(root,f.relative_to(root).as_posix())
        overlays.append((v,files))
    max_rgb = max_fall = clipped = 0
    total = c['frames']*c['width']*c['height']*3
    try:
        with ExitStack() as stack, raw.open('xb') as stream:
            readers = {}
            for item in document['clips']:
                path = local_path(root, item['source'])
                sources.append({'source': item['source'], 'sha256': digest(path), 'profile': source_profile(path, item.get('source_color'))})
            for frame in range(c['frames']):
                picture = np.zeros((c['height'], c['width'], 3), np.float32)
                for i, item in enumerate(document['clips']):
                    if item['start'] <= frame < item['start']+item['frames']:
                        if i not in readers:
                            readers[i] = stack.enter_context(Decoder(local_path(root, item['source']), sources[i]['profile'], c, item.get('trim_seconds', 0), item['frames']))
                        sample = readers[i].read()*2**item.get('exposure', 0)
                        if not np.isfinite(sample).all():
                            raise ContractError('Nonfinite pixels in HDR source')
                        a = opacity(item, frame)
                        picture = picture*(1-a) + sample*a
                for item, files in overlays:
                    if item['start'] <= frame < item['start']+item['frames']:
                        path=files[frame-item['start']] if len(files)>1 else files[0]
                        rgb,alpha=overlay_pixels(path,c,item.get('white_nits',203))
                        a = alpha*opacity(item, frame)
                        picture = picture*(1-a) + rgb*a
                limit = output['peak_nits']/100
                clipped += int(np.count_nonzero((picture < 0) | (picture > limit)))
                np.clip(picture, 0, limit, out=picture)
                max_rgb = max(max_rgb, float(picture.max())*100)
                max_fall = max(max_fall, float(picture.max(axis=2).mean())*100)
                stream.write(picture.transpose(2, 0, 1)[[1, 2, 0]].astype('<f4').tobytes())
        encode_linear(raw, c, out/'master.mkv', output['transfer'], True)
        encode_linear(raw, c, out/'video.picture.mp4', output['transfer'], max_cll=(math.ceil(max_rgb), math.ceil(max_fall)))
        picture = out/'video.picture.mp4'
        if document.get('audio'):
            run(['ffmpeg', '-v', 'error', '-nostdin', '-i', picture, '-i', local_path(root, document['audio']), '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-af', 'apad', '-c:a', 'aac', '-b:a', '256k', '-t', str(c['frames']/c['fps']), '-movflags', '+faststart', out/'video.mp4'])
        else:
            picture.rename(out/'video.mp4')
        # Explicit SDR viewing derivative; the HDR master never uses this path.
        run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'rawvideo', '-pixel_format', 'gbrpf32le', '-video_size', f"{c['width']}x{c['height']}", '-framerate', str(c['fps']), '-i', raw, '-frames:v', str(c['frames']), '-vf',
             f"tonemap=tonemap=mobius:param=0.3:desat=0:peak={output['peak_nits']/100},zscale=pin=bt2020:tin=linear:min=gbr:rin=full:p=bt709:t=bt709:m=bt709:r=limited:npl=100,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709",
             '-c:v', 'libx264', '-crf', '18', out/'preview-sdr.mp4'])
        result = {'schema': 1, 'pipeline': 'float32 linear BT.2020; 1 = 100 nits', 'canvas': c, 'output': output,
                  'inputs': sources, 'overlays': [{'source': v['source'], 'files':{f.relative_to(root).as_posix():digest(f) for f in files}, 'white_nits': v.get('white_nits', 203), 'origin': 'SDR sRGB'} for v,files in overlays],
                  'audio': {'sha256': digest(local_path(root, document['audio']))} if document.get('audio') else None,
                  'max_rgb_nits': max_rgb, 'max_frame_average_maxrgb_nits': max_fall, 'clipped_channel_fraction': clipped/total,
                  'video': str(out/'video.mp4'), 'master': str(out/'master.mkv'), 'preview': str(out/'preview-sdr.mp4'),
                  'review_required': True, 'limitations': ['No Dolby Vision/HDR10+ metadata', 'SDR plates do not gain highlight detail', 'Canvas effects are not native HDR effects'],
                  'files': {name: digest(out/name) for name in ('video.mp4', 'master.mkv', 'preview-sdr.mp4')}}
        write_json(out/'document.json', document)
        write_json(out/'manifest.json', result)
        return result
    finally:
        if raw.exists():
            raw.unlink()
