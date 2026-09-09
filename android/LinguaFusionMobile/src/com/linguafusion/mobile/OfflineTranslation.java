package com.linguafusion.mobile;

import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.common.model.DownloadConditions;
import com.google.mlkit.common.model.RemoteModelManager;
import com.google.mlkit.nl.translate.TranslateRemoteModel;
import com.google.mlkit.nl.translate.Translation;
import com.google.mlkit.nl.translate.Translator;
import com.google.mlkit.nl.translate.TranslatorOptions;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;

/**
 * On-device translation through ML Kit.
 *
 * ML Kit's own API is asynchronous, but every caller here is already on a
 * background thread and the web layer expects a value back, so the tasks are
 * awaited rather than threaded through callbacks.
 *
 * Two things about ML Kit are worth knowing and are surfaced rather than
 * hidden. Its language packs are downloaded, so a pair can be unavailable
 * until someone fetches it. And every non-English pair is routed through
 * English internally, which costs accuracy -- {@link OfflineLanguages
 * #pivotsThroughEnglish} identifies those so the app can say so.
 *
 * Every method blocks. None may be called on the UI thread.
 */
final class OfflineTranslation {
    /** Long enough for a slow phone, short enough not to look hung. */
    private static final long TRANSLATE_TIMEOUT_SECONDS = 60;
    private static final long MODEL_TIMEOUT_MINUTES = 15;

    private final Map<String, Translator> translators = new HashMap<>();
    private final RemoteModelManager models = RemoteModelManager.getInstance();

    /**
     * Translates text, assuming both packs are present.
     *
     * @return the translation, or a message beginning with "ERROR: "
     */
    String translate(String text, String from, String to) {
        if (text == null || text.trim().isEmpty()) {
            return "";
        }
        if (!OfflineLanguages.canTranslate(from, to)) {
            if (OfflineLanguages.normalise(from).equals(OfflineLanguages.normalise(to))) {
                return text;
            }
            return "ERROR: That pair of languages is not available offline.";
        }
        try {
            final Translator translator = translatorFor(from, to);
            return Tasks.await(translator.translate(text),
                    TRANSLATE_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } catch (Exception failure) {
            // Almost always a missing language pack, which is worth naming
            // because the person can fix it.
            return "ERROR: Offline translation failed. "
                    + "Check both languages are downloaded. (" + reason(failure) + ")";
        }
    }

    /** Which of the offered languages are downloaded and ready. */
    Set<String> installedLanguages() {
        final Set<String> installed = new HashSet<>();
        try {
            final Set<TranslateRemoteModel> downloaded =
                    Tasks.await(models.getDownloadedModels(TranslateRemoteModel.class),
                            30, TimeUnit.SECONDS);
            for (TranslateRemoteModel model : downloaded) {
                final String code = OfflineLanguages.normalise(model.getLanguage());
                if (OfflineLanguages.isSupported(code)) {
                    installed.add(code);
                }
            }
        } catch (Exception failure) {
            // An empty set reads as "nothing ready", which is the safe answer:
            // the screen offers a download rather than promising it works.
            return installed;
        }
        return installed;
    }

    /**
     * Downloads one language pack.
     *
     * @return null on success, otherwise a message
     */
    String downloadLanguage(String code, boolean wifiOnly) {
        final String mlKit = OfflineLanguages.mlKitCode(code);
        if (mlKit == null) {
            return "That language is not available offline.";
        }
        try {
            final DownloadConditions.Builder conditions = new DownloadConditions.Builder();
            if (wifiOnly) {
                conditions.requireWifi();
            }
            Tasks.await(models.download(new TranslateRemoteModel.Builder(mlKit).build(),
                    conditions.build()), MODEL_TIMEOUT_MINUTES, TimeUnit.MINUTES);
            return null;
        } catch (Exception failure) {
            return "That language pack could not be downloaded (" + reason(failure) + ").";
        }
    }

    /** Removes a language pack, freeing its space. */
    String removeLanguage(String code) {
        final String mlKit = OfflineLanguages.mlKitCode(code);
        if (mlKit == null) {
            return "That language is not available offline.";
        }
        if ("en".equals(mlKit)) {
            // Every non-English pair pivots through English, so removing it
            // would quietly break pairs that look unrelated to it.
            return "English cannot be removed: every other pair is translated through it.";
        }
        try {
            Tasks.await(models.deleteDownloadedModel(
                    new TranslateRemoteModel.Builder(mlKit).build()), 2, TimeUnit.MINUTES);
            closeTranslatorsUsing(OfflineLanguages.normalise(code));
            return null;
        } catch (Exception failure) {
            return "That language pack could not be removed (" + reason(failure) + ").";
        }
    }

    /**
     * Translators are expensive to build and cheap to keep, and one is needed
     * per direction, so they are cached until the app stops or their language
     * is removed.
     */
    private synchronized Translator translatorFor(String from, String to) {
        final String source = OfflineLanguages.mlKitCode(from);
        final String target = OfflineLanguages.mlKitCode(to);
        final String key = source + '>' + target;
        Translator translator = translators.get(key);
        if (translator == null) {
            translator = Translation.getClient(new TranslatorOptions.Builder()
                    .setSourceLanguage(source)
                    .setTargetLanguage(target)
                    .build());
            translators.put(key, translator);
        }
        return translator;
    }

    private synchronized void closeTranslatorsUsing(String code) {
        final Set<String> stale = new HashSet<>();
        for (String key : translators.keySet()) {
            if (key.startsWith(code + '>') || key.endsWith('>' + code)) {
                stale.add(key);
            }
        }
        for (String key : stale) {
            final Translator translator = translators.remove(key);
            if (translator != null) {
                translator.close();
            }
        }
    }

    synchronized void close() {
        for (Translator translator : translators.values()) {
            translator.close();
        }
        translators.clear();
    }

    /** ML Kit wraps its causes; the innermost message is the useful one. */
    private static String reason(Throwable failure) {
        Throwable cause = failure;
        while (cause.getCause() != null && cause.getCause() != cause) {
            cause = cause.getCause();
        }
        final String message = cause.getMessage();
        return message == null || message.isEmpty()
                ? cause.getClass().getSimpleName() : message;
    }
}
