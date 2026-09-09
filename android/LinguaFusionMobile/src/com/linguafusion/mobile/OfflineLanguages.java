package com.linguafusion.mobile;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * The languages that work with nothing but the phone.
 *
 * Deliberately five: English, German, Arabic, Spanish and French. Hindi and
 * Odia are excluded on purpose -- Odia has no offline speech model at all, and
 * promising either would be worse than not offering them, because the failure
 * would only appear once someone was already somewhere without a signal.
 *
 * Whisper and ML Kit both use ISO 639-1 codes and agree on all five, but they
 * are asked for separately here so that a future language where they disagree
 * (Chinese and Hebrew are the usual traps) has somewhere to say so.
 *
 * Free of Android types so it can be tested on a normal JVM.
 */
final class OfflineLanguages {
    /** A language the app can handle with no network at all. */
    static final class Entry {
        final String code;        // what the app and Whisper use
        final String mlKitCode;   // what ML Kit's TranslateLanguage expects
        final String englishName;
        final String nativeName;

        Entry(String code, String mlKitCode, String englishName, String nativeName) {
            this.code = code;
            this.mlKitCode = mlKitCode;
            this.englishName = englishName;
            this.nativeName = nativeName;
        }
    }

    /** Chosen when the speaker has not said which language to expect. */
    static final String AUTO_DETECT = "auto";

    private static final Map<String, Entry> SUPPORTED;

    static {
        final Map<String, Entry> supported = new LinkedHashMap<>();
        for (Entry entry : new Entry[]{
                new Entry("en", "en", "English", "English"),
                new Entry("de", "de", "German", "Deutsch"),
                new Entry("ar", "ar", "Arabic", "العربية"),
                new Entry("es", "es", "Spanish", "Español"),
                new Entry("fr", "fr", "French", "Français"),
        }) {
            supported.put(entry.code, entry);
        }
        SUPPORTED = Collections.unmodifiableMap(supported);
    }

    private OfflineLanguages() {
    }

    static List<Entry> all() {
        return new ArrayList<>(SUPPORTED.values());
    }

    static boolean isSupported(String code) {
        return code != null && SUPPORTED.containsKey(normalise(code));
    }

    static Entry find(String code) {
        return code == null ? null : SUPPORTED.get(normalise(code));
    }

    /**
     * The ML Kit code for a language, or null if the app does not offer it
     * offline. Callers must treat null as "cannot do this offline" rather than
     * falling back to something else -- silently translating into a language
     * nobody asked for is worse than saying no.
     */
    static String mlKitCode(String code) {
        final Entry entry = find(code);
        return entry == null ? null : entry.mlKitCode;
    }

    /**
     * What Whisper should be told to expect. Whisper accepts "auto", so an
     * unset or unknown choice becomes detection rather than a wrong guess.
     */
    static String whisperCode(String code) {
        final Entry entry = find(code);
        return entry == null ? AUTO_DETECT : entry.code;
    }

    /**
     * Normalises what arrives from the web layer, a saved preference, or
     * Whisper's own detection: "EN", "en-GB" and "en_US" all mean English.
     * Whisper reports plain two-letter codes, but a stored preference may have
     * come from a browser, which does not.
     */
    static String normalise(String code) {
        if (code == null) {
            return "";
        }
        String trimmed = code.trim().toLowerCase(Locale.ROOT);
        final int cut = indexOfSeparator(trimmed);
        if (cut > 0) {
            trimmed = trimmed.substring(0, cut);
        }
        return trimmed;
    }

    private static int indexOfSeparator(String value) {
        for (int i = 0; i < value.length(); i++) {
            final char at = value.charAt(i);
            if (at == '-' || at == '_') {
                return i;
            }
        }
        return -1;
    }

    /**
     * Whether a pair can be translated on the device. ML Kit routes every
     * non-English pair through English internally, so German to Arabic works
     * but loses more than either would against English -- true here, with that
     * caveat surfaced to the person rather than hidden.
     */
    static boolean canTranslate(String from, String to) {
        return isSupported(from) && isSupported(to) && !normalise(from).equals(normalise(to));
    }

    /** Whether this pair is the lossier kind, so the app can say so. */
    static boolean pivotsThroughEnglish(String from, String to) {
        return canTranslate(from, to)
                && !normalise(from).equals("en")
                && !normalise(to).equals("en");
    }
}
