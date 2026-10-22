"""Generate docs/TOOLS.md from the live tool catalog. Run with --check to verify it is current."""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'docs/TOOLS.md'

# (area, guide links, tools). Every catalog tool must appear exactly once.
GROUPS = [
    ('Start and discover', [('Agent guide', 'AGENT_INTERFACE.md')],
     ['get_capabilities', 'read_guide', 'create_project', 'get_project']),
    ('Bring in and inspect media', [('Editor tools', 'EDITOR_TOOLS.md')],
     ['inspect_media', 'preview_source', 'source_contact_sheet', 'view_image', 'preview_segment',
      'import_media', 'import_media_batch', 'set_review_policy']),
    ('Author the timeline', [('Timeline', 'TIMELINE.md'), ('Release tools', 'RELEASE-TOOLS.md')],
     ['plan_edit', 'build_recipe', 'validate_timeline', 'save_timeline', 'edit_timeline', 'preview_timeline']),
    ('Music, sound and captions', [('Editor tools', 'EDITOR_TOOLS.md')],
     ['analyze_audio', 'plan_music_edit', 'plan_storyboard', 'fill_storyboard', 'list_sfx',
      'transcribe_audio', 'make_captions']),
    ('Analysis and effects', [('Effects', 'EXPANSION.md')],
     ['analyze_clip', 'analyze_energy', 'review_mask', 'morph_images', 'render_page']),
    ('Match a reference', [('Editor tools', 'EDITOR_TOOLS.md')],
     ['analyze_reference', 'compare_reference', 'save_reference_plan', 'audit_reference_plan',
      'bind_reference', 'inspect_identity']),
    ('Fonts and text shaping', [('Editor tools', 'EDITOR_TOOLS.md'), ('Release tools', 'RELEASE-TOOLS.md')],
     ['list_fonts', 'preview_fonts', 'shape_text']),
    ('Compositions and plugins', [('Compositions', 'COMPOSITIONS.md')],
     ['create_composition', 'save_composition', 'inspect_composition', 'render_composition',
      'list_plugins', 'run_plugin_operator']),
    ('3D scenes and WebGL', [('3D', 'SCENE3D.md'), ('WebGL', 'WEBGL.md')],
     ['create_scene3d', 'inspect_model3d', 'import_model3d', 'check_scene3d', 'render_scene3d',
      'create_webgl_kit', 'assemble_render_clips']),
    ('Blender and authored animation', [('Animation', 'ANIMATION.md')],
     ['render_blender', 'create_animation_kit', 'build_display_atlas', 'synthesize_score',
      'assemble_blender_clips', 'analyze_camera_motion']),
    ('Render and review', [('Editor tools', 'EDITOR_TOOLS.md'), ('Validation', 'VALIDATION.md')],
     ['start_render', 'get_render', 'review_render', 'revise_motion', 'analyze_render_motion']),
    ('ComfyUI models', [('Models', 'COMFY_MODELS.md')],
     ['build_workflow', 'check_workflow', 'submit_workflow', 'collect_workflow',
      'import_workflow_output', 'process_clip', 'run_model_workflow']),
    ('HDR', [('HDR', 'HDR.md')],
     ['import_hdr_media', 'render_hdr']),
]


def summary(description):
    """First sentence of a tool description, as one line."""
    text = ' '.join(description.split())
    match = re.search(r'^(.+?[.!?])(?:\s|$)', text)
    return (match.group(1) if match else text).replace('|', '\\|')


def parameters(row):
    """Parameter names; optional ones end with '?'."""
    names = [n + ('' if p['required'] else '?') for n, p in row['parameters'].items()]
    return ', '.join(f'`{n}`' for n in names) if names else '—'


def render():
    from openkatana.comfy_apps import catalog
    rows = {row['name']: row for row in catalog()}
    grouped = [name for _, _, names in GROUPS for name in names]
    missing = sorted(set(rows) - set(grouped))
    unknown = sorted(set(grouped) - set(rows))
    duplicated = sorted({n for n in grouped if grouped.count(n) > 1})
    if missing or unknown or duplicated:
        raise SystemExit(f'Update GROUPS: missing={missing} unknown={unknown} duplicated={duplicated}')

    lines = [
        '# Tool reference',
        '',
        f'OpenKatana has {len(rows)} tools, shared by the CLI, the MCP server and the ComfyUI',
        'nodes. This page is generated from the tool catalog by',
        '`python scripts/build_tools_doc.py`; do not edit it by hand.',
        '',
        'For exact signatures and types, run `openkatana tools`. Each section links to the',
        'guide with details and limits. Parameters ending in `?` are optional.',
        '',
        '| Area | Tools | Guide |',
        '|---|---|---|',
    ]
    for area, guides, names in GROUPS:
        anchor = re.sub(r'[^a-z0-9 -]', '', area.lower()).replace(' ', '-')
        links = ', '.join(f'[{label}]({path})' for label, path in guides)
        lines.append(f'| [{area}](#{anchor}) | {len(names)} | {links} |')
    for area, guides, names in GROUPS:
        links = ' · '.join(f'[{label}]({path})' for label, path in guides)
        lines += ['', f'## {area}', '', f'Guide: {links}', '',
                  '| Tool | What it does | Parameters |', '|---|---|---|']
        for name in names:
            row = rows[name]
            lines.append(f'| `{name}` | {summary(row["description"])} | {parameters(row)} |')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if docs/TOOLS.md is out of date')
    args = parser.parse_args()
    text = render()
    if args.check:
        current = OUT.read_text(encoding='utf-8').replace('\r\n', '\n') if OUT.exists() else ''
        if current != text:
            raise SystemExit('docs/TOOLS.md is stale; run python scripts/build_tools_doc.py')
        print('docs/TOOLS.md is current')
        return
    OUT.write_text(text, encoding='utf-8', newline='\n')
    print(f'Wrote {OUT.relative_to(ROOT).as_posix()}')


if __name__ == '__main__':
    main()
