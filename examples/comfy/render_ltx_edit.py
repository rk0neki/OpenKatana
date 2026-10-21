"""Turn a downloaded model video into a local edit; no network or model calls."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
if (ROOT / 'openkatana').is_dir():
    sys.path.insert(0, str(ROOT))

import openkatana
from openkatana.agent_api import AgentAPI
from openkatana.bundled_fonts import copy_license
from openkatana.render import probe, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).parent / 'assets/ltx25-source.mp4')
    parser.add_argument('--workspace', type=Path, default=Path('work/ltx-edit'))
    parser.add_argument('--model-label', help='Actual source model name; do not infer it from appearance')
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    bundled = (Path(__file__).parent / 'assets/ltx25-source.mp4').resolve()
    model_label = args.model_label or ('LTX-2.5' if source == bundled else 'MODEL OUTPUT')
    api = AgentAPI(args.workspace.resolve())
    api.inspect_media(str(source))
    video = next(s for s in probe(source)['streams'] if s['codec_type'] == 'video')
    if float(video.get('duration', 0)) < 5:
        raise ValueError('This five-second example needs at least five seconds of video')
    project = 'ltx-edit-' + uuid.uuid4().hex[:8]
    root = Path(api.create_project('Copper orbit — model to edit', project)['directory'])
    api.preview_source(project, str(source), [0, 2, 4])
    media = api.import_media(project, str(source), rights='review_pending', duration=5)
    sound = api.import_media(project, str(source), rights='review_pending', duration=5, audio_only=True)
    font = Path(openkatana.__file__).parent / 'fonts/Inter[opsz,wght].ttf'
    shutil.copyfile(font, root / 'title.ttf')
    copy_license(font, root / 'title.ttf')
    result = api.build_recipe(project, 'ramp-freeze', [media['id']],
        seconds=5, width=576, height=320, fps=24)
    edit = result['timeline']
    edit['fonts'] = [{'family': 'Title', 'url': 'title.ttf'}]
    edit['text'] = [
        {'type': 'font', 'family': 'Title', 'text': 'COPPER ORBIT',
         'f0': 66, 'f1': 120, 'pos': [.5, .83], 'size': 27,
         'fill': '#ffffff', 'stroke': '#000000', 'render_style': 'explicit', 'shadow': False},
        {'type': 'font', 'family': 'Title', 'text': f'AI VIDEO / {model_label}  +  OPENKATANA EDIT',
         'f0': 0, 'f1': 120, 'pos': [.5, .95], 'size': 9,
         'fill': '#ffffff', 'stroke': '#000000', 'render_style': 'explicit', 'shadow': False}]
    edit['audio'] = {'mode': 'mix', 'tracks': [{'src': sound['path'], 'duration': 5}]}
    saved = api.save_timeline(project, edit, api.get_project(project)['revision'])
    api.preview_timeline(project, [0, 48, 70, 119])
    job = api.start_render(project, 'ltx-local-edit')
    deadline = time.monotonic() + 900
    while job['state'] == 'running' and time.monotonic() < deadline:
        time.sleep(.5)
        job = api.get_render(project, job['id'])
    if job['state'] != 'succeeded':
        raise RuntimeError('Inspect this saved render job; do not resubmit: ' + json.dumps(job))
    output = Path(job['video_path'])
    streams = probe(output)['streams']
    assert any(s['codec_type'] == 'audio' for s in streams), 'Soundtrack missing'
    motion = api.analyze_render_motion(project, str(output), cuts=[66])
    write_json(root / 'example-result.json', {
        'project_id': project, 'video': output.relative_to(root).as_posix(),
        'revision': saved['revision'], 'frames': 120, 'fps': 24,
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'model_calls': 0, 'network_calls': 0, 'preset': 'ramp-freeze',
        'intentional_freeze_from_frame': 66, 'motion_report': motion,
        'rights': 'review_pending; see example source record; not publication approval'})
    print(output)


if __name__ == '__main__':
    main()
