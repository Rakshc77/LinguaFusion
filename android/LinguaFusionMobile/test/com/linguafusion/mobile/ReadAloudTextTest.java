package com.linguafusion.mobile;

import org.junit.Test;

import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class ReadAloudTextTest {
    @Test public void languagesAreNormalisedAndOfflineScopeStaysAtFive() {
        assertEquals("ar", ReadAloudText.language("AR-SA", true));
        assertEquals("fr", ReadAloudText.language("fr_FR", true));
        assertEquals("", ReadAloudText.language("hi", true));
        assertEquals("hi", ReadAloudText.language("hi", false));
        assertEquals("", ReadAloudText.language("xx", false));
    }

    @Test public void idsRatesAndTextHaveStrictLimits() {
        assertTrue(ReadAloudText.requestId("translation_1"));
        assertFalse(ReadAloudText.requestId("bad id"));
        assertEquals(0.75f, ReadAloudText.rate(0.75d), 0f);
        assertEquals(0f, ReadAloudText.rate(2d), 0f);
        assertEquals("Hello", ReadAloudText.text(" Hello "));
        assertEquals("", ReadAloudText.text("a".repeat(ReadAloudText.MAX_CHARACTERS + 1)));
    }

    @Test public void longSpeechSplitsWithoutLosingWords() {
        List<String> chunks = ReadAloudText.chunks("one two three four five", 10);
        assertEquals(List.of("one two", "three four", "five"), chunks);
        for (String chunk : chunks) assertTrue(chunk.length() <= 10);
        assertEquals("one two three four five", String.join(" ", chunks));
    }
}
