"""Typed Comfy media operations executed only in OpenKatana's environment."""
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image

from .agent_api import AgentAPI
from .contracts import ContractError, local_path, number
from .render import encode, probe, run

MAX_FRAME_BYTES = 512 * 1024**2


def transfer_directory(workspace, name):
    import uuid
    return Path(workspace).resolve() / '.comfy-apps' / 'transfers' / uuid.UUID(name).hex


def load_frames(path):
    frames = np.load(path, allow_pickle=False, mmap_mode='r')
    if frames.dtype != np.uint8 or frames.ndim != 4 or frames.shape[-1] != 3 or min(frames.shape) < 1:
        raise ContractError('Expected a nonempty uint8 RGB frame batch')
    if frames.nbytes > MAX_FRAME_BYTES:
        raise ContractError('Frame transfer exceeds 512 MiB; split the clip into shorter sections')
    return frames


def interpolate_frames(folder, multiplier):
    from .vision import interpolate_pair
    number(multiplier, 'multiplier', 2, 8, integer=True)
    frames = load_frames(folder / 'input.npy')
    if frames.nbytes * multiplier > MAX_FRAME_BYTES:
        raise ContractError('Interpolated frames exceed 512 MiB; use a shorter/smaller frame batch')
    output = np.lib.format.open_memmap(folder / 'output.npy', mode='w+', dtype='uint8',
                                     shape=(len(frames) * multiplier, *frames.shape[1:]))
    for i, frame in enumerate(frames):
        for j, sample in enumerate(interpolate_pair(frame, frames[min(i+1, len(frames)-1)], multiplier)):
            output[i*multiplier+j] = sample
    output.flush()
    return {'frames': len(output), 'output': str(folder / 'output.npy')}


def import_frames(workspace, folder, request):
    from . import projects
    from .onboarding import setup_project
    api = AgentAPI(workspace)
    project_id = request['project_id']
    root = api._project(project_id)
    setup_project(root, request.get('name', 'Comfy edit'))
    fps = request.get('fps', 24)
    number(fps, 'fps', 1, 120)
    rights = request.get('rights', 'review_pending')
    if rights not in ('own', 'licensed', 'public_domain', 'review_pending'):
        raise ContractError('Choose an explicit media rights status')
    if request.get('video'):
        source = folder / 'input.mp4'
        info = probe(source)
        stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
        if stream.get('color_transfer') in ('smpte2084', 'arib-std-b67'):
            raise ContractError('HDR video needs explicit HDR conformance before an SDR timeline import')
    else:
        frames = load_frames(folder / 'input.npy')
        plates = folder / 'frames'
        plates.mkdir()
        for i, frame in enumerate(frames):
            Image.fromarray(frame).save(plates / f'{i:05d}.png')
        source = plates / '00000.png'
        if len(frames) > 1:
            source = folder / 'input.mp4'
            encode(plates, {'fps': fps, 'frames': len(frames)}, source)
        info = probe(source)
    asset = projects.import_asset(root, source, rights)
    audio_asset = None
    audio = folder / 'input.wav'
    if not audio.is_file() and any(s['codec_type'] == 'audio' for s in info['streams']):
        run(['ffmpeg', '-v', 'error', '-i', source, '-vn', '-c:a', 'pcm_s16le', audio])
    if audio.is_file():
        audio_asset = projects.import_asset(root, audio, rights)
    return {'project_id': project_id, 'media_id': asset['id'], 'asset': asset,
            'music_asset_id': audio_asset['id'] if audio_asset else '', 'audio': audio_asset}


def render_video(workspace, project_id):
    api = AgentAPI(workspace)
    state = api.get_project(project_id)
    if not state['timeline']:
        raise ContractError('Save a timeline first, or connect Make edit to this node')
    job = api.start_render(project_id, 'comfy-graph-' + state['revision'])
    deadline = time.monotonic() + 3500
    while job['state'] == 'running' and time.monotonic() < deadline:
        time.sleep(.2)
        job = api.get_render(project_id, job['id'])
    if job['state'] != 'succeeded':
        raise ContractError('Render ' + job['state'] + ': ' + json.dumps(job))
    # Keep the actual output lazy as VIDEO; IMAGE is a bounded preview batch.
    root = api._project(project_id)
    folder = local_path(root, job['video']).parent / 'frames'
    return {**job, 'frames_directory': str(folder), 'fps': state['timeline']['canvas']['fps']}


def dispatch_media(workspace, action, request):
    if action == 'render_video':
        return render_video(workspace, request['project_id'])
    folder = transfer_directory(workspace, request['transfer_id'])
    if action == 'interpolate_frames':
        return interpolate_frames(folder, request['multiplier'])
    return import_frames(workspace, folder, request)
