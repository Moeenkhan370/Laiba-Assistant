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

from config import CURRENT_CONFIG
from engines.chatbot_engine import ChatbotEngine
from engines.threed_engine import ThreeDEngine
from android_media import AndroidMediaBridge

# Set Window dark background
Window.clearcolor = (0, 0, 0, 1)



from threading import Thread
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivy.graphics import RoundedRectangle


class ChatBubble(BoxLayout):
    def __init__(self, message, sender="Laiba", **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            padding=(dp(13), dp(9)),
            spacing=dp(4),
            **kwargs
        )
        self.size_hint_x = 0.86
        self.bind(minimum_height=self.setter("height"))

        is_user = sender == "You"
        bg = (0.0, 0.38, 0.42, 1) if is_user else (0.075, 0.12, 0.20, 1)
        fg = (0.75, 1, 1, 1) if is_user else (0.94, 0.97, 1, 1)

        with self.canvas.before:
            Color(*bg)
            self.panel = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[dp(15)]
            )
        self.bind(pos=self._update_panel, size=self._update_panel)

        label = Label(
            text=message,
            color=fg,
            halign="left",
            valign="middle",
            font_size="15sp",
            size_hint_y=None,
            text_size=(Window.width * 0.70, None)
        )
        label.bind(texture_size=lambda obj, size: setattr(obj, "height", size[1] + dp(8)))
        self.add_widget(label)

    def _update_panel(self, *args):
        self.panel.pos = self.pos
        self.panel.size = self.size


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
        self.chatbot = ChatbotEngine()
        self.media_bridge = AndroidMediaBridge(self)
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
        root = BoxLayout(
            orientation="vertical",
            padding=dp(24),
            spacing=dp(16)
        )
        root.canvas.before.clear()
        with root.canvas.before:
            Color(0.015, 0.025, 0.055, 1)
            root_bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(
            pos=lambda obj, val: setattr(root_bg, "pos", val),
            size=lambda obj, val: setattr(root_bg, "size", val)
        )

        root.add_widget(Label(
            text="[b]⚡ LAIBA AI[/b]",
            markup=True,
            font_size="28sp",
            color=(0, 0.9, 1, 1),
            size_hint_y=None,
            height=dp(85)
        ))
        root.add_widget(Label(
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
        root.add_widget(self.api_key_input)

        self.verify_button = Button(
            text="CONNECT GEMINI",
            size_hint_y=None,
            height=dp(54),
            background_normal="",
            background_color=(0, 0.65, 0.75, 1),
            color=(1, 1, 1, 1)
        )
        self.verify_button.bind(on_release=self.verify_api_key)
        root.add_widget(self.verify_button)

        self.setup_status = Label(
            text="Your API key stays in this app's private storage.",
            color=(0.65, 0.8, 0.9, 1),
            halign="center"
        )
        root.add_widget(self.setup_status)
        return root

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
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(9))

        with root.canvas.before:
            Color(0.008, 0.018, 0.045, 1)
            bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda o,v: setattr(bg,"pos",v),
                  size=lambda o,v: setattr(bg,"size",v))

        header = BoxLayout(size_hint_y=None, height=dp(55), spacing=dp(8))
        header.add_widget(Label(
            text="[b]LAIBA[/b] [color=00DFFF]AI[/color]",
            markup=True, font_size="23sp", halign="left",
            color=(0.85,0.96,1,1)))
        self.network_label = Label(
            text="● Checking...", size_hint_x=None, width=dp(105),
            font_size="11sp", color=(1,0.8,0.25,1))
        header.add_widget(self.network_label)

        zip_button = Button(text="ZIP", size_hint_x=None, width=dp(55),
            background_normal="", background_color=(0.02,0.35,0.48,1))
        zip_button.bind(on_release=self.export_zip)
        header.add_widget(zip_button)

        keys_button = Button(
            text="API KEYS", size_hint_x=None, width=dp(78),
            font_size="10sp", background_normal="",
            background_color=(0.35, 0.12, 0.48, 1)
        )
        keys_button.bind(on_release=self.open_api_keys)
        header.add_widget(keys_button)
        root.add_widget(header)

        voice_button = Button(
            text="✦  OPEN VOICE MODE",
            size_hint_y=None,
            height=dp(48),
            font_size="15sp",
            bold=True,
            background_normal="",
            background_color=(0.015, 0.30, 0.48, 1),
            color=(0.35, 0.88, 1, 1)
        )
        voice_button.bind(on_release=self.open_voice_mode)
        root.add_widget(voice_button)

        orb_panel = BoxLayout(orientation="vertical", size_hint_y=None,
                              height=dp(145), padding=dp(8), spacing=dp(2))
        with orb_panel.canvas.before:
            Color(0.025,0.075,0.13,1)
            orb_bg = RoundedRectangle(pos=orb_panel.pos,
                                      size=orb_panel.size, radius=[dp(22)])
        orb_panel.bind(pos=lambda o,v:setattr(orb_bg,"pos",v),
                       size=lambda o,v:setattr(orb_bg,"size",v))
        orb_panel.add_widget(Label(
            text="[color=00DFFF]◉[/color]", markup=True,
            font_size="66sp", color=(0.1,0.8,1,1)))
        orb_panel.add_widget(Label(
            text="[b]LAIBA AI[/b]  •  Always ready",
            markup=True, font_size="13sp", color=(0.7,0.9,1,1),
            size_hint_y=None, height=dp(25)))
        root.add_widget(orb_panel)

        self.three_d_widget = ThreeDCanvasWidget(
            self.threed_engine, size_hint_y=None, height=dp(115))
        root.add_widget(self.three_d_widget)

        controls = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        for label, callback in [
            ("Rotate X", lambda x:self.rotate_mesh(15,0,0)),
            ("Rotate Y", lambda x:self.rotate_mesh(0,15,0)),
            ("Cube / Pyramid", self.toggle_shape)
        ]:
            b = Button(text=label, font_size="11sp",
                background_normal="", background_color=(0.035,0.16,0.25,1),
                color=(0.35,0.9,1,1))
            b.bind(on_release=callback)
            controls.add_widget(b)
        root.add_widget(controls)

        self.chat_scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
        self.message_list = BoxLayout(
            orientation="vertical", size_hint_y=None,
            spacing=dp(9), padding=(dp(3),dp(8)))
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

        input_panel = BoxLayout(orientation="vertical",
            size_hint_y=None, height=dp(105), spacing=dp(5), padding=dp(5))
        with input_panel.canvas.before:
            Color(0.025,0.065,0.11,1)
            panel_bg = RoundedRectangle(pos=input_panel.pos,
                size=input_panel.size, radius=[dp(17)])
        input_panel.bind(pos=lambda o,v:setattr(panel_bg,"pos",v),
                         size=lambda o,v:setattr(panel_bg,"size",v))

        media_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
        for icon_text, callback in [
            ("Camera",self.open_camera),
            ("Gallery",self.open_gallery),
            ("Live",self.open_live_camera),
            ("Mic",self.open_microphone)
        ]:
            b = Button(text=icon_text, font_size="11sp",
                background_normal="", background_color=(0.025,0.23,0.32,1),
                color=(0.4,0.95,1,1))
            b.bind(on_release=callback)
            media_row.add_widget(b)
        input_panel.add_widget(media_row)

        composer = BoxLayout(size_hint_y=None, height=dp(49), spacing=dp(6))
        self.user_input = TextInput(
            hint_text="Message Laiba...", multiline=False,
            background_normal="", background_active="",
            background_color=(0.055,0.10,0.16,1),
            foreground_color=(1,1,1,1), cursor_color=(0,0.9,1,1),
            hint_text_color=(0.5,0.68,0.78,1),
            padding=(dp(12),dp(12)))
        self.user_input.bind(on_text_validate=self.send_message)
        composer.add_widget(self.user_input)

        send_button = Button(text="➤", size_hint_x=None, width=dp(52),
            font_size="22sp", background_normal="",
            background_color=(0,0.65,0.82,1),
            color=(1,1,1,1))
        send_button.bind(on_release=self.send_message)
        composer.add_widget(send_button)
        input_panel.add_widget(composer)
        root.add_widget(input_panel)

        Clock.schedule_once(lambda dt:self.check_network(),0.5)
        Clock.schedule_interval(lambda dt:self.check_network(),30)
        return root

    def add_bubble(self, message, sender="Laiba", save=True):
        message = str(message)
        row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            spacing=dp(4)
        )
        bubble = ChatBubble(message, sender=sender)
        bubble.bind(minimum_height=row.setter("height"))

        if sender == "You":
            row.add_widget(Widget())
            row.add_widget(bubble)
        else:
            row.add_widget(bubble)
            row.add_widget(Widget())

        self.message_list.add_widget(row)
        Clock.schedule_once(
            lambda dt: setattr(self.chat_scroll, "scroll_y", 0), 0.1
        )

        if save:
            self.chat_history.append({"sender": sender, "text": message})
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
        self.voice_status.text = "Listening..."
        self.voice_hint.text = "I'm listening. Speak in Urdu or English."
        self.voice_orb.set_state("listening")
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
            self.voice_status.text = "Listening..."
            self.voice_orb.set_state("listening")
            self.media_bridge.microphone()
        else:
            self.voice_muted = True
            self.voice_mic_button.text = "MIC OFF"
            self.voice_status.text = "Microphone muted"
            self.voice_orb.set_state("ready")
            self.media_bridge.stop_listening()

    def end_voice_call(self, *args):
        self.voice_active = False
        self.voice_muted = True
        self.media_bridge.stop_listening()
        self.media_bridge.stop_speaking()
        self.close_voice_mode()

    def close_voice_mode(self, *args):
        self.voice_active = False
        self.voice_muted = True
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
                result = "Network or AI error: " + str(exc)
            Clock.schedule_once(
                lambda dt: self.finish_reply(result, thinking), 0
            )

        Thread(target=worker, daemon=True).start()

    def send_voice_transcript(self, text):
        text = str(text).strip()
        if not text:
            return

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
                result = "Network or AI error: " + str(exc)

            Clock.schedule_once(
                lambda dt: self.finish_reply(result, thinking), 0
            )

        Thread(target=worker, daemon=True).start()

    def on_tts_state(self, state):
        if not getattr(self, "voice_active", False):
            return

        if state == "speaking":
            self.voice_status.text = "Laiba is speaking..."
            self.voice_orb.set_state("speaking")
            self.voice_hint.text = "You can interrupt Laiba by speaking."

        elif state in ("done", "error"):
            if self.voice_active and not self.voice_muted:
                self.voice_status.text = "Listening..."
                self.voice_orb.set_state("listening")
                self.voice_hint.text = "I'm listening. Speak now."
                Clock.schedule_once(
                    lambda dt: self.media_bridge._restart_listening()
                    if self.voice_active and not self.voice_muted else None,
                    0.5
                )

    def finish_reply(self, result, thinking):
        if thinking.parent:
            thinking.parent.remove_widget(thinking)
        self.add_bubble(str(result), "Laiba")
        self.media_bridge.speak(str(result))


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
                models = self.chatbot.discover_flash_models(key)
                ok = bool(models)
                message = (
                    "Key is working. {} Flash models found.".format(len(models))
                    if ok else "No compatible Flash models found."
                )
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

        try:
            self.chatbot.api_keys = new_keys
            self.chatbot.api_key = new_active
            self.chatbot.model_name = ""
            self.chatbot.model_candidates = []

            CURRENT_CONFIG["GEMINI_API_KEYS"] = new_keys
            CURRENT_CONFIG["GEMINI_API_KEY"] = new_active
            CURRENT_CONFIG["GEMINI_MODEL"] = ""
            CURRENT_CONFIG["GEMINI_MODEL_CANDIDATES"] = []

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

    def export_zip(self, instance):
        try:
            result = self.chatbot.export_project_zip()
            message = result.get("message", result)
        except Exception as exc:
            message = "ZIP export error: " + str(exc)
        self.add_bubble(str(message), "Laiba")


if __name__ == "__main__":
    LaibaKivyApp().run()
