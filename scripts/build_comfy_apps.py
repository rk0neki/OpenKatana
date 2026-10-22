"""Regenerate the node catalog and distributable App Mode workflows. No execution."""
import json
from pathlib import Path
from openkatana.comfy_apps import catalog
from openkatana.comfy_app_templates import templates

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Always write LF so the source manifest hashes match on every platform.
    (ROOT / 'comfy_nodes/catalog.json').write_text(json.dumps(catalog(), indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    folder = ROOT / 'comfy_nodes/example_workflows'
    folder.mkdir(exist_ok=True)
    for name, data in templates().items():
        (folder / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'tools': len(catalog()), 'apps': len(templates())}))


if __name__ == '__main__':
    main()
