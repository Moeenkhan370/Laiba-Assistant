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
        self.tts_init_failed = False
        self.pending_speech = None
        self.tts_listener = None
        self.tts_progress_listener = None
        self.tts_language = None
        self.speech_recognizer = None
        self.continuous_listening = False
        self.recognition_listener = None
        self.recognition_active = False
        self._android_ui_runnables = []
        self.is_speaking = False
        self.tts_audio_manager = None
        self.tts_audio_attributes = None
        self._tts_last_utterance_id = None
        self._tts_stop_requested = False
        self.init_native_tts()

    def _configure_tts_audio(self):
        """Configure Android TTS for normal media playback."""
        try:
            from jnius import autoclass

            Activity = autoclass("org.kivy.android.PythonActivity")
            AudioManager = autoclass("android.media.AudioManager")
            AudioAttributes = autoclass("android.media.AudioAttributes")
            Builder = autoclass("android.media.AudioAttributes$Builder")

            activity = Activity.mActivity
            manager = activity.getSystemService("audio")

            if manager is None:
                raise RuntimeError("Android AudioManager is unavailable")

            self.tts_audio_manager = manager
            manager.setMode(AudioManager.MODE_NORMAL)

            attributes = (
                Builder()
                .setLegacyStreamType(AudioManager.STREAM_MUSIC)
                .build()
            )

            self.tts_audio_attributes = attributes

            result = self.tts.setAudioAttributes(attributes)
            print(
                "LAIBA_TTS_AUDIO_ATTRIBUTES:",
                result,
                flush=True
            )

            current = int(
                manager.getStreamVolume(AudioManager.STREAM_MUSIC)
            )
            maximum = int(
                manager.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
            )

            print(
                "LAIBA_TTS_MUSIC_VOLUME:",
                current,
                "/",
                maximum,
                flush=True
            )

            if current <= 0:
                print(
                    "LAIBA_TTS_WARNING: media volume is muted",
                    flush=True
                )

            print(
                "LAIBA_TTS_AUDIO_ROUTE: STREAM_MUSIC",
                flush=True
            )
            return True

        except Exception as exc:
            print(
                "LAIBA_TTS_AUDIO_CONFIG_WARNING:",
                repr(exc),
                flush=True
            )
            return False

    @staticmethod
    def _split_tts_text(text, max_chars=3500):
        words = str(text).split()
        chunks = []
        current = ""

        for word in words:
            if len(word) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""

                for offset in range(0, len(word), max_chars):
                    chunks.append(word[offset:offset + max_chars])
                continue

            candidate = (current + " " + word).strip()

            if len(candidate) > max_chars and current:
                chunks.append(current)
                current = word
            else:
                current = candidate

        if current:
            chunks.append(current)

        return chunks

    def init_native_tts(self):
        try:
            from jnius import autoclass, PythonJavaClass, java_method

            bridge = self

            class ProgressCallback(PythonJavaClass):
                __javainterfaces__ = [
                    "com/moeen/laibaassistant/LaibaTtsListener$Callback"
                ]
                __javacontext__ = "app"

                def __init__(self):
                    super().__init__()

                @java_method("(Ljava/lang/String;)V")
                def onStart(self, utterance_id):
                    bridge._queue_tts_event(
                        "start", utterance_id
                    )

                @java_method("(Ljava/lang/String;)V")
                def onDone(self, utterance_id):
                    bridge._queue_tts_event(
                        "done", utterance_id
                    )

                @java_method("(Ljava/lang/String;I)V")
                def onError(self, utterance_id, error_code):
                    bridge._queue_tts_event(
                        "error", utterance_id, error_code
                    )

                @java_method("(Ljava/lang/String;Z)V")
                def onStop(self, utterance_id, interrupted):
                    bridge._queue_tts_event(
                        "stop",
                        utterance_id,
                        0,
                        bool(interrupted)
                    )

            class InitListener(PythonJavaClass):
                __javainterfaces__ = [
                    "android/speech/tts/TextToSpeech$OnInitListener"
                ]
                __javacontext__ = "app"

                def __init__(self):
                    super().__init__()

                @java_method("(I)V")
                def onInit(self, status):
                    try:
                        TTS = autoclass(
                            "android.speech.tts.TextToSpeech"
                        )

                        if status != TTS.SUCCESS:
                            bridge.tts_init_failed = True
                            bridge.pending_speech = None
                            print(
                                "LAIBA_TTS_INIT_FAILED:",
                                status,
                                flush=True
                            )
                            bridge._tts_state("error")
                            return

                        Locale = autoclass("java.util.Locale")

                        language_options = [
                            ("ur-PK", Locale("ur", "PK")),
                            ("device-default", Locale.getDefault()),
                            ("en-US", Locale("en", "US"))
                        ]

                        selected = None

                        for language_name, language_locale in language_options:
                            try:
                                result = bridge.tts.setLanguage(
                                    language_locale
                                )

                                print(
                                    "LAIBA_TTS_LANGUAGE:",
                                    language_name,
                                    result,
                                    flush=True
                                )

                                if result >= TTS.LANG_AVAILABLE:
                                    selected = language_name
                                    break

                            except Exception as language_exc:
                                print(
                                    "LAIBA_TTS_LANGUAGE_ERROR:",
                                    language_name,
                                    repr(language_exc),
                                    flush=True
                                )

                        if selected is None:
                            bridge.tts_ready = False
                            bridge.tts_init_failed = True
                            bridge.pending_speech = None
                            print(
                                "LAIBA_TTS_NO_SUPPORTED_VOICE",
                                flush=True
                            )
                            bridge._tts_state("error")
                            return

                        bridge.tts_language = selected
                        bridge.tts_ready = True
                        bridge.tts_init_failed = False

                        bridge._configure_tts_audio()

                        Helper = autoclass(
                            "com.moeen.laibaassistant.LaibaTtsListener"
                        )

                        bridge.tts_progress_listener = ProgressCallback()

                        attached = Helper.attach(
                            bridge.tts,
                            bridge.tts_progress_listener
                        )

                        if not attached:
                            raise RuntimeError(
                                "Could not attach Android TTS progress listener"
                            )

                        print(
                            "LAIBA_TTS_PROGRESS_LISTENER: READY",
                            flush=True
                        )
                        print(
                            "LAIBA_TTS_READY:",
                            bridge.tts_language,
                            flush=True
                        )

                        try:
                            print(
                                "LAIBA_TTS_ENGINE:",
                                bridge.tts.getDefaultEngine(),
                                flush=True
                            )

                            voice = bridge.tts.getVoice()

                            if voice:
                                print(
                                    "LAIBA_TTS_SELECTED_VOICE:",
                                    str(voice.getName()),
                                    str(voice.getLocale().toLanguageTag()),
                                    flush=True
                                )

                        except Exception as voice_exc:
                            print(
                                "LAIBA_TTS_VOICE_INFO_ERROR:",
                                repr(voice_exc),
                                flush=True
                            )

                        pending = bridge.pending_speech
                        bridge.pending_speech = None

                        if pending:
                            Clock.schedule_once(
                                lambda dt: bridge.speak(pending),
                                0
                            )

                    except Exception as exc:
                        print(
                            "LAIBA_TTS_INIT_ERROR:",
                            repr(exc),
                            flush=True
                        )
                        bridge.tts_ready = False
                        bridge.tts_init_failed = True
                        bridge.pending_speech = None
                        bridge._tts_state("error")

            Activity = autoclass(
                "org.kivy.android.PythonActivity"
            )

            self.tts_listener = InitListener()

            self.tts = autoclass(
                "android.speech.tts.TextToSpeech"
            )(
                Activity.mActivity,
                self.tts_listener
            )

            print(
                "LAIBA_TTS_INITIALIZATION_REQUESTED",
                flush=True
            )

        except Exception as exc:
            print(
                "LAIBA_NATIVE_TTS_ERROR:",
                repr(exc),
                flush=True
            )
            self.tts_ready = False
            self.tts_init_failed = True
            self.pending_speech = None
            self._tts_state("error")

    def _queue_tts_event(
        self,
        event,
        utterance_id="",
        error_code=0,
        interrupted=False
    ):
        try:
            Clock.schedule_once(
                lambda dt: self._handle_tts_event(
                    event,
                    str(utterance_id or ""),
                    int(error_code),
                    bool(interrupted)
                ),
                0
            )
        except Exception as exc:
            print(
                "LAIBA_TTS_CALLBACK_QUEUE_ERROR:",
                repr(exc),
                flush=True
            )

    def _handle_tts_event(
        self,
        event,
        utterance_id,
        error_code=0,
        interrupted=False
    ):
        print(
            "LAIBA_TTS_PROGRESS:",
            event,
            utterance_id,
            error_code,
            interrupted,
            flush=True
        )

        if event == "start":
            return

        if event == "done":
            if utterance_id == self._tts_last_utterance_id:
                self._tts_last_utterance_id = None
                self._tts_stop_requested = False
                self._tts_state("done")
            return

        if event == "error":
            if (
                self.is_speaking
                and utterance_id.startswith("laiba_reply_")
            ):
                self.pending_speech = None
                self._tts_last_utterance_id = None
                self.is_speaking = False

                print(
                    "LAIBA_TTS_PLAYBACK_ERROR:",
                    error_code,
                    utterance_id,
                    flush=True
                )

                self._tts_state("error")
            return

        if event == "stop":
            if (
                interrupted
                and not self._tts_stop_requested
                and self.is_speaking
            ):
                self.pending_speech = None
                self._tts_last_utterance_id = None
                self.is_speaking = False

                print(
                    "LAIBA_TTS_UNEXPECTED_STOP:",
                    utterance_id,
                    flush=True
                )

                self._tts_state("error")

    def stop_speaking(self):
        self.pending_speech = None
        self._tts_stop_requested = True
        self._tts_last_utterance_id = None
        self.is_speaking = False

        try:
            if self.tts:
                self.tts.stop()
        except Exception as exc:
            print(
                "LAIBA_TTS_STOP_ERROR:",
                repr(exc),
                flush=True
            )

        self._tts_state("stopped")

    def speak(self, text):
        self._speak_native(str(text))

    def _speak_native(self, text):
        try:
            from jnius import autoclass

            text = str(text).strip()

            if not text:
                return

            if not self.tts or not self.tts_ready:
                if self.tts_init_failed:
                    self.pending_speech = None
                    print(
                        "LAIBA_TTS_UNAVAILABLE: initialization failed",
                        flush=True
                    )
                    self._tts_state("error")
                    return

                self.pending_speech = text

                print(
                    "LAIBA_TTS_PENDING: waiting for Android TTS",
                    flush=True
                )
                return

            TTS = autoclass(
                "android.speech.tts.TextToSpeech"
            )
            AudioManager = autoclass(
                "android.media.AudioManager"
            )
            Bundle = autoclass("android.os.Bundle")

            if self.tts_audio_manager is not None:
                try:
                    self.tts_audio_manager.setMode(
                        AudioManager.MODE_NORMAL
                    )
                except Exception as audio_exc:
                    print(
                        "LAIBA_TTS_ROUTE_WARNING:",
                        repr(audio_exc),
                        flush=True
                    )

            chunks = self._split_tts_text(text, 3500)

            if not chunks:
                return

            self._tts_stop_requested = False
            self._tts_last_utterance_id = (
                "laiba_reply_" + str(len(chunks) - 1)
            )

            self.is_speaking = True
            self._tts_state("speaking")

            print(
                "LAIBA_TTS_SPEAK_REQUEST:",
                "characters=", len(text),
                "chunks=", len(chunks),
                "language=", self.tts_language,
                "stream=STREAM_MUSIC",
                flush=True
            )

            for index, chunk in enumerate(chunks):
                params = Bundle()
                params.putInt(
                    "streamType",
                    AudioManager.STREAM_MUSIC
                )
                params.putFloat("volume", 1.0)

                queue_mode = (
                    TTS.QUEUE_FLUSH
                    if index == 0
                    else TTS.QUEUE_ADD
                )

                utterance_id = "laiba_reply_" + str(index)

                result = self.tts.speak(
                    chunk,
                    queue_mode,
                    params,
                    utterance_id
                )

                print(
                    "LAIBA_TTS_CHUNK_RESULT:",
                    index + 1,
                    "/",
                    len(chunks),
                    result,
                    flush=True
                )

                if result == TTS.ERROR:
                    self.pending_speech = None
                    self._tts_last_utterance_id = None
                    self.is_speaking = False

                    try:
                        self.tts.stop()
                    except Exception:
                        pass

                    print(
                        "LAIBA_TTS_SPEAK_ERROR: Android returned ERROR",
                        flush=True
                    )

                    self._tts_state("error")
                    return

            print(
                "LAIBA_TTS_QUEUE_SUBMITTED",
                flush=True
            )

        except Exception as exc:
            self.pending_speech = None
            self._tts_last_utterance_id = None
            self.is_speaking = False

            print(
                "LAIBA_NATIVE_TTS_ERROR:",
                repr(exc),
                flush=True
            )

            self._tts_state("error")

    def _tts_state(self, state):
        print(
            "LAIBA_TTS_STATE:",
            state,
            flush=True
        )

        self.is_speaking = (state == "speaking")

        callback = getattr(
            self.app,
            "on_tts_state",
            None
        )

        if callback:
            Clock.schedule_once(
                lambda dt: callback(state),
                0
            )

    def shutdown(self):
        self.pending_speech = None
        self.is_speaking = False
        self.recognition_active = False

        def destroy_recognizer():
            try:
                if self.speech_recognizer:
                    self.speech_recognizer.cancel()
                    self.speech_recognizer.destroy()
            except Exception as exc:
                print("LAIBA_RECOGNIZER_SHUTDOWN:", repr(exc), flush=True)
            finally:
                self.speech_recognizer = None
                self.recognition_listener = None

        try:
            self._run_on_android_ui_thread(destroy_recognizer)
        except Exception as exc:
            print("LAIBA_RECOGNIZER_SHUTDOWN_QUEUE:", repr(exc), flush=True)

        try:
            if self.tts:
                self.tts.stop()
                self.tts.shutdown()
        except Exception as exc:
            print("LAIBA_TTS_SHUTDOWN:", repr(exc), flush=True)
        finally:
            self.tts = None
            self.tts_ready = False
            self.tts_listener = None
            self.tts_progress_listener = None

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
                        self._voice_state(
                            "error", "Microphone permission denied: " + details
                        )
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
            self._voice_state("error", "Android permission error: " + str(exc))
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

    def _voice_state(self, state, detail=""):
        print(
            "LAIBA_VOICE_STATE:", state, str(detail), flush=True
        )
        callback = getattr(self.app, "on_voice_bridge_state", None)
        if callable(callback):
            Clock.schedule_once(
                lambda dt: callback(state, str(detail)), 0
            )

    def _run_on_android_ui_thread(self, callback):
        from jnius import autoclass, PythonJavaClass, java_method

        bridge = self

        class UiRunnable(PythonJavaClass):
            __javainterfaces__ = ["java/lang/Runnable"]
            __javacontext__ = "app"

            def __init__(self):
                super().__init__()

            @java_method("()V")
            def run(self):
                try:
                    callback()
                except Exception as exc:
                    print("LAIBA_ANDROID_UI_ERROR:", repr(exc), flush=True)
                finally:
                    try:
                        bridge._android_ui_runnables.remove(self)
                    except ValueError:
                        pass

        runnable = UiRunnable()
        self._android_ui_runnables.append(runnable)
        try:
            Activity = autoclass("org.kivy.android.PythonActivity")
            Activity.mActivity.runOnUiThread(runnable)
        except Exception:
            self._android_ui_runnables.remove(runnable)
            raise

    def microphone(self):
        print("LAIBA_MIC_BUTTON: pressed", flush=True)
        self._voice_state("permission", "Requesting microphone permission...")
        self.permissions(
            ["android.permission.RECORD_AUDIO"],
            self._start_speech
        )

    def _start_speech(self):
        app = self.app
        if getattr(app, "voice_active", False):
            if (
                getattr(app, "voice_muted", True)
                or getattr(app, "voice_processing", False)
                or self.is_speaking
            ):
                return
        try:
            self._run_on_android_ui_thread(
                self._init_and_listen_ui_thread
            )
        except Exception as exc:
            self._voice_state("error", "Android UI thread error: " + str(exc))

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
                    self.bridge._voice_state(
                        "ready", "Microphone is ready. Speak now."
                    )

                @java_method("()V")
                def onBeginningOfSpeech(self):
                    print("LAIBA_SPEECH: speech detected", flush=True)
                    self.bridge._voice_state(
                        "hearing", "I can hear you. Processing your speech..."
                    )
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
                    bridge = self.bridge
                    bridge.recognition_active = False

                    names = {
                        1: "NETWORK_TIMEOUT", 2: "NETWORK",
                        3: "AUDIO", 4: "SERVER",
                        5: "CLIENT", 6: "SPEECH_TIMEOUT",
                        7: "NO_MATCH", 8: "RECOGNIZER_BUSY",
                        9: "INSUFFICIENT_PERMISSIONS"
                    }
                    print(
                        "LAIBA_SPEECH_ERROR:",
                        error, names.get(error, "UNKNOWN"), flush=True
                    )

                    if error == 9:
                        bridge._voice_state(
                            "error",
                            "Microphone permission is missing. Allow microphone access in Android settings."
                        )
                        return

                    if error in (6, 7):
                        bridge._voice_state(
                            "no_match",
                            "No speech was detected. Please speak clearly."
                        )
                    else:
                        bridge._voice_state(
                            "retrying",
                            "Speech recognition error: " +
                            names.get(error, "UNKNOWN")
                        )

                    if error == 8:
                        def recover(dt):
                            def reset_recognizer():
                                try:
                                    if bridge.speech_recognizer:
                                        bridge.speech_recognizer.cancel()
                                        bridge.speech_recognizer.destroy()
                                except Exception as exc:
                                    print("LAIBA_RECOGNIZER_RESET:", repr(exc), flush=True)
                                finally:
                                    bridge.speech_recognizer = None
                                    bridge.recognition_listener = None

                            bridge._run_on_android_ui_thread(reset_recognizer)
                            Clock.schedule_once(
                                lambda dt: bridge._restart_listening(),
                                0.8
                            )

                        Clock.schedule_once(recover, 0.3)
                    else:
                        delay = 0.8 if error in (6, 7) else 1.5
                        Clock.schedule_once(
                            lambda dt: bridge._restart_listening(),
                            delay
                        )

                @java_method("(Landroid/os/Bundle;)V")
                def onResults(self, results):
                    self.bridge.recognition_active = False
                    try:
                        SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
                        matches = results.getStringArrayList(
                            SpeechRecognizer.RESULTS_RECOGNITION
                        )
                        if matches and matches.size() > 0:
                            text = str(matches.get(0)).strip()
                            print("LAIBA_SPEECH_RESULT:", text, flush=True)
                            if text:
                                self.bridge._voice_state(
                                    "processing", "Speech recognized. Preparing reply..."
                                )
                                Clock.schedule_once(
                                    lambda dt: self.bridge.app.send_voice_transcript(text), 0
                                )
                            else:
                                self.bridge._voice_state(
                                    "no_match", "No speech text was returned. Please try again."
                                )
                                Clock.schedule_once(
                                    lambda dt: self.bridge._restart_listening(), 0.7
                                )
                        else:
                            self.bridge._voice_state(
                                "no_match", "Speech was not recognized. Please try again."
                            )
                            Clock.schedule_once(
                                lambda dt: self.bridge._restart_listening(), 0.7
                            )
                    except Exception as exc:
                        print("LAIBA_SPEECH_RESULTS_ERROR:", exc)
                        Clock.schedule_once(
                            lambda dt: self.bridge._restart_listening(), 0.7
                        )

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
            self._voice_state("starting", "Starting Android speech recognition...")

            if not SpeechRecognizer.isRecognitionAvailable(activity):
                raise RuntimeError(
                    "No Android speech recognition service is installed or enabled."
                )

            if self.speech_recognizer is None:
                self.speech_recognizer = SpeechRecognizer.createSpeechRecognizer(activity)

            if self.speech_recognizer is None:
                raise RuntimeError(
                    "Android could not create the speech recognizer."
                )

            if self.recognition_listener is None:
                self.recognition_listener = Listener(self)

            self.speech_recognizer.setRecognitionListener(self.recognition_listener)

            intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
            )
            intent.putExtra(
                RecognizerIntent.EXTRA_LANGUAGE,
                "ur-PK"
            )
            intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)

            if not self.recognition_active:
                self.recognition_active = True
                self.speech_recognizer.startListening(intent)
                print("LAIBA_SPEECH: started listening", flush=True)

        except Exception as exc:
            self.recognition_active = False
            print("LAIBA_SPEECH_INIT_ERROR:", repr(exc), flush=True)
            self._voice_state(
                "error", "Speech recognizer could not start: " + str(exc)
            )

    def stop_listening(self):
        self.recognition_active = False

        def stop():
            if self.speech_recognizer:
                self.speech_recognizer.stopListening()

        try:
            self._run_on_android_ui_thread(stop)
        except Exception as exc:
            print("LAIBA_SPEECH_STOP:", repr(exc), flush=True)

    def _restart_listening(self):
        app = self.app
        if (
            getattr(app, "voice_active", False)
            and not getattr(app, "voice_muted", True)
            and not getattr(app, "voice_processing", False)
            and not self.is_speaking
            and not getattr(self, "pending_speech", None)
            and not self.recognition_active
        ):
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
