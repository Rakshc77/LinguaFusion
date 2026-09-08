"""Rebuild page layout from Google Vision's geometry.

Vision returns every word with a bounding box, but `fullTextAnnotation.text`
flattens all of that into a stream of lines. On a receipt, a form or anything in
columns the result is unreadable: the label and its value end up on different
lines, and table rows interleave.

These functions are pure so the reconstruction can be tested against fixed
geometry without calling the API.

Deliberately NOT a table parser. It groups words into visual lines and detects
column gaps, which is enough to keep a table legible as aligned text. Inferring
a real cell grid from OCR boxes is unreliable, and a wrong grid reads worse than
honest aligned text.
"""
from statistics import median

# A word joins a line when its vertical centre sits inside the line's band.
# Expressed as a fraction of line height so it scales with font size.
LINE_TOLERANCE = 0.6
# A horizontal gap wider than this many times the local character width is
# treated as a column separator rather than a word space.
COLUMN_GAP_RATIO = 2.2
MIN_COLUMN_GAP = 12


def _box(vertices):
    xs = [vertex.get('x', 0) for vertex in vertices or []]
    ys = [vertex.get('y', 0) for vertex in vertices or []]
    if not xs or not ys:
        return None
    return {'left': min(xs), 'right': max(xs), 'top': min(ys), 'bottom': max(ys)}


def _word_text(word):
    parts = []
    for symbol in word.get('symbols', []):
        parts.append(symbol.get('text', ''))
        breaks = (symbol.get('property') or {}).get('detectedBreak') or {}
        if breaks.get('type') in ('SPACE', 'EOL_SURE_SPACE'):
            parts.append(' ')
    return ''.join(parts)


def words_from(annotation):
    """Every word on the page with its geometry, in reading order per block."""
    found = []
    for page in (annotation or {}).get('pages', []):
        for block in page.get('blocks', []):
            for paragraph in block.get('paragraphs', []):
                for word in paragraph.get('words', []):
                    box = _box((word.get('boundingBox') or {}).get('vertices'))
                    text = _word_text(word).strip()
                    if box and text:
                        found.append({'text': text, **box,
                                      'height': max(1, box['bottom'] - box['top'])})
    return found


def group_into_lines(words):
    """Group words that sit on the same visual line, left to right.

    Sorting by the top edge alone splits a line whenever one word is a pixel
    higher, which is exactly what makes flattened output unreadable.
    """
    lines = []
    for word in sorted(words, key=lambda item: (item['top'], item['left'])):
        centre = (word['top'] + word['bottom']) / 2
        placed = False
        for line in lines:
            if abs(centre - line['centre']) <= LINE_TOLERANCE * line['height']:
                line['words'].append(word)
                line['centre'] = sum((w['top'] + w['bottom']) / 2 for w in line['words']) / len(line['words'])
                line['height'] = max(line['height'], word['height'])
                placed = True
                break
        if not placed:
            lines.append({'centre': centre, 'height': word['height'], 'words': [word]})
    for line in lines:
        line['words'].sort(key=lambda item: item['left'])
    lines.sort(key=lambda line: line['centre'])
    return lines


def render_line(line):
    """One line of text, with wide gaps preserved as column separation."""
    words = line['words']
    if not words:
        return ''
    pieces = [words[0]['text']]
    for previous, current in zip(words, words[1:]):
        gap = current['left'] - previous['right']
        # Character width estimated from the previous word, so the threshold
        # follows the font rather than assuming a fixed page size.
        character = max(1, (previous['right'] - previous['left']) / max(1, len(previous['text'])))
        if gap > max(MIN_COLUMN_GAP, COLUMN_GAP_RATIO * character):
            pieces.append('\t')
        elif gap > character * 0.3:
            pieces.append(' ')
        pieces.append(current['text'])
    return ''.join(pieces).rstrip()


def reconstruct(annotation):
    """Layout-preserving text, plus what was found, from a Vision annotation."""
    words = words_from(annotation)
    if not words:
        return {'text': (annotation or {}).get('text', '') or '', 'lines': 0,
                'columns': 0, 'layout_preserved': False}

    lines = group_into_lines(words)
    rendered = [render_line(line) for line in lines]

    # A paragraph break is a gap noticeably larger than THIS page's normal line
    # spacing. A fixed multiple of line height gets it wrong both ways: it
    # splits loosely-leaded forms and misses breaks in tightly-set prose.
    gaps = [later['centre'] - earlier['centre'] for earlier, later in zip(lines, lines[1:])]
    # A true median: taking the upper of two values would make the single
    # large gap on a two-paragraph page count as normal spacing.
    typical = median(gaps) if gaps else 0

    output = []
    previous = None
    for line, text in zip(lines, rendered):
        if previous is not None:
            gap = line['centre'] - previous['centre']
            tall = max(previous['height'], line['height'])
            break_here = gap > 1.6 * typical if typical else gap > 2.2 * tall
            # Guard against a page whose median gap is itself tiny.
            if break_here and gap > 1.5 * tall:
                output.append('')
        output.append(text)
        previous = line

    columns = max((text.count('\t') + 1) for text in rendered) if rendered else 1
    return {'text': '\n'.join(output).strip(), 'lines': len(lines),
            'columns': columns, 'layout_preserved': True,
            'looks_tabular': columns >= 2 and sum('\t' in t for t in rendered) >= 2}
