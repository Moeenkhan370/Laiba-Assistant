"""Python-to-Java bridge for Laiba Android reminders."""

import hashlib


class ReminderBridge:
    def __init__(self):
        self.scheduler = None
        self.activity = None

    def _connect(self):
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity

            if activity is None:
                raise RuntimeError("Android activity is unavailable")

            self.activity = activity
            self.scheduler = autoclass(
                "com.moeen.laibaassistant.ReminderScheduler"
            )
            return True

        except Exception as exc:
            print("[LAIBA REMINDER] Java connection error:", exc)
            self.activity = None
            self.scheduler = None
            return False

    @staticmethod
    def make_id(title, message, time_ms):
        source = "{}|{}|{}".format(title, message, time_ms)
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        return int(digest[:7], 16)

    def schedule(
        self,
        title,
        message,
        time_ms,
        repeat_ms=0,
        reminder_id=None
    ):
        try:
            if not self._connect():
                return False

            title = str(title).strip()
            message = str(message).strip()
            time_ms = int(time_ms)
            repeat_ms = int(repeat_ms)

            if not message or time_ms <= 0 or repeat_ms < 0:
                print("[LAIBA REMINDER] Invalid reminder details")
                return False

            rid = (
                int(reminder_id)
                if reminder_id is not None
                else self.make_id(title, message, time_ms)
            )

            self.scheduler.schedule(
                self.activity,
                rid,
                title,
                message,
                time_ms,
                repeat_ms
            )

            # Verify that Java saved the reminder in SharedPreferences.
            prefs = self.activity.getSharedPreferences(
                "laiba_reminders", 0
            )

            if not prefs.contains("r_" + str(rid)):
                print("[LAIBA REMINDER] Reminder was not saved:", rid)
                return False

            print("[LAIBA REMINDER] Reminder saved:", rid)
            return rid

        except Exception as exc:
            print("[LAIBA REMINDER] Schedule error:", exc)
            return False

    def cancel(self, reminder_id):
        try:
            if not self._connect():
                return False

            rid = int(reminder_id)

            self.scheduler.cancel(self.activity, rid)

            prefs = self.activity.getSharedPreferences(
                "laiba_reminders", 0
            )

            if prefs.contains("r_" + str(rid)):
                print("[LAIBA REMINDER] Cancel verification failed:", rid)
                return False

            print("[LAIBA REMINDER] Reminder cancelled:", rid)
            return True

        except Exception as exc:
            print("[LAIBA REMINDER] Cancel error:", exc)
            return False

    def is_available(self):
        return self._connect()
