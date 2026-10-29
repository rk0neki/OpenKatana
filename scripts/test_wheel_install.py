"""Install a built wheel in a fresh venv and exercise it outside the checkout.

Requires network access for Python dependencies and preinstalled FFmpeg/browser.
Does not install models, make generation calls, or publish anything.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True,
                        help='New directory outside the source checkout; retained for inspection.')
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    out = args.out.resolve()
    if out.is_relative_to(ROOT) or ROOT.is_relative_to(out):
        parser.error('Choose a new output directory outside the source checkout')
    out.mkdir(parents=True, exist_ok=False)
    logs = out / 'logs'; logs.mkdir()
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in {'PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'}}
    env['PYTHONNOUSERSITE'] = '1'
    env['PYTHONUTF8'] = '1'
    env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    started = time.monotonic()
    steps = []

    def run(label, command, timeout=1200):
        with (logs / (label + '.log')).open('w', encoding='utf-8') as log:
            subprocess.run([str(a) for a in command], cwd=out, env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)
        steps.append(label)
        print(label + ': passed', flush=True)
        return (logs / (label + '.log')).read_text(encoding='utf-8')

    try:
        run('create-environment', [sys.executable, '-I', '-m', 'venv', out / 'venv'])
        python = out / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        run('install-wheel', [python, '-I', '-m', 'pip', 'install', '--no-cache-dir',
                              str(wheel) + '[text,vision,mcp]'])
        run('dependency-check', [python, '-I', '-m', 'pip', 'check'])
        identity = json.loads(run('installed-identity', [python, '-I', '-c',
            'import json,sys,site,pathlib,openkatana; '
            'assert not site.ENABLE_USER_SITE; '
            'assert pathlib.Path(openkatana.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()); '
            'print(json.dumps(dict(version=openkatana.__version__, module=openkatana.__file__, prefix=sys.prefix)))']))
        share = Path(identity['prefix']) / 'share/openkatana'
        required = ['docs/EFFECTS-PLAYBOOK.md', 'docs/SETUP.md',
                    'skills/openkatana-video/SKILL.md', 'scripts/install_comfy_nodes.py']
        for folder in ('examples', 'docs/assets', 'comfy_nodes'):
            required.extend(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).rglob('*')
                            if p.is_file() and '__pycache__' not in p.parts)
        for name in required:
            if (share / name).read_bytes() != (ROOT / name).read_bytes():
                raise AssertionError('Installed resource differs: ' + name)
        steps.append('installed-resources')
        doctor = json.loads(run('doctor', [python, '-I', '-m', 'openkatana', 'doctor']))
        if not doctor['ready_to_render']:
            raise AssertionError('Install FFmpeg/ffprobe and a browser before the render checks')
        setup = json.loads(run('setup', [python, '-I', '-m', 'openkatana', 'setup',
                                       '--project', out / 'projects/first-film']))
        if Path(setup['resources']).resolve() != share.resolve():
            raise AssertionError('Setup used source checkout resources')
        if Path(setup['effects_playbook']).read_text(encoding='utf-8') != (share / 'docs/EFFECTS-PLAYBOOK.md').read_text(encoding='utf-8'):
            raise AssertionError('Project preset missing or different')
        run('quick-edit', [python, '-I', share / 'examples/quick-edit/render.py',
                           '--width', '320', '--height', '180'])
        run('comfy-example', [python, '-I', share / 'examples/comfy/render_ltx_edit.py'])
        # Copy only the browser test driver; all product imports and child processes
        # must resolve to the installed wheel, including documentation and assets.
        driver = out / 'studio_check.py'
        shutil.copyfile(ROOT / 'scripts/test_studio_live.py', driver)
        run('studio', [python, '-I', driver, '--out', out / 'studio'])
        studio = json.loads((out / 'studio/result.json').read_text(encoding='utf-8'))
        if not studio['passed'] or studio['browser_errors']:
            raise AssertionError('Studio workflow failed')
        run('installed-packages', [python, '-I', '-m', 'pip', 'freeze'])
        result = {'passed': True, 'version': identity['version'],
                  'wheel': wheel.name, 'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
                  'fresh_environment': True, 'source_imports': False,
                  'resource_files_checked': len(required), 'steps': steps,
                  'studio': studio, 'elapsed_seconds': round(time.monotonic() - started, 1),
                  'runtime_scope': 'Fresh Python environment; system FFmpeg and browser already installed',
                  'model_calls': 0, 'published': False}
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, indent=2))
    except Exception as error:
        (out / 'result.json').write_text(json.dumps({'passed': False, 'steps': steps,
            'error': str(error)}, indent=2) + '\n', encoding='utf-8')
        raise


if __name__ == '__main__':
    main()
