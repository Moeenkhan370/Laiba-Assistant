package com.moeen.laibaassistant;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.os.Build;
import android.os.PowerManager;
import android.speech.tts.TextToSpeech;
import java.util.Locale;

public class ReminderReceiver extends BroadcastReceiver {

    private static final String CHANNEL = "laiba_voice_reminders";

    @Override
    public void onReceive(Context context, Intent intent) {

        String action = intent.getAction();

        if ("LAIBA_SNOOZE".equals(action)) {
            int snoozeId = intent.getIntExtra("id", 0) + 1000000;
            String title = intent.getStringExtra("title");
            String message = intent.getStringExtra("message");

            ReminderScheduler.schedule(
                context, snoozeId, title, message,
                System.currentTimeMillis() + 300000, 0
            );
            return;
        }

        if ("LAIBA_DISMISS".equals(action)) {
            int id = intent.getIntExtra("id", 0);
            ((NotificationManager) context.getSystemService(
                Context.NOTIFICATION_SERVICE
            )).cancel(id);
            return;
        }

        int id = intent.getIntExtra("id", 0);
        String title = intent.getStringExtra("title");
        String message = intent.getStringExtra("message");
        long repeat = intent.getLongExtra("repeat", 0);

        if (title == null) title = "Laiba Reminder";
        if (message == null) message = "آپ کا یاد دہانی کا وقت ہو گیا ہے۔";

        showNotification(context, id, title, message);
        speak(context, message);

        if (repeat > 0) {
            ReminderScheduler.schedule(
                context, id, title, message,
                System.currentTimeMillis() + repeat, repeat
            );
        } else {
            ReminderScheduler.cancel(context, id);
        }
    }

    private void showNotification(
        Context context, int id, String title, String message
    ) {
        NotificationManager nm = (NotificationManager)
            context.getSystemService(Context.NOTIFICATION_SERVICE);

        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL, "Laiba Voice Reminders",
                NotificationManager.IMPORTANCE_HIGH
            );
            channel.setDescription("Scheduled Urdu voice reminders");
            channel.enableVibration(true);
            nm.createNotificationChannel(channel);
        }

        Intent launch = context.getPackageManager()
            .getLaunchIntentForPackage(context.getPackageName());

        PendingIntent open = null;
        if (launch != null) {
            open = PendingIntent.getActivity(
                context, id, launch,
                PendingIntent.FLAG_UPDATE_CURRENT |
                (Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0)
            );
        }

        Intent snoozeIntent = new Intent(context, ReminderReceiver.class);
        snoozeIntent.setAction("LAIBA_SNOOZE");
        snoozeIntent.putExtra("id", id);
        snoozeIntent.putExtra("title", title);
        snoozeIntent.putExtra("message", message);

        PendingIntent snooze = PendingIntent.getBroadcast(
            context, id + 2000000, snoozeIntent,
            PendingIntent.FLAG_UPDATE_CURRENT |
            (Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0)
        );

        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
            ? new Notification.Builder(context, CHANNEL)
            : new Notification.Builder(context);

        builder.setSmallIcon(context.getApplicationInfo().icon)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(new Notification.BigTextStyle().bigText(message))
            .setAutoCancel(true)
            .addAction(android.R.drawable.ic_lock_idle_alarm,
                "Snooze 5 min", snooze);

        if (open != null) builder.setContentIntent(open);

        nm.notify(id, builder.build());
    }

    private void speak(Context context, String message) {
        final PowerManager.WakeLock lock =
            ((PowerManager) context.getSystemService(
                Context.POWER_SERVICE
            )).newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "Laiba:ReminderSpeech"
            );

        try {
            lock.acquire(120000);
        } catch (Exception ignored) {}

        final PendingResult pending = goAsync();

        final TextToSpeech[] engine = new TextToSpeech[1];

        engine[0] = new TextToSpeech(context.getApplicationContext(), status -> {
            try {
                if (status == TextToSpeech.SUCCESS) {
                    int result = engine[0].setLanguage(
                        new Locale("ur", "PK")
                    );

                    if (result == TextToSpeech.LANG_MISSING_DATA ||
                        result == TextToSpeech.LANG_NOT_SUPPORTED) {
                        engine[0].setLanguage(new Locale("ur"));
                    }

                    engine[0].setSpeechRate(0.88f);

                    if (Build.VERSION.SDK_INT >= 21) {
                        engine[0].speak(
                            message,
                            TextToSpeech.QUEUE_FLUSH,
                            null,
                            "laiba_reminder"
                        );
                    } else {
                        engine[0].speak(
                            message, TextToSpeech.QUEUE_FLUSH, null
                        );
                    }
                }
            } catch (Exception e) {
                android.util.Log.e("LaibaReminder", "TTS error", e);
            }

            new Thread(() -> {
                try { Thread.sleep(15000); }
                catch (InterruptedException ignored) {}

                try { engine[0].shutdown(); }
                catch (Exception ignored) {}

                try {
                    if (lock.isHeld()) lock.release();
                } catch (Exception ignored) {}

                try { pending.finish(); }
                catch (Exception ignored) {}
            }).start();
        });
    }
}
