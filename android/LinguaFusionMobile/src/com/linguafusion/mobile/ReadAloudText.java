package com.linguafusion.mobile;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Validation and chunking kept free of Android APIs so it is JVM-testable. */
final class ReadAloudText {
    static final int MAX_CHARACTERS = 12_000;
    private static final Set<String> ONLINE = Collections.unmodifiableSet(
        new HashSet<>(Arrays.asList("en", "de", "ar", "es", "fr", "hi", "or")));
    private static final Set<String> OFFLINE = Collections.unmodifiableSet(
        new HashSet<>(Arrays.asList("en", "de", "ar", "es", "fr")));

    private ReadAloudText() {}

    static String language(String value, boolean offline) {
        if (value == null) return "";
        String normalised = value.trim().toLowerCase(Locale.ROOT);
        int dash = normalised.indexOf('-');
        int underscore = normalised.indexOf('_');
        int cut = dash < 0 ? underscore : underscore < 0 ? dash : Math.min(dash, underscore);
        if (cut > 0) normalised = normalised.substring(0, cut);
        return (offline ? OFFLINE : ONLINE).contains(normalised) ? normalised : "";
    }

    static boolean requestId(String value) {
        return value != null && value.matches("[A-Za-z0-9_-]{1,64}");
    }

    static float rate(double value) {
        if (value == 0.75d || value == 1d || value == 1.25d) return (float) value;
        return 0f;
    }

    static String text(String value) {
        if (value == null) return "";
        String trimmed = value.trim();
        return trimmed.length() <= MAX_CHARACTERS ? trimmed : "";
    }

    static List<String> chunks(String text, int maximum) {
        if (maximum < 1) throw new IllegalArgumentException("maximum must be positive");
        List<String> chunks = new ArrayList<>();
        int start = 0;
        while (start < text.length()) {
            int end = Math.min(text.length(), start + maximum);
            // If the limit lands immediately before whitespace, the current
            // slice already ends on a complete word. Searching backwards in
            // that case would make an unnecessarily short chunk.
            if (end < text.length() && !Character.isWhitespace(text.charAt(end))) {
                int split = -1;
                for (int at = end; at > start + maximum / 2; at--) {
                    if (Character.isWhitespace(text.charAt(at - 1))) {
                        split = at;
                        break;
                    }
                }
                if (split > start) end = split;
            }
            String chunk = text.substring(start, end).trim();
            if (!chunk.isEmpty()) chunks.add(chunk);
            start = end;
            while (start < text.length() && Character.isWhitespace(text.charAt(start))) start++;
        }
        return chunks;
    }
}
