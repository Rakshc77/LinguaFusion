package com.linguafusion.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.provider.Settings;
import android.widget.ProgressBar;
import android.widget.Toast;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Updating, in a build the owner distributes directly.
 *
 * Nothing else will ever update this copy, so it updates itself: it compares
 * the published versionCode with its own, and offers what it finds. Android
 * still confirms every install, and the download is checked against its
 * published digest before the installer sees it.
 *
 * The Play flavour has a different class of the same name that answers
 * "nothing" and carries no downloader at all, because Play forbids an app it
 * distributes from replacing itself.
 */
final class AppUpdater {
    interface Listener {
        void onChecked(boolean available, String versionName, int megabytes);
    }

    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();

    static boolean supported() {
        return true;
    }


    /** An explicit check, which ignores the once-per-launch guard and says so
     *  when there is nothing, because this one the person did ask for. */
    static void check(Activity activity,ExecutorService executor,String baseUrl,Listener listener){
        executor.execute(() -> {
            AppUpdate updater=new AppUpdate(activity,baseUrl);
            AppUpdate.Available update=updater.check();
            listener.onChecked(update!=null,update==null?"":update.versionName,
                update==null?0:update.megabytes());
            if(update!=null)activity.runOnUiThread(() -> showUpdateOffer(activity,updater,update));
        });
    }

    private static void showUpdateOffer(Activity activity,AppUpdate updater,AppUpdate.Available update){
        if(activity.isFinishing()||activity.isDestroyed())return;
        new AlertDialog.Builder(activity)
            .setTitle("Update available")
            .setMessage("Version "+update.versionName+" is ready ("+update.megabytes()+" MB)." + "\n\n"
                + "It installs over this one, so nothing on the phone is lost. Android will "
                + "ask you to confirm the install.")
            .setPositiveButton("Update", (dialog,which) -> startUpdate(activity,updater,update))
            .setNegativeButton("Not now", null)
            .show();
    }

    private static void startUpdate(Activity activity,AppUpdate updater,AppUpdate.Available update){
        if(!updater.canInstall()){
            // Android 8 and later gate this per app. Send them straight to the
            // switch rather than describing where it is.
            new AlertDialog.Builder(activity)
                .setTitle("Allow updates first")
                .setMessage("Android needs your permission for this app to install its own updates. "
                    + "Turn on \"Allow from this source\", then press Update again.")
                .setPositiveButton("Open settings", (dialog,which) -> {
                    try{
                        activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                            Uri.parse("package:"+activity.getPackageName())));
                    }catch(Exception missing){
                        Toast.makeText(activity,"Find it under Apps, Special access, Install unknown apps.",Toast.LENGTH_LONG).show();
                    }
                })
                .setNegativeButton("Cancel", null)
                .show();
            return;
        }
        final ProgressBar spinner=new ProgressBar(activity);
        final AlertDialog progress=new AlertDialog.Builder(activity)
            .setTitle("Downloading update")
            .setMessage("This can take a minute. Android will ask you to confirm the install.")
            .setView(spinner).setCancelable(false).create();
        progress.show();
        EXECUTOR.execute(() -> {
            String failure=updater.downloadAndInstall(update,null);
            activity.runOnUiThread(() -> {
                progress.dismiss();
                if(failure!=null)Toast.makeText(activity,failure,Toast.LENGTH_LONG).show();
            });
        });
    }
    private AppUpdater() {
    }
}
