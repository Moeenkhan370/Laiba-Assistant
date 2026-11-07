
import os
from threading import Thread
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.label import Label


class AndroidMediaBridge:
    SPEECH_CODE = 7312
    VIDEO_CODE = 7313

    def __init__(self, app):
        self.app = app
        self.activity_bound = False

    def message(self, text):
        Clock.schedule_once(
            lambda dt: self.app.add_bubble(str(text), "Laiba"), 0
        )

    def permissions(self, names, callback):
        try:
            from android.permissions import request_permissions
            def result(perms, grants):
                if all(bool(x) for x in grants):
                    callback()
                else:
                    self.message("Android permission denied: " + ", ".join(names))
            request_permissions(names, result)
        except Exception as exc:
            self.message("Android permission error: " + str(exc))

    def camera(self):
        self.permissions(["CAMERA"], self._take_picture)

    def _take_picture(self):
        try:
            from plyer import camera
            os.makedirs(self.app.user_data_dir, exist_ok=True)
            path = os.path.join(self.app.user_data_dir, "laiba_camera.jpg")
            camera.take_picture(
                filename=path,
                on_complete=self._camera_done
            )
        except Exception as exc:
            self.message("Camera error: " + str(exc))

    def _camera_done(self, path):
        if path and os.path.isfile(str(path)):
            self.send_image(str(path))
        else:
            self.message("Camera cancelled or image was not saved.")

    def gallery(self):
        try:
            from plyer import filechooser
            filechooser.open_file(
                on_selection=self._gallery_done,
                filters=["*.jpg", "*.jpeg", "*.png", "*.webp"]
            )
        except Exception as exc:
            self.message("Gallery error: " + str(exc))

    def _gallery_done(self, selection):
        if selection:
            path = str(selection[0])
            if path.startswith("file://"):
                path = path[7:]
            self.send_image(path)
        else:
            self.message("No image selected.")

    def send_image(self, path):
        if not os.path.isfile(path):
            self.message("Image path is not accessible: " + path)
            return

        self.app.add_bubble("[Image attached]", "You")
        thinking = Label(
            text="Laiba is analyzing the image...",
            color=(0, 0.85, 1, 1),
            size_hint_y=None,
            height=dp(32)
        )
        self.app.message_list.add_widget(thinking)

        def worker():
            try:
                result = self.app.chatbot.process_message(
                    "Please analyze this image and describe what you see.",
                    image_path=path
                )
            except Exception as exc:
                result = "Image analysis error: " + str(exc)

            Clock.schedule_once(
                lambda dt: self.app.finish_reply(result, thinking), 0
            )

        Thread(target=worker, daemon=True).start()

    def _bind_activity(self):
        if self.activity_bound:
            return
        from android import activity
        activity.bind(on_activity_result=self._activity_result)
        self.activity_bound = True

    def microphone(self):
        self.permissions(
            ["RECORD_AUDIO"],
            self._start_speech
        )

    def _start_speech(self):
        try:
            self._bind_activity()
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            RecognizerIntent = autoclass("android.speech.RecognizerIntent")

            intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
            )
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ur-PK")
            intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "Laiba is listening...")
            PythonActivity.mActivity.startActivityForResult(
                intent, self.SPEECH_CODE
            )
        except Exception as exc:
            self.message("Microphone / speech recognition error: " + str(exc))

    def live_camera(self):
        self.permissions(
            ["CAMERA", "RECORD_AUDIO"],
            self._start_video
        )

    def _start_video(self):
        try:
            self._bind_activity()
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")

            intent = Intent("android.media.action.VIDEO_CAPTURE")
            intent.putExtra("android.intent.extra.durationLimit", 60)
            intent.putExtra("android.intent.extra.videoQuality", 1)
            PythonActivity.mActivity.startActivityForResult(
                intent, self.VIDEO_CODE
            )
        except Exception as exc:
            self.message("Live camera error: " + str(exc))

    def _activity_result(self, request_code, result_code, intent):
        try:
            code = int(request_code)
            result = int(result_code)

            if code == self.SPEECH_CODE:
                if result == -1 and intent:
                    from jnius import autoclass
                    RecognizerIntent = autoclass(
                        "android.speech.RecognizerIntent"
                    )
                    results = intent.getStringArrayListExtra(
                        RecognizerIntent.EXTRA_RESULTS
                    )
                    if results and results.size() > 0:
                        spoken = str(results.get(0))
                        Clock.schedule_once(
                            lambda dt: self._send_spoken(spoken), 0
                        )
                    else:
                        self.message("Speech was not recognized.")
                else:
                    self.message("Microphone cancelled.")

            elif code == self.VIDEO_CODE:
                if result == -1:
                    uri = intent.getData() if intent else None
                    if uri:
                        self.message(
                            "Video captured. Saved video: " + str(uri.toString())
                        )
                    else:
                        self.message("Video capture completed. Check your gallery.")
                else:
                    self.message("Video recording cancelled.")

        except Exception as exc:
            self.message("Android activity result error: " + str(exc))

    def _send_spoken(self, spoken):
        self.app.user_input.text = spoken
        self.app.send_message()
