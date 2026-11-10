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
            if self.tts:
                self.tts.stop()
        except Exception as exc:
            print("LAIBA_TTS_STOP:", exc)

    def speak(self, text):
        try:
            from jnius import autoclass
            self.is_speaking = True

            if not self.tts or not self.tts_ready:
                print("LAIBA_TTS_NOT_READY")
                Clock.schedule_once(
                    lambda dt: self._tts_state("error"), 0
                )
                return

            TTS = autoclass("android.speech.tts.TextToSpeech")
            result = self.tts.speak(
                str(text), TTS.QUEUE_FLUSH, None, "laiba_reply"
            )

            if result == TTS.ERROR:
                Clock.schedule_once(
                    lambda dt: self._tts_state("error"), 0
                )

        except Exception as exc:
            print("LAIBA_TTS_SPEAK_ERROR:", exc)
            Clock.schedule_once(
                lambda dt: self._tts_state("error"), 0
            )

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
                        "Permission callback error: " + str(