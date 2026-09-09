package com.linguafusion.mobile;

/**
 * The whisper.cpp binding. Thin on purpose: it exposes the model as a handle
 * and does no thinking of its own, so everything above it can be reasoned
 * about in plain Java. {@link OfflineSpeech} owns the handle's lifetime.
 *
 * Every method here blocks, some for minutes. None may be called on the UI
 * thread.
 */
final class WhisperNative {
    /** Whether the native library is present and loadable on this device. */
    static final boolean AVAILABLE = load();

    private static boolean load() {
        try {
            System.loadLibrary("lingua_whisper");
            return true;
        } catch (UnsatisfiedLinkError missing) {
            // A device whose ABI we did not build for. The app must keep
            // working -- offline transcription simply is not offered.
            return false;
        }
    }

    private WhisperNative() {
    }

    /** Loads a GGML model file. Returns 0 if it could not be read. */
    static native long openModel(String path);

    static native void closeModel(long handle);

    /**
     * Transcribes 16 kHz mono audio.
     *
     * @param language ISO code, or "auto" to let the model decide
     * @return the joined text, or null if the run failed
     */
    static native String transcribe(long handle, float[] audio, String language, int threads);

    /** The language the model heard, as an ISO code, or null if unclear. */
    static native String detectLanguage(long handle, float[] audio, int threads);

    /** The sample rate the model expects, so callers cannot guess wrong. */
    static native int expectedSampleRate();

    /** Which CPU features the build is using; for the diagnostics screen. */
    static native String systemInfo();
}
