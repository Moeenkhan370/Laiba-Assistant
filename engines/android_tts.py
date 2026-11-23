"""Python-controlled Android Native TextToSpeech engine."""

from kivy.clock import Clock
from kivy.utils import platform
from engines.runtime_diagnostics import get_diagnostics


class AndroidNativeTTS:

    def __init__(self, state_callback):
        self.state_callback = state_callback
        self.diagnostics = get_diagnostics()
        self.tts = None
        self.ready = False
        self.failed = False
        self.pending_speech = None
        self.init_listener = None
        self.completion_listener = None
        self.last_utterance_id = None
        self.completion_waits = 0
        self.counter = 0

        self._initialize()

    def _state(self, state):
        if self.diagnostics and state == "error":
            self.diagnostics.record(
                "tts", "Native TTS state error", severity="ERROR"
            )
        try:
            self.state_callback(state)
        except Exception as exc:
            print("LAIBA_PY_TTS_STATE_ERROR:", repr(exc), flush=True)

    @staticmethod
    def _split_text(text, max_chars=3500):
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

    def _initialize(self):
        if platform != "android":
            self.failed = True
            print("LAIBA_PY_TTS: Android platform required.", flush=True)
            return

        try:
            from jnius import autoclass, PythonJavaClass, java_method

            engine = self

            class InitListener(PythonJavaClass):
                __javainterfaces__ = [
                    "android/speech/tts/TextToSpeech$OnInitListener"
                ]
                __javacontext__ = "app"

                def __init__(self):
                    super().__init__()

                @java_method("(I)V")
                def onInit(self, status):
                    # Wait until the TextToSpeech constructor has returned.
                    Clock.schedule_once(
                        lambda dt: engine._finish_initialization(status), 0
                    )

            class CompletionListener(PythonJavaClass):
                __javainterfaces__ = [
                    "android/speech/tts/TextToSpeech$OnUtteranceCompletedListener"
                ]
                __javacontext__ = "app"

                def __init__(self):
                    super().__init__()

                @java_method("(Ljava/lang/String;)V")
                def onUtteranceCompleted(self, utterance_id):
                    engine._queue_completion(str(utterance_id or ""))

            Activity = autoclass("org.kivy.android.PythonActivity")
            TTS = autoclass("android.speech.tts.TextToSpeech")

            self.init_listener = InitListener()
            self.tts = TTS(Activity.mActivity, self.init_listener)

            self._completion_class = CompletionListener

            print("LAIBA_PY_TTS_INITIALIZATION_REQUESTED", flush=True)

        except Exception as exc:
            self.failed = True
            if self.diagnostics:
                self.diagnostics.record_exception(
                    "tts", "Native TTS initialization failed", exc
                )
            print("LAIBA_PY_TTS_INIT_ERROR:", repr(exc), flush=True)
            self._state("error")

    def _finish_initialization(self, status):
        try:
            from jnius import autoclass

            TTS = autoclass("android.speech.tts.TextToSpeech")
            print("LAIBA_TTS_INIT_STATUS:", status, flush=True)
            try:
                print("LAIBA_TTS_ENGINE:", self.tts.getDefaultEngine(), flush=True)
            except Exception as engine_exc:
                print("LAIBA_TTS_ENGINE_INFO_ERROR:", repr(engine_exc), flush=True)

            if status != TTS.SUCCESS or self.tts is None:
                raise RuntimeError(
                    "Android TextToSpeech initialization failed: "
                    + str(status)
                )

            Locale = autoclass("java.util.Locale")

            # Prefer the tested Urdu-Pakistan voice.
            locales = [
                Locale("ur", "PK"),
                Locale("ur"),
                Locale.getDefault()
            ]

            language_set = False

            for locale in locales:
                availability = self.tts.isLanguageAvailable(locale)
                print(
                    "LAIBA_TTS_LOCALE_CHECK:",
                    str(locale), "availability=", availability,
                    flush=True
                )

                if availability >= TTS.LANG_AVAILABLE:
                    result = self.tts.setLanguage(locale)

                    if result >= TTS.LANG_AVAILABLE:
                        language_set = True
                        print(
                            "LAIBA_PY_TTS_LANGUAGE:",
                            str(locale),
                            "setLanguage_result=", result,
                            flush=True
                        )
                        try:
                            voice = self.tts.getVoice()
                            if voice:
                                print(
                                    "LAIBA_TTS_SELECTED_VOICE:",
                                    str(voice.getName()),
                                    str(voice.getLocale()),
                                    flush=True
                                )
                        except Exception as voice_exc:
                            print("LAIBA_TTS_VOICE_INFO_ERROR:", repr(voice_exc), flush=True)
                        break

            if not language_set:
                raise RuntimeError(
                    "No supported Android TTS language was found."
                )

            # Route speech through the normal media audio path.
            try:
                AudioAttributes = autoclass(
                    "android.media.AudioAttributes"
                )
                Builder = autoclass(
                    "android.media.AudioAttributes$Builder"
                )

                builder = Builder()
                builder.setUsage(AudioAttributes.USAGE_MEDIA)
                builder.setContentType(
                    AudioAttributes.CONTENT_TYPE_SPEECH
                )

                audio_result = self.tts.setAudioAttributes(
                    builder.build()
                )
                print("LAIBA_TTS_AUDIO_ATTRIBUTES_RESULT:", audio_result, flush=True)
                try:
                    Activity = autoclass("org.kivy.android.PythonActivity")
                    AudioManager = autoclass("android.media.AudioManager")
                    manager = Activity.mActivity.getSystemService("audio")
                    print(
                        "LAIBA_TTS_MEDIA_VOLUME:",
                        int(manager.getStreamVolume(AudioManager.STREAM_MUSIC)),
                        "/",
                        int(manager.getStreamMaxVolume(AudioManager.STREAM_MUSIC)),
                        flush=True
                    )
                except Exception as volume_exc:
                    print("LAIBA_TTS_VOLUME_INFO_ERROR:", repr(volume_exc), flush=True)

                if audio_result != TTS.SUCCESS:
                    print(
                        "LAIBA_PY_TTS_AUDIO_ATTRIBUTES_WARNING:",
                        audio_result,
                        flush=True
                    )

            except Exception as audio_exc:
                print(
                    "LAIBA_PY_TTS_AUDIO_ROUTE_WARNING:",
                    repr(audio_exc),
                    flush=True
                )

            self.completion_listener = self._completion_class()

            listener_result = self.tts.setOnUtteranceCompletedListener(
                self.completion_listener
            )

            if listener_result == TTS.ERROR:
                raise RuntimeError(
                    "Android TTS completion listener could not attach."
                )

            self.ready = True
            self.failed = False

            print("LAIBA_PY_TTS_READY", flush=True)

            pending = self.pending_speech
            self.pending_speech = None

            if pending:
                Clock.schedule_once(
                    lambda dt: self.speak(pending), 0
                )

        except Exception as exc:
            self.ready = False
            self.failed = True
            self.pending_speech = None
            if self.diagnostics:
                self.diagnostics.record_exception(
                    "tts", "Native TTS setup failed", exc
                )

            print(
                "LAIBA_PY_TTS_SETUP_ERROR:",
                repr(exc),
                flush=True
            )

            self._state("error")

    def speak(self, text):
        text = str(text or "").strip()

        if not text:
            return

        if not self.tts or not self.ready:
            if self.failed:
                self.pending_speech = None
                self._state("error")
            else:
                self.pending_speech = text
                print("LAIBA_PY_TTS_WAITING_FOR_INIT", flush=True)
            return

        try:
            from jnius import autoclass

            TTS = autoclass("android.speech.tts.TextToSpeech")
            chunks = self._split_text(text)

            if not chunks:
                return

            self.counter += 1
            prefix = "laiba_python_" + str(self.counter)

            self.last_utterance_id = (
                prefix + "_" + str(len(chunks) - 1)
            )
            self.completion_waits = 0

            self._state("speaking")

            for index, chunk in enumerate(chunks):
                utterance_id = prefix + "_" + str(index)

                queue_mode = (
                    TTS.QUEUE_FLUSH
                    if index == 0
                    else TTS.QUEUE_ADD
                )

                result = self.tts.speak(
                    chunk,
                    queue_mode,
                    None,
                    utterance_id
                )

                print(
                    "LAIBA_TTS_SPEAK_RESULT:",
                    utterance_id,
                    "result=", result,
                    "characters=", len(chunk),
                    flush=True
                )
                if result != TTS.SUCCESS:
                    raise RuntimeError(
                        "Android TTS speak() returned: " + str(result)
                    )

            print(
                "LAIBA_PY_TTS_QUEUED:",
                len(chunks),
                "chunk(s)",
                flush=True
            )

        except Exception as exc:
            if self.diagnostics:
                self.diagnostics.record_exception(
                    "tts", "Native TTS speak failed", exc
                )
            print("LAIBA_PY_TTS_SPEAK_ERROR:", repr(exc), flush=True)
            self._fail()

    def _queue_completion(self, utterance_id):
        print("LAIBA_TTS_COMPLETION_CALLBACK:", utterance_id, flush=True)
        try:
            Clock.schedule_once(
                lambda dt: self._handle_completion(utterance_id), 0
            )
        except Exception as exc:
            print("LAIBA_PY_TTS_CALLBACK_ERROR:", repr(exc), flush=True)

    def _handle_completion(self, utterance_id):
        if utterance_id != self.last_utterance_id:
            return

        self.completion_waits = 0
        self._wait_until_idle(utterance_id)

    def _wait_until_idle(self, utterance_id):
        if utterance_id != self.last_utterance_id:
            return

        try:
            if self.tts and self.tts.isSpeaking():
                self.completion_waits += 1

                if self.completion_waits > 40:
                    raise RuntimeError(
                        "Android TTS did not become idle after completion."
                    )

                Clock.schedule_once(
                    lambda dt: self._wait_until_idle(utterance_id),
                    0.25
                )
                return

            # Allow the final audio buffer to reach the output path.
            Clock.schedule_once(
                lambda dt: self._finish_done(utterance_id),
                0.7
            )

        except Exception as exc:
            print("LAIBA_PY_TTS_COMPLETION_ERROR:", repr(exc), flush=True)
            self._fail()

    def _finish_done(self, utterance_id):
        if utterance_id != self.last_utterance_id:
            return

        self.last_utterance_id = None
        self._state("done")
        print("LAIBA_PY_TTS_DONE", flush=True)

    def _fail(self):
        self.last_utterance_id = None
        self.pending_speech = None

        try:
            if self.tts:
                self.tts.stop()
        except Exception:
            pass

        self._state("error")

    def stop(self):
        self.pending_speech = None
        self.last_utterance_id = None

        try:
            if self.tts:
                self.tts.stop()
        except Exception as exc:
            print("LAIBA_PY_TTS_STOP_ERROR:", repr(exc), flush=True)

        self._state("stopped")

    def shutdown(self):
        self.pending_speech = None
        self.last_utterance_id = None
        self.ready = False

        try:
            if self.tts:
                self.tts.stop()
                self.tts.shutdown()
        except Exception as exc:
            print("LAIBA_PY_TTS_SHUTDOWN_ERROR:", repr(exc), flush=True)
        finally:
            self.tts = None
            self.init_listener = None
            self.completion_listener = None
            self._completion_class = None
