package com.linguafusion.mobile;

import android.os.Build;

/**
 * Writing Arabic, Hindi or Odia text in Latin letters, on the device.
 *
 * Android carries ICU's transliteration engine in the platform itself, so
 * this needs no dependency and nothing downloaded. It arrived in API 29,
 * below which the feature is simply not offered rather than silently
 * returning the original text -- someone who cannot read the script would
 * have no way to tell those apart.
 *
 * This is a reading aid and not a translation, and it is not a pronunciation
 * guide either: ICU transliterates script to script, so it says which letters
 * are there, not how a speaker would actually say them. Short vowels absent
 * from written Arabic stay absent. The cloud's guide, which uses a language
 * model, reads better; this one works in a tunnel.
 */
final class OfflineRomanize {
    /** ICU's transliteration arrived in Android 10. */
    private static final int REQUIRED_API = Build.VERSION_CODES.Q;

    private OfflineRomanize() {
    }

    static boolean isSupported() {
        return Build.VERSION.SDK_INT >= REQUIRED_API;
    }

    /**
     * Which languages are worth romanising. Latin-script languages are
     * excluded because turning German into Latin letters is a no-op that
     * would look like the feature had failed.
     */
    static boolean isWorthRomanising(String languageCode) {
        final String code = OfflineLanguages.normalise(languageCode);
        return "ar".equals(code) || "hi".equals(code) || "or".equals(code);
    }

    /** What the picker offers. Not the same set as speech and translation:
     *  these are scripts worth rewriting, and Hindi and Odia belong here even
     *  though neither can be transcribed or translated on the device. */
    static final String[][] LANGUAGES = {
        {"ar", "Arabic", "العربية"},
        {"hi", "Hindi", "हिन्दी"},
        {"or", "Odia", "ଓଡ଼ିଆ"},
    };

    /** The ICU rule to apply, or null if there is nothing sensible to do. */
    static String ruleFor(String languageCode) {
        switch (OfflineLanguages.normalise(languageCode)) {
            case "ar": return "Arabic-Latin";
            case "hi": return "Devanagari-Latin";
            case "or": return "Oriya-Latin";
            default: return null;
        }
    }

    /**
     * Romanises text.
     *
     * @return the Latin-letter form, or a message beginning with "ERROR: "
     */
    static String romanize(String text, String languageCode) {
        if (text == null || text.trim().isEmpty()) {
            return "";
        }
        if (!isSupported()) {
            return "ERROR: This phone is too old to do that without the cloud "
                    + "(it needs Android 10 or newer).";
        }
        final String rule = ruleFor(languageCode);
        if (rule == null) {
            return "ERROR: That language is already written in Latin letters.";
        }
        try {
            final android.icu.text.Transliterator transliterator =
                    android.icu.text.Transliterator.getInstance(rule);
            return transliterator.transliterate(text);
        } catch (IllegalArgumentException unknownRule) {
            // A rule this build of ICU does not carry. Fall back to the
            // generic one, which handles most scripts, before giving up.
            try {
                return android.icu.text.Transliterator
                        .getInstance("Any-Latin").transliterate(text);
            } catch (RuntimeException failure) {
                return "ERROR: This phone cannot romanise that script offline.";
            }
        } catch (RuntimeException failure) {
            return "ERROR: That text could not be romanised.";
        }
    }
}
