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
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Rectangle, Line
from kivy.core.window import Window

from config import CURRENT_CONFIG
from engines.chatbot_engine import ChatbotEngine
from engines.threed_engine import ThreeDEngine

# Set Window dark background
Window.clearcolor = (0, 0, 0, 1)


class ThreeDCanvasWidget(BoxLayout):
    def __init__(self, threed_engine, **kwargs):
        super().__init__(**kwargs)
        self.threed_engine = threed_engine
        self.bind(size=self.update_canvas, pos=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0.03, 0.03, 0.03, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(0, 1, 0.8, 1)
            Line(rectangle=(self.x, self.y, self.width, self.height), width=1)

        # Draw the engine's rotated 3D projection in widget-local coordinates.
        self.canvas.clear()
        with self.canvas:
            Color(0, 1, 0.8, 0.9)
            scale = min(self.width, self.height) * 0.65
            segments = self.threed_engine.get_projected_wireframe(
                scale=scale, center_x=self.width / 2, center_y=self.height / 2
            )
            for start, end in segments:
                Line(points=[self.x + start[0], self.y + start[1],
                             self.x + end[0], self.y + end[1]], width=1.5)


class LaibaKivyApp(App):
    def build(self):
        # Store API settings inside Android app-private storage.
        app_config.CONFIG_FILE = os.path.join(
            self.user_data_dir, "laiba_config.json"
        )

        saved_config = app_config.load_config()
        CURRENT_CONFIG.clear()
        CURRENT_CONFIG.update(saved_config)

        # Migrate retired Gemini model to the current stable model.
        if CURRENT_CONFIG.get("GEMINI_MODEL") == "gemini-2.0-flash":
            CURRENT_CONFIG["GEMINI_MODEL"] = "gemini-3.8-flash"

        self.title = "Google Gemini AI Setup"
        self.chatbot = ChatbotEngine()
        self.threed_engine = ThreeDEngine()

        if self.chatbot.api_key:
            self.title = CURRENT_CONFIG.get("APP_NAME", "Laiba Assistant")
            return self.build_main_screen()

        root = BoxLayout(
            orientation="vertical",
            padding=24,
            spacing=16
        )

        root.add_widget(Label(
            text="[b]CONNECT GOOGLE GEMINI AI[/b]",
            markup=True,
            font_size="23sp",
            color=(0, 1, 0.8, 1),
            size_hint_y=None,
            height=80
        ))

        root.add_widget(Label(
            text="Enter your Google Gemini AI API Key to activate Laiba.",
            font_size="16sp",
            color=(1, 1, 1, 1),
            halign="center",
            size_hint_y=None,
            height=65
        ))

        self.api_key_input = TextInput(
            hint_text="Paste your Google Gemini AI API Key",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=55,
            background_color=(0.08, 0.08, 0.08, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0, 1, 0.8, 1)
        )
        self.api_key_input.bind(
            on_text_validate=self.verify_api_key
        )
        root.add_widget(self.api_key_input)

        self.verify_button = Button(
            text="VERIFY CONNECTION",
            size_hint_y=None,
            height=55,
            background_color=(0, 0.65, 0.48, 1),
            color=(1, 1, 1, 1)
        )
        self.verify_button.bind(
            on_release=self.verify_api_key
        )
        root.add_widget(self.verify_button)

        self.setup_status = Label(
            text="Create your API key in Google AI Studio, then paste it here.",
            color=(0.7, 0.7, 0.7, 1),
            halign="center"
        )
        root.add_widget(self.setup_status)

        return root

    def verify_api_key(self, instance):
        from threading import Thread
        from kivy.clock import Clock

        key = self.api_key_input.text.strip()

        if not key:
            self.setup_status.text = "Please enter your Google Gemini AI API Key."
            return

        self.verify_button.disabled = True
        self.setup_status.text = "Verifying your Google Gemini AI connection..."

        def worker():
            old_key = self.chatbot.api_key
            self.chatbot.api_key = key

            try:
                result = self.chatbot.test_api_connection()
                ok = bool(result.get("ok"))
                message = str(result.get("message", "Verification failed."))

                if ok:
                    save_result = self.chatbot.set_api_key(key)
                    if "saved successfully" not in save_result.lower():
                        ok = False
                        message = save_result
            except Exception as exc:
                ok = False
                message = str(exc)
            finally:
                if not ok:
                    self.chatbot.api_key = old_key

            message = message.replace(key, "[HIDDEN]")
            Clock.schedule_once(
                lambda dt: self._finish_api_verification(ok, message), 0
            )

        Thread(target=worker, daemon=True).start()

    def _finish_api_verification(self, ok, message):
        if ok:
            self.setup_status.text = "Google Gemini AI connected successfully!"
            self.title = CURRENT_CONFIG.get("APP_NAME", "Laiba Assistant")
            self.root.clear_widgets()
            self.root.add_widget(self.build_main_screen())
        else:
            self.verify_button.disabled = False
            self.setup_status.text = "Connection failed: " + message

    def build_main_screen(self):
        self.title = CURRENT_CONFIG.get("APP_NAME", "Laiba Assistant")
        self.chatbot = ChatbotEngine()
        self.threed_engine = ThreeDEngine()

        root_layout = BoxLayout(orientation='vertical', padding=8, spacing=8)

        # Header
        header = BoxLayout(size_hint_y=None, height=45, spacing=5)
        lbl_title = Label(
            text="[b]⚡ LAIBA AI APK[/b]",
            markup=True,
            color=(0, 1, 0.8, 1),
            font_size='18sp'
        )
        header.add_widget(lbl_title)

        btn_zip = Button(
            text="📦 Zip & Share",
            size_hint_x=None,
            width=110,
            background_color=(0.02, 0.59, 0.41, 1)
        )
        btn_zip.bind(on_release=self.export_zip)
        header.add_widget(btn_zip)

        root_layout.add_widget(header)


        # 3D View Widget
        self.three_d_widget = ThreeDCanvasWidget(self.threed_engine, size_hint_y=0.35)
        root_layout.add_widget(self.three_d_widget)

        # 3D Controls
        ctrl_row = BoxLayout(size_hint_y=None, height=35, spacing=5)
        btn_rot_x = Button(text="Rot X", background_color=(0.12, 0.16, 0.22, 1))
        btn_rot_x.bind(on_release=lambda x: self.rotate_mesh(15, 0, 0))

        btn_rot_y = Button(text="Rot Y", background_color=(0.12, 0.16, 0.22, 1))
        btn_rot_y.bind(on_release=lambda x: self.rotate_mesh(0, 15, 0))

        btn_shape = Button(text="Cube / Pyramid", background_color=(0.07, 0.09, 0.15, 1))
        btn_shape.bind(on_release=self.toggle_shape)

        ctrl_row.add_widget(btn_rot_x)
        ctrl_row.add_widget(btn_rot_y)
        ctrl_row.add_widget(btn_shape)
        root_layout.add_widget(ctrl_row)

        # Chat Log Box
        self.chat_log = TextInput(
            text="System: Laiba APK Environment Initialized.\nSystem: Text chat is available when a Gemini API key is configured.\nSystem: Voice and camera integrations are not enabled in this build.\n\n",
            readonly=True,
            multiline=True,
            background_color=(0.03, 0.03, 0.03, 1),
            foreground_color=(0.95, 0.95, 0.95, 1),
            size_hint_y=0.45
        )
        root_layout.add_widget(self.chat_log)

        # Input Box Row
        input_row = BoxLayout(size_hint_y=None, height=45, spacing=5)
        self.user_input = TextInput(
            hint_text="Type message or command...",
            multiline=False,
            background_color=(0.08, 0.08, 0.08, 1),
            foreground_color=(1, 1, 1, 1)
        )
        self.user_input.bind(on_text_validate=self.send_message)

        btn_send = Button(
            text="Send ⚡",
            size_hint_x=None,
            width=80,
            background_color=(0, 1, 0.8, 1),
            color=(0, 0, 0, 1)
        )
        btn_send.bind(on_release=self.send_message)

        input_row.add_widget(self.user_input)
        input_row.add_widget(btn_send)
        root_layout.add_widget(input_row)

        return root_layout

    def save_api_key(self, instance):
        result = self.chatbot.set_api_key(self.api_key_input.text)
        self.api_key_input.text = ""
        self.chat_log.text += f"System: {result}\n\n"

    def rotate_mesh(self, dx, dy, dz):
        self.threed_engine.rotate(dx, dy, dz)
        self.three_d_widget.update_canvas()

    def toggle_shape(self, instance):
        if self.threed_engine.active_shape == "cube":
            self.threed_engine.load_pyramid()
        else:
            self.threed_engine.load_cube()
        self.three_d_widget.update_canvas()

    def send_message(self, *args):
        from threading import Thread
        from kivy.clock import Clock
        text = self.user_input.text.strip()
        if not text:
            return
        self.user_input.text = ""
        self.chat_log.text += f"You: {text}\nLaiba: thinking...\n"
        def worker():
            result = self.chatbot.process_message(text)
            Clock.schedule_once(lambda dt: self._append_reply(result), 0)
        Thread(target=worker, daemon=True).start()

    def _append_reply(self, result):
        self.chat_log.text = self.chat_log.text.replace("Laiba: thinking...\n", "")
        self.chat_log.text += f"Laiba: {result}\n\n"

    def export_zip(self, instance):
        res = self.chatbot.export_project_zip()
        self.chat_log.text += f"System: {res.get('message', res)}\n\n"


if __name__ == "__main__":
    LaibaKivyApp().run()
