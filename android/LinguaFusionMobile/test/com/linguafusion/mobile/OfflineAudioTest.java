package com.linguafusion.mobile;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * The PCM conversion runs on every recording and fails quietly when wrong:
 * swapped byte order or a lost sign produces audio that still plays and still
 * transcribes, just into nonsense. These pin the arithmetic.
 */
public class OfflineAudioTest {

    /** Little-endian: the FIRST byte is the low half of the sample. */
    private static byte[] sample(int value) {
        return new byte[]{(byte) (value & 0xff), (byte) (value >> 8)};
    }

    @Test
    public void silence_is_zero() {
        float[] samples = OfflineAudio.toSamples(sample(0), 2);
        assertEquals(1, samples.length);
        assertEquals(0.0f, samples[0], 0.0f);
    }

    @Test
    public void the_most_negative_sample_reaches_exactly_minus_one() {
        // -32768 / 32768 == -1.0 exactly. Dividing by 32767 instead would put
        // this below -1 and clip inside the model.
        float[] samples = OfflineAudio.toSamples(sample(-32768), 2);
        assertEquals(-1.0f, samples[0], 0.0f);
    }

    @Test
    public void the_most_positive_sample_stays_below_one() {
        float[] samples = OfflineAudio.toSamples(sample(32767), 2);
        assertTrue("must not exceed full scale", samples[0] < 1.0f);
        assertEquals(0.99997f, samples[0], 0.0001f);
    }

    @Test
    public void byte_order_is_little_endian() {
        // 0x0100 == 256. Read big-endian this would be 1, a 256x error that
        // sounds like near-silence rather than like a bug.
        float[] samples = OfflineAudio.toSamples(new byte[]{0x00, 0x01}, 2);
        assertEquals(256 / 32768.0f, samples[0], 1e-7f);
    }

    @Test
    public void negative_samples_keep_their_sign() {
        // 0xFFFF is -1, not 65535. Losing sign extension turns the quiet
        // negative half of every waveform into full-scale positive noise.
        float[] samples = OfflineAudio.toSamples(new byte[]{(byte) 0xff, (byte) 0xff}, 2);
        assertTrue("expected a negative sample, got " + samples[0], samples[0] < 0);
        assertEquals(-1 / 32768.0f, samples[0], 1e-7f);
    }

    @Test
    public void a_trailing_odd_byte_is_dropped_rather_than_half_read() {
        float[] samples = OfflineAudio.toSamples(new byte[]{0x00, 0x01, 0x7f}, 3);
        assertEquals(1, samples.length);
    }

    @Test
    public void only_the_stated_length_is_read() {
        // The recorder passes a buffer that is longer than the audio in it.
        byte[] buffer = new byte[64];
        buffer[0] = 0x00;
        buffer[1] = 0x01;
        assertEquals(1, OfflineAudio.toSamples(buffer, 2).length);
        assertEquals(32, OfflineAudio.toSamples(buffer, buffer.length).length);
    }

    @Test
    public void a_length_beyond_the_buffer_cannot_read_past_it() {
        float[] samples = OfflineAudio.toSamples(new byte[]{0x00, 0x01}, 9999);
        assertEquals(1, samples.length);
    }

    @Test
    public void empty_and_null_input_produce_no_samples() {
        assertEquals(0, OfflineAudio.toSamples(null, 10).length);
        assertEquals(0, OfflineAudio.toSamples(new byte[0], 0).length);
        assertEquals(0, OfflineAudio.toSamples(new byte[]{0x01}, 1).length);
    }

    @Test
    public void duration_matches_the_recorder_rate() {
        // One second is 16000 samples of two bytes each.
        assertEquals(1.0, OfflineAudio.seconds(32000), 1e-9);
        assertEquals(0.5, OfflineAudio.seconds(16000), 1e-9);
    }

    @Test
    public void audio_too_short_to_carry_speech_is_rejected() {
        assertFalse(OfflineAudio.isLongEnough(new float[100]));
        assertFalse(OfflineAudio.isLongEnough(null));
        assertTrue(OfflineAudio.isLongEnough(new float[OfflineAudio.SAMPLE_RATE]));
    }
}
