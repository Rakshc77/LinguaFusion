package com.linguafusion.mobile;

import android.webkit.JavascriptInterface;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.Set;
import java.util.concurrent.ExecutorService;

/**
 * What the bundled offline page is allowed to ask the phone to do.
 *
 * This interface exists only for the page shipped inside the APK. The cloud
 * WebView deliberately has no JavaScript interface at all -- a remotely served
 * page has no business driving the microphone or deleting files -- and that
 * boundary is why the offline interface has to be local rather than the cloud
 * page gaining offline powers.
 *
 * Every method runs on a WebView thread, not the UI thread, and the slow ones
 * are handed to the caller's executor and answered through a callback into the
 * page. Nothing here blocks the interface.
 */
final class OfflineBridge {
    /** What the bridge needs from the Activity, kept small on purpose. */
    interface Host {
        /** Stops recording and hands back raw 16 kHz mono PCM, or null. */
        byte[] takeRecordedPcm();

        /** Starts recording; returns null on success or a message. */
        String startRecording();

        void cancelRecording();

        /** Delivers a result to the page by calling window.LF.resolve(id, ...). */
        void resolve(String requestId, String json);

        /** Remembers a choice across launches. */
        void remember(String key, String value);

        String recall(String key, String fallback);

        /** Leaves offline mode and returns to the connection screen. */
        void leaveOfflineMode();

        /** Opens the picture chooser; the answer arrives on this request id. */
        void pickImageForText(String requestId);

        /** Looks for a newer build now, rather than waiting for a relaunch. */
        void checkForUpdate(String requestId);
    }

    private final Host host;
    private final ExecutorService executor;
    private final OfflineSpeech speech;
    private final OfflineTranslation translation;

    OfflineBridge(Host host, ExecutorService executor,
                  OfflineSpeech speech, OfflineTranslation translation) {
        this.host = host;
        this.executor = executor;
        this.speech = speech;
        this.translation = translation;
    }

    /* ---------- things the page can ask for immediately ---------- */

    /** Everything the page needs to draw itself: languages, models, state. */
    @JavascriptInterface
    public String describe() {
        try {
            final JSONObject description = new JSONObject();
            description.put("transcriptionSupported", OfflineSpeech.isSupported());

            final JSONArray languages = new JSONArray();
            for (OfflineLanguages.Entry entry : OfflineLanguages.all()) {
                languages.put(new JSONObject()
                        .put("code", entry.code)
                        .put("name", entry.englishName)
                        .put("nativeName", entry.nativeName));
            }
            description.put("languages", languages);

            final JSONArray models = new JSONArray();
            for (WhisperModels.Model model : WhisperModels.all()) {
                models.put(new JSONObject()
                        .put("id", model.id)
                        .put("name", model.name)
                        .put("megabytes", model.megabytes())
                        .put("bestFor", model.bestFor)
                        .put("tradeOff", model.tradeOff)
                        .put("installed", speech.isInstalled(model))
                        .put("partialBytes", speech.downloadedBytes(model))
                        .put("totalBytes", model.bytes));
            }
            description.put("models", models);
            description.put("chosenModel", chosenModelId());
            description.put("recommendedModel", WhisperModels.RECOMMENDED);
            description.put("modelLoaded", speech.isLoaded());
            description.put("readingSupported", true);
            description.put("romanizeSupported", OfflineRomanize.isSupported());
            final JSONArray romanizable = new JSONArray();
            for (String[] entry : OfflineRomanize.LANGUAGES) {
                romanizable.put(new JSONObject()
                        .put("code", entry[0]).put("name", entry[1]).put("nativeName", entry[2]));
            }
            description.put("romanizeLanguages", romanizable);
            // Named so the page can say which pictures it cannot read, rather
            // than letting someone photograph Arabic and get silence.
            description.put("readableLanguages", readable());
            description.put("sourceLanguage", host.recall("offline.from", "auto"));
            description.put("targetLanguage", host.recall("offline.to", "en"));
            return description.toString();
        } catch (JSONException impossible) {
            return "{}";
        }
    }

