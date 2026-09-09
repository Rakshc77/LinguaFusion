package com.linguafusion.mobile;

import android.content.Context;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.RandomAccessFile;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;

/**
 * On-device transcription: owning the model file, and running Whisper on it.
 *
 * The model is a large download that has to survive being interrupted, so it
 * is fetched to a partial file that is resumed rather than restarted, and is
 * only checked and promoted once complete. A model that fails its checksum is
 * deleted: whisper.cpp will load a truncated file without complaint and then
 * transcribe noise, which is far worse than having no model at all.
 *
 * Every method here blocks. None may be called on the UI thread.
 */
final class OfflineSpeech {
    /** Interested parties: the download screen, mostly. */
    interface Progress {
        void onProgress(long done, long total);
    }

    private static final String DIRECTORY = "whisper-models";
    private static final int BUFFER = 1 << 16;

    private final Context context;
    private long handle;
    private String loadedModelId;

    OfflineSpeech(Context context) {
        this.context = context.getApplicationContext();
    }

    /** Whether this device can run offline transcription at all. */
    static boolean isSupported() {
        return WhisperNative.AVAILABLE;
    }

    private File directory() {
        // Internal storage: these are large, private, and should go when the
        // app does. getFilesDir survives an app update; the cache dir does not
        // and Android may delete it under storage pressure mid-download.
        final File directory = new File(context.getFilesDir(), DIRECTORY);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            return context.getFilesDir();
        }
        return directory;
    }

    File fileFor(WhisperModels.Model model) {
        return new File(directory(), model.fileName);
    }

    /** Whether this model is downloaded and intact. */
    boolean isInstalled(WhisperModels.Model model) {
        final File file = fileFor(model);
        // Size alone: hashing 200 MB on every check would be far too slow.
        // The full checksum is verified once, when the download completes.
        return model != null && file.isFile() && file.length() == model.bytes;
    }

    /** Bytes currently on disk for a model, complete or not. */
    long downloadedBytes(WhisperModels.Model model) {
        final File complete = fileFor(model);
        if (complete.isFile()) {
            return complete.length();
        }
        final File partial = new File(complete.getPath() + ".part");
        return partial.isFile() ? partial.length() : 0L;
    }

    /**
     * Downloads a model, resuming if a partial file is already there.
     *
     * @return null on success, otherwise a message describing what went wrong
     */
    String download(WhisperModels.Model model, Progress progress) {
        if (model == null) {
            return "No such speech model.";
        }
        if (isInstalled(model)) {
            return null;
        }
        final File target = fileFor(model);
        final File partial = new File(target.getPath() + ".part");
        HttpURLConnection connection = null;
        try {
            long already = partial.isFile() ? partial.length() : 0L;
            if (already > model.bytes) {
                // A previous run wrote more than the model can be; it is not
                // this model. Start again rather than resume into nonsense.
                if (!partial.delete()) {
                    return "Could not clear an unusable partial download.";
                }
                already = 0L;
            }

            connection = (HttpURLConnection) new URL(model.url).openConnection();
            connection.setConnectTimeout(30_000);
            connection.setReadTimeout(60_000);
            if (already > 0) {
                connection.setRequestProperty("Range", "bytes=" + already + "-");
            }
            final int status = connection.getResponseCode();
            if (status == HttpURLConnection.HTTP_OK && already > 0) {
                // The server ignored the range and is sending the whole file,
                // so the existing bytes must not be kept or they would be
                // prepended to a second copy.
                already = 0L;
            } else if (status != HttpURLConnection.HTTP_OK
                    && status != HttpURLConnection.HTTP_PARTIAL) {
                return "The model could not be downloaded (HTTP " + status + ").";
            }

            try (InputStream input = connection.getInputStream();
                 RandomAccessFile output = new RandomAccessFile(partial, "rw")) {
                output.setLength(already);
                output.seek(already);
                final byte[] buffer = new byte[BUFFER];
                long done = already;
                int read;
                while ((read = input.read(buffer)) > 0) {
                    output.write(buffer, 0, read);
                    done += read;
                    if (progress != null) {
                        progress.onProgress(done, model.bytes);
                    }
                }
            }

            if (partial.length() != model.bytes) {
                return "The download stopped early; try again to resume it.";
            }
            final String digest = sha256(partial);
            if (!WhisperModels.matches(model, partial.length(), digest)) {
                // Deleted, not kept: a damaged model transcribes noise
                // confidently, which is worse than having none.
                partial.delete();
                return "The downloaded model was damaged and has been discarded.";
            }
            if (target.isFile() && !target.delete()) {
                return "Could not replace the existing model file.";
            }
            if (!partial.renameTo(target)) {
                return "Could not put the model in place.";
            }
            return null;
        } catch (IOException failure) {
            // The partial file is deliberately kept so the next attempt resumes.
            return "The download was interrupted: " + failure.getMessage();
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    /** Removes a model and any partial download of it. */
    boolean remove(WhisperModels.Model model) {
        if (model == null) {
            return false;
        }
        if (model.id.equals(loadedModelId)) {
            unload();
        }
        final File target = fileFor(model);
        final File partial = new File(target.getPath() + ".part");
        final boolean removed = !target.isFile() || target.delete();
        if (partial.isFile()) {
            partial.delete();
        }
        return removed;
    }

    /** Loads a model into memory, replacing whatever was loaded before. */
    synchronized String load(WhisperModels.Model model) {
        if (!isSupported()) {
            return "This phone cannot run offline transcription.";
        }
        if (model == null) {
            return "No such speech model.";
        }
        if (model.id.equals(loadedModelId) && handle != 0) {
            return null;
        }
        if (!isInstalled(model)) {
            return "That speech model has not been downloaded yet.";
        }
        unload();
        final long opened = WhisperNative.openModel(fileFor(model).getAbsolutePath());
        if (opened == 0) {
            return "The speech model could not be loaded.";
        }
        handle = opened;
        loadedModelId = model.id;
        return null;
    }

    synchronized void unload() {
        if (handle != 0) {
            WhisperNative.closeModel(handle);
            handle = 0;
            loadedModelId = null;
        }
    }

    synchronized boolean isLoaded() {
        return handle != 0;
    }

    /**
     * Transcribes recorded PCM.
     *
     * @param language an offered language code, or "auto"
     * @return the text, or a message beginning with "ERROR: " -- the same
     *         convention the existing recording bridge already uses
     */
    synchronized String transcribe(byte[] pcm, int length, String language) {
        if (handle == 0) {
            return "ERROR: No speech model is loaded.";
        }
        final float[] samples = OfflineAudio.toSamples(pcm, length);
        if (!OfflineAudio.isLongEnough(samples)) {
            return "ERROR: That recording is too short to transcribe.";
        }
        final String text = WhisperNative.transcribe(
                handle, samples, OfflineLanguages.whisperCode(language), threads());
        if (text == null) {
            return "ERROR: The recording could not be transcribed.";
        }
        return text.trim();
    }

    /** The language heard, as an offered code, or null if it is not one. */
    synchronized String detectLanguage(byte[] pcm, int length) {
        if (handle == 0) {
            return null;
        }
        final float[] samples = OfflineAudio.toSamples(pcm, length);
        if (!OfflineAudio.isLongEnough(samples)) {
            return null;
        }
        final String detected = WhisperNative.detectLanguage(handle, samples, threads());
        return OfflineLanguages.isSupported(detected) ? OfflineLanguages.normalise(detected) : null;
    }

    /**
     * Whisper is compute-bound and scales with cores, but using every core
     * makes the phone hot and the UI stutter, and on big.LITTLE designs the
     * small cores drag the whole batch. Half the cores, at least two.
     */
    private static int threads() {
        return Math.max(2, Runtime.getRuntime().availableProcessors() / 2);
    }

    private static String sha256(File file) throws IOException {
        try {
            final MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = new FileInputStream(file)) {
                final byte[] buffer = new byte[BUFFER];
                int read;
                while ((read = input.read(buffer)) > 0) {
                    digest.update(buffer, 0, read);
                }
            }
            final StringBuilder hex = new StringBuilder(64);
            for (byte value : digest.digest()) {
                hex.append(String.format(Locale.ROOT, "%02x", value));
            }
            return hex.toString();
        } catch (java.security.NoSuchAlgorithmException impossible) {
            throw new IOException("SHA-256 is unavailable on this device", impossible);
        }
    }
}
