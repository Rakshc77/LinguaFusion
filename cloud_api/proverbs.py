"""Recognising idioms and proverbs, so they are not translated literally.

A translator that renders "it's raining cats and dogs" as falling animals has
not made a small error, it has produced nonsense that reads as confident. The
same is true in the other direction, and worse for Arabic, Hindi and Odia,
where proverbs carry a great deal of ordinary conversation and general models
have seen far less of them.

This module only *recognises*. What is done with a match differs by where the
translation happens, and deliberately so:

- Online, a match becomes a hint to the model: "this phrase is an idiom
  meaning X; in Spanish it is conventionally Y." The model still writes the
  sentence. Nothing is substituted behind its back.
- Offline, ML Kit cannot be advised, so the equivalent is substituted directly.
  That is riskier, which is why matching is deliberately strict.

The strictness is the point. `CLAUDE.md` records what happened when automated
"correction" was trusted to improve text: Ollama rewrote lyrics into confident
fabrication. A false idiom match does the same thing in miniature -- someone
genuinely discussing a buried dog should not have their sentence replaced. So
this matches whole normalised phrases only, never fragments, and a caller can
always see what matched and why.
"""
import json
import pathlib
import re
import unicodedata

DATA = pathlib.Path(__file__).with_name('proverbs.json')

# Arabic diacritics are optional in writing, so text that means the same thing
# can differ byte for byte. Stripping them is what makes matching possible.
_ARABIC_DIACRITICS = re.compile(r'[ً-ْٰـ]')
_ARABIC_FOLD = str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ة': 'ه', 'ى': 'ي'})
_PUNCTUATION = re.compile(r'[^\w\s]', re.UNICODE)
_SPACES = re.compile(r'\s+')


def normalise(text, language=None):
    """Fold away everything that varies without changing meaning.

    Case, punctuation, spacing, and for Arabic the optional diacritics and the
    interchangeable letter forms. Devanagari and Odia need no folding beyond
    the shared steps; their scripts do not carry the same optional marks.
    """
    if not text:
        return ''
    folded = unicodedata.normalize('NFC', text)
    if (language or '').startswith('ar'):
        folded = _ARABIC_DIACRITICS.sub('', folded).translate(_ARABIC_FOLD)
    folded = _PUNCTUATION.sub(' ', folded.lower())
    return _SPACES.sub(' ', folded).strip()


class Proverbs:
    """The recognised set, loaded once."""

    def __init__(self, entries):
        self.entries = entries
        # Pre-normalised, because matching runs on every translation and the
        # folding above is not free.
        self._index = []
        for entry in entries:
            for language, forms in entry.get('forms', {}).items():
                for form in forms:
                    key = normalise(form, language)
                    if key:
                        # The original spelling travels with the folded key:
                        # a hint that quotes "it s raining" back at a model is
                        # showing it mangled text.
                        self._index.append((language, key, form, entry))
        # Longest first: "the straw that broke the camel's back" must win over
        # a shorter entry that happens to sit inside it.
        self._index.sort(key=lambda row: -len(row[1]))

    @classmethod
    def load(cls, path=DATA):
        return cls(json.loads(pathlib.Path(path).read_text(encoding='utf-8'))['proverbs'])

    def languages(self):
        seen = set()
        for entry in self.entries:
            seen.update(entry.get('forms', {}))
        return sorted(seen)

    def find(self, text, language=None):
        """Idioms present in this text, longest first, without overlaps.

        `language` narrows the search when the source language is known. Left
        unset every language is tried, which is what the online path needs:
        the model detects the language, we do not.
        """
        haystack = {}
        matched = []
        taken = []
        for form_language, key, form, entry in self._index:
            if language and form_language != normalise(language):
                continue
            if form_language not in haystack:
                haystack[form_language] = normalise(text, form_language)
            where = haystack[form_language].find(key)
            if where < 0:
                continue
            span = (where, where + len(key))
            # One phrase cannot be two idioms. The longest already won.
            if any(span[0] < end and start < span[1] for start, end in taken):
                continue
            taken.append(span)
            matched.append({'id': entry['id'], 'meaning': entry['meaning'],
                            'matched_language': form_language,
                            'matched': key,            # normalised, for tests
                            'phrase': form,            # as actually written
                            'entry': entry})
        return matched

    def equivalent(self, entry, target):
        """How this idiom is normally said in the target language, if at all.

        Returns None when the set has no equivalent rather than inventing one:
        a literal rendering of the meaning is the caller's job, and is better
        than a fabricated proverb.
        """
        target = normalise(target)
        forms = entry.get('forms', {}).get(target) or []
        return forms[0] if forms else None

    def hint(self, text, target, language=None, limit=4):
        """A note for a translation model about the idioms in this text.

        Capped, because a long list would crowd out the text itself and every
        line costs tokens the owner pays for.
        """
        target = normalise(target)
        notes = []
        for match in self.find(text, language)[:limit]:
            entry = match['entry']
            equivalent = self.equivalent(entry, target)
            note = f'"{match["phrase"]}" is an idiom meaning: {entry["meaning"]}.'
            if equivalent:
                note += f' It is conventionally said as "{equivalent}".'
            else:
                note += ' Render the meaning naturally; do not translate it word for word.'
            notes.append(note)
        return notes
