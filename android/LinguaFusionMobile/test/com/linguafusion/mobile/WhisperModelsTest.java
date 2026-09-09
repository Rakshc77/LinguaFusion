package com.linguafusion.mobile;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class WhisperModelsTest {

    @Test
    public void the_recommended_model_exists_and_is_the_fallback() {
        assertNotNull(WhisperModels.find(WhisperModels.RECOMMENDED));
        // An unset or unrecognised choice must land on something usable
        // rather than leaving the app with no model at all.
        assertEquals(WhisperModels.RECOMMENDED, WhisperModels.chosen(null).id);
        assertEquals(WhisperModels.RECOMMENDED, WhisperModels.chosen("no-such-model").id);
        assertEquals("base-q5_1", WhisperModels.chosen("base-q5_1").id);
    }

    @Test
    public void every_model_has_a_real_size_and_a_full_checksum() {
        for (WhisperModels.Model model : WhisperModels.all()) {
            assertTrue(model.id, model.bytes > 1_000_000L);
            assertEquals("sha256 must be 64 hex characters: " + model.id,
                    64, model.sha256.length());
            assertTrue(model.id, model.sha256.matches("[0-9a-f]{64}"));
            assertTrue(model.id, model.url.startsWith("https://"));
            assertTrue(model.id, model.url.endsWith(model.fileName));
        }
    }

    @Test
    public void models_are_told_apart_by_size_and_checksum() {
        final WhisperModels.Model small = WhisperModels.find("small-q5_1");
        assertTrue(WhisperModels.matches(small, small.bytes, small.sha256));
        // Upper case is what some servers return; it is still the same digest.
        assertTrue(WhisperModels.matches(small, small.bytes,
                small.sha256.toUpperCase(java.util.Locale.ROOT)));
    }

    @Test
    public void a_truncated_download_is_rejected() {
        // The common failure: a dropped connection leaves a plausible file
        // that whisper.cpp would load and then transcribe noise from.
        final WhisperModels.Model small = WhisperModels.find("small-q5_1");
        assertFalse(WhisperModels.matches(small, small.bytes - 1, small.sha256));
        assertFalse(WhisperModels.matches(small, 0, small.sha256));
    }

    @Test
    public void a_corrupted_download_of_the_right_length_is_rejected() {
        final WhisperModels.Model small = WhisperModels.find("small-q5_1");
        final String wrong = small.sha256.replace('a', 'b');
        assertFalse(WhisperModels.matches(small, small.bytes, wrong));
        assertFalse(WhisperModels.matches(small, small.bytes, null));
        assertFalse(WhisperModels.matches(small, small.bytes, ""));
    }

    @Test
    public void one_model_cannot_be_passed_off_as_another() {
        final WhisperModels.Model base = WhisperModels.find("base-q5_1");
        final WhisperModels.Model small = WhisperModels.find("small-q5_1");
        assertFalse(WhisperModels.matches(base, small.bytes, small.sha256));
        assertFalse(WhisperModels.matches(null, base.bytes, base.sha256));
    }

    @Test
    public void every_model_explains_what_it_is_good_and_bad_at() {
        // The picker has to help someone choose between a 60 MB and a 488 MB
        // download; a bare name does not.
        for (WhisperModels.Model model : WhisperModels.all()) {
            assertTrue(model.id, model.name != null && !model.name.isEmpty());
            assertTrue(model.id, model.bestFor != null && model.bestFor.length() > 10);
            assertTrue(model.id, model.tradeOff != null && model.tradeOff.length() > 10);
        }
    }

    @Test
    public void sizes_are_shown_in_whole_megabytes() {
        assertEquals(60, WhisperModels.find("base-q5_1").megabytes());
        assertEquals(190, WhisperModels.find("small-q5_1").megabytes());
        assertEquals(488, WhisperModels.find("small").megabytes());
    }

    @Test
    public void model_ids_are_unique() {
        final java.util.Set<String> seen = new java.util.HashSet<>();
        for (WhisperModels.Model model : WhisperModels.all()) {
            assertTrue("duplicate id " + model.id, seen.add(model.id));
        }
        assertNull(WhisperModels.find("tiny"));
    }
}
