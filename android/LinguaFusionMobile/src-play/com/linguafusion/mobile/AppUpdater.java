package com.linguafusion.mobile;

import android.app.Activity;

import java.util.concurrent.ExecutorService;

/**
 * Updating, in a build Google Play distributes: there is nothing to do.
 *
 * Play keeps this copy current, and its Device and Network Abuse policy
 * forbids an app it distributes from replacing itself by any other route. The
 * downloader and installer are not merely disabled here, they are absent --
 * this flavour never compiles them, so the Play build contains no code for
 * fetching or installing an APK at all.
 *
 * The hosted interface still updates itself. That is interpreted code in a
 * WebView, which the same policy explicitly excludes.
 */
final class AppUpdater {
    interface Listener {
        /** versionName and megabytes are meaningless when nothing is offered. */
        void onChecked(boolean available, String versionName, int megabytes);
    }

    static boolean supported() {
        return false;
    }

    static void check(Activity activity, ExecutorService executor, String baseUrl, Listener listener) {
        // Answer immediately rather than leaving the caller waiting: the page
        // bounds its wait, and a silent no-op would spend that whole timeout.
        listener.onChecked(false, "", 0);
    }

    private AppUpdater() {
    }
}
