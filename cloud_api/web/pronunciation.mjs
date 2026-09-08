// Pure view-model for the pronunciation pane. No DOM, so the rules that keep a
// guide from being mistaken for a translation are directly testable.
//
// The pane is a reading aid only. The native text stays primary and is never
// replaced, and a response that does not echo the exact text we submitted is
// rejected rather than shown.

export const PRONUNCIATION_LANGUAGES = [['hi', 'Hindi'], ['ar', 'Arabic'], ['or', 'Odia']];
export const MAX_PRONUNCIATION_CHARACTERS = 2000;

const LANGUAGE_NAMES = new Map(PRONUNCIATION_LANGUAGES);

// Latin letters, plus the marks a readable guide legitimately uses. Anything
// outside this means we were handed native script or another language back.
const NON_LATIN = /\p{Letter}/u;
const LATIN = /\p{Script=Latin}/u;

export function isSupportedLanguage(language) {
  return LANGUAGE_NAMES.has(language);
}

export function validateRequest(text, language) {
  const trimmed = (text || '').trim();
  if (!trimmed) return { ok: false, message: 'Enter some text to get a pronunciation guide.' };
  if (!isSupportedLanguage(language)) {
    return { ok: false, message: 'Pronunciation guides cover Hindi, Arabic and Odia only.' };
  }
  if (trimmed.length > MAX_PRONUNCIATION_CHARACTERS) {
    return { ok: false, message: `Use at most ${MAX_PRONUNCIATION_CHARACTERS} characters.` };
  }
  return { ok: true, text: trimmed };
}

/**
 * Turn a server response into what the pane may display.
 *
 * `submitted` is the exact text the user sent. If the response does not echo it
 * character for character, the guide is discarded: a differing "native" field
 * means the model rewrote or translated the source, which is precisely the
 * failure this feature must not present as pronunciation.
 */
export function pronunciationView(submitted, language, result) {
  if (!result || result.ok !== true) {
    return { ok: false, message: 'No pronunciation guide was returned.' };
  }
  if (result.native !== submitted) {
    return { ok: false, message: 'The guide did not match your text, so it was discarded.' };
  }
  if (result.language !== language) {
    return { ok: false, message: 'The guide did not match your chosen language, so it was discarded.' };
  }
  if (result.approximate !== true) {
    return { ok: false, message: 'The guide could not be confirmed as approximate, so it was discarded.' };
  }
  const romanized = typeof result.romanized === 'string' ? result.romanized.trim() : '';
  if (!romanized) {
    return { ok: false, message: 'No pronunciation guide was returned.' };
  }
  // A guide that still carries native script is not a Latin reading aid.
  for (const character of romanized) {
    if (NON_LATIN.test(character) && !LATIN.test(character)) {
      return { ok: false, message: 'The guide was not in Latin script, so it was discarded.' };
    }
  }
  return {
    ok: true,
    native: submitted,
    romanized,
    language,
    languageName: LANGUAGE_NAMES.get(language),
    // Shown next to the guide every time, never as a one-off dismissible hint.
    notice: typeof result.notice === 'string' && result.notice.trim()
      ? result.notice.trim()
      : 'Approximate pronunciation, not an English translation.',
  };
}
