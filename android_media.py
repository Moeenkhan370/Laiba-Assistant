
import os
from threading import Thread
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.label import Label


class _TTSInitListener:
    pass


class AndroidMediaBridge:
    SPEECH_CODE = 7312
    VIDEO_CODE = 7313

    def __init__(self, app):
        self.app = app
        self.activity_bound = False
        self.camera_output_uri = None
        self.tts = None
        self.tts_ready = False
        self.init_native_tts()

    def init_native_tts(self):
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            class Listener(PythonJavaClass):
                __javainterfaces__ = [
                    "android/speech/tts/TextToSpeech$OnInitListener"
                ]
                __javacontext__ = "app"
                def __init__(self, bridge):
                    super().__init__()
                    self.bridge = bridge
                @java_method("(I)V")
                def onInit(self, status):
                    try:
                        TTS = autoclass("android.speech.tts.TextToSpeech")
                        if status == TTS.SUCCESS:
                            Locale = autoclass("java.util.Locale")
                            result = self.bridge.tts.setLanguage(
                                Locale("ur", "PK")
                            )
                            self.bridge.tts_ready = (
                                result >= TTS.LANG_AVAILABLE
                            )
                    except Exception as exc:
                        print("LAIBA_TTS_INIT:", exc)

            Activity = autoclass("org.kivy.android.PythonActivity")
            self.tts_listener = Listener(self)
            self.tts = autoclass(
                "android.speech.tts.TextToSpeech"
            )(Activity.mActivity, self.tts_listener)
        except Exception as exc:
            print("LAIBA_NATIVE_TTS_ERROR:", exc)

    def speak(self, text):
        try:
            if self.tts and self.tts_ready:
                TTS = autoclass("android.speech.tts.TextToSpeech")
                self.tts.speak(
                    str(text), TTS.QUEUE_FLUSH, None
                )
        except Exception as exc:
            print("LAIBA_TTS_SPEAK_ERROR:", exc)

    def message(self, text):
        Clock.schedule_once(
            lambda dt: self.app.add_bubble(str(text), "Laiba"), 0
        )

    def permissions(self, names, callback):
        try:
            from android.permissions import request_permissions
            def result(perms, grants):
                try:
                    details = ", ".join(
                        str(permission) + "=" + str(grant)
                        for permission, grant in zip(perms, grants)
                    )
                    print("LAIBA_PERMISSION_RESULT:", details)

                    if grants and all(bool(x) for x in grants):
                        callback()
                    else:
                        self.message(
                            "Android permission denied: " + details
                        )
                except Exception as exc:
                    self.message(
                        "Permission callback error: " + str(exc)
                    )
            request_permissions(names, result)
        except Exception as exc:
            self.message("Android permission error: " + str(exc))

    CAMERA_CODE = 7315

    def camera(self):
        try:
            from jnius import autoclass
            BuildVersion = autoclass("android.os.Build$VERSION")

            if int(BuildVersion.SDK_INT) < 29:
                self.permissions(
                    ["android.permission.WRITE_EXTERNAL_STORAGE"],
                    self._take_picture
                )
            else:
                self._take_picture()
        except Exception as exc:
            self.message("Camera permission error: " + str(exc))

    def _take_picture(self):
        try:
            self._bind_activity()
            from jnius import autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )
            Intent = autoclass("android.content.Intent")
            ContentValues = autoclass("android.content.ContentValues")
            MediaStore = autoclass("android.provider.MediaStore")
            MediaStoreImages = autoclass(
                "android.provider.MediaStore$Images$Media"
            )
            BuildVersion = autoclass("android.os.Build$VERSION")

            activity = PythonActivity.mActivity
            resolver = activity.getContentResolver()

            values = ContentValues()
            filename = (
                "Laiba_" + str(__import__("time").time_ns()) + ".jpg"
            )
            values.put(
                MediaStoreImages.DISPLAY_NAME, filename
            )
            values.put(
                MediaStoreImages.MIME_TYPE, "image/jpeg"
            )

            if int(BuildVersion.SDK_INT) >= 29:
                values.put(
                    MediaStoreImages.RELATIVE_PATH,
                    "Pictures/Laiba"
                )

            uri = resolver.insert(
                MediaStoreImages.EXTERNAL_CONTENT_URI,
                values
            )

            if uri is None:
                raise RuntimeError("Could not create camera image destination.")

            intent = Intent("android.media.action.IMAGE_CAPTURE")
            intent.putExtra(MediaStore.EXTRA_OUTPUT, uri)
            intent.addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION |
                Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            )

            if not intent.resolveActivity(activity.getPackageManager()):
                resolver.delete(uri, None, None)
                raise RuntimeError("No camera application is available.")

            self.camera_output_uri = uri
            activity.startActivityForResult(intent, self.CAMERA_CODE)

        except Exception as exc:
            self.camera_output_uri = None
            self.message("Camera error: " + str(exc))

    GALLERY_CODE = 7314

    def gallery(self):
        try:
            self._bind_activity()
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")

            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType("image/*")
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)

            PythonActivity.mActivity.startActivityForResult(
                intent, self.GALLERY_CODE
            )
        except Exception as exc:
            self.message("Gallery error: " + str(exc))

    def _save_camera_bitmap(self, bitmap):
        try:
            from jnius import autoclass

            Bitmap = autoclass("android.graphics.Bitmap")
            CompressFormat = autoclass(
                "android.graphics.Bitmap$CompressFormat"
            )
            ByteArrayOutputStream = autoclass(
                "java.io.ByteArrayOutputStream"
            )

            stream = ByteArrayOutputStream()
            bitmap.compress(CompressFormat.JPEG, 95, stream)
            data = bytes(stream.toByteArray())
            stream.close()

            if not data:
                raise ValueError("Camera image is empty.")
            if len(data) > 20 * 1024 * 1024:
                raise ValueError("Camera image exceeds 20 MB.")

            os.makedirs(self.app.user_data_dir, exist_ok=True)
            path = os.path.join(
                self.app.user_data_dir,
                "laiba_camera_" + str(__import__("time").time_ns()) + ".jpg"
            )
            with open(path, "wb") as output:
                output.write(data)

            self.send_image(path)

        except Exception as exc:
            self.message("Could not save camera image: " + str(exc))

    def _copy_gallery_uri(self, uri):
        try:
            from jnius import autoclass, jarray

            activity = autoclass(
                "org.kivy.android.PythonActivity"
            ).mActivity

            resolver = activity.getContentResolver()
            mime = str(resolver.getType(uri) or "").lower()

            extensions = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp"
            }

            if mime not in extensions:
                self.message("Unsupported image format: " + mime)
                return

            os.makedirs(self.app.user_data_dir, exist_ok=True)
            path = os.path.join(
                self.app.user_data_dir,
                "laiba_gallery_" + str(__import__("time").time_ns())
                + extensions[mime]
            )

            stream = resolver.openInputStream(uri)
            if stream is None:
                self.message("Could not open selected image.")
                return

            buffer = jarray("b")(65536)
            total = 0

            try:
                with open(path, "wb") as output:
                    while True:
                        count = int(stream.read(buffer))
                        if count < 0:
                            break
                        if count == 0:
                            continue

                        total += count
                        if total > 20 * 1024 * 1024:
                            raise ValueError("Image exceeds 20 MB limit.")

                        output.write(bytes(
                            (int(buffer[i]) & 255 for i in range(count))
                        ))
            finally:
                stream.close()

            if total == 0:
                raise ValueError("Selected image is empty.")

            self.send_image(path)

        except Exception as exc:
            self.message("Gallery image error: " + str(exc))

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
            ["android.permission.RECORD_AUDIO"],
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
        # External camera application handles its own camera/audio permissions.
        # This application does not need to request them for VIDEO_CAPTURE.
        self._start_video()

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

            elif code == self.GALLERY_CODE:
                if result == -1 and intent:
                    uri = intent.getData()
                    if uri:
                        self._copy_gallery_uri(uri)
                    else:
                        self.message("No image was selected.")
                else:
                    self.message("Gallery selection cancelled.")

            elif code == self.CAMERA_CODE:
                uri = self.camera_output_uri
                self.camera_output_uri = None

                if result == -1 and uri is not None:
                    self._copy_gallery_uri(uri)
                else:
                    if uri is not None:
                        try:
                            from jnius import autoclass
                            activity = autoclass(
                                "org.kivy.android.PythonActivity"
                            ).mActivity
                            activity.getContentResolver().delete(
                                uri, None, None
                            )
                        except Exception:
                            pass
                    self.message("Camera capture cancelled.")

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
