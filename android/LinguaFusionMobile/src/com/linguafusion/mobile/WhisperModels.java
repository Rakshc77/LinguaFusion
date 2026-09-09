package com.linguafusion.mobile;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * The speech models the app can download, and what each costs.
 *
 * All are multilingual: one model covers every offered language, so adding a
 * supported language later needs no new download. Only quantised builds are
 * offered by default -- q5_1 is a little under half the size for accuracy that
 * is very close, which on a phone is the trade worth making.
 *
 * Sizes and checksums are the real published ones, not estimates. A model that
 * arrives corrupted or truncated must be rejected rather than loaded, because
 * whisper.cpp will happily accept a damaged file and then transcribe noise.
 *
 * Free of Android types so it can be tested on a normal JVM.
 */
final class WhisperModels {
    static final class Model {
        final String id;
        final String fileName;
        final String url;
        final long bytes;
        final String sha256;
        final String name;
        final String bestFor;
        final String tradeOff;

        Model(String id, String fileName, String url, long bytes, String sha256,
              String name, String bestFor, String tradeOff) {
            this.id = id;
            this.fileName = fileName;
            this.url = url;
            this.bytes = bytes;
            this.sha256 = sha256;
            this.name = name;
            this.bestFor = bestFor;
            this.tradeOff = tradeOff;
        }

        /** Rounded for display; people think in whole megabytes. */
        int megabytes() {
            return (int) Math.round(bytes / 1_000_000.0);
        }
    }

    private static final String SOURCE =
            "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/";

    /** The default. Small-quality speech for a bit under 200 MB. */
    static final String RECOMMENDED = "small-q5_1";

    private static final List<Model> MODELS;

    static {
        final List<Model> models = new ArrayList<>();
        models.add(new Model("base-q5_1", "ggml-base-q5_1.bin", SOURCE + "ggml-base-q5_1.bin",
                59707625L, "422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898",
                "Base", "The smallest download, and the fastest on an older phone.",
                "Noticeably weaker on accents, background noise and Arabic."));
        models.add(new Model("small-q5_1", "ggml-small-q5_1.bin", SOURCE + "ggml-small-q5_1.bin",
                190085487L, "ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb",
                "Small", "The best balance, and what most people should use.",
                "Around three times slower than Base."));
        models.add(new Model("small", "ggml-small.bin", SOURCE + "ggml-small.bin",
                487601967L, "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
                "Small, full precision", "Squeezing out the last of Small's accuracy.",
                "Two and a half times the download for a small gain."));
        MODELS = Collections.unmodifiableList(models);
    }

    private WhisperModels() {
    }

    static List<Model> all() {
        return MODELS;
    }

    static Model find(String id) {
        for (Model model : MODELS) {
            if (model.id.equals(id)) {
                return model;
            }
        }
        return null;
    }

    /** The chosen model, falling back to the recommended one if unset. */
    static Model chosen(String id) {
        final Model model = find(id);
        return model != null ? model : find(RECOMMENDED);
    }

    /**
     * Whether a downloaded file is the model it claims to be. Size is checked
     * first because it is free and catches the common case -- a download cut
     * short by a dropped connection.
     */
    static boolean matches(Model model, long actualBytes, String actualSha256) {
        return model != null
                && actualBytes == model.bytes
                && model.sha256.equalsIgnoreCase(actualSha256 == null ? "" : actualSha256.trim());
    }
}
