"""Layout reconstruction from Vision geometry, tested on fixed boxes.

Vision's flat `text` puts a label and its value on separate lines whenever they
sit side by side, which makes forms, receipts and tables unreadable. These
tests build pages out of coordinates so the grouping can be checked exactly.
"""
from cloud_api.ocr_layout import group_into_lines, reconstruct, render_line, words_from


def word(text, left, top, width=None, height=20):
    width = width if width is not None else 12 * len(text)
    return {
        'boundingBox': {'vertices': [
            {'x': left, 'y': top}, {'x': left + width, 'y': top},
            {'x': left + width, 'y': top + height}, {'x': left, 'y': top + height}]},
        'symbols': [{'text': character} for character in text],
    }


def page(*words):
    return {'text': ' '.join(w['symbols'][0]['text'] for w in words),
            'pages': [{'blocks': [{'paragraphs': [{'words': list(words)}]}]}]}


def test_words_carry_their_geometry():
    found = words_from(page(word('Total', 10, 10), word('42.00', 300, 12)))
    assert [item['text'] for item in found] == ['Total', '42.00']
    assert found[0]['left'] == 10 and found[1]['left'] == 300


def test_words_on_one_visual_line_are_not_split_by_a_pixel():
    # Vision reports slightly different tops for words on the same line. Sorting
    # by top alone breaks the line apart, which is what ruins forms.
    lines = group_into_lines(words_from(page(
        word('Name', 10, 10), word('Ada', 200, 12), word('Lovelace', 260, 9))))
    assert len(lines) == 1, 'a one-pixel wobble must not start a new line'
    assert [w['text'] for w in lines[0]['words']] == ['Name', 'Ada', 'Lovelace']


def test_a_wide_gap_becomes_a_column_separator():
    line = group_into_lines(words_from(page(
        word('Item', 10, 10), word('Qty', 400, 10), word('Price', 700, 10))))[0]
    rendered = render_line(line)
    assert rendered.count('\t') == 2, rendered
    assert rendered.split('\t') == ['Item', 'Qty', 'Price']


def test_ordinary_word_spacing_is_not_mistaken_for_a_column():
    line = group_into_lines(words_from(page(
        word('the', 10, 10), word('quick', 55, 10), word('brown', 125, 10))))[0]
    assert '\t' not in render_line(line)
    assert render_line(line) == 'the quick brown'


def test_a_table_keeps_its_rows_and_columns_aligned():
    result = reconstruct(page(
        word('Item', 10, 10), word('Qty', 400, 10), word('Price', 700, 10),
        word('Apple', 10, 40), word('3', 400, 40), word('1.20', 700, 40),
        word('Pear', 10, 70), word('12', 400, 70), word('0.80', 700, 70)))
    rows = result['text'].split('\n')
    assert len(rows) == 3, result['text']
    assert all(row.count('\t') == 2 for row in rows), result['text']
    assert rows[1].split('\t') == ['Apple', '3', '1.20']
    assert result['looks_tabular'] is True
    assert result['columns'] == 3


def test_a_label_stays_beside_its_value():
    # The failure this exists to prevent: flat text emits every label, then
    # every value, so nothing can be matched up afterwards.
    result = reconstruct(page(
        word('Patient', 10, 10), word('Ada', 400, 10),
        word('Weight', 10, 50), word('62kg', 400, 50)))
    first, second = result['text'].split('\n')
    assert 'Patient' in first and 'Ada' in first
    assert 'Weight' in second and '62kg' in second


def test_a_paragraph_break_is_preserved():
    result = reconstruct(page(
        word('First', 10, 10), word('line', 70, 10),
        word('Second', 10, 34),
        word('After', 10, 200), word('a', 80, 200), word('gap', 110, 200)))
    assert '' in result['text'].split('\n'), 'a large vertical gap should read as a break'


def test_prose_is_not_reported_as_a_table():
    result = reconstruct(page(
        word('This', 10, 10), word('is', 60, 10), word('prose', 90, 10),
        word('running', 10, 40), word('on', 100, 40)))
    assert result['looks_tabular'] is False
    assert result['columns'] == 1


def test_an_empty_or_unstructured_response_falls_back_to_the_flat_text():
    # Never lose the text just because geometry is missing.
    assert reconstruct({'text': 'plain', 'pages': []})['text'] == 'plain'
    assert reconstruct({})['text'] == ''
    assert reconstruct(None)['text'] == ''
    assert reconstruct({'text': 'plain', 'pages': []})['layout_preserved'] is False


def test_detected_break_spaces_inside_a_word_are_kept():
    entry = word('', 10, 10, width=60)
    entry['symbols'] = [{'text': 'A'}, {'text': 'B', 'property': {'detectedBreak': {'type': 'SPACE'}}},
                        {'text': 'C'}]
    found = words_from({'pages': [{'blocks': [{'paragraphs': [{'words': [entry]}]}]}]})
    assert found[0]['text'] == 'AB C'