    /** Which translation packs are ready. Slow enough to be asynchronous. */
    @JavascriptInterface
    public void listTranslationLanguages(String requestId) {
        executor.execute(() -> {
            try {
                final Set<String> installed = translation.installedLanguages();
                final JSONArray ready = new JSONArray();
                for (String code : installed) {
                    ready.put(code);
                }
                host.resolve(requestId, new JSONObject().put("installed", ready).toString());
            } catch (JSONException impossible) {
                host.resolve(requestId, "{}");
            }
        });
    }

    /* ---------- the offline pipeline ---------- */

    @JavascriptInterface
    public String startRecording() {
        final String failure = host.startRecording();
        return failure == null ? "" : failure;
    }

    @JavascriptInterface
    public void cancelRecording() {
        host.cancelRecording();
    }

    /**
     * Stops recording and runs the whole offline pipeline: transcribe, then
     * translate if a target language is set. Done in one call so the audio
     * never crosses into JavaScript.
     */
    @JavascriptInterface
    public void stopAndProcess(String requestId, String from, String to, boolean alsoTranslate) {
        final byte[] pcm = host.takeRecordedPcm();
        executor.execute(() -> {
            final JSONObject result = new JSONObject();
            try {
                if (pcm == null || pcm.length < 2) {
                    host.resolve(requestId, result.put("error", "Nothing was recorded.").toString());
                    return;
                }
                result.put("seconds", Math.round(OfflineAudio.seconds(pcm.length) * 10) / 10.0);

                final String loadFailure = ensureModelLoaded();
                if (loadFailure != null) {
                    host.resolve(requestId, result.put("error", loadFailure).toString());
                    return;
                }

                String spoken = OfflineLanguages.normalise(from);
                if (!OfflineLanguages.isSupported(spoken)) {
                    final String detected = speech.detectLanguage(pcm, pcm.length);
                    spoken = detected == null ? "" : detected;
                    result.put("detected", spoken);
                }

                final String transcript = speech.transcribe(pcm, pcm.length,
                        spoken.isEmpty() ? OfflineLanguages.AUTO_DETECT : spoken);
                if (transcript.startsWith("ERROR: ")) {
                    host.resolve(requestId,
                            result.put("error", transcript.substring(7)).toString());
                    return;
                }
                result.put("transcript", transcript);
                result.put("spokenLanguage", spoken);

                if (alsoTranslate && OfflineLanguages.canTranslate(spoken, to)) {
                    final String translated = translation.translate(transcript, spoken, to);
                    if (translated.startsWith("ERROR: ")) {
                        result.put("translationError", translated.substring(7));
                    } else {
                        result.put("translation", translated);
                        result.put("pivoted", OfflineLanguages.pivotsThroughEnglish(spoken, to));
                    }
                } else if (alsoTranslate) {
                    result.put("translationError",
                            "That pair of languages cannot be translated offline.");
                }
                host.resolve(requestId, result.toString());
            } catch (JSONException impossible) {
                host.resolve(requestId, "{}");
            }
        });
    }

    /** Translate typed text, with no recording involved. */
    @JavascriptInterface
    public void translateText(String requestId, String text, String from, String to) {
        executor.execute(() -> {
            try {
                final JSONObject result = new JSONObject();
                final String translated = translation.translate(text, from, to);
                if (translated.startsWith("ERROR: ")) {
                    result.put("error", translated.substring(7));
                } else {
                    result.put("translation", translated);
                    result.put("pivoted", OfflineLanguages.pivotsThroughEnglish(from, to));
                }
                host.resolve(requestId, result.toString());
            } catch (JSONException impossible) {
                host.resolve(requestId, "{}");
            }
        });
    }

    /* ---------- managing what is stored on the phone ---------- */

