"""OpenKatana's own preset catalogue: named short-form formats, each a recipe family (recipes.FAMILIES) plus a look and
finishing choices. Pass a preset name as build_recipe's `family`; get_capabilities lists them under `presets`.

Each format combines configurable recipes and looks; it is a starting point for the editor.
"""
from .contracts import ContractError

PRESETS = {
    'beat-montage': {'title': 'Beat montage', 'family': 'beat_cut_punch',
                     'about': 'Cuts on the music beat grid, punch-ins on loud downbeats, sound cues on drops.', 'needs': 'music; 3+ clips'},
    'neon-beat': {'title': 'Neon beat', 'family': 'beat_cut_punch', 'look': 'neon_night',
                  'about': 'The beat montage in a cool neon grade with glow and colour fringing.', 'needs': 'music; 3+ clips; night footage suits it'},
    'photocopy-zine': {'title': 'Photocopy zine', 'family': 'xerox_ink',
                       'about': 'Bar-length cuts through a high-contrast photocopy look with grain.', 'needs': '2+ clips; music optional (sets the bar length)'},
    'noir-portrait': {'title': 'Noir portrait', 'family': 'mono_noir',
                      'about': 'Slow push-ins in black and white with letterbox bars and a white dip out.', 'needs': '1+ clips, faces suit it'},
    'travel-diary': {'title': 'Travel diary', 'family': 'mono_noir', 'look': 'golden_hour', 'post': None,
                     'about': 'Slow push-ins in a warm golden grade with a light leak, full frame.', 'needs': '2+ clips of places'},
    'tape-memories': {'title': 'Tape memories', 'family': 'mono_noir', 'look': 'home_tape', 'post': None,
                      'about': 'Slow push-ins through a home-video tape look.', 'needs': '2+ clips; casual footage suits it'},
    'split-collage': {'title': 'Split collage', 'family': 'cutout_collage',
                      'about': 'Two clips side by side on paper, then cut-out shots (outlined when a clip has a matte).', 'needs': '2 clips; a matte for cut-outs'},
    'ramp-freeze': {'title': 'Ramp and freeze', 'family': 'speed_ramp_freeze',
                    'about': 'A speed ramp down into a freeze frame with a flash and a slow push.', 'needs': '1 clip with motion'},
    'dreamy-slowmo': {'title': 'Dreamy slow-mo', 'family': 'speed_ramp_freeze', 'look': 'dreamy_bloom',
                      'about': 'The ramp and freeze in a soft bloom grade with a peach light leak.', 'needs': '1 clip with motion'},
    'face-strobe': {'title': 'Face strobe', 'family': 'facelock_strobe',
                    'about': 'Camera locked to the face, ping-pong playback and a strobe hit.', 'needs': '1 clip with a face track'},
    'lyric-type': {'title': 'Lyric type', 'family': 'timed_type',
                   'about': 'Words typed on in three-word phrases over the cuts.', 'needs': 'text and a font; 1+ clips'},
    'glitch-drop': {'title': 'Glitch drop', 'family': 'glitch_hits',
                    'about': 'Half-bar cuts with glitch transitions and RGB-split hits.', 'needs': '2+ clips; music optional (sets the cut length)'},
}


def catalog():
    return [{'name': k, **{f: v[f] for f in ('title', 'family', 'about', 'needs')}, **({'look': v['look']} if 'look' in v else {})}
            for k, v in PRESETS.items()]


def resolve(name):
    """(recipe family, preset or None) for a build_recipe family argument."""
    from .recipes import FAMILIES
    if name in FAMILIES:
        return name, None
    if name in PRESETS:
        return PRESETS[name]['family'], PRESETS[name]
    raise ContractError(f'family: a recipe family ({", ".join(FAMILIES)}) or a preset ({", ".join(PRESETS)})')


def finish(edit, preset):
    if preset is None:
        return edit
    if 'look' in preset:
        edit['look'] = preset['look']
    if 'post' in preset:
        if preset['post'] is None:
            edit.pop('post', None)
        else:
            edit['post'] = preset['post']
    return edit
