from kivy.utils import platform
import os
import base64
import wave
from threading import Thread
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.label import Label
from engines.android_tts import AndroidNativeTTS
from engines.runtime_diagnostics import get_diagnostics

ANDROID_SPEECH_RECOGNIZER_CLASS = "android.speech.SpeechRecognizer"
ANDROID_RECOGNIZER_INTENT_CLASS = "android.speech.RecognizerIntent"


class _TTSInitListener:
    pass


class AndroidMediaBridge:
    SPEECH_CODE = 7312
    VIDEO_CODE = 7313

    def __init__(self, app):
        self.app = app
        self.diagnostics = get_diagnostics()
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
        self._tts_original_text = None
        self._tts_fallback_attempted = False
        self.init_native_tts()

    @staticmethod
    def _split_tts_text(text, max_chars=3500):
        words = str(text).split()
        chunks = []
        current = ""

        for word in words:
            while len(word) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(word[:max_chars])
                word = word[max_chars:]

            candidate = (current + " " + word).strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = word
            else:
                current = candidate

        if current:
            chunks.append(current)

        return chunks

    def init_native_tts(self):
        try:
            self.native_tts = AndroidNativeTTS(self._tts_state)
        except Exception as exc:
            self.native_tts = None
            print("LAIBA_PY_TTS_BRIDGE_ERROR:", repr(exc), flush=True)
            self._tts_state("error")

    def speak(self, text):
        text = str(text or "").strip()
        if not text:
            return

        if not self.native_tts:
            self._tts_state("error")
            return

        self.native_tts.speak(text)

    def speak_voice_reply(self, text):
        """Use Gemini 2.5 Flash Preview TTS only for two-way voice replies."""
        text = str(text or "").strip()
        if not text:
            return

        self._gemini_tts_generation = getattr(
            self, "_gemini_tts_generation", 0
        ) + 1
        generation = self._gemini_tts_generation

        chatbot = getattr(self.app, "chatbot", None)
        keys = []
        if chatbot:
            keys.extend(getattr(chatbot, "api_keys", []) or [])
            keys.insert(0, getattr(chatbot, "api_key", ""))

        keys = list(dict.fromkeys(
            str(key).strip() for key in keys if str(key).strip()
        ))

        if not keys:
            print("LAIBA_GEMINI_TTS_FALLBACK: No API key", flush=True)
            self.speak(text)
            return

        def worker():
            import requests
            import re

            model = "gemini-3.8-flash-lite-tts"
            url = (
                "https://generativelanguage.googleapis.com/v1beta/"
                "models/" + model + ":generateContent"
            )
            payload = {
                "contents": [{
                    "parts": [{"text": text}]
                }],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": "Kore"
                            }
                        }
                    }
                }
            }

            last_error = "No configured API key worked."

            for key in keys:
                try:
                    response = requests.post(
                        url,
                        params={"key": key},
                        json=payload,
                        timeout=60
                    )

                    if not response.ok:
                        last_error = "HTTP {}".format(response.status_code)
                        print(
                            "LAIBA_GEMINI_TTS_MODEL_ERROR:",
                            last_error, flush=True
                        )
                        response.close()
                        continue

                    data = response.json()
                    response.close()

                    candidates = data.get("candidates") or []
                    parts = (
                        candidates[0].get("content", {}).get("parts", [])
                        if candidates else []
                    )
                    inline = next(
                        (
                            part.get("inlineData") or part.get("inline_data")
                            for part in parts
                            if part.get("inlineData") or part.get("inline_data")
                        ),
                        None
                    )

                    if not inline or not inline.get("data"):
                        last_error = "Gemini returned no audio data."
                        continue

                    audio_bytes = base64.b64decode(
                        inline["data"], validate=True
                    )
                    mime = str(
                        inline.get("mimeType") or
                        inline.get("mime_type") or ""
                    )

                    sample_rate = 24000

                    if not audio_bytes:
                        last_error = "Gemini returned empty audio."
                        continue

                    os.makedirs(self.app.user_data_dir, exist_ok=True)
                    path = os.path.join(
                        self.app.user_data_dir,
                        "laiba_gemini_tts_{}.wav".format(
                            __import__("time").time_ns()
                        )
                    )

                    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
                        with open(path, "wb") as output:
                            output.write(audio_bytes)
                    else:
                        rate_match = re.search(r"rate=(\d+)", mime)
                        sample_rate = int(rate_match.group(1)) if rate_match else 24000
                        with wave.open(path, "wb") as output:
                            output.setnchannels(1)
                            output.setsampwidth(2)
                            output.setframerate(sample_rate)
                            output.writeframes(audio_bytes)

                    print(
                        "LAIBA_GEMINI_TTS_GENERATION: PASS",
                        "model=", model,
                        "bytes=", len(audio_bytes),
                        "rate=", sample_rate,
                        flush=True
                    )
                    Clock.schedule_once(
                        lambda dt: self._play_gemini_tts_audio(
                            path, text, generation
                        ), 0
                    )
                    return

                except Exception as exc:
                    last_error = type(exc).__name__ + ": " + str(exc)[:180]
                    print(
                        "LAIBA_GEMINI_TTS_REQUEST_ERROR:",
                        last_error, flush=True
                    )

            print(
                "LAIBA_GEMINI_TTS_FALLBACK_TO_ANDROID_NATIVE:",
                last_error, flush=True
            )
            if self.diagnostics:
                self.diagnostics.record(
                    "tts", "Gemini TTS unavailable; Android Native TTS fallback",
                    last_error, severity="WARNING"
                )
            Clock.schedule_once(
                lambda dt: self._fallback_voice_reply(
                    text, generation
                ), 0
            )

        Thread(target=worker, daemon=True).start()

    def _fallback_voice_reply(self, text, generation):
        if generation != getattr(self, "_gemini_tts_generation", 0):
            return
        self.speak(text)

    def _play_gemini_tts_audio(self, path, text, generation):
        if generation != getattr(self, "_gemini_tts_generation", 0):
            try:
                os.remove(path)
            except OSError:
                pass
            return

        player = None

        try:
            from jnius import autoclass, PythonJavaClass, java_method

            MediaPlayer = autoclass("android.media.MediaPlayer")
            bridge = self

            class CompletionListener(PythonJavaClass):
                __javainterfaces__ = [
                    "android/media/MediaPlayer$OnCompletionListener"
                ]
                __javacontext__ = "app"

                def __init__(self):
                    super().__init__()

                @java_method("(Landroid/media/MediaPlayer;)V")
                def onCompletion(self, mp):
                    Clock.schedule_once(
                        lambda dt: bridge._finish_gemini_tts(
                            path, generation, mp
                        ), 0
                    )

            class ErrorListener(PythonJavaClass):
                __javainterfaces__ = [
                    "android/media/MediaPlayer$OnErrorListener"
                ]
                __javacontext__ = "app"

                def __init__(self):
                    super().__init__()

                @java_method("(Landroid/media/MediaPlayer;II)Z")
                def onError(self, mp, what, extra):
                    print(
                        "LAIBA_GEMINI_TTS_MEDIA_ERROR:",
                        what, extra, flush=True
                    )
                    Clock.schedule_once(
                        lambda dt: bridge._gemini_tts_playback_failed(
                            path, text, generation, mp
                        ), 0
                    )
                    return True

            player = MediaPlayer()
            player.setAudioStreamType(3)
            player.setDataSource(path)

            self._gemini_tts_completion_listener = CompletionListener()
            self._gemini_tts_error_listener = ErrorListener()

            player.setOnCompletionListener(
                self._gemini_tts_completion_listener
            )
            player.setOnErrorListener(
                self._gemini_tts_error_listener
            )

            player.prepare()

            if generation != getattr(
                self, "_gemini_tts_generation", 0
            ):
                player.release()
                return

            self._gemini_tts_player = player
            self.is_speaking = True
            self._tts_state("speaking")
            player.start()

            print(
                "LAIBA_GEMINI_TTS_PLAYBACK_STARTED",
                "backend=Android MediaPlayer",
                flush=True
            )

        except Exception as exc:
            print(
                "LAIBA_GEMINI_TTS_PLAYBACK_ERROR:",
                repr(exc), flush=True
            )
            if player:
                try:
                    player.release()
                except Exception:
                    pass

            self._gemini_tts_player = None
            self._gemini_tts_completion_listener = None
            self._gemini_tts_error_listener = None

            try:
                os.remove(path)
            except OSError:
                pass

            self._fallback_voice_reply(text, generation)

    def _finish_gemini_tts(self, path, generation, player):
        if generation != getattr(self, "_gemini_tts_generation", 0):
            return

        if player is not getattr(self, "_gemini_tts_player", None):
            return

        self._gemini_tts_player = None

        try:
            player.release()
        except Exception:
            pass

        self._gemini_tts_completion_listener = None
        self._gemini_tts_error_listener = None

        try:
            os.remove(path)
        except OSError:
            pass

        self.is_speaking = False
        print("LAIBA_GEMINI_TTS_PLAYBACK_DONE", flush=True)
        self._tts_state("done")

    def _gemini_tts_playback_failed(
        self, path, text, generation, player
    ):
        if generation != getattr(self, "_gemini_tts_generation", 0):
            return

        if player is not getattr(self, "_gemini_tts_player", None):
            return

        self._gemini_tts_player = None

        try:
            player.release()
        except Exception:
            pass

        self._gemini_tts_completion_listener = None
        self._gemini_tts_error_listener = None

        try:
            os.remove(path)
        except OSError:
            pass

        print(
            "LAIBA_GEMINI_TTS_FALLBACK_TO_ANDROID_NATIVE",
            flush=True
        )
        self._fallback_voice_reply(text, generation)

    def stop_speaking(self):
        self._gemini_tts_generation = getattr(
            self, "_gemini_tts_generation", 0
        ) + 1

        player = getattr(self, "_gemini_tts_player", None)
        self._gemini_tts_player = None

        if player:
            try:
                player.stop()
            except Exception:
                pass
            try:
                player.release()
            except Exception:
                pass

        self._gemini_tts_completion_listener = None
        self._gemini_tts_error_listener = None

        try:
            if self.native_tts:
                self.native_tts.stop()
            else:
                self._tts_state("stopped")
        except Exception as exc:
            print(
                "LAIBA_PY_TTS_STOP_ERROR:",
                repr(exc), flush=True
            )
            self._tts_state("error")

    def _tts_state(self, state):
        self.is_speaking = (state == "speaking")
        print("LAIBA_TTS_STATE:", state, flush=True)

        callback = getattr(self.app, "on_tts_state", None)
        if callable(callback):
            Clock.schedule_once(
                lambda dt: callback(state), 0
            )

    def install_apk(self, apk_path):
        if platform != "android":
            self.message("APK installation is available on Android only.")
            return False
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Installer = autoclass(
                "com.moeen.laibaassistant.LaibaPackageInstaller"
            )
            activity = PythonActivity.mActivity
            path = str(apk_path)
            def launch():
                try:
                    Installer.install(activity, path)
                except Exception as exc:
                    self.message("APK installation failed: " + str(exc))
            self._run_on_android_ui_thread(launch)
            return True
        except Exception as exc:
            self.message("Installer unavailable: " + str(exc))
            return False

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
            if self.native_tts:
                self.native_tts.shutdown()
        except Exception as exc:
            print("LAIBA_PY_TTS_SHUTDOWN:", repr(exc), flush=True)
        finally:
            self.native_tts = None

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
                    if self.diagnostics:
                        self.diagnostics.record_exception(
                            "permission", "Permission callback failed", exc
                        )
                    self.message(
                        "Permission callback error: " + str(exc)
                    )
            print("LAIBA_MIC_PERMISSION: requesting", names, flush=True)
            request_permissions(names, result)
        except Exception as exc:
            if self.diagnostics:
                self.diagnostics.record_exception(
                    "permission", "Android permission request failed", exc
                )
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
        if self.diagnostics and state in ("error", "retrying", "no_match"):
            self.diagnostics.record(
                "speech", state, detail,
                severity="ERROR" if state == "error" else "WARNING"
            )
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
                    if bridge.diagnostics:
                        bridge.diagnostics.record_exception(
                            "android_callback", "UI thread callback failed", exc
                        )
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

                    if error in (5, 8):
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
                        SpeechRecognizer = autoclass(ANDROID_SPEECH_RECOGNIZER_CLASS)
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
            SpeechRecognizer = autoclass(ANDROID_SPEECH_RECOGNIZER_CLASS)
            Intent = autoclass("android.content.Intent")
            RecognizerIntent = autoclass(ANDROID_RECOGNIZER_INTENT_CLASS)

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
            and not (self.native_tts and self.native_tts.pending_speech)
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