    @JavascriptInterface
    public void downloadModel(String requestId, String modelId) {
        final WhisperModels.Model model = WhisperModels.find(modelId);
        executor.execute(() -> {
            final String failure = speech.download(model, (done, total) ->
                    host.resolve(requestId + ":progress", progress(done, total)));
            host.resolve(requestId, answer(failure));
        });
    }

    @JavascriptInterface
    public void removeModel(String requestId, String modelId) {
        executor.execute(() -> {
            final boolean removed = speech.remove(WhisperModels.find(modelId));
            host.resolve(requestId, answer(removed ? null : "That model could not be removed."));
        });
    }

    @JavascriptInterface
    public void chooseModel(String modelId) {
        final WhisperModels.Model model = WhisperModels.find(modelId);
        if (model != null) {
            host.remember("offline.model", model.id);
            // Drop the old one; the next transcription loads the new choice.
            speech.unload();
        }
    }

    @JavascriptInterface
    public void downloadTranslationLanguage(String requestId, String code, boolean wifiOnly) {
        executor.execute(() ->
                host.resolve(requestId, answer(translation.downloadLanguage(code, wifiOnly))));
    }

    @JavascriptInterface
    public void removeTranslationLanguage(String requestId, String code) {
        executor.execute(() ->
                host.resolve(requestId, answer(translation.removeLanguage(code))));
    }

    @JavascriptInterface
    public void rememberLanguages(String from, String to) {
        host.remember("offline.from", OfflineLanguages.normalise(from));
        host.remember("offline.to", OfflineLanguages.normalise(to));
    }

    /** Reads a picture the person chooses. The image never enters
     *  JavaScript: the picker is native and the bytes go straight to ML Kit. */
    @JavascriptInterface
    public void readPicture(String requestId) {
        host.pickImageForText(requestId);
    }

    @JavascriptInterface
    public void romanize(String requestId, String text, String language) {
        executor.execute(() -> {
            try {
                final JSONObject result = new JSONObject();
                final String romanised = OfflineRomanize.romanize(text, language);
                if (romanised.startsWith("ERROR: ")) {
                    result.put("error", romanised.substring(7));
                } else {
                    result.put("romanized", romanised);
                }
                host.resolve(requestId, result.toString());
            } catch (JSONException impossible) {
                host.resolve(requestId, "{}");
            }
        });
    }

    /** The app offers an update on each launch. This is for the person who
     *  said "Not now" and changed their mind, who would otherwise have to
     *  close and reopen the app to be asked again. */
    @JavascriptInterface
    public void checkForUpdate(String requestId) {
        host.checkForUpdate(requestId);
    }

    @JavascriptInterface
    public void leaveOfflineMode() {
        host.leaveOfflineMode();
    }

    /* ---------- helpers ---------- */

    private static JSONArray readable() {
        final JSONArray codes = new JSONArray();
        for (OfflineLanguages.Entry entry : OfflineLanguages.all()) {
            if (OfflineVision.canRead(entry.code)) {
                codes.put(entry.code);
            }
        }
        return codes;
    }

    private String chosenModelId() {
        return WhisperModels.chosen(host.recall("offline.model", WhisperModels.RECOMMENDED)).id;
    }

    /** Loads the chosen model if it is not already in memory. */
    private String ensureModelLoaded() {
        if (speech.isLoaded()) {
            return null;
        }
        final WhisperModels.Model model = WhisperModels.chosen(host.recall("offline.model", null));
        if (!speech.isInstalled(model)) {
            return "Download the " + model.name + " speech model first ("
                    + model.megabytes() + " MB), under Storage.";
        }
        return speech.load(model);
    }

    private static String answer(String failure) {
        try {
            final JSONObject result = new JSONObject();
            if (failure != null) {
                result.put("error", failure);
            } else {
                result.put("ok", true);
            }
            return result.toString();
        } catch (JSONException impossible) {
            return "{}";
        }
    }

    private static String progress(long done, long total) {
        try {
            return new JSONObject().put("done", done).put("total", total).toString();
        } catch (JSONException impossible) {
            return "{}";
        }
    }
}
