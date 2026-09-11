package com.linguafusion.mobile;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.os.Build;
import android.widget.Toast;

/** Completes the user-confirmed PackageInstaller handshake for sideloads. */
public final class UpdateInstallReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent result) {
        if (result == null || !result.hasExtra(PackageInstaller.EXTRA_STATUS)) return;
        final int status = result.getIntExtra(
            PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            final Intent confirmation;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                confirmation = result.getParcelableExtra(Intent.EXTRA_INTENT, Intent.class);
            } else {
                //noinspection deprecation -- needed on Android 12 and earlier.
                confirmation = result.getParcelableExtra(Intent.EXTRA_INTENT);
            }
            if (confirmation == null) {
                message(context,
                    "Android did not provide an installation confirmation. Download the app manually instead.");
                return;
            }
            try {
                confirmation.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(confirmation);
            } catch (Exception failure) {
                message(context, "Android could not open the installation confirmation: "
                    + failure.getMessage());
            }
            return;
        }
        if (status == PackageInstaller.STATUS_SUCCESS) {
            message(context, "LinguaFusion was updated.");
            return;
        }
        final String detail = result.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
        message(context, "The update was not installed"
            + (detail == null || detail.isEmpty() ? "." : ": " + detail));
    }

    private static void message(Context context, String text) {
        Toast.makeText(context, text, Toast.LENGTH_LONG).show();
    }
}
