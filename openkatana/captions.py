"""Captions from supplied word timings (audit F-CAP-001): grouping into readable caption events, styles (including a
karaoke word highlight), and SRT / WebVTT export. No transcription happens here — timings come from a words file
(e.g. a transcript made elsewhere) or an existing SRT/VTT, and must be checked against the audio by the editor.

Accepted word files: [[t0, t1, "word"], ...], [{"start"|"t0", "end"|"t1", "word"|"text"}, ...], or {"words": [...]}.
SRT/VTT cues are used as ready-made groups (no per-word timing, so karaoke spreads each cue's words evenly)."""
import json
import re
from pathlib import Path

from .contracts import ContractError, number
from .native import frame_of

STYLES = {
    'clean': {'pos': [.5, .86], 'fill': '#ffffff', 'stroke': '#14202c', 'lw': 3, 'shadow': False},
    'bold_pop': {'pos': [.5, .8], 'fill': '#ffffff', 'stroke': '#000000', 'lw': 6, 'shadow': 'dark', 'anim': 'pop'},
    'karaoke': {'pos': [.5, .86], 'fill': '#ffffff', 'stroke': '#14202c', 'lw': 3, 'shadow': False},
    'lower_third': {'pos': [.06, .86], 'align': 'left', 'fill': '#ffffff', 'stroke': '#000000', 'lw': 2, 'shadow': 'dark'},
    'title_card': {'pos': [.5, .5], 'fill': '#ffffff', 'stroke': None, 'shadow': 'dark', 'anim': 'fade'},
}


def _ts(text):
    h, m, rest = text.replace(',', '.').split(':')
    return int(h) * 3600 + int(m) * 60 + float(rest)


def read_words(path):
    """[(t0, t1, word)] and, for SRT/VTT, the cue groups."""
    path = Path(path)
    raw = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() in ('.srt', '.vtt'):
        cues = []
        for block in re.split(r'\n\s*\n', raw.strip()):
            m = re.search(r'(\d+:\d\d:\d\d[.,]\d+)\s*-->\s*(\d+:\d\d:\d\d[.,]\d+)', block)
            if not m:
                continue
            text = ' '.join(l.strip() for l in block.split('\n')[block.split('\n').index(next(l for l in block.split('\n') if '-->' in l)) + 1:] if l.strip())
            if text:
                cues.append((_ts(m.group(1)), _ts(m.group(2)), text))
        if not cues:
            raise ContractError(f'{path.name}: no subtitle cues found')
        words, groups = [], []
        for t0, t1, text in cues:   # spread each cue's words evenly for karaoke
            parts = text.split(); step = (t1 - t0) / len(parts); start = len(words)
            words += [(t0 + k * step, t0 + (k + 1) * step, w) for k, w in enumerate(parts)]
            groups.append(list(range(start, len(words))))
        return words, groups
    data = json.loads(raw)
    data = data.get('words', data) if isinstance(data, dict) else data
    words = []
    for i, w in enumerate(data if isinstance(data, list) else []):
        if isinstance(w, list) and len(w) >= 3:
            t0, t1, text = w[0], w[1], w[2]
        elif isinstance(w, dict):
            t0, t1, text = w.get('start', w.get('t0')), w.get('end', w.get('t1')), w.get('word', w.get('text'))
        else:
            raise ContractError(f'{path.name}: word {i} is not [t0, t1, word] or {{start, end, word}}')
        number(t0, f'word {i} start', 0); number(t1, f'word {i} end', t0)
        if not isinstance(text, str) or not text.strip():
            raise ContractError(f'{path.name}: word {i} has no text')
        words.append((float(t0), float(t1), text.strip()))
    if not words:
        raise ContractError(f'{path.name}: no words')
    return words, None


def group(words, max_chars=32, max_words=7, max_gap=.6, max_duration=3.0):
    groups, cur = [], []
    for i, (t0, t1, w) in enumerate(words):
        if cur:
            text = ' '.join(words[j][2] for j in cur + [i])
            if (len(text) > max_chars or len(cur) >= max_words or t0 - words[cur[-1]][1] > max_gap or t1 - words[cur[0]][0] > max_duration
                    or re.search(r'[.!?]$', words[cur[-1]][2])):
                groups.append(cur); cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    return groups


def make(words_path, fps, family, style='clean', size=None, height=1080, offset=0.0, highlight='#ffd200', karaoke_mode='word',
         max_chars=32, max_words=7, max_gap=.6, max_duration=3.0, hold=.15, min_duration=.5):
    if style not in STYLES:
        raise ContractError(f'style: use one of {", ".join(STYLES)}')
    if not isinstance(family, str) or not family:
        raise ContractError('family: the declared timeline font family to draw captions with')
    words, groups = read_words(words_path)
    words = [(max(0.0, t0 - offset), max(0.0, t1 - offset), w) for t0, t1, w in words]
    groups = groups or group(words, max_chars, max_words, max_gap, max_duration)
    events, cues = [], []
    for gi, g in enumerate(groups):
        t0, t1 = words[g[0]][0], words[g[-1]][1] + hold
        if gi + 1 < len(groups):
            t1 = min(t1, words[groups[gi + 1][0]][0])
        t1 = max(t1, t0 + min_duration) if gi + 1 == len(groups) else max(min(t1, words[groups[gi + 1][0]][0]), t0 + 1 / fps)
        text = ' '.join(words[j][2] for j in g)
        f0, f1 = frame_of(t0, fps), max(frame_of(t0, fps) + 1, frame_of(t1, fps))
        item = {'type': 'caption', 'text': text, 'f0': f0, 'f1': f1, 'family': family, 'size': size or round(height * .045), **STYLES[style]}
        if item.get('stroke') is None:
            item.pop('stroke', None); item['stroke'] = None
        if style == 'karaoke':
            item['karaoke'] = {'highlight': highlight, 'mode': karaoke_mode,
                               'words': [{'text': words[j][2], 't0': round(max(0.0, words[j][0] - f0 / fps), 4), 't1': round(max(0.0, words[j][1] - f0 / fps), 4)} for j in g]}
        events.append(item); cues.append((t0, t1, text))
    return events, cues


def _stamp(t, sep):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}'


def srt(cues):
    return '\n'.join(f'{i}\n{_stamp(a, ",")} --> {_stamp(b, ",")}\n{t}\n' for i, (a, b, t) in enumerate(cues, 1))


def vtt(cues):
    return 'WEBVTT\n\n' + '\n'.join(f'{_stamp(a, ".")} --> {_stamp(b, ".")}\n{t}\n' for a, b, t in cues)
