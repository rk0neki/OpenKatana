"""Single-run glyph geometry using licensed HarfBuzz/fontTools, independent of browser layout."""
from __future__ import annotations

import io
import math
from pathlib import Path
import re

from .contracts import ContractError
from .render import digest, write_json


def shape_text(font, text, size=72, direction=None, language='und', script=None,
               features=None, variations=None, radius=None):
    """Shape one homogeneous script/direction run, returning positions and SVG paths.

    Clusters index Python Unicode characters. This is not a paragraph bidi or font
    fallback engine; use compositions for mixed-script, multiline browser layout.
    Curved placement rotates complete shaped glyphs and preserves their contours.
    """
    try:
        import uharfbuzz as hb
        from fontTools.ttLib import TTFont
        from fontTools.pens.svgPathPen import SVGPathPen
        from fontTools.pens.transformPen import TransformPen
        from fontTools.pens.boundsPen import BoundsPen
    except ImportError as e:
        raise ContractError('Glyph geometry requires the text extra: run python -m pip install -e ".[text]" from the OpenKatana checkout') from e
    font = Path(font).resolve()
    if font.suffix.lower() not in ('.ttf', '.otf') or not font.is_file():
        raise ContractError('Supply an existing TTF or OTF font; collections and webfonts are not accepted here')
    if not isinstance(text, str) or not 1 <= len(text) <= 4096 or any(c in text for c in '\n\r\t'):
        raise ContractError('Use a single nonempty text run of at most 4096 characters')
    if type(size) not in (int, float) or not math.isfinite(size) or not 1 <= size <= 4096:
        raise ContractError('size must be a finite number from 1 to 4096')
    if direction not in (None, 'ltr', 'rtl', 'ttb', 'btt'):
        raise ContractError('direction must be ltr, rtl, ttb or btt')
    if not isinstance(language, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,64}', language):
        raise ContractError('language must be a BCP 47 tag')
    if script is not None and (not isinstance(script, str) or not re.fullmatch('[A-Za-z]{4}', script)):
        raise ContractError('script must be a four-letter ISO 15924 tag')
    features = {} if features is None else features
    variations = {} if variations is None else variations
    for label, values in [('features', features), ('variations', variations)]:
        if not isinstance(values, dict) or len(values) > 64:
            raise ContractError(label + ' must be a mapping of at most 64 OpenType tags')
        for tag, value in values.items():
            if not isinstance(tag, str) or not re.fullmatch('[ -~]{4}', tag):
                raise ContractError('Use four-character OpenType tags')
            if label == 'features':
                if type(value) not in (int, bool) or not 0 <= value <= 65535:
                    raise ContractError('Feature values must be booleans or nonnegative integers')
            elif type(value) not in (int, float) or not math.isfinite(value):
                raise ContractError('Variation values must be finite numbers')
    if radius is not None and (type(radius) not in (int, float) or not math.isfinite(radius) or abs(radius) < size):
        raise ContractError('Curved placement radius must be finite with magnitude at least size')
    raw = font.read_bytes()
    with TTFont(io.BytesIO(raw), lazy=False) as tt:
        axes = {a.axisTag: (a.minValue, a.maxValue) for a in tt['fvar'].axes} if 'fvar' in tt else {}
        for tag, value in variations.items():
            if tag not in axes or not axes[tag][0] <= value <= axes[tag][1]:
                raise ContractError(f'Variation {tag} is absent or outside its font bounds')
        face = hb.Face(raw); hbfont = hb.Font(face); hbfont.scale = (face.upem, face.upem)
        hbfont.set_variations(variations)
        buf = hb.Buffer(); buf.add_str(text); buf.language = language
        if direction: buf.direction = direction
        if script: buf.script = script
        buf.guess_segment_properties(); hb.shape(hbfont, buf, features)
        if radius is not None and buf.direction in ('ttb', 'btt'):
            raise ContractError('Curved placement currently supports horizontal runs only')
        glyphset = tt.getGlyphSet(location=variations); order = tt.getGlyphOrder(); scale = size / face.upem
        x = y = 0.; glyphs = []; all_bounds = []
        width = sum(p.x_advance for p in buf.glyph_positions) * scale
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            gx, gy = (x + pos.x_offset) * scale, -(y + pos.y_offset) * scale
            angle = 0.
            if radius is not None:
                angle = (gx - width / 2) / radius
                gx, gy = radius * math.sin(angle), gy + radius * (1 - math.cos(angle))
            co, si = math.cos(angle), math.sin(angle)
            transform = (scale*co, scale*si, scale*si, -scale*co, gx, gy)
            name = order[info.codepoint]; pen = SVGPathPen(glyphset)
            glyphset[name].draw(TransformPen(pen, transform))
            bp = BoundsPen(glyphset); glyphset[name].draw(TransformPen(bp, transform))
            if bp.bounds: all_bounds.append(bp.bounds)
            glyphs.append({'id': info.codepoint, 'name': name, 'cluster': info.cluster,
                           'advance': [pos.x_advance*scale, -pos.y_advance*scale],
                           'offset': [pos.x_offset*scale, -pos.y_offset*scale],
                           'origin': [gx, gy], 'angle': angle, 'path': pen.getCommands(),
                           'bounds': list(bp.bounds) if bp.bounds else None})
            x += pos.x_advance; y += pos.y_advance
    bounds = [min(b[0] for b in all_bounds), min(b[1] for b in all_bounds),
              max(b[2] for b in all_bounds), max(b[3] for b in all_bounds)] if all_bounds else [0, -size, max(size, width), 0]
    pad = max(1, size*.05); vx, vy = bounds[0]-pad, bounds[1]-pad
    vw, vh = max(1, bounds[2]-bounds[0])+2*pad, max(1, bounds[3]-bounds[1])+2*pad
    paths = ''.join('<path d="' + g['path'] + '"/>' for g in glyphs)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx} {vy} {vw} {vh}" width="{vw}" height="{vh}"><g fill="black">{paths}</g></svg>'
    return {'schema': 1, 'font_sha256': digest(font), 'text': text, 'size': size,
            'direction': buf.direction, 'language': buf.language, 'script': buf.script,
            'features': features, 'variations': variations, 'radius': radius, 'units_per_em': face.upem,
            'advance': [x*scale, -y*scale], 'bounds': bounds, 'glyphs': glyphs,
            'missing_clusters': sorted({g['cluster'] for g in glyphs if g['id'] == 0}),
            'svg': svg, 'scope': 'single script/direction run; composition handles paragraph bidi/layout',
            'versions': {'uharfbuzz': hb.__version__, 'harfbuzz': hb.version_string()}}


def export_text(font, text, out, **options):
    result = shape_text(font, text, **options)
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=False)
    (out/'text.svg').write_text(result['svg'], encoding='utf-8')
    result['svg_file'] = str(out/'text.svg')
    write_json(out/'glyphs.json', result)
    return result
