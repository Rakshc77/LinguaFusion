package com.linguafusion.mobile;

/**
 * Turns recorded PCM into what Whisper expects.
 *
 * The recorder writes raw 16-bit signed little-endian mono at 16 kHz, which is
 * already Whisper's sample rate, so nothing resamples. What does have to
 * happen is the conversion to normalised floats, and that is easy to get
 * subtly wrong -- byte order, sign extension, and the asymmetry of two's
 * complement all bite quietly, producing audio that is merely distorted rather
 * than obviously broken. It lives here, free of Android types, so it can be
 * tested on a normal JVM.
 */
final class OfflineAudio {
    /** What the recorder captures and the model expects. Not a coincidence. */
    static final int SAMPLE_RATE = 16000;
    static final int BYTES_PER_SAMPLE = 2;

    /**
     * A 16-bit sample spans -32768..32767. Dividing by 32768 keeps every value
     * inside -1..1 without clipping the negative extreme, which dividing by
     * 32767 would let past 1.0.
     */
    private static final float FULL_SCALE = 32768.0f;

    private OfflineAudio() {
    }

    /**
     * Converts little-endian 16-bit mono PCM to normalised floats.
     *
     * @param pcm    raw bytes as written by the recorder
     * @param length how many bytes are valid, so a partly filled buffer can be
     *               passed without copying it first
     */
    static float[] toSamples(byte[] pcm, int length) {
        if (pcm == null || length < BYTES_PER_SAMPLE) {
            return new float[0];
        }
        // A trailing odd byte is an incomplete sample; dropping it is right,
        // and reading it would pull in whatever the buffer happened to hold.
        final int usable = Math.min(length, pcm.length) / BYTES_PER_SAMPLE;
        final float[] samples = new float[usable];
        for (int i = 0; i < usable; i++) {
            final int low = pcm[i * 2] & 0xff;
            // The high byte keeps its sign: that is what makes the result
            // negative for the bottom half of the range.
            final int high = pcm[i * 2 + 1];
            samples[i] = ((high << 8) | low) / FULL_SCALE;
        }
        return samples;
    }

    /** Seconds of audio in a PCM buffer of this many bytes. */
    static double seconds(long bytes) {
        return bytes / (double) (SAMPLE_RATE * BYTES_PER_SAMPLE);
    }

    /**
     * Whisper works on 30-second windows and pads anything shorter, but audio
     * below about a third of a second carries no usable speech and makes the
     * model hallucinate a plausible sentence out of noise. Callers use this to
     * refuse instead.
     */
    static boolean isLongEnough(float[] samples) {
        return samples != null && samples.length >= SAMPLE_RATE / 3;
    }
}
