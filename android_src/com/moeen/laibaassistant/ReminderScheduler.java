package com.moeen.laibaassistant;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.content.SharedPreferences;
import org.json.JSONObject;

public class ReminderScheduler {

    private static final String PREF = "laiba_reminders";

    public static void schedule(
        Context context,
        int id,
        String title,
        String message,
        long time,
        long repeat
    ) {
        try {
            JSONObject data = new JSONObject();
            data.put("id", id);
            data.put("title", title);
            data.put("message", message);
            data.put("time", time);
            data.put("repeat", repeat);

            context.getSharedPreferences(PREF, 0)
                .edit().putString("r_" + id, data.toString()).apply();

            setAlarm(context, id, title, message, time, repeat);
        } catch (Exception e) {
            android.util.Log.e("LaibaReminder", "Schedule error", e);
        }
    }

    private static void setAlarm(
        Context context, int id, String title,
        String message, long time, long repeat
    ) {
        try {
            AlarmManager manager =
                (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);

            Intent intent = new Intent(context, ReminderReceiver.class);
            intent.putExtra("id", id);
            intent.putExtra("title", title);
            intent.putExtra("message", message);
            intent.putExtra("repeat", repeat);

            PendingIntent pi = PendingIntent.getBroadcast(
                context, id, intent,
                PendingIntent.FLAG_UPDATE_CURRENT |
                (Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0)
            );

            if (Build.VERSION.SDK_INT >= 31 &&
                !manager.canScheduleExactAlarms()) {
                manager.setAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP, time, pi
                );
            } else if (Build.VERSION.SDK_INT >= 23) {
                manager.setExactAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP, time, pi
                );
            } else {
                manager.setExact(AlarmManager.RTC_WAKEUP, time, pi);
            }
        } catch (Exception e) {
            android.util.Log.e("LaibaReminder", "Alarm error", e);
        }
    }

    public static void cancel(Context context, int id) {
        try {
            AlarmManager manager =
                (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);

            Intent intent = new Intent(context, ReminderReceiver.class);

            PendingIntent pi = PendingIntent.getBroadcast(
                context, id, intent,
                PendingIntent.FLAG_UPDATE_CURRENT |
                (Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0)
            );

            manager.cancel(pi);

            context.getSharedPreferences(PREF, 0)
                .edit().remove("r_" + id).apply();
        } catch (Exception e) {
            android.util.Log.e("LaibaReminder", "Cancel error", e);
        }
    }

    public static void restore(Context context) {
        try {
            SharedPreferences prefs =
                context.getSharedPreferences(PREF, 0);

            for (String key : prefs.getAll().keySet()) {
                String value = prefs.getString(key, null);
                if (value == null) continue;

                JSONObject data = new JSONObject(value);

                long time = data.getLong("time");
                long repeat = data.optLong("repeat", 0);

                if (repeat > 0) {
                    while (time <= System.currentTimeMillis()) {
                        time += repeat;
                    }
                }

                if (time > System.currentTimeMillis()) {
                    setAlarm(
                        context,
                        data.getInt("id"),
                        data.getString("title"),
                        data.getString("message"),
                        time,
                        repeat
                    );
                }
            }
        } catch (Exception e) {
            android.util.Log.e("LaibaReminder", "Restore error", e);
        }
    }
}
