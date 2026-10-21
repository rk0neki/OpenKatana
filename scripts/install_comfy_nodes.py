"""Install local OpenKatana nodes, saved Apps and interpreter configuration.

Run with OpenKatana's installed Python. No pip installs, models, services or paid
calls. Existing edited Apps/configuration are preserved. Restart ComfyUI once.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

NAME = 'openkatana-nodes'
SOURCE = Path(__file__).resolve().parents[1] / 'comfy_nodes'


def desktop_root():
    config = Path(os.environ.get('APPDATA', '')) / 'ComfyUI' / 'config.json'
    if config.is_file():
        base = json.loads(config.read_text(encoding='utf-8')).get('basePath')
        if base:
            return Path(base)
    return None


def install(root, python, workspace=None):
    from openkatana.comfy_app_templates import templates
    from openkatana.comfy_apps import catalog
    root = Path(root).expanduser().resolve()
    if not (root / 'custom_nodes').is_dir():
        raise ValueError('ComfyUI custom_nodes folder not found')
    python = Path(python).resolve()
    if not python.is_file():
        raise ValueError('OpenKatana Python interpreter does not exist')
    # Check the selected environment before changing the Comfy installation.
    checked = subprocess.run([str(python), '-m', 'openkatana.comfy_apps'],
        input=json.dumps({'action': 'catalog'}), cwd=SOURCE.parent, text=True,
        encoding='utf-8', capture_output=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if checked.returncode or not json.loads(checked.stdout).get('ok'):
        raise ValueError('Selected Python cannot run OpenKatana; run scripts/setup.py first')
    installed_catalog = json.loads((SOURCE / 'catalog.json').read_text(encoding='utf-8'))
    if installed_catalog != catalog():
        raise ValueError('Node catalogue is stale; regenerate it with scripts/build_comfy_apps.py')
    link = root / 'custom_nodes' / NAME
    if link.exists() or link.is_symlink():
        if Path(os.path.realpath(link)) != SOURCE:
            raise ValueError(f'{link} already exists and points elsewhere; preserving it')
    elif os.name == 'nt':
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(SOURCE)], check=True, capture_output=True)
    else:
        link.symlink_to(SOURCE, target_is_directory=True)
    config = root / 'user' / 'openkatana' / 'config.json'
    value = {'python': str(python), 'checkout': str(SOURCE.parent),
             'workspace': str(Path(workspace or root / 'output' / 'OpenKatana').resolve())}
    config.parent.mkdir(parents=True, exist_ok=True)
    if config.exists():
        if json.loads(config.read_text(encoding='utf-8')) != value:
            raise ValueError(f'Existing configuration differs; edit {config} explicitly. It was preserved.')
    else:
        with config.open('x', encoding='utf-8') as f:
            json.dump(value, f, indent=2)
    apps = root / 'user' / 'default' / 'workflows' / 'OpenKatana'
    apps.mkdir(parents=True, exist_ok=True)
    installed, preserved = [], []
    for name, data in templates().items():
        path = apps / name
        if path.exists():
            preserved.append(name)
        else:
            with path.open('x', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            installed.append(name)
    return {'link': str(link), 'config': str(config), 'workspace': value['workspace'],
            'apps': str(apps), 'installed': installed, 'preserved': preserved,
            'tool_count': len(installed_catalog), 'next': 'Restart ComfyUI, then open Apps → OpenKatana → 01 Open Studio.'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--comfy-root', type=Path, help='ComfyUI folder that contains custom_nodes')
    ap.add_argument('--python', type=Path, default=Path(sys.executable), help='OpenKatana interpreter (defaults to this interpreter)')
    ap.add_argument('--workspace', type=Path, help='Shared projects folder (default: ComfyUI/output/OpenKatana)')
    ap.add_argument('--remove', action='store_true', help='remove the link (never the checkout)')
    args = ap.parse_args(argv)
    root = args.comfy_root or desktop_root()
    if not root or not (root / 'custom_nodes').is_dir():
        sys.exit('ComfyUI custom_nodes folder not found; pass --comfy-root')
    link = root / 'custom_nodes' / NAME
    linked = link.exists() and Path(os.path.realpath(link)) == SOURCE
    if args.remove:
        if link.exists() and not linked:
            sys.exit(f'{link} is not a link to this checkout; leaving it alone')
        if linked:
            os.rmdir(link) if os.name == 'nt' else link.unlink()  # removes the junction/symlink only
        print(json.dumps({'removed': linked, 'link': str(link)}))
        return
    print(json.dumps(install(root, args.python, args.workspace), indent=2))


if __name__ == '__main__':
    main()
