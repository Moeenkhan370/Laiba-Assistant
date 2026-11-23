package com.moeen.laibaassistant;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import androidx.core.content.FileProvider;
import java.io.File;

public final class LaibaPackageInstaller {
    private LaibaPackageInstaller() {}

    public static void install(Activity activity, String apkPath) {
        if (activity == null || apkPath == null) {
            throw new IllegalArgumentException("Activity and APK path are required.");
        }

        File apk = new File(apkPath);
        if (!apk.isFile() || !apk.canRead()) {
            throw new IllegalArgumentException("Verified APK is not readable.");
        }

        if (Build.VERSION.SDK_INT >= 26
                && !activity.getPackageManager().canRequestPackageInstalls()) {
            Intent settings = new Intent(
                android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:" + activity.getPackageName())
            );
            activity.startActivity(settings);
            return;
        }

        Uri uri = FileProvider.getUriForFile(
            activity,
            activity.getPackageName() + ".fileprovider",
            apk
        );

        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, "application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        activity.startActivity(intent);
    }
}
