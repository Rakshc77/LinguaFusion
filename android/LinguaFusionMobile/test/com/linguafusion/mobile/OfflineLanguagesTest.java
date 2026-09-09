package com.linguafusion.mobile;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class OfflineLanguagesTest {

    @Test
    public void the_five_agreed_languages_are_offered_and_no_others() {
        assertEquals(5, OfflineLanguages.all().size());
        for (String code : new String[]{"en", "de", "ar", "es", "fr"}) {
            assertTrue(code, OfflineLanguages.isSupported(code));
        }
    }

    @Test
    public void hindi_and_odia_are_not_offered_offline() {
        // Excluded deliberately: Odia has no offline speech model, and
        // offering either would fail only once someone had no signal.
        assertFalse(OfflineLanguages.isSupported("hi"));
        assertFalse(OfflineLanguages.isSupported("or"));
        assertNull(OfflineLanguages.mlKitCode("hi"));
        assertNull(OfflineLanguages.mlKitCode("or"));
    }

    @Test
    public void an_unsupported_language_is_refused_rather_than_substituted() {
        // Returning some other language here would translate into a language
        // nobody asked for, which is worse than refusing.
        assertNull(OfflineLanguages.mlKitCode("ja"));
        assertNull(OfflineLanguages.mlKitCode(null));
        assertNull(OfflineLanguages.find("klingon"));
    }

    @Test
    public void regional_and_upper_case_tags_resolve_to_the_base_language() {
        // A stored preference may have come from a browser as "en-GB", and
        // Whisper reports plain "en".
        for (String tag : new String[]{"EN", "en-GB", "en_US", " en ", "En-us"}) {
            assertTrue(tag, OfflineLanguages.isSupported(tag));
            assertEquals(tag, "en", OfflineLanguages.mlKitCode(tag));
        }
    }

    @Test
    public void an_unknown_language_makes_whisper_detect_rather_than_guess() {
        assertEquals(OfflineLanguages.AUTO_DETECT, OfflineLanguages.whisperCode(null));
        assertEquals(OfflineLanguages.AUTO_DETECT, OfflineLanguages.whisperCode("ja"));
        assertEquals(OfflineLanguages.AUTO_DETECT, OfflineLanguages.whisperCode("auto"));
        assertEquals("de", OfflineLanguages.whisperCode("de-AT"));
    }

    @Test
    public void translating_a_language_into_itself_is_not_a_translation() {
        assertFalse(OfflineLanguages.canTranslate("en", "en"));
        assertFalse(OfflineLanguages.canTranslate("de", "de-AT"));
        assertTrue(OfflineLanguages.canTranslate("de", "fr"));
    }

    @Test
    public void a_pair_with_an_unsupported_side_cannot_be_translated() {
        assertFalse(OfflineLanguages.canTranslate("en", "hi"));
        assertFalse(OfflineLanguages.canTranslate("hi", "en"));
        assertFalse(OfflineLanguages.canTranslate(null, "en"));
    }

    @Test
    public void pairs_that_pivot_through_english_are_identifiable() {
        // ML Kit routes non-English pairs through English, which costs
        // quality. The app tells the person rather than hiding it.
        assertTrue(OfflineLanguages.pivotsThroughEnglish("de", "ar"));
        assertTrue(OfflineLanguages.pivotsThroughEnglish("es", "fr"));
        assertFalse(OfflineLanguages.pivotsThroughEnglish("en", "de"));
        assertFalse(OfflineLanguages.pivotsThroughEnglish("de", "en"));
        assertFalse("an impossible pair does not pivot, it just fails",
                OfflineLanguages.pivotsThroughEnglish("de", "hi"));
    }

    @Test
    public void every_offered_language_has_both_engine_codes_and_two_names() {
        for (OfflineLanguages.Entry entry : OfflineLanguages.all()) {
            assertTrue(entry.code, entry.code.length() == 2);
            assertTrue(entry.code, entry.mlKitCode != null && !entry.mlKitCode.isEmpty());
            assertTrue(entry.code, entry.englishName != null && !entry.englishName.isEmpty());
            assertTrue(entry.code, entry.nativeName != null && !entry.nativeName.isEmpty());
        }
    }
}
