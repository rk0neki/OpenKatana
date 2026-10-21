"""Render an eight-second photo/video edit. Uses bundled media; no network/models."""
import argparse
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
    parser.add_argument('--workspace', type=Path, default=Path('work/quick-edit'))
    parser.add_argument('--width', type=int, default=960)
    parser.add_argument('--height', type=int, default=540)
    args = parser.parse_args()
    assets = Path(__file__).parent / 'assets'
    api = AgentAPI(args.workspace.resolve())
    project = 'one-home-' + uuid.uuid4().hex[:8]
    created = api.create_project('One home — quick edit', project)
    root = Path(created['directory'])
    ids = []
    for filename in ['apollo17.jpg', 'earth-rotation.mp4', 'blue-marble.jpg']:
        source = str((assets / filename).resolve())
        api.inspect_media(source)
        api.preview_source(project, source, [0])
        media = api.import_media(project, source, rights='public_domain',
            **({'duration': 8, 'max_width': 960} if filename.endswith('.mp4') else {}))
        ids.append(media['id'])
    score = api.import_media(project, str((assets / 'orbit.wav').resolve()), rights='licensed')
    font = Path(openkatana.__file__).parent / 'fonts' / 'Inter[opsz,wght].ttf'
    shutil.copyfile(font, root / 'title.ttf'); copy_license(font, root / 'title.ttf')
    result = api.build_recipe(project, 'beat-montage', ids, music_asset_id=score['id'],
                              seconds=8, width=args.width, height=args.height, fps=24)
    edit = result['timeline']; end = edit['canvas']['frames']
    edit['fonts'] = [{'family': 'Title', 'url': 'title.ttf'}]
    edit['text'] = []
    for label, y, size, first, last in [
        ('ONE HOME', .82, .067, 0, min(96, end)),
        ('A SMALL PLANET. A BIG PICTURE.', .82, .033, min(96, end), end),
        ('OPENKATANA / PHOTO + VIDEO + MUSIC', .92, .019, 0, end)]:
        edit['text'].append({'type': 'font', 'family': 'Title', 'text': label,
            'f0': first, 'f1': last, 'pos': [.5, y], 'size': round(args.width * size),
            'fill': '#ffffff', 'stroke': '#000000', 'render_style': 'explicit', 'shadow': False})
    api.save_timeline(project, edit, api.get_project(project)['revision'])
    api.preview_timeline(project, [0, end // 2, end - 1])
    job = api.start_render(project, 'quick-edit-render')
    deadline = time.monotonic() + 900
    while job['state'] == 'running' and time.monotonic() < deadline:
        time.sleep(.5)
        job = api.get_render(project, job['id'])
    if job['state'] != 'succeeded':
        raise RuntimeError('Inspect this saved render job; do not resubmit: ' + json.dumps(job))
    streams = probe(job['video_path'])['streams']
    assert any(s['codec_type'] == 'audio' for s in streams), 'Soundtrack missing'
    output = Path(job['video_path'])
    write_json(root / 'example-result.json', {'project_id': project,
        'video': output.relative_to(root).as_posix(), 'frames': end,
        'preset': 'beat-montage', 'model_calls': 0, 'network_calls': 0,
        'sources': 'See examples/quick-edit/assets/sources.json'})
    print(output)


if __name__ == '__main__':
    main()
