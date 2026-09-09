package com.linguafusion.mobile;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.os.Build;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;

/**
 * Updating the app without going and finding the APK again.
 *
 * The app is distributed privately rather than through Play, so nothing
 * updates it automatically. This checks what the service publishes, and if it
 * is newer, downloads and hands it to Android's package installer.
 *
 * **Android always asks the person to confirm** an install from outside Play,
 * and it always will -- that prompt cannot be skipped and should not be. What
 * this removes is everything around it: noticing an update exists, opening a
 * browser, finding the file, checking the fingerprint by eye.
 *
 * The downloaded file is an executable, so it is checked against the published
 * SHA-256 before the installer is allowed near it. A mismatch deletes it. The
 * install would fail anyway on a signature mismatch, because Android refuses
 * to replace an app with one signed by a different key -- but that is a last
 * line, not the first.
 *
 * Blocking. Not for the UI thread.
 */
final class AppUpdate {
    /** What the service publishes beside the APK. */
    private static final String DETAILS_PATH = "/pilot/android-app.json";
    private static final String APK_PATH = "/pilot/linguafusion-android.apk";
    private static final int BUFFER = 1 << 16;

    /** A published version, once it is known to be newer than what is here. */
    static final class Available {
        final long versionCode;
        final String versionName;
        final long bytes;
        final String sha256;

        Available(long versionCode, String versionName, long bytes, String sha256) {
            this.versionCode = versionCode;
            this.versionName = versionName;
            this.bytes = bytes;
            this.sha256 = sha256;
        }

        int megabytes() {
            return (int) Math.round(bytes / 1_000_000.0);
        }
    }

    private final Context context;
    private final String baseUrl;

    AppUpdate(Context context, String baseUrl) {
        this.context = context.getApplicationContext();
        this.baseUrl = baseUrl;
    }

    /** The version code of the app running right now. */
    static long installedVersion(Context context) {
        try {
            final PackageInfo info = context.getPackageManager()
                    .getPackageInfo(context.getPackageName(), 0);
            return Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                    ? info.getLongVersionCode() : info.versionCode;
        } catch (PackageManager.NameNotFoundException impossible) {
            return 0;
        }
    }

    /**
     * Asks the service what it publishes.
     *
     * @return the newer version, or null if there is none or the check failed.
     *         A failed check is deliberately indistinguishable from "nothing
     *         new": an update prompt is not worth an error message when the
     *         person did not ask for one.
     */
    Available check() {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(baseUrl + DETAILS_PATH).openConnection();
            connection.setConnectTimeout(15_000);
            connection.setReadTimeout(15_000);
            if (connection.getResponseCode() != HttpURLConnection.HTTP_OK) {
                return null;
            }
            final StringBuilder body = new StringBuilder();
            try (InputStream input = connection.getInputStream()) {
                final byte[] buffer = new byte[4096];
                int read;
                while ((read = input.read(buffer)) > 0 && body.length() < 8192) {
                    body.append(new String(buffer, 0, read, "UTF-8"));
                }
            }
            final JSONObject details = new JSONObject(body.toString());
            final long published = details.optLong("versionCode", 0);
            final String sha256 = details.optString("sha256", "");
            // An older build of the service publishes no version at all. Treat
            // that as nothing to offer rather than guessing.
            if (published <= installedVersion(context) || !sha256.matches("[0-9a-f]{64}")) {
                return null;
            }
            return new Available(published, details.optString("versionName", ""),
                    details.optLong("bytes", 0), sha256);
        } catch (Exception unreachable) {
            return null;
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    /** Whether this phone will let the app install anything at all. */
    boolean canInstall() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O
                || context.getPackageManager().canRequestPackageInstalls();
    }

    /**
     * Downloads the update and hands it to Android's installer.
     *
     * @return null once the installer has been asked to take over, otherwise
     *         a message saying what stopped it
     */
    String downloadAndInstall(Available update, OfflineSpeech.Progress progress) {
        if (update == null) {
            return "There is no update to install.";
        }
        final File target = new File(context.getCacheDir(), "linguafusion-update.apk");
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(baseUrl + APK_PATH).openConnection();
            connection.setConnectTimeout(30_000);
            connection.setReadTimeout(60_000);
            if (connection.getResponseCode() != HttpURLConnection.HTTP_OK) {
                return "The update could not be downloaded (HTTP "
                        + connection.getResponseCode() + ").";
            }
            try (InputStream input = connection.getInputStream();
                 OutputStream output = new java.io.FileOutputStream(target, false)) {
                final byte[] buffer = new byte[BUFFER];
                long done = 0;
                int read;
                while ((read = input.read(buffer)) > 0) {
                    output.write(buffer, 0, read);
                    done += read;
                    if (progress != null) {
                        progress.onProgress(done, update.bytes);
                    }
                }
            }

            if (!update.sha256.equalsIgnoreCase(sha256(target))) {
                // Never hand an unverified executable to the installer.
                target.delete();
                return "The downloaded update did not match its published "
                        + "fingerprint and has been discarded.";
            }
            return install(target);
        } catch (IOException failure) {
            target.delete();
            return "The update download was interrupted: " + failure.getMessage();
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    /**
     * Hands the file to the system installer, which shows its own dialog.
     * PackageInstaller rather than an ACTION_VIEW intent: it needs no
     * FileProvider, and it reports failures back to the app instead of
     * silently doing nothing.
     */
    private String install(File apk) {
        PackageInstaller.Session session = null;
        try {
            final PackageInstaller installer = context.getPackageManager().getPackageInstaller();
            final PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(
                    PackageInstaller.SessionParams.MODE_FULL_INSTALL);
            final int sessionId = installer.createSession(params);
            session = installer.openSession(sessionId);
            try (InputStream input = new FileInputStream(apk);
                 OutputStream output = session.openWrite("linguafusion", 0, apk.length())) {
                final byte[] buffer = new byte[BUFFER];
                int read;
                while ((read = input.read(buffer)) > 0) {
                    output.write(buffer, 0, read);
                }
                session.fsync(output);
            }
            final Intent callback = new Intent(context, MainActivity.class);
            final int flags = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
                    ? android.app.PendingIntent.FLAG_MUTABLE : 0;
            session.commit(android.app.PendingIntent.getActivity(
                    context, sessionId, callback, flags).getIntentSender());
            return null;
        } catch (Exception failure) {
            if (session != null) {
                session.abandon();
            }
            return "Android would not start the install (" + failure.getMessage() + ").";
        } finally {
            if (session != null) {
                session.close();
            }
        }
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
