"""Original LED dot font (5x7 caps, 9-row cell with descenders for lowercase).

Authored for this project; not derived from any existing font file. Each glyph is a
list of rows, '#' = lit dot. Cell height is 9 rows: rows 0-6 are cap height, the
baseline is row 6, rows 7-8 hold descenders. Glyph width varies (proportional).
"""
import numpy as np

CAP = 7
CELL = 9
GAP = 1      # columns between glyphs
SPACE = 3    # width of a space

_G = {
 'A': ['.###.', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
 'B': ['####.', '#...#', '#...#', '####.', '#...#', '#...#', '####.'],
 'C': ['.###.', '#...#', '#....', '#....', '#....', '#...#', '.###.'],
 'D': ['####.', '#...#', '#...#', '#...#', '#...#', '#...#', '####.'],
 'E': ['#####', '#....', '#....', '####.', '#....', '#....', '#####'],
 'F': ['#####', '#....', '#....', '####.', '#....', '#....', '#....'],
 'G': ['.###.', '#...#', '#....', '#.###', '#...#', '#...#', '.####'],
 'H': ['#...#', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
 'I': ['###', '.#.', '.#.', '.#.', '.#.', '.#.', '###'],
 'J': ['..###', '...#.', '...#.', '...#.', '...#.', '#..#.', '.##..'],
 'K': ['#...#', '#..#.', '#.#..', '##...', '#.#..', '#..#.', '#...#'],
 'L': ['#....', '#....', '#....', '#....', '#....', '#....', '#####'],
 'M': ['#...#', '##.##', '#.#.#', '#.#.#', '#...#', '#...#', '#...#'],
 'N': ['#...#', '#...#', '##..#', '#.#.#', '#..##', '#...#', '#...#'],
 'O': ['.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
 'P': ['####.', '#...#', '#...#', '####.', '#....', '#....', '#....'],
 'Q': ['.###.', '#...#', '#...#', '#...#', '#.#.#', '#..#.', '.##.#'],
 'R': ['####.', '#...#', '#...#', '####.', '#.#..', '#..#.', '#...#'],
 'S': ['.####', '#....', '#....', '.###.', '....#', '....#', '####.'],
 'T': ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'],
 'U': ['#...#', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
 'V': ['#...#', '#...#', '#...#', '#...#', '#...#', '.#.#.', '..#..'],
 'W': ['#...#', '#...#', '#...#', '#.#.#', '#.#.#', '##.##', '#...#'],
 'X': ['#...#', '#...#', '.#.#.', '..#..', '.#.#.', '#...#', '#...#'],
 'Y': ['#...#', '#...#', '.#.#.', '..#..', '..#..', '..#..', '..#..'],
 'Z': ['#####', '....#', '...#.', '..#..', '.#...', '#....', '#####'],
 '.': ['..', '..', '..', '..', '..', '##', '##'],
 ',': ['..', '..', '..', '..', '##', '.#', '#.'],
 # lowercase: x-height rows 2-6, ascenders from row 0, descenders rows 7-8
 'a': ['.....', '.....', '.###.', '....#', '.####', '#...#', '.####'],
 'd': ['....#', '....#', '.####', '#...#', '#...#', '#...#', '.####'],
 'e': ['.....', '.....', '.###.', '#...#', '#####', '#....', '.###.'],
 'i': ['.#.', '...', '##.', '.#.', '.#.', '.#.', '###'],
 'n': ['.....', '.....', '####.', '#...#', '#...#', '#...#', '#...#'],
 'p': ['.....', '.....', '####.', '#...#', '#...#', '#...#', '####.', '#....', '#....'],
 't': ['.#..', '.#..', '###.', '.#..', '.#..', '.#..', '..##'],
}


def glyph(ch):
    if ch == ' ':
        return np.zeros((CELL, SPACE), np.float32)
    if ch not in _G:
        raise ValueError(f'Unsupported LED glyph {ch!r}; use a shaped composition for full typography')
    rows = _G[ch]
    w = len(rows[0])
    g = np.zeros((CELL, w), np.float32)
    for r, line in enumerate(rows):
        assert len(line) == w, (ch, line)
        g[r] = [1.0 if c == '#' else 0.0 for c in line]
    return g


def has_descender(text):
    return any(len(_G.get(c, [])) > CAP for c in text)


def line_bitmap(text, scale=1):
    """Return (bitmap, char_spans). Bitmap is CELL*scale rows (or CAP*scale when no
    descenders are used). char_spans[i] = (c0, c1) column span of character i."""
    parts, spans, x = [], [], 0
    for i, ch in enumerate(text):
        g = glyph(ch)
        if parts:
            parts.append(np.zeros((CELL, GAP), np.float32)); x += GAP
        spans.append((x * scale, (x + g.shape[1]) * scale))
        parts.append(g); x += g.shape[1]
    bm = np.concatenate(parts, axis=1) if parts else np.zeros((CELL, 0), np.float32)
    rows = CELL if has_descender(text) else CAP
    bm = bm[:rows]
    if scale > 1:
        bm = np.kron(bm, np.ones((scale, scale), np.float32))
    return bm, spans


def text_width(text, scale=1):
    return line_bitmap(text, scale)[0].shape[1]
