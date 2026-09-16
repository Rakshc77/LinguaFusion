package com.linguafusion.mobile;

import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** One native TTS engine shared by Online and Offline, with one active result. */
final class ReadAloudEngine implements TextToSpeech.OnInitListener {
    interface Result {
        void state(String id, String state, String message);
    }

    private static final class Request {
        final String id;
        final String text;
        final String language;
        final float rate;
        final boolean offline;
        final Result result;

        Request(String id, String text, String language, float rate, boolean offline, Result result) {
            this.id = id;
            this.text = text;
            this.language = language;
            this.rate = rate;
            this.offline = offline;
            this.result = result;
        }
    }

    private final Handler main = new Handler(Looper.getMainLooper());
    private final Context context;
    private TextToSpeech speech;
    private boolean ready;
    private boolean failed;
    private Request pending;
    private Request active;
    private String finalUtterance = "";
    private int generation;

    ReadAloudEngine(Context context) {
        this.context = context.getApplicationContext();
        speech = new TextToSpeech(this.context, this);
    }

    void speak(String id, String value, String languageValue, double rateValue,
               boolean offline, Result result) {
        main.post(() -> {
            String text = ReadAloudText.text(value);
            String language = ReadAloudText.language(languageValue, offline);
            float rate = ReadAloudText.rate(rateValue);
            if (!ReadAloudText.requestId(id)) {
                result.state(id == null ? "" : id, "error", "This result cannot be read aloud.");
                return;
            }
            if (text.isEmpty()) {
                String message = value != null && value.trim().length() > ReadAloudText.MAX_CHARACTERS
                    ? "This result is too long to read aloud at once."
                    : "There is nothing to read aloud yet.";
                result.state(id, "error", message);
                return;
            }
            if (language.isEmpty()) {
                result.state(id, "error", "Choose a supported reading language.");
                return;
            }
            if (rate == 0f) {
                result.state(id, "error", "Choose a supported reading speed.");
                return;
            }
            stopOnMain(true);
            Request request = new Request(id, text, language, rate, offline, result);
            if (failed) {
                result.state(id, "error", "Android's text-to-speech service is unavailable.");
            } else if (!ready) {
                pending = request;
                result.state(id, "speaking", "Preparing this phone's voice…");
            } else {
                start(request);
            }
        });
    }

    void stop() {
        main.post(() -> stopOnMain(true));
    }

    void shutdown() {
        if (Looper.myLooper() == Looper.getMainLooper()) shutdownOnMain();
        else main.post(this::shutdownOnMain);
    }

    @Override public void onInit(int status) {
        main.post(() -> {
            if (speech == null) return;
            ready = status == TextToSpeech.SUCCESS;
            failed = !ready;
            if (ready) {
                speech.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    @Override public void onStart(String utteranceId) {}
                    @Override public void onDone(String utteranceId) { main.post(() -> finish(utteranceId, false)); }
                    @Override public void onError(String utteranceId) { main.post(() -> finish(utteranceId, true)); }
                    @Override public void onStop(String utteranceId, boolean interrupted) {
                        main.post(() -> stoppedByEngine(utteranceId));
                    }
                });
            }
            Request request = pending;
            pending = null;
            if (request == null) return;
            if (ready) start(request);
            else request.result.state(request.id, "error", "Android's text-to-speech service is unavailable.");
        });
    }

    private void start(Request request) {
        Locale locale = Locale.forLanguageTag(request.language);
        Set<Voice> available = speech.getVoices();
        Voice voice = (available == null ? java.util.stream.Stream.<Voice>empty() : available.stream())
            .filter(candidate -> request.language.equals(candidate.getLocale().getLanguage()))
            .filter(candidate -> !request.offline || !candidate.isNetworkConnectionRequired())
            .max(Comparator.comparingInt(Voice::getQuality))
            .orElse(null);
        if (request.offline && voice == null) {
            openVoiceInstaller();
            request.result.state(request.id, "error",
                "The Android voice installer was opened. Download an offline "
                    + locale.getDisplayLanguage() + " voice, then return and try again.");
            return;
        }
        int languageResult = voice == null ? speech.setLanguage(locale) : speech.setVoice(voice);
        if (languageResult == TextToSpeech.LANG_MISSING_DATA || languageResult == TextToSpeech.LANG_NOT_SUPPORTED) {
            openVoiceInstaller();
            request.result.state(request.id, "error",
                "The Android voice installer was opened because this phone has no usable "
                    + locale.getDisplayLanguage() + " voice.");
            return;
        }
        if (speech.setSpeechRate(request.rate) == TextToSpeech.ERROR) {
            request.result.state(request.id, "error", "This phone could not set the reading speed.");
            return;
        }

        active = request;
        int token = ++generation;
        int maximum = Math.max(256, TextToSpeech.getMaxSpeechInputLength() - 32);
        List<String> chunks = ReadAloudText.chunks(request.text, maximum);
        finalUtterance = "lf-" + token + "-" + (chunks.size() - 1);
        for (int index = 0; index < chunks.size(); index++) {
            int queue = index == 0 ? TextToSpeech.QUEUE_FLUSH : TextToSpeech.QUEUE_ADD;
            int started = speech.speak(chunks.get(index), queue, null, "lf-" + token + "-" + index);
            if (started == TextToSpeech.ERROR) {
                speech.stop();
                active = null;
                finalUtterance = "";
                request.result.state(request.id, "error", "This phone could not start Read Aloud.");
                return;
            }
        }
        request.result.state(request.id, "speaking",
            request.offline ? "Speaking offline with this phone's voice…" : "Speaking with this phone's voice…");
    }

    private void finish(String utteranceId, boolean error) {
        if (active == null || !utteranceId.equals(finalUtterance)) return;
        Request finished = active;
        active = null;
        finalUtterance = "";
        finished.result.state(finished.id, error ? "error" : "done",
            error ? "This phone could not finish reading that result." : "Finished.");
    }

    private void stoppedByEngine(String utteranceId) {
        if (active == null || !utteranceId.equals(finalUtterance)) return;
        Request stopped = active;
        active = null;
        finalUtterance = "";
        stopped.result.state(stopped.id, "stopped", "Stopped.");
    }

    private void stopOnMain(boolean report) {
        Request stopped = active != null ? active : pending;
        active = null;
        pending = null;
        finalUtterance = "";
        generation++;
        if (speech != null) speech.stop();
        if (report && stopped != null) stopped.result.state(stopped.id, "stopped", "Stopped.");
    }

    private void shutdownOnMain() {
        stopOnMain(false);
        if (speech != null) speech.shutdown();
        speech = null;
        ready = false;
    }

    /** Open Android's own trusted voice-data installer after a user-initiated
     * Read Aloud attempt. Some TTS engines expose only their settings page, so
     * keep a system-settings fallback instead of leaving a dead-end message. */
    private void openVoiceInstaller() {
        Intent install = new Intent(TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            context.startActivity(install);
        } catch (RuntimeException unavailable) {
            try {
                context.startActivity(new Intent(Settings.ACTION_TTS_SETTINGS)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            } catch (RuntimeException ignored) {
                // The result message remains useful on stripped-down devices.
            }
        }
    }
}
