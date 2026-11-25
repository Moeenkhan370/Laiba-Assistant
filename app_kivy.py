"""
Laiba Project - Kivy / Termux Buildozer APK Compatibility Application
Allows compiling Laiba project into an Android APK using Buildozer in Termux.
Includes a Kivy UI, lightweight mesh preview, and Gemini text/image request engine. Voice/camera services require separate Android bridges.
"""

import os
import sys
import config as app_config
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Rectangle, Line, Ellipse
from kivy.core.window import Window
from kivy.core.clipboard import Clipboard

from config import CURRENT_CONFIG
from engines.chatbot_engine import ChatbotEngine
from engines.github_client import GitHubClient
from engines.threed_engine import ThreeDEngine
from android_media import AndroidMediaBridge
from engines.self_update import SelfUpdateEngine
from engines.runtime_diagnostics import configure_diagnostics

# Set Window dark background
Window.clearcolor = (0, 0, 0, 1)
Window.softinput_mode = 'below_target'



from threading import Thread
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivy.graphics import RoundedRectangle


class ThreeDCanvasWidget(BoxLayout):
    def __init__(self, threed_engine, **kwargs):
        super().__init__(**kwargs)
        self.threed_engine = threed_engine
        self.bind(size=self.update_canvas, pos=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0.025, 0.045, 0.075, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(0, 0.85, 1, 1)
            Line(rectangle=(self.x, self.y, self.width, self.height), width=1)

        self.canvas.clear()
        with self.canvas:
            Color(0, 0.9, 1, 0.9)
            scale = min(self.width, self.height) * 0.65
            segments = self.threed_engine.get_projected_wireframe(
                scale=scale,
                center_x=self.width / 2,
                center_y=self.height / 2
            )
            for start, end in segments:
                Line(
                    points=[
                        self.x + start[0], self.y + start[1],
                        self.x + end[0], self.y + end[1]
                    ],
                    width=1.5
                )



class VoiceOrbWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.phase = 0.0
        self.state = "ready"
        self.bind(pos=self.draw_orb, size=self.draw_orb)
        self.anim_event = Clock.schedule_interval(self.animate, 1 / 30)

    def animate(self, dt):
        self.phase += dt * 2.2
        self.draw_orb()

    def set_state(self, state):
        self.state = state
        self.draw_orb()

    def draw_orb(self, *args):
        self.canvas.clear()
        cx, cy = self.center
        radius = min(self.width, self.height) * 0.23
        pulse = 1.0 + 0.07 * __import__("math").sin(self.phase * 2)
        if self.state == "speaking":
            pulse += 0.08 * abs(__import__("math").sin(self.phase * 3))
        with self.canvas:
            for scale, alpha in ((2.0, 0.10), (1.65, 0.17), (1.3, 0.25)):
                Color(0.0, 0.55, 1.0, alpha)
                Ellipse(pos=(cx-radius*scale*pulse,
                             cy-radius*scale*pulse),
                        size=(radius*2*scale*pulse,
                              radius*2*scale*pulse))
            Color(0.05, 0.55, 1.0, 0.95)
            Ellipse(pos=(cx-radius*pulse, cy-radius*pulse),
                    size=(radius*2*pulse, radius*2*pulse))
            Color(0.30, 0.85, 1.0, 0.95)
            Ellipse(pos=(cx-radius*0.65, cy-radius*0.65),
                    size=(radius*1.3, radius*1.3))

class LaibaKivyApp(App):
    def build(self):
        app_config.CONFIG_FILE = os.path.join(
            self.user_data_dir, "laiba_config.json"
        )
        self.history_file = os.path.join(
            self.user_data_dir, "laiba_chat_history.json"
        )

        saved_config = app_config.load_config()
        CURRENT_CONFIG.clear()
        CURRENT_CONFIG.update(saved_config)

        self.title = CURRENT_CONFIG.get("APP_NAME", "Laiba Assistant")
        self.diagnostics = configure_diagnostics(self.user_data_dir)
        self.chatbot = ChatbotEngine()
        self.media_bridge = AndroidMediaBridge(self)
        self.chatbot.external_opener = self.media_bridge.open_external_url
        self.update_engine = SelfUpdateEngine(
            current_version=CURRENT_CONFIG.get("VERSION", "1.0.4"),
            update_url=CURRENT_CONFIG.get("UPDATE_SERVER_URL", ""),
            state_path=os.path.join(
                self.user_data_dir, "laiba_update_state.json"
            )
        )
        self.chatbot.self_updater = self.update_engine
        self.update_in_progress = False
        self.threed_engine = ThreeDEngine()
        self.chat_history = self.load_history()

        if not self.chatbot.api_key and self.chatbot.api_keys:
            self.chatbot.api_key = self.chatbot.api_keys[0]
            CURRENT_CONFIG["GEMINI_API_KEY"] = self.chatbot.api_key

        if self.chatbot.api_key:
            return self.build_main_screen()
        return self.build_setup_screen()

    def load_history(self):
        try:
            import json
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save_history(self):
        import json
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.chat_history[-150:], f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print("[LAIBA] Chat history save error:", exc)

    def build_setup_screen(self):
        root = ScrollView(
            do_scroll_x=False,
            bar_width=dp(3)
        )
        self.setup_scroll = root

        with root.canvas.before:
            Color(0.015, 0.025, 0.055, 1)
            root_bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(
            pos=lambda obj, val: setattr(root_bg, "pos", val),
            size=lambda obj, val: setattr(root_bg, "size", val)
        )

        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=dp(24),
            spacing=dp(16)
        )
        content.bind(minimum_height=content.setter("height"))

        content.add_widget(Label(
            text="[b]LAIBA AI[/b]",
            markup=True,
            font_size="28sp",
            color=(0, 0.9, 1, 1),
            size_hint_y=None,
            height=dp(85)
        ))
        content.add_widget(Label(
            text="Connect your Gemini AI brain",
            font_size="16sp",
            color=(0.8, 0.9, 1, 1),
            size_hint_y=None,
            height=dp(45)
        ))

        self.api_key_input = TextInput(
            hint_text="Paste Gemini API Key",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=dp(54),
            background_color=(0.06, 0.09, 0.15, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0, 0.9, 1, 1)
        )
        self.api_key_input.bind(on_text_validate=self.verify_api_key)
        self.api_key_input.bind(focus=self._on_setup_input_focus)
        content.add_widget(self.api_key_input)

        self.verify_button = Button(
            text="CONNECT GEMINI",
            size_hint_y=None,
            height=dp(54),
            background_normal="",
            background_color=(0, 0.65, 0.75, 1),
            color=(1, 1, 1, 1)
        )
        self.verify_button.bind(on_release=self.verify_api_key)
        content.add_widget(self.verify_button)

        self.setup_status = Label(
            text="Your API key stays in this app's private storage.",
            color=(0.65, 0.8, 0.9, 1),
            halign="center",
            size_hint_y=None,
            height=dp(54)
        )
        content.add_widget(self.setup_status)

        root.add_widget(content)
        return root

    def _on_setup_input_focus(self, instance, focused):
        if focused and hasattr(self, "setup_scroll"):
            Clock.schedule_once(
                lambda dt: self.setup_scroll.scroll_to(
                    instance, padding=dp(32), animate=True
                ), 0.15
            )
            Clock.schedule_once(
                lambda dt: self.setup_scroll.scroll_to(
                    instance, padding=dp(32), animate=True
                ), 0.4
            )

    def verify_api_key(self, instance):
        key = self.api_key_input.text.strip()
        if not key:
            self.setup_status.text = "Please enter your Gemini API key."
            return

        self.verify_button.disabled = True
        self.setup_status.text = "Connecting to Gemini..."

        def worker():
            old_key = self.chatbot.api_key
            ok = False
            message = "Connection failed."
            try:
                self.chatbot.api_key = key
                result = self.chatbot.test_api_connection()
                ok = bool(result.get("ok"))
                message = str(result.get("message", message))
                if ok:
                    save_result = self.chatbot.set_api_key(key)
                    if not save_result.lower().startswith("api key saved"):
                        ok = False
                        message = save_result
            except Exception as exc:
                message = str(exc)
            finally:
                if not ok:
                    self.chatbot.api_key = old_key
                message = message.replace(key, "[HIDDEN]")
            Clock.schedule_once(
                lambda dt: self.finish_verification(ok, message), 0
            )

        Thread(target=worker, daemon=True).start()

    def finish_verification(self, ok, message):
        if not ok:
            self.verify_button.disabled = False
            self.setup_status.text = "Connection failed: " + message
            return
        screen = self.build_main_screen()
        self.root.clear_widgets()
        self.root.add_widget(screen)


    def build_main_screen(self):
        self.title = "Laiba AI Assistant"
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(7))
        root.bind(size=lambda *_: Clock.schedule_once(self._scroll_chat_to_bottom, 0.15))

        with root.canvas.before:
            Color(0.008, 0.018, 0.045, 1)
            bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda o,v:setattr(bg,"pos",v),
                  size=lambda o,v:setattr(bg,"size",v))

        header = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        header.add_widget(Label(
            text="[b]LAIBA[/b] [color=00DFFF]AI[/color]",
            markup=True, font_size="22sp", halign="left",
            color=(0.85,0.96,1,1)))

        self.network_label = Label(
            text="● Checking...", size_hint_x=None, width=dp(92),
            font_size="11sp", color=(1,0.8,0.25,1))
        header.add_widget(self.network_label)

        menu = Button(text="☰ MENU", size_hint_x=None, width=dp(88),
            background_normal="", background_color=(0.20,0.12,0.48,1))
        menu.bind(on_release=self.open_settings_menu)
        header.add_widget(menu)
        root.add_widget(header)

        self.chat_scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.message_list = BoxLayout(
            orientation="vertical", size_hint=(1, None),
            spacing=dp(12), padding=(dp(5), dp(10)))
        self.message_list.bind(
            minimum_height=self.message_list.setter("height"))
        self.chat_scroll.add_widget(self.message_list)
        root.add_widget(self.chat_scroll)

        if self.chat_history:
            for item in self.chat_history[-60:]:
                self.add_bubble(item.get("text",""),
                                item.get("sender","Laiba"), save=False)
        else:
            self.add_bubble(
                "Assalam-o-Alaikum! Main Laiba hoon. Aap mujh se Urdu, "
                "Roman Urdu ya English mein baat kar sakte hain.", "Laiba")

        panel = BoxLayout(orientation="vertical",
            size_hint_y=None, height=dp(101), spacing=dp(5), padding=dp(5))
        with panel.canvas.before:
            Color(0.025,0.065,0.11,1)
            panel_bg = RoundedRectangle(pos=panel.pos,
                size=panel.size, radius=[dp(17)])
        panel.bind(pos=lambda o,v:setattr(panel_bg,"pos",v),
                   size=lambda o,v:setattr(panel_bg,"size",v))

        media = BoxLayout(size_hint_y=None, height=dp(37), spacing=dp(6))
        for name, callback in [
            ("📷",self.open_camera),
            ("▧",self.open_gallery),
            ("◉",self.open_live_camera),
            ("🎙",self.open_microphone)
        ]:
            b = Button(text=name, font_size="11sp",
                background_normal="", background_color=(0.025,0.23,0.32,1),
                color=(0.4,0.95,1,1))
            b.bind(on_release=callback)
            media.add_widget(b)
        panel.add_widget(media)

        composer = BoxLayout(size_hint_y=None, height=dp(49), spacing=dp(6))
        self.user_input = TextInput(
            hint_text="Message Laiba...", multiline=False,
            background_normal="", background_active="",
            background_color=(0.055,0.10,0.16,1),
            foreground_color=(1,1,1,1), cursor_color=(0,0.9,1,1),
            hint_text_color=(0.5,0.68,0.78,1),
            padding=(dp(12),dp(12)))
        self.user_input.bind(on_text_validate=self.send_message)
        self.user_input.bind(focus=self._on_chat_input_focus)
        composer.add_widget(self.user_input)

        send = Button(text="➤", size_hint_x=None, width=dp(52),
            font_size="22sp", background_normal="",
            background_color=(0,0.65,0.82,1))
        send.bind(on_release=self.send_message)
        composer.add_widget(send)
        panel.add_widget(composer)
        root.add_widget(panel)

        Clock.schedule_once(lambda dt:self.check_network(),0.5)
        Clock.schedule_interval(lambda dt:self.check_network(),30)
        return root
    def open_settings_menu(self, *args):
        content = BoxLayout(orientation="vertical",
                            padding=dp(12), spacing=dp(9))
        content.add_widget(Label(text="[b]LAIBA SETTINGS[/b]",
            markup=True, size_hint_y=None, height=dp(38),
            color=(0,0.85,1,1), font_size="19sp"))

        scroll = ScrollView(do_scroll_x=False)
        items = BoxLayout(orientation="vertical",
            size_hint_y=None, spacing=dp(9), padding=dp(3))
        items.bind(minimum_height=items.setter("height"))

        popup = Popup(title="Laiba Settings", content=content,
                      size_hint=(0.94,0.88))

        for label, callback, color in [
            ("OPEN VOICE MODE", self.open_voice_mode, (0,0.35,0.55,1)),
            ("RUNTIME DIAGNOSTICS", self.open_runtime_diagnostics, (0.02,0.48,0.38,1)),
            ("GEMINI API KEYS", self.open_api_keys, (0.32,0.12,0.48,1)),
            ("GITHUB TOKEN / WORKFLOWS", self.open_github_settings, (0.02,0.38,0.32,1)),
            ("CHECK FOR UPDATES", self.check_laiba_updates, (0.02,0.42,0.52,1)),
            ("EXPORT PROJECT ZIP", self.export_zip, (0.02,0.35,0.48,1))
        ]:
            b = Button(text=label, size_hint_y=None, height=dp(48),
                       background_normal="", background_color=color)
            b.bind(on_release=lambda instance, cb=callback:
                   (popup.dismiss(), cb()))
            items.add_widget(b)

        items.add_widget(Label(text="[b]3D OBJECT CONTROLS[/b]",
            markup=True, size_hint_y=None, height=dp(35),
            color=(0,0.85,1,1)))

        self.three_d_widget = ThreeDCanvasWidget(
            self.threed_engine, size_hint_y=None, height=dp(190))
        items.add_widget(self.three_d_widget)

        controls = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        for label, callback in [
            ("Rotate X",lambda *_:self.rotate_mesh(15,0,0)),
            ("Rotate Y",lambda *_:self.rotate_mesh(0,15,0)),
            ("Cube / Pyramid",self.toggle_shape)
        ]:
            b = Button(text=label, font_size="10sp",
                background_normal="", background_color=(0.035,0.16,0.25,1))
            b.bind(on_release=callback)
            controls.add_widget(b)
        items.add_widget(controls)

        scroll.add_widget(items)
        content.add_widget(scroll)

        close = Button(text="CLOSE MENU", size_hint_y=None,
            height=dp(44), background_normal="",
            background_color=(0.18,0.22,0.32,1))
        close.bind(on_release=popup.dismiss)
        content.add_widget(close)
        popup.open()


    def open_runtime_diagnostics(self, *args):
        layout = BoxLayout(
            orientation="vertical", padding=dp(10), spacing=dp(7)
        )
        status = Label(
            text="Runtime monitor ready.",
            size_hint_y=None, height=dp(42),
            color=(0.35, 0.95, 0.75, 1)
        )
        log_view = Label(
            text="", size_hint_y=None, halign="left", valign="top",
            color=(0.82, 0.91, 1, 1), font_size="11sp"
        )
        log_view.bind(
            width=lambda obj, value: setattr(obj, "text_size", (value, None))
        )
        log_view.bind(
            texture_size=lambda obj, value: setattr(obj, "height", value[1])
        )
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        scroll.add_widget(log_view)

        popup = Popup(
            title="Laiba Runtime Diagnostics",
            content=layout, size_hint=(0.97, 0.93)
        )

        def refresh(*_):
            entries = self.diagnostics.recent(35)
            if not entries:
                log_view.text = "No runtime errors recorded."
            else:
                rows = []
                for item in entries:
                    rows.append(
                        "[{severity}] {time}\n{category}: {event}\n{details}".format(
                            **item
                        )
                    )
                    if item.get("traceback"):
                        rows.append(item["traceback"][-1800:])
                    rows.append("")
                log_view.text = "\n".join(rows)
            log_view.texture_update()
            scroll.scroll_y = 0

        def run_tests(*_):
            status.text = "Running system checks..."
            status.color = (1, 0.8, 0.3, 1)

            def worker():
                checks = []

                def add(name, ok, detail):
                    result = "PASS" if ok else "FAIL"
                    checks.append("{}: {} - {}".format(name, result, detail))
                    self.diagnostics.record(
                        "system_test", name, detail,
                        severity="INFO" if ok else "ERROR"
                    )

                try:
                    probe = os.path.join(
                        self.user_data_dir, ".laiba_diag_probe"
                    )
                    with open(probe, "w", encoding="utf-8") as stream:
                        stream.write("ok")
                    os.remove(probe)
                    add("Private storage", True, "App storage is writable")
                except Exception as exc:
                    add("Private storage", False, type(exc).__name__)

                bridge = getattr(self, "media_bridge", None)
                native = getattr(bridge, "native_tts", None)
                if native is not None:
                    ready = bool(getattr(native, "ready", False))
                    failed = bool(getattr(native, "failed", False))
                    add(
                        "Android Native TTS", ready,
                        "ready={}, failed={}".format(ready, failed)
                    )
                else:
                    add("Android Native TTS", False, "TTS bridge unavailable")

                try:
                    from kivy.utils import platform
                    if platform == "android":
                        from jnius import autoclass
                        Activity = autoclass(
                            "org.kivy.android.PythonActivity"
                        )
                        SpeechRecognizer = autoclass(
                            "android.speech.SpeechRecognizer"
                        )
                        available = bool(
                            SpeechRecognizer.isRecognitionAvailable(
                                Activity.mActivity
                            )
                        )
                        add(
                            "Speech recognition service", available,
                            "Android recognition service availability"
                        )
                        try:
                            from android.permissions import check_permission
                            granted = bool(check_permission(
                                "android.permission.RECORD_AUDIO"
                            ))
                            add(
                                "Microphone permission", granted,
                                "RECORD_AUDIO permission granted={}".format(
                                    granted
                                )
                            )
                        except Exception as exc:
                            add(
                                "Microphone permission", False,
                                "Permission check unavailable: " +
                                type(exc).__name__
                            )
                    else:
                        add(
                            "Android speech service", True,
                            "Not applicable on this platform"
                        )
                except Exception as exc:
                    add(
                        "Speech recognition service", False,
                        type(exc).__name__ + ": " + str(exc)[:160]
                    )

                try:
                    if not (
                        getattr(self.chatbot, "api_key", None)
                        or getattr(self.chatbot, "api_keys", [])
                    ):
                        add("Gemini API", False, "No API key configured")
                    else:
                        tester = getattr(
                            self.chatbot, "test_api_connection", None
                        )
                        if callable(tester):
                            result = tester()
                            if isinstance(result, dict):
                                ok = bool(result.get("ok"))
                                detail = str(
                                    result.get("message", "Connection test")
                                )[:180]
                            else:
                                ok = bool(result)
                                detail = "Gemini connection test completed"
                            add("Gemini API", ok, detail)
                        else:
                            add(
                                "Gemini API", True,
                                "API key configured; live test unavailable"
                            )
                except Exception as exc:
                    self.diagnostics.record_exception(
                        "gemini", "Diagnostic connection test failed", exc
                    )
                    add("Gemini API", False, type(exc).__name__)

                summary = "\n".join(checks)
                Clock.schedule_once(
                    lambda dt: (
                        setattr(status, "text", summary),
                        setattr(
                            status, "color",
                            (0.35, 0.95, 0.75, 1)
                            if all(": PASS -" in line for line in checks)
                            else (1, 0.72, 0.28, 1)
                        ),
                        refresh()
                    ), 0
                )

            Thread(target=worker, daemon=True).start()

        actions = GridLayout(
            cols=2, spacing=dp(6), size_hint_y=None, height=dp(100)
        )

        def add_action(label, callback, color):
            button = Button(
                text=label, background_normal="",
                background_color=color, font_size="12sp"
            )
            button.bind(on_release=callback)
            actions.add_widget(button)

        add_action(
            "TEST ALL SYSTEMS", run_tests, (0.02, 0.42, 0.55, 1)
        )

        def copy_logs(*_):
            try:
                Clipboard.copy(self.diagnostics.format_text())
                status.text = "Logs copied to clipboard."
            except Exception as exc:
                status.text = "Copy failed: " + type(exc).__name__

        add_action(
            "COPY LOGS", copy_logs, (0.12, 0.32, 0.48, 1)
        )

        def export_report(*_):
            try:
                path = self.diagnostics.export_report()
                status.text = "Diagnostic report saved:\n" + path
            except Exception as exc:
                status.text = "Export failed: " + type(exc).__name__

        add_action(
            "EXPORT REPORT", export_report, (0.08, 0.42, 0.34, 1)
        )

        def clear_logs(*_):
            self.diagnostics.clear()
            status.text = "Runtime history cleared."
            refresh()

        add_action(
            "CLEAR HISTORY", clear_logs, (0.48, 0.16, 0.20, 1)
        )

        close = Button(
            text="CLOSE", size_hint_y=None, height=dp(42),
            background_normal="", background_color=(0.18, 0.22, 0.32, 1)
        )
        close.bind(on_release=popup.dismiss)

        layout.add_widget(status)
        layout.add_widget(actions)
        layout.add_widget(scroll)
        layout.add_widget(close)

        refresh()
        refresh_event = Clock.schedule_interval(refresh, 1.5)
        popup.bind(
            on_dismiss=lambda *_: refresh_event.cancel()
        )
        popup.open()

    def _scroll_chat_to_bottom(self, *args):
        if not hasattr(self, "chat_scroll"):
            return
        self.chat_scroll.scroll_y = 0

    def _on_chat_input_focus(self, instance, focused):
        if focused:
            Clock.schedule_once(self._scroll_chat_to_bottom, 0.15)
            Clock.schedule_once(self._scroll_chat_to_bottom, 0.45)

    def copy_message(self, text, *args):
        try:
            Clipboard.copy(str(text))
            self.show_copy_status("Copied to clipboard")
        except Exception as exc:
            self.show_copy_status("Copy failed: " + str(exc))

    def show_copy_status(self, message):
        try:
            if hasattr(self, "network_label"):
                self.network_label.text = message
                Clock.schedule_once(
                    lambda dt: self.check_network(), 1.8
                )
        except Exception:
            pass

    def add_bubble(self, message, sender="Laiba", save=True):
        message = str(message)

        row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            spacing=dp(5),
            padding=(dp(2), dp(2))
        )

        label = Label(
            text=("YOU\\n" if sender == "You" else "LAIBA\\n") + message,
            color=(0.45, 0.95, 1, 1) if sender == "You"
                  else (0.94, 0.97, 1, 1),
            font_size="15sp",
            halign="left",
            valign="top",
            size_hint=(1, None),
            text_size=(None, None),
            padding=(dp(8), dp(5))
        )

        copy_btn = Button(
            text="COPY",
            size_hint=(None, None),
            size=(dp(64), dp(38)),
            font_size="11sp",
            background_normal="",
            background_down="",
            background_color=(0.025, 0.23, 0.32, 1),
            color=(0.4, 0.95, 1, 1)
        )
        copy_btn.bind(
            on_release=lambda instance, value=message:
                self.copy_message(value)
        )

        row.add_widget(label)
        row.add_widget(copy_btn)

        def update_layout(*args):
            available = max(dp(80), row.width - dp(76))
            label.text_size = (available - dp(16), None)
            label.texture_update()
            label.height = label.texture_size[1] + dp(12)
            row.height = max(label.height, dp(36))

        row.bind(width=lambda *_: update_layout())
        label.bind(texture_size=lambda *_: update_layout())
        self.message_list.add_widget(row)
        Clock.schedule_once(lambda dt: update_layout(), 0)
        Clock.schedule_once(self._scroll_chat_to_bottom, 0.1)
        Clock.schedule_once(self._scroll_chat_to_bottom, 0.3)

        if save:
            self.chat_history.append({
                "sender": sender,
                "text": message
            })
            self.save_history()

    def check_network(self):
        if getattr(self, "_network_check_running", False):
            return

        self._network_check_running = True

        def worker():
            online = False
            try:
                import requests
                response = requests.get(
                    "https://www.google.com/generate_204",
                    timeout=(3, 6),
                    headers={"Cache-Control": "no-cache"}
                )
                online = 200 <= response.status_code < 400
                response.close()
            except Exception:
                online = False
            finally:
                self._network_check_running = False
                Clock.schedule_once(
                    lambda dt: self.update_network_status(online), 0
                )

        Thread(target=worker, daemon=True).start()

    def update_network_status(self, online):
        if not hasattr(self, "network_label"):
            return
        if online:
            self.network_label.text = "● Online"
            self.network_label.color = (0.2, 1, 0.65, 1)
        else:
            self.network_label.text = "● Offline"
            self.network_label.color = (1, 0.35, 0.35, 1)

    def rotate_mesh(self, dx, dy, dz):
        self.threed_engine.rotate(dx, dy, dz)
        self.three_d_widget.update_canvas()

    def toggle_shape(self, instance):
        if self.threed_engine.active_shape == "cube":
            self.threed_engine.load_pyramid()
        else:
            self.threed_engine.load_cube()
        self.three_d_widget.update_canvas()

    def open_voice_mode(self, *args):
        self.voice_active = False
        self.voice_muted = False
        self.voice_processing = False
        screen = BoxLayout(
            orientation="vertical",
            padding=dp(22),
            spacing=dp(12)
        )
        with screen.canvas.before:
            Color(0.008, 0.018, 0.055, 1)
            bg = Rectangle(pos=screen.pos, size=screen.size)
        screen.bind(
            pos=lambda o, v: setattr(bg, "pos", v),
            size=lambda o, v: setattr(bg, "size", v)
        )

        back = Button(
            text="‹  BACK",
            size_hint_y=None,
            height=dp(48),
            background_normal="",
            background_color=(0.04, 0.12, 0.22, 1)
        )
        back.bind(on_release=self.close_voice_mode)
        screen.add_widget(back)

        screen.add_widget(Label(
            text="[b]LAIBA AI[/b]",
            markup=True,
            font_size="25sp",
            color=(0.65, 0.92, 1, 1),
            size_hint_y=None,
            height=dp(48)
        ))

        self.voice_status = Label(
            text="Ready to talk",
            font_size="16sp",
            color=(0.45, 0.85, 1, 1),
            size_hint_y=None,
            height=dp(38)
        )
        screen.add_widget(self.voice_status)

        self.voice_orb = VoiceOrbWidget()
        screen.add_widget(self.voice_orb)

        self.voice_hint = Label(
            text="Tap Start Conversation",
            font_size="14sp",
            color=(0.65, 0.78, 0.9, 1),
            size_hint_y=None,
            height=dp(35)
        )
        screen.add_widget(self.voice_hint)

        controls = BoxLayout(
            size_hint_y=None,
            height=dp(65),
            spacing=dp(12)
        )
        self.voice_start_button = Button(
            text="▶  START",
            background_normal="",
            background_color=(0.0, 0.48, 0.78, 1)
        )
        self.voice_start_button.bind(on_release=self.start_voice_call)
        controls.add_widget(self.voice_start_button)

        self.voice_mic_button = Button(
            text="MIC ON",
            background_normal="",
            background_color=(0.04, 0.30, 0.40, 1),
            disabled=True
        )
        self.voice_mic_button.bind(on_release=self.toggle_voice_mic)
        controls.add_widget(self.voice_mic_button)

        end_button = Button(
            text="■  END CALL",
            background_normal="",
            background_color=(0.75, 0.08, 0.15, 1)
        )
        end_button.bind(on_release=self.end_voice_call)
        controls.add_widget(end_button)

        screen.add_widget(controls)
        self.voice_screen = screen
        self.root.clear_widgets()
        self.root.add_widget(screen)

    def start_voice_call(self, *args):
        if self.voice_active:
            return
        self.voice_active = True
        self.voice_muted = False
        self.voice_processing = False
        self.voice_status.text = "Starting microphone..."
        self.voice_hint.text = "Connecting to Android speech recognition..."
        self.voice_orb.set_state("ready")
        self.voice_start_button.disabled = True
        self.voice_mic_button.disabled = False
        self.voice_mic_button.text = "MIC ON"
        self.media_bridge.microphone()

    def toggle_voice_mic(self, *args):
        if not self.voice_active:
            return

        if self.voice_muted:
            self.voice_muted = False
            self.voice_mic_button.text = "MIC ON"
            if self.voice_processing:
                self.voice_status.text = "Laiba is preparing her reply..."
                self.voice_orb.set_state("ready")
                self.voice_hint.text = "Listening will resume when the reply starts."
            else:
                self.voice_status.text = (
                    "Laiba is speaking — you can interrupt."
                    if self.media_bridge.is_speaking else "Listening..."
                )
                self.voice_orb.set_state(
                    "speaking" if self.media_bridge.is_speaking else "listening"
                )
                self.voice_hint.text = "Speak anytime to interrupt Laiba."
                self.media_bridge.microphone()

        elif self.media_bridge.is_speaking:
            # Button press while Laiba speaks = barge-in.
            self.media_bridge.stop_speaking()
            self.voice_processing = False
            self.voice_status.text = "Listening..."
            self.voice_hint.text = "Reply interrupted. I'm listening."
            self.voice_orb.set_state("listening")
            Clock.schedule_once(
                lambda dt: self.media_bridge.microphone(), 0.25
            )

        else:
            self.voice_muted = True
            self.voice_mic_button.text = "MIC OFF"
            self.voice_status.text = "Microphone muted"
            self.voice_orb.set_state("ready")
            self.media_bridge.stop_listening()

    def end_voice_call(self, *args):
        self.voice_active = False
        self.voice_muted = True
        self.voice_processing = False
        self.media_bridge.stop_listening()
        self.media_bridge.stop_speaking()
        self.close_voice_mode()

    def close_voice_mode(self, *args):
        self.voice_active = False
        self.voice_muted = True
        self.voice_processing = False
        self.media_bridge.stop_listening()
        self.media_bridge.stop_speaking()
        self.root.clear_widgets()
        self.root.add_widget(self.build_main_screen())

    def open_camera(self, *args):
        self.media_bridge.camera()

    def open_gallery(self, *args):
        self.media_bridge.gallery()

    def open_live_camera(self, *args):
        self.media_bridge.live_camera()

    def open_microphone(self, *args):
        self.media_bridge.microphone()

    def send_message(self, *args):
        text = self.user_input.text.strip()
        if not text:
            return

        self.user_input.text = ""
        self.add_bubble(text, "You")
        thinking = Label(
            text="Laiba is thinking...",
            color=(0, 0.85, 1, 1),
            size_hint_y=None,
            height=dp(32)
        )
        self.message_list.add_widget(thinking)

        def worker():
            try:
                result = self.chatbot.process_message(text)
            except Exception as exc:
                self.diagnostics.record_exception(
                    "chat", "Message processing failed", exc
                )
                result = "Network or AI error: " + str(exc)
            Clock.schedule_once(
                lambda dt: self.finish_reply(result, thinking), 0
            )

        Thread(target=worker, daemon=True).start()

    def send_voice_transcript(self, text):
        text = str(text).strip()
        if not text:
            return

        if getattr(self, "voice_active", False):
            self.voice_processing = True
            self.voice_status.text = "Laiba is thinking..."
            self.voice_orb.set_state("ready")
            self.voice_hint.text = "Preparing your answer..."

        self.add_bubble(text, "You")
        thinking = Label(
            text="Laiba is thinking...",
            color=(0, 0.85, 1, 1),
            size_hint_y=None,
            height=dp(32)
        )
        self.message_list.add_widget(thinking)

        def worker():
            try:
                result = self.chatbot.process_message(text, voice_mode=True)
            except Exception as exc:
                self.diagnostics.record_exception(
                    "chat", "Message processing failed", exc
                )
                result = "Network or AI error: " + str(exc)

            Clock.schedule_once(
                lambda dt: self.finish_reply(result, thinking), 0
            )

        Thread(target=worker, daemon=True).start()

    def on_voice_bridge_state(self, state, detail=""):
        if state in ("error", "retrying", "no_match"):
            self.diagnostics.record(
                "speech", state, detail,
                severity="ERROR" if state == "error" else "WARNING"
            )
        if not getattr(self, "voice_active", False):
            return

        if state == "permission":
            self.voice_status.text = "Requesting microphone..."
            self.voice_hint.text = detail
            self.voice_orb.set_state("ready")

        elif state == "starting":
            self.voice_status.text = "Starting microphone..."
            self.voice_hint.text = detail
            self.voice_orb.set_state("ready")

        elif state == "ready":
            if self.media_bridge.is_speaking:
                self.voice_status.text = "Laiba is speaking..."
                self.voice_hint.text = "Speak anytime to interrupt Laiba."
                self.voice_orb.set_state("speaking")
            else:
                self.voice_status.text = "Listening..."
                self.voice_hint.text = "Microphone ready. Speak in Urdu or English."
                self.voice_orb.set_state("listening")

        elif state == "hearing":
            self.voice_status.text = "Hearing you..."
            self.voice_hint.text = detail
            self.voice_orb.set_state("listening")

        elif state == "processing":
            self.voice_status.text = "Recognizing your words..."
            self.voice_hint.text = detail
            self.voice_orb.set_state("ready")

        elif state == "no_match":
            self.voice_status.text = "Didn't catch that"
            self.voice_hint.text = detail
            self.voice_orb.set_state("ready")

        elif state == "retrying":
            self.voice_status.text = "Reconnecting microphone..."
            self.voice_hint.text = detail
            self.voice_orb.set_state("ready")

        elif state == "error":
            self.voice_muted = True
            self.voice_status.text = "Microphone unavailable"
            self.voice_hint.text = detail
            self.voice_orb.set_state("ready")
            self.voice_mic_button.text = "RETRY MIC"

    def on_voice_barge_in(self):
        if not getattr(self, "voice_active", False):
            return

        self.voice_processing = False
        self.voice_status.text = "Hearing you..."
        self.voice_hint.text = "Laiba stopped. Go ahead with your question."
        self.voice_orb.set_state("listening")

    def _resume_voice_listening(self, delay=0.7):
        retry = {"count": 0}

        def attempt(dt):
            if (
                not self.voice_active
                or self.voice_muted
                or self.voice_processing
            ):
                return

            self.media_bridge._restart_listening()
            retry["count"] += 1

            if (
                not self.media_bridge.recognition_active
                and not self.media_bridge.recognition_start_pending
                and retry["count"] < 4
            ):
                Clock.schedule_once(attempt, 0.9)

        Clock.schedule_once(attempt, delay)

    def on_tts_state(self, state):
        if state == "error":
            self.diagnostics.record(
                "tts", "Gemini TTS playback failed; restoring microphone",
                severity="WARNING"
            )

        if not getattr(self, "voice_active", False):
            return

        if state == "speaking":
            # Keep the microphone cancelled for the entire TTS playback.
            self.voice_processing = True
            self.media_bridge.stop_listening()
            self.voice_status.text = "Laiba is speaking..."
            self.voice_orb.set_state("speaking")
            self.voice_hint.text = "Microphone will restart after Laiba finishes."

        elif state in ("done", "error"):
            self.voice_processing = False

            if not self.voice_muted:
                if state == "error":
                    self.voice_status.text = "Voice reply unavailable — listening"
                    self.voice_hint.text = (
                        "Voice playback failed. You can speak now."
                    )
                else:
                    self.voice_status.text = "Listening..."
                    self.voice_hint.text = "I'm listening. Speak now."

                self.voice_orb.set_state("listening")
                self._resume_voice_listening(
                    0.5 if state == "error" else 0.8
                )

    def finish_reply(self, result, thinking):
        if thinking.parent:
            thinking.parent.remove_widget(thinking)
        self.add_bubble(str(result), "Laiba")
        if getattr(self, "voice_active", False):
            self.voice_processing = True
            self.voice_status.text = "Laiba is preparing her voice reply..."
            self.voice_orb.set_state("speaking")
        if getattr(self, "voice_active", False):
            # Cancel microphone before Gemini starts generating audio.
            self.media_bridge.stop_listening()
            self.media_bridge.speak_voice_reply(str(result))
        else:
            self.media_bridge.speak(str(result))



    def open_github_settings(self, *args):
        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        content.add_widget(Label(
            text="[b]GITHUB CONNECTION[/b]", markup=True,
            size_hint_y=None, height=dp(38), color=(0,0.85,1,1)
        ))
        status = Label(
            text="Enter your GitHub token. It will be saved in app private storage.",
            size_hint_y=None, height=dp(55), color=(0.7,0.85,1,1)
        )
        content.add_widget(status)
        token_input = TextInput(
            hint_text="Paste GitHub Personal Access Token",
            password=True, multiline=False, size_hint_y=None, height=dp(50),
            background_color=(0.06,0.09,0.15,1),
            foreground_color=(1,1,1,1)
        )
        content.add_widget(token_input)
        if CURRENT_CONFIG.get("GITHUB_TOKEN"):
            token_input.hint_text = "Token saved. Enter a new token to replace it."

        connect = Button(
            text="CONNECT / SAVE TOKEN", size_hint_y=None, height=dp(48),
            background_normal="", background_color=(0,0.55,0.68,1)
        )
        content.add_widget(connect)
        popup = Popup(title="Laiba - GitHub", content=content, size_hint=(0.94,0.62))

        def connect_github(*_):
            token = token_input.text.strip()
            if not token:
                status.text = "Please enter your GitHub token."
                return
            connect.disabled = True
            status.text = "Checking GitHub access..."

            def worker():
                ok = False
                message = "GitHub connection failed."
                old_token = CURRENT_CONFIG.get("GITHUB_TOKEN", "")
                try:
                    client = GitHubClient(
                        token,
                        CURRENT_CONFIG["GITHUB_REPOSITORY"],
                        CURRENT_CONFIG["GITHUB_BRANCH"]
                    )
                    result = client.check_access()
                    ok = bool(result.get("ok"))
                    message = result.get("message", message)
                    if ok:
                        CURRENT_CONFIG["GITHUB_TOKEN"] = token
                        if not app_config.save_config(CURRENT_CONFIG):
                            CURRENT_CONFIG["GITHUB_TOKEN"] = old_token
                            ok = False
                            message = "Could not save token in app private storage."
                except Exception as exc:
                    message = "GitHub error: " + str(exc)[:160]

                message = str(message).replace(token, "[HIDDEN]")
                def finish(_dt):
                    connect.disabled = False
                    status.text = message
                    if ok:
                        token_input.text = ""
                        token_input.hint_text = "Token saved. Enter another token to replace it."
                Clock.schedule_once(finish, 0)

            Thread(target=worker, daemon=True).start()

        connect.bind(on_release=connect_github)
        close = Button(
            text="CLOSE", size_hint_y=None, height=dp(42),
            background_normal="", background_color=(0.18,0.22,0.32,1)
        )
        close.bind(on_release=popup.dismiss)
        content.add_widget(close)
        popup.open()

    def open_api_keys(self, *args):
        content = BoxLayout(
            orientation="vertical", padding=dp(12), spacing=dp(8)
        )

        content.add_widget(Label(
            text="[b]GEMINI MULTIPLE API KEYS[/b]",
            markup=True, size_hint_y=None, height=dp(35),
            color=(0, 0.85, 1, 1)
        ))

        status = Label(
            text="Keys are stored in private app configuration.",
            size_hint_y=None, height=dp(42),
            color=(0.7, 0.85, 1, 1)
        )
        content.add_widget(status)

        key_input = TextInput(
            hint_text="Enter another Gemini API Key",
            password=True, multiline=False,
            size_hint_y=None, height=dp(48),
            background_color=(0.06, 0.09, 0.15, 1),
            foreground_color=(1, 1, 1, 1)
        )
        content.add_widget(key_input)

        add_button = Button(
            text="ADD & VERIFY KEY",
            size_hint_y=None, height=dp(46),
            background_normal="",
            background_color=(0, 0.55, 0.68, 1)
        )
        content.add_widget(add_button)

        scroll = ScrollView(do_scroll_x=False)
        key_list = BoxLayout(
            orientation="vertical", size_hint_y=None,
            spacing=dp(7), padding=dp(3)
        )
        key_list.bind(minimum_height=key_list.setter("height"))
        scroll.add_widget(key_list)
        content.add_widget(scroll)

        popup = Popup(
            title="Laiba - Gemini Key Manager",
            content=content, size_hint=(0.94, 0.82)
        )

        self.refresh_api_key_list(key_list, status)
        add_button.bind(on_release=lambda *_: self.add_managed_api_key(
            key_input, status, key_list, add_button
        ))
        popup.open()

    def refresh_api_key_list(self, container, status):
        container.clear_widgets()
        keys = list(dict.fromkeys(
            getattr(self.chatbot, "api_keys", [])
        ))

        if not keys and self.chatbot.api_key:
            keys = [self.chatbot.api_key]

        if not keys:
            container.add_widget(Label(
                text="No Gemini API Keys configured.",
                size_hint_y=None, height=dp(45)
            ))
            return

        for index, key in enumerate(keys, 1):
            row = BoxLayout(
                size_hint_y=None, height=dp(46), spacing=dp(4)
            )
            masked = key[:5] + "..." + key[-4:] if len(key) > 10 else "Hidden"
            row.add_widget(Label(
                text="Key {}: {}".format(index, masked),
                font_size="11sp", color=(0.85, 0.95, 1, 1)
            ))

            test_button = Button(
                text="TEST", size_hint_x=None, width=dp(62),
                background_normal="",
                background_color=(0.02, 0.42, 0.32, 1)
            )
            test_button.bind(
                on_release=lambda _, k=key: self.test_managed_api_key(k, status)
            )
            row.add_widget(test_button)

            delete_button = Button(
                text="DELETE", size_hint_x=None, width=dp(72),
                background_normal="",
                background_color=(0.55, 0.12, 0.16, 1)
            )
            delete_button.bind(
                on_release=lambda _, k=key: self.delete_managed_api_key(
                    k, container, status
                )
            )
            row.add_widget(delete_button)
            container.add_widget(row)

    def add_managed_api_key(self, key_input, status, key_list, button):
        key = key_input.text.strip()
        if not key:
            status.text = "Please enter an API key."
            return

        old_keys = list(self.chatbot.api_keys)
        button.disabled = True
        status.text = "Verifying Gemini API key..."

        def worker():
            try:
                result = self.chatbot.set_api_key(key)
                ok = str(result).startswith("API key saved")
                message = str(result).replace(key, "[HIDDEN]")
                if not ok:
                    self.chatbot.api_keys = old_keys
            except Exception as exc:
                ok = False
                self.chatbot.api_keys = old_keys
                message = str(exc).replace(key, "[HIDDEN]")[:250]

            Clock.schedule_once(
                lambda dt: self.finish_managed_api_key(
                    ok, message, key_input, status, key_list, button
                ), 0
            )

        Thread(target=worker, daemon=True).start()

    def finish_managed_api_key(
        self, ok, message, key_input, status, key_list, button
    ):
        button.disabled = False
        status.text = message
        if ok:
            key_input.text = ""
            self.refresh_api_key_list(key_list, status)

    def test_managed_api_key(self, key, status):
        status.text = "Testing selected API key..."

        def worker():
            try:
                result = self.chatbot.test_api_connection(key)
                ok = bool(result.get("ok"))
                message = result.get("message", "API key test failed.")
            except Exception as exc:
                ok = False
                message = "Key test failed: " + str(exc)[:180]

            Clock.schedule_once(
                lambda dt: setattr(status, "text", message), 0
            )

        Thread(target=worker, daemon=True).start()

    def delete_managed_api_key(self, key, key_list, status):
        old_keys = list(self.chatbot.api_keys)
        if key not in old_keys:
            status.text = "API key not found."
            return

        new_keys = [item for item in old_keys if item != key]
        if not new_keys:
            status.text = "At least one API key must remain configured."
            return

        old_key = self.chatbot.api_key
        old_model = self.chatbot.model_name
        old_candidates = self.chatbot.model_candidates
        old_config = dict(CURRENT_CONFIG)

        new_active = new_keys[0] if old_key == key else old_key
        auto_switching = bool(CURRENT_CONFIG.get("GEMINI_AUTO_MODEL_SWITCHING", False))
        fixed_model = str(CURRENT_CONFIG.get("GEMINI_FIXED_MODEL", "gemma-4-26b-a4b-it")).strip()

        try:
            self.chatbot.api_keys = new_keys
            self.chatbot.api_key = new_active
            self.chatbot.model_name = "" if auto_switching else fixed_model
            self.chatbot.model_candidates = [] if auto_switching else [fixed_model]

            CURRENT_CONFIG["GEMINI_API_KEYS"] = new_keys
            CURRENT_CONFIG["GEMINI_API_KEY"] = new_active
            CURRENT_CONFIG["GEMINI_MODEL"] = "" if auto_switching else fixed_model
            CURRENT_CONFIG["GEMINI_MODEL_CANDIDATES"] = [] if auto_switching else [fixed_model]

            if not app_config.save_config(CURRENT_CONFIG):
                raise RuntimeError("Configuration save failed.")

            status.text = "API key deleted successfully."
            self.refresh_api_key_list(key_list, status)

        except Exception as exc:
            self.chatbot.api_keys = old_keys
            self.chatbot.api_key = old_key
            self.chatbot.model_name = old_model
            self.chatbot.model_candidates = old_candidates
            CURRENT_CONFIG.clear()
            CURRENT_CONFIG.update(old_config)
            status.text = "Delete failed: " + str(exc)[:180]

    def _update_notice(self, message):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        box.add_widget(Label(text=str(message), halign="center", valign="middle"))
        close = Button(text="OK", size_hint_y=None, height=dp(44))
        popup = Popup(title="Laiba Update", content=box, size_hint=(0.88, 0.42))
        close.bind(on_release=popup.dismiss)
        box.add_widget(close)
        popup.open()

    def check_laiba_updates(self, *args):
        if self.update_in_progress:
            self._update_notice("An update operation is already running.")
            return
        self.update_in_progress = True
        self._update_notice("Checking for Laiba updates...")

        def worker():
            try:
                result = self.update_engine.check_for_updates()
                Clock.schedule_once(
                    lambda dt: self._finish_update_check(result), 0
                )
            except Exception as exc:
                message = str(exc)
                Clock.schedule_once(
                    lambda dt, msg=message: self._finish_update_error(msg), 0
                )

        Thread(target=worker, daemon=True).start()

    def _finish_update_error(self, message):
        self.update_in_progress = False
        self._update_notice("Update check failed: " + str(message)[:300])

    def _finish_update_check(self, result):
        if result.get("status") != "ok":
            self.update_in_progress = False
            self._update_notice(result.get("changelog", "Update check failed."))
            return
        if not result.get("update_available"):
            self.update_in_progress = False
            self._update_notice("Laiba is up to date.")
            return
        url = result.get("download_url")
        digest = result.get("sha256")
        if not url or not digest:
            self.update_in_progress = False
            self._update_notice("Update rejected: secure APK URL or SHA-256 is missing.")
            return

        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        box.add_widget(Label(
            text="New version: {}\\n\\n{}\\n\\nDownload and open Android installer?".format(
                result.get("latest_version", "Unknown"),
                result.get("changelog", "No changelog provided.")
            ),
            halign="center", valign="middle"
        ))
        actions = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        popup = Popup(title="Laiba Update Available", content=box, size_hint=(0.92, 0.55))
        cancel = Button(text="CANCEL")
        install = Button(text="DOWNLOAD & INSTALL")
        cancel.bind(on_release=lambda *_: (popup.dismiss(), setattr(self, "update_in_progress", False)))
        install.bind(on_release=lambda *_: (popup.dismiss(), self._download_laiba_update(result)))
        actions.add_widget(cancel)
        actions.add_widget(install)
        box.add_widget(actions)
        popup.open()

    def _download_laiba_update(self, info):
        self._update_notice("Downloading and verifying APK...")
        def worker():
            path = os.path.join(self.user_data_dir, "updates", "Laiba-update.apk")
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                downloaded = self.update_engine.download_apk(
                    info["download_url"], info["sha256"], path
                )
                if not isinstance(downloaded, dict) or not downloaded.get("path"):
                    raise RuntimeError("Downloader did not return a verified APK.")
                path = str(downloaded["path"])
                valid, message = self.update_engine.verify_file(path, info["sha256"])
                if not valid:
                    raise RuntimeError(message)
                Clock.schedule_once(lambda dt: self._open_laiba_system_installer(path, info), 0)
            except Exception as exc:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
                message = str(exc)
                Clock.schedule_once(lambda dt, msg=message: self._finish_update_error(msg), 0)
        Thread(target=worker, daemon=True).start()

    def _open_laiba_system_installer(self, apk_path, info):
        try:
            self.update_engine.mark_update_pending(
                info["latest_version"], apk_path, info["sha256"]
            )
            opened = bool(self.media_bridge.install_apk(apk_path))
            if not opened:
                self.update_engine.save_update_state({
                    "status": "failed",
                    "reason": "Android system installer could not be opened."
                })
                self.update_in_progress = False
                self._update_notice(
                    "Android could not open the installer. The current app remains unchanged."
                )
                return
            self.update_in_progress = False
            self._update_notice(
                "Android installer opened. Confirm installation there. "
                "Laiba will verify the installed version on next launch."
            )
        except Exception as exc:
            self.update_in_progress = False
            try:
                self.update_engine.save_update_state({
                    "status": "failed", "reason": str(exc)[:250]
                })
            except Exception:
                pass
            self._update_notice("Installer error: " + str(exc)[:250])


    def on_pause(self):
        try:
            self.media_bridge.stop_listening()
            self.media_bridge.stop_speaking()
        except Exception as exc:
            print(f"[Laiba] Pause cleanup: {exc}")
        return True

    def on_resume(self):
        try:
            state = self.update_engine.resolve_update_state()
            if state.get("status") in ("confirmed", "failed"):
                Clock.schedule_once(lambda dt, st=state: self._update_notice(
                    "Update " + st["status"] + (": " + st.get("reason", "") if st.get("reason") else ".")
                ), 0)
        except Exception:
            pass
        try:
            if getattr(self, "voice_active", False) and not getattr(self, "voice_processing", False):
                Clock.schedule_once(lambda dt: self.media_bridge._restart_listening(), 0.7)
        except Exception as exc:
            print(f"[Laiba] Resume voice restart: {exc}")

    def on_stop(self):
        try:
            self.media_bridge.shutdown()
        except Exception as exc:
            print(f"[Laiba] Media shutdown: {exc}")

    def export_zip(self, instance):
        try:
            result = self.chatbot.export_project_zip()
            message = result.get("message", result)
        except Exception as exc:
            message = "ZIP export error: " + str(exc)
        self.add_bubble(str(message), "Laiba")


if __name__ == "__main__":
    LaibaKivyApp().run()
