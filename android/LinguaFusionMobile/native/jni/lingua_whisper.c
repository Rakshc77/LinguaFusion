// JNI binding between the app and whisper.cpp.
//
// whisper.cpp ships an Android example, but its bindings target Kotlin and
// carry mangled `WhisperLib$Companion` symbol names, and its transcribe call
// hardcodes `params.language = "en"`. This app is Java and needs five
// languages plus detection, so the binding is written here instead. The
// whisper.cpp API calls follow that example; the shape around them does not.
//
// Everything here is called from a background thread -- transcription takes
// seconds to minutes and must never touch the UI thread.

#include <jni.h>
#include <android/log.h>
#include <stdlib.h>
#include <string.h>

#include "whisper.h"

#define TAG "LinguaWhisper"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

// Whisper is trained on 16 kHz mono audio. The app's recorder already captures
// at exactly that rate, so nothing resamples; this is asserted rather than
// assumed because a mismatch degrades output quietly instead of failing.
#define EXPECTED_SAMPLE_RATE 16000

JNIEXPORT jlong JNICALL
Java_com_linguafusion_mobile_WhisperNative_openModel(JNIEnv *env, jclass clazz, jstring path) {
    (void) clazz;
    const char *model_path = (*env)->GetStringUTFChars(env, path, NULL);
    if (model_path == NULL) {
        return 0;
    }
    struct whisper_context_params params = whisper_context_default_params();
    // No GPU backend is compiled in; say so rather than letting it probe.
    params.use_gpu = false;
    struct whisper_context *context = whisper_init_from_file_with_params(model_path, params);
    if (context == NULL) {
        LOGE("could not load the model at %s", model_path);
    }
    (*env)->ReleaseStringUTFChars(env, path, model_path);
    return (jlong) context;
}

JNIEXPORT void JNICALL
Java_com_linguafusion_mobile_WhisperNative_closeModel(JNIEnv *env, jclass clazz, jlong handle) {
    (void) env;
    (void) clazz;
    if (handle != 0) {
        whisper_free((struct whisper_context *) handle);
    }
}

JNIEXPORT jint JNICALL
Java_com_linguafusion_mobile_WhisperNative_expectedSampleRate(JNIEnv *env, jclass clazz) {
    (void) env;
    (void) clazz;
    return EXPECTED_SAMPLE_RATE;
}

JNIEXPORT jstring JNICALL
Java_com_linguafusion_mobile_WhisperNative_systemInfo(JNIEnv *env, jclass clazz) {
    (void) clazz;
    return (*env)->NewStringUTF(env, whisper_print_system_info());
}

/* Transcribe. `language` is an ISO code ("en", "de", "ar", "es", "fr") or
 * "auto" to let the model decide. Returns the joined text, or NULL if the run
 * failed -- the caller turns that into a message a person can act on. */
JNIEXPORT jstring JNICALL
Java_com_linguafusion_mobile_WhisperNative_transcribe(
        JNIEnv *env, jclass clazz, jlong handle, jfloatArray audio,
        jstring language, jint threads) {
    (void) clazz;
    struct whisper_context *context = (struct whisper_context *) handle;
    if (context == NULL || audio == NULL) {
        return NULL;
    }

    jfloat *samples = (*env)->GetFloatArrayElements(env, audio, NULL);
    const jsize sample_count = (*env)->GetArrayLength(env, audio);
    if (samples == NULL) {
        return NULL;
    }

    const char *requested = (*env)->GetStringUTFChars(env, language, NULL);
    const int detect = (requested == NULL) || (strcmp(requested, "auto") == 0);

    struct whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    // Nothing prints: this runs inside an app, not a terminal, and the
    // per-segment logging upstream enables is pure overhead on a phone.
    params.print_realtime = false;
    params.print_progress = false;
    params.print_timestamps = false;
    params.print_special = false;
    // Transcribe in the spoken language. Whisper can translate to English
    // itself, but translation here goes through ML Kit so that every language
    // pair behaves the same way and the user's choice is honoured.
    params.translate = false;
    params.language = detect ? "auto" : requested;
    params.detect_language = false;
    params.n_threads = threads > 0 ? threads : 4;
    params.offset_ms = 0;
    params.no_context = true;
    params.single_segment = false;
    // Suppress the "(wind blowing)"-style annotations; they are noise here.
    params.suppress_nst = true;

    jstring result = NULL;
    if (whisper_full(context, params, samples, sample_count) != 0) {
        LOGE("whisper_full failed over %d samples", (int) sample_count);
    } else {
        const int segments = whisper_full_n_segments(context);
        size_t length = 1;
        for (int i = 0; i < segments; i++) {
            const char *text = whisper_full_get_segment_text(context, i);
            if (text != NULL) {
                length += strlen(text);
            }
        }
        char *joined = (char *) calloc(length, sizeof(char));
        if (joined != NULL) {
            for (int i = 0; i < segments; i++) {
                const char *text = whisper_full_get_segment_text(context, i);
                if (text != NULL) {
                    strcat(joined, text);
                }
            }
            result = (*env)->NewStringUTF(env, joined);
            free(joined);
        } else {
            LOGE("out of memory joining %d segments", segments);
        }
    }

    if (requested != NULL) {
        (*env)->ReleaseStringUTFChars(env, language, requested);
    }
    // JNI_ABORT: the array was only read, so there is nothing to copy back.
    (*env)->ReleaseFloatArrayElements(env, audio, samples, JNI_ABORT);
    return result;
}

/* Which language the model heard, as an ISO code. Runs the encoder only, so
 * it is far cheaper than a transcription and can be used to label a recording
 * before deciding what to do with it. */
JNIEXPORT jstring JNICALL
Java_com_linguafusion_mobile_WhisperNative_detectLanguage(
        JNIEnv *env, jclass clazz, jlong handle, jfloatArray audio, jint threads) {
    (void) clazz;
    struct whisper_context *context = (struct whisper_context *) handle;
    if (context == NULL || audio == NULL) {
        return NULL;
    }
    jfloat *samples = (*env)->GetFloatArrayElements(env, audio, NULL);
    const jsize sample_count = (*env)->GetArrayLength(env, audio);
    if (samples == NULL) {
        return NULL;
    }

    jstring result = NULL;
    const int used = threads > 0 ? threads : 4;
    if (whisper_pcm_to_mel(context, samples, sample_count, used) == 0) {
        float probabilities[128] = {0};
        const int id = whisper_lang_auto_detect(context, 0, used, probabilities);
        if (id >= 0) {
            const char *code = whisper_lang_str(id);
            if (code != NULL) {
                result = (*env)->NewStringUTF(env, code);
            }
        } else {
            LOGE("language detection failed (%d)", id);
        }
    }
    (*env)->ReleaseFloatArrayElements(env, audio, samples, JNI_ABORT);
    return result;
}
