"""
Laiba Project - Kivy / Termux Buildozer APK Compatibility Application
Allows compiling Laiba project into an Android APK using Buildozer in Termux.
Includes a Kivy UI, lightweight mesh preview, and Gemini text/image request engine. Voice/camera services require separate Android bridges.
"""

import os
import sys
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

        # API key setup is explicit; the key is stored in the app-private config.
        key_row = BoxLayout(size_hint_y=None, height=40, spacing=5)
        self.api_key_input = TextInput(
            hint_text="Gemini API key (stored privately on this device)",
            password=True, multiline=False,
            background_color=(0.08, 0.08, 0.08, 1),
            foreground_color=(1, 1, 1, 1)
        )
        btn_save_key = Button(text="Save Key", size_hint_x=None, width=90)
        btn_save_key.bind(on_release=self.save_api_key)
        key_row.add_widget(self.api_key_input)
        key_row.add_widget(btn_save_key)
        root_layout.add_widget(key_row)

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
