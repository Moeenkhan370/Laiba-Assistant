import os
import asyncio
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
        self.edge_player = None
        self.tts_ready = False
        self.speech_recognizer = None
        self.continuous_listening = False
        self.recognition_listener = None
        self.recognition_active = False
        self.is_speaking = False
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
                            if result < TTS.LANG_AVAILABLE:
                                result = self.bridge.tts.setLanguage(
                                    Locale("en", "US")
                                )
                            self.bridge.tts_ready = (
                                result >= TTS.LANG_AVAILABLE
                            )
                            print("LAIBA_TTS_READY:", self.bridge.tts_ready, flush=True)
                            if self.bridge.tts_ready:
                                pending = getattr(self.bridge, "pending_speech", None)
                                self.bridge.pending_speech = None
                                if pending:
                                    Clock.schedule_once(
                                        lambda dt: self.bridge.speak(pending), 0
                                    )
                    except Exception as exc:
                        print("LAIBA_TTS_INIT:", exc)

            class ProgressListener(PythonJavaClass):
                __javainterfaces__ = [
                    "android/speech/tts/UtteranceProgressListener"
                ]
                __javacontext__ = "app"

                def __init__(self, bridge):
                    super().__init__()
                    self.bridge = bridge

                @java_method("(Ljava/lang/String;)V")
                def onStart(self, utterance_id):
                    Clock.schedule_once(
                        lambda dt: self.bridge._tts_state("speaking"), 0
                    )

                @java_method("(Ljava/lang/String;)V")
                def onDone(self, utterance_id):
                    Clock.schedule_once(
                        lambda dt: self.bridge._tts_state("done"), 0
                    )

                @java_method("(Ljava/lang/String;)V")
                def onError(self, utterance_id):
                    Clock.schedule_once(
                        lambda dt: self.bridge._tts_state("error"), 0
                    )

            self.tts_progress_listener = ProgressListener(self)

            Activity = autoclass("org.kivy.android.PythonActivity")
            self.tts_listener = Listener(self)
            self.tts = autoclass(
                "android.speech.tts.TextToSpeech"
            )(Activity.mActivity, self.tts_listener)
            self.tts.setOnUtteranceProgressListener(
                self.tts_progress_listener
            )
        except Exception as exc:
            print("LAIBA_NATIVE_TTS_ERROR:", exc)

    def stop_speaking(self):
        self.is_speaking = False
        try:
            if self.edge_player:
                self.edge_player.stop()
                self.edge_player.release()
                self.edge_player = None
        except Exception as exc:
            print("LAIBA_EDGE_STOP:", exc)
        try:
            if self.tts:
                self.tts.stop()
        except Exception as exc:
            print("LAIBA_TTS_STOP:", exc)

    def speak(self, text):
        self.is_speaking = True
        Thread(target=self._generate_edge_audio, args=(str(text),), daemon=True).start()

    def _generate_edge_audio(self, text):
        try:
            import edge_tts
            os.makedirs(self.app.user_data_dir, exist_ok=True)
            path = os.path.join(self.app.user_data_dir, "laiba_speech.mp3")

            async def generate():
                tts = edge_tts.Communicate(
                    text, "ur-PK-UzmaNeural"
                )
                await tts.save(path)

            asyncio.run(generate())
            Clock.schedule_once(lambda dt: self._play_edge_audio(path, text), 0)
        except Exception as exc:
            print("LAIBA_EDGE_ERROR:", repr(exc), flush=True)
            Clock.schedule_once(lambda dt: self._speak_native(text), 0)

    def _play_edge_audio(self, path, text):
        try:
            from jnius import autoclass, PythonJavaClass, java_method
            class DoneListener(PythonJavaClass):
                __javainterfaces__ = ["android/media/MediaPlayer$OnCompletionListener"]
                __javacontext__ = "app"
                def __init__(self, bridge):
                    super().__init__()
                    self.bridge = bridge
                @java_method("(Landroid/media/MediaPlayer;)V")
                def onCompletion(self, mp):
                    Clock.schedule_once(lambda dt: self.bridge._tts_state("done"), 0)

            MediaPlayer = autoclass("android.media.MediaPlayer")
            self.edge_player = MediaPlayer()
            self.edge_player.setDataSource(path)
            self.edge_completion_listener = DoneListener(self)
            self.edge_player.setOnCompletionListener(self.edge_completion_listener)
            self.edge_player.prepare()
            self.edge_player.start()
            self._tts_state("speaking")
        except Exception as exc:
            print("LAIBA_EDGE_PLAYBACK_ERROR:", repr(exc), flush=True)
            self._speak_native(text)

    def _speak_native(self, text):
        try:
            from jnius import autoclass
            if not self.tts or not self.tts_ready:
                self.pending_speech = str(text)
                return
            TTS = autoclass("android.speech.tts.TextToSpeech")
            result = self.tts.speak(
                str(text), TTS.QUEUE_FLUSH, None, "laiba_reply"
            )
            if result == TTS.ERROR:
                self._tts_state("error")
        except Exception as exc:
            print("LAIBA_NATIVE_FALLBACK_ERROR:", exc)
            self._tts_state("error")

    def _tts_state(self, state):
        self.is_speaking = (state == "speaking")
        callback = getattr(self.app, "on_tts_state", None)
        if callback:
            callback(state)

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
                    print("LAIBA_PERMISSION_RESULT:", details, flush=True)

                    if grants and all(bool(x) for x in grants):
                        print("LAIBA_MIC_PERMISSION: GRANTED", flush=True)
                        callback()
                    else:
                        print("LAIBA_MIC_PERMISSION: DENIED", details, flush=True)
                        self.message(
                            "Android permission denied: " + details
                        )
                except Exception as exc:
                    self.message(
                        "Permission callback error: " + str(exc)
                    )
            print("LAIBA_MIC_PERMISSION: requesting", names, flush=True)
            request_permissions(names, result)
        except Exception as exc:
            print("LAIBA_PERMISSION_EXCEPTION:", repr(exc), flush=True)
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
        print("LAIBA_MIC_BUTTON: pressed", flush=True)
        self.permissions(
            ["android.permission.RECORD_AUDIO"],
            self._start_speech
        )

    def _start_speech(self):
        Clock.schedule_once(lambda dt: self._init_and_listen_ui_thread(), 0)

    def _init_and_listen_ui_thread(self):
        try:
            from jnius import autoclass, PythonJavaClass, java_method

            class Listener(PythonJavaClass):
                __javainterfaces__ = [
                    "android/speech/RecognitionListener"
                ]
                __javacontext__ = "app"

                def __init__(self, bridge):
                    super().__init__()
                    self.bridge = bridge

                @java_method("(Landroid/os/Bundle;)V")
                def onReadyForSpeech(self, params):
                    print("LAIBA_SPEECH: ready for speech", flush=True)

                @java_method("()V")
                def onBeginningOfSpeech(self):
                    print("LAIBA_SPEECH: speech detected", flush=True)
                    Clock.schedule_once(
                        lambda dt: self.bridge.stop_speaking(), 0
                    )

                @java_method("(F)V")
                def onRmsChanged(self, value):
                    pass

                @java_method("([B)V")
                def onBufferReceived(self, buffer):
                    pass

                @java_method("()V")
                def onEndOfSpeech(self):
                    pass

                @java_method("(I)V")
                def onError(self, error):
                    self.bridge.recognition_active = False
                    Clock.schedule_once(lambda dt: self.bridge._tts_state("error"), 0)
                    Clock.schedule_once(
                        lambda dt: self.bridge._restart_listening()
                        if getattr(self.bridge.app, "voice_active", False)
                        and not getattr(self.bridge.app, "voice_muted", True)
                        else None,
                        1.5
                    )
                    names = {
                        1: "NETWORK_TIMEOUT", 2: "NETWORK",
                        3: "AUDIO", 4: "SERVER",
                        5: "CLIENT", 6: "SPEECH_TIMEOUT",
                        7: "NO_MATCH", 8: "RECOGNIZER_BUSY",
                        9: "INSUFFICIENT_PERMISSIONS"
                    }
                    print("LAIBA_SPEECH_ERROR:", error, names.get(error, "UNKNOWN"), flush=True)

                    if error == 8:
                        def recover(dt):
                            try:
                                if self.bridge.speech_recognizer:
                                    self.bridge.speech_recognizer.destroy()
                            except Exception as exc:
                                print("LAIBA_RECOGNIZER_RESET:", exc)
                            self.bridge.speech_recognizer = None
                            self.bridge.recognition_listener = None

                        Clock.schedule_once(recover, 0)

                @java_method("(Landroid/os/Bundle;)V")
                def onResults(self, results):
                    self.bridge.recognition_active = False
                    Clock.schedule_once(lambda dt: self.bridge._tts_state("done"), 0)
                    try:
                        SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
                        matches = results.getStringArrayList(
                            SpeechRecognizer.RESULTS_RECOGNITION
                        )
                        if matches and matches.size() > 0:
                            text = str(matches.get(0))
                            print("LAIBA_SPEECH_RESULT:", text)
                            Clock.schedule_once(
                                lambda dt: self.bridge.app.send_voice_transcript(text), 0
                            )
                    except Exception as exc:
                        print("LAIBA_SPEECH_RESULTS_ERROR:", exc)

                @java_method("(Landroid/os/Bundle;)V")
                def onPartialResults(self, partialResults):
                    pass

                @java_method("(ILjava/lang/String;Landroid/os/Bundle;)V")
                def onEvent(self, eventType, params):
                    pass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
            Intent = autoclass("android.content.Intent")
            RecognizerIntent = autoclass("android.speech.RecognizerIntent")

            activity = PythonActivity.mActivity
            if self.speech_recognizer is None:
                self.speech_recognizer = SpeechRecognizer.createSpeechRecognizer(activity)

            if self.recognition_listener is None:
                self.recognition_listener = Listener(self)

            self.speech_recognizer.setRecognitionListener(self.recognition_listener)

            intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
            )
            intent.putExtra(
                RecognizerIntent.EXTRA_ENABLE_LANGUAGE_SWITCH,
                RecognizerIntent.LANGUAGE_SWITCH_BALANCED
            )
            from java.util import ArrayList
            languages = ArrayList()
            languages.add("ur-PK")
            languages.add("en-US")
            intent.putStringArrayListExtra(
                RecognizerIntent.EXTRA_LANGUAGE_SWITCH_ALLOWED_LANGUAGES,
                languages
            )
            intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)

            if not self.recognition_active:
                self.recognition_active = True
                self.speech_recognizer.startListening(intent)
                print("LAIBA_SPEECH: started listening", flush=True)

        except Exception as exc:
            self.recognition_active = False
            print("LAIBA_SPEECH_INIT_ERROR:", exc)

    def stop_listening(self):
        try:
            self.recognition_active = False
            if self.speech_recognizer:
                self.speech_recognizer.stopListening()
        except Exception as exc:
            print("LAIBA_SPEECH_STOP:", exc)

    def _restart_listening(self):
        if not self.recognition_active:
            self._start_speech()

    def live_camera(self):
        self.message("Live camera stream mode is ready.")

    def _activity_result(self, requestCode, resultCode, intent):
        try:
            from jnius import autoclass
            Activity = autoclass("android.app.Activity")

            if requestCode == self.GALLERY_CODE:
                if resultCode == Activity.RESULT_OK and intent is not None:
                    uri = intent.getData()
                    if uri:
                        self._copy_gallery_uri(uri)
                else:
                    self.message("Gallery selection cancelled.")

            elif requestCode == self.CAMERA_CODE:
                if resultCode == Activity.RESULT_OK:
                    if self.camera_output_uri:
                        self._copy_gallery_uri(self.camera_output_uri)
                else:
                    self.message("Camera capture cancelled.")
        except Exception as exc:
            print("LAIBA_ACTIVITY_RESULT_ERROR:", exc)
