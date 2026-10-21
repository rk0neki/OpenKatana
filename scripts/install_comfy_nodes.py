"""Link OpenKatana's Comfy nodes into a local ComfyUI's custom_nodes folder (no copy, no pip install, no download).

usage: python scripts/install_comfy_nodes.py [--comfy-root DIR] [--remove]

--comfy-root defaults to the ComfyUI Desktop base path (%APPDATA%/ComfyUI/config.json "basePath").
The link is custom_nodes/openkatana-nodes -> <this checkout>/comfy_nodes (a directory junction on Windows), so the
nodes follow this checkout. Restart ComfyUI afterwards so it loads them.
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--comfy-root', type=Path, help='ComfyUI folder that contains custom_nodes')
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
    if link.exists() or link.is_symlink():
        if not linked:
            sys.exit(f'{link} already exists and is not a link to {SOURCE}; leaving it alone')
    elif os.name == 'nt':
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(SOURCE)], check=True, capture_output=True)
    else:
        link.symlink_to(SOURCE, target_is_directory=True)
    print(json.dumps({'link': str(link), 'target': str(SOURCE), 'next': 'restart ComfyUI so it loads the OpenKatana nodes'}))


if __name__ == '__main__':
    main()
