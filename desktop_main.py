"""
Laiba Project - Main Application Interface
Tkinter pure-black dynamic assistant featuring:
- Active 3D Model Wireframe/Mesh Canvas Preview (OBJ/STL/GLTF/PLY)
- Gemini Multimodal Dynamic Chatbot & Camera capture tool
- Self-Update Engine & File Modifier Interface
- 1-Click WhatsApp Project Zip & Share Tool
- Termux / Buildozer packaging ready hooks
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from config import CURRENT_CONFIG
from engines.chatbot_engine import ChatbotEngine
from engines.file_modifier import FileModifierEngine
from engines.self_update import SelfUpdateEngine
from engines.threed_engine import ThreeDEngine


class LaibaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Laiba AI Engine — Pure Black 3D Multimodal Assistant")
        self.root.geometry("1020x720")
        self.root.minsize(800, 600)
        self.root.configure(bg="#000000")

        # Core Engines Initialization
        self.chatbot = ChatbotEngine()
        self.self_updater = SelfUpdateEngine()
        self.file_modifier = FileModifierEngine()
        self.threed_engine = ThreeDEngine()

        self.selected_image_path = None
        self.is_listening = False

        self.setup_ui()
        self.init_3d_canvas()

    def setup_ui(self):
        # 1. Header Bar (Pure Black + Neon Cyan Border line)
        header = tk.Frame(self.root, bg="#000000", highlightbackground="#00ffcc", highlightthickness=1)
        header.pack(fill=tk.X, side=tk.TOP, padx=5, pady=(5, 0))

        lbl_title = tk.Label(
            header,
            text="⚡ LAIBA AI SUITE",
            font=("Segoe UI", 15, "bold"),
            fg="#00ffcc",
            bg="#000000"
        )
        lbl_title.pack(side=tk.LEFT, padx=12, pady=8)

        lbl_sub = tk.Label(
            header,
            text=f"v{CURRENT_CONFIG['VERSION']} | Theme: Pure Black | 3D Engine: Active",
            font=("Segoe UI", 9),
            fg="#666666",
            bg="#000000"
        )
        lbl_sub.pack(side=tk.LEFT, padx=5, pady=10)

        # Top Action Buttons
        btn_zip = tk.Button(
            header,
            text="📦 Zip & Share (WhatsApp)",
            command=self.on_zip_and_share,
            bg="#059669",
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            cursor="hand2"
        )
        btn_zip.pack(side=tk.RIGHT, padx=10, pady=8)

        btn_update = tk.Button(
            header,
            text="🔄 Check Update",
            command=self.on_check_update,
            bg="#1d4ed8",
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            padx=10,
            cursor="hand2"
        )
        btn_update.pack(side=tk.RIGHT, padx=5, pady=8)

        # 2. Main Body Container
        body = tk.Frame(self.root, bg="#000000")
        body.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left Panel: 3D Model Interactive Viewport
        left_panel = tk.Frame(body, bg="#080808", width=340, highlightbackground="#1f2937", highlightthickness=1)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left_panel.pack_propagate(False)

        lbl_3d_title = tk.Label(
            left_panel,
            text="🧊 3D MODEL ENGINE CANVAS",
            font=("Segoe UI", 10, "bold"),
            fg="#00ffcc",
            bg="#080808"
        )
        lbl_3d_title.pack(anchor="w", padx=10, pady=(10, 5))

        # 3D Viewport Canvas
        self.canvas_3d = tk.Canvas(
            left_panel,
            bg="#000000",
            highlightbackground="#00ffcc",
            highlightthickness=1,
            height=280
        )
        self.canvas_3d.pack(fill=tk.X, padx=10, pady=5)

        # 3D Controls Frame
        ctrl_3d = tk.Frame(left_panel, bg="#080808")
        ctrl_3d.pack(fill=tk.X, padx=10, pady=5)

        btn_rot_x = tk.Button(ctrl_3d, text="Rotate X", command=lambda: self.rotate_3d(15, 0, 0), bg="#1f2937", fg="#00ffcc", font=("Segoe UI", 8), relief=tk.FLAT)
        btn_rot_x.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        btn_rot_y = tk.Button(ctrl_3d, text="Rotate Y", command=lambda: self.rotate_3d(0, 15, 0), bg="#1f2937", fg="#00ffcc", font=("Segoe UI", 8), relief=tk.FLAT)
        btn_rot_y.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        btn_rot_z = tk.Button(ctrl_3d, text="Rotate Z", command=lambda: self.rotate_3d(0, 0, 15), bg="#1f2937", fg="#00ffcc", font=("Segoe UI", 8), relief=tk.FLAT)
        btn_rot_z.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # Load / Toggle shape buttons
        load_frame = tk.Frame(left_panel, bg="#080808")
        load_frame.pack(fill=tk.X, padx=10, pady=2)

        btn_cube = tk.Button(load_frame, text="Cube Mesh", command=self.load_cube_mesh, bg="#111827", fg="#ffffff", font=("Segoe UI", 8), relief=tk.FLAT)
        btn_cube.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        btn_pyramid = tk.Button(load_frame, text="Pyramid", command=self.load_pyramid_mesh, bg="#111827", fg="#ffffff", font=("Segoe UI", 8), relief=tk.FLAT)
        btn_pyramid.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        btn_open_file = tk.Button(load_frame, text="📁 Import 3D", command=self.import_3d_file, bg="#111827", fg="#38bdf8", font=("Segoe UI", 8, "bold"), relief=tk.FLAT)
        btn_open_file.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # 3D Info Display Box
        self.lbl_3d_info = tk.Label(
            left_panel,
            text="Model: Standby | Mesh: Cube\nVertices: 8 | Faces: 6",
            font=("Consolas", 8),
            fg="#9ca3af",
            bg="#000000",
            justify=tk.LEFT,
            anchor="w",
            padx=8,
            pady=6,
            relief=tk.FLAT
        )
        self.lbl_3d_info.pack(fill=tk.X, padx=10, pady=8)

        # Engine Console Status
        lbl_console = tk.Label(left_panel, text="SYSTEM ENG STATUS", font=("Segoe UI", 9, "bold"), fg="#00ffcc", bg="#080808")
        lbl_console.pack(anchor="w", padx=10, pady=(10, 2))

        self.txt_status = tk.Text(left_panel, bg="#000000", fg="#10b981", font=("Consolas", 8), height=9, relief=tk.FLAT, wrap=tk.WORD)
        self.txt_status.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.update_status("• Black Engine Interface initialized\n• 3D Canvas Renderer active\n• Gemini Multimodal API ready\n• Self-Update Engine active\n• Buildozer APK hooks ready\n")

        # Right Panel: Dynamic Chatbot Conversation UI
        right_panel = tk.Frame(body, bg="#080808", highlightbackground="#1f2937", highlightthickness=1)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Chat Log Window
        self.chat_display = tk.Text(
            right_panel,
            bg="#000000",
            fg="#f3f4f6",
            font=("Consolas", 10),
            wrap=tk.WORD,
            relief=tk.FLAT,
            insertbackground="#00ffcc"
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tag configurations for styled chat text
        self.chat_display.tag_config("user", foreground="#38bdf8", font=("Consolas", 10, "bold"))
        self.chat_display.tag_config("laiba", foreground="#00ffcc", font=("Consolas", 10))
        self.chat_display.tag_config("sys", foreground="#f59e0b", font=("Consolas", 9, "italic"))

        self.chat_display.insert(
            tk.END,
            "System: Welcome to Laiba Pure Black 3D Dynamic AI Engine.\n"
            "System: Voice, Camera, 3D Mesh Engine, and WhatsApp Exporter enabled.\n"
            "System: Type commands, load 3D models, or query Gemini multimodal API below.\n\n",
            "sys"
        )

        # Input Control Section
        control_frame = tk.Frame(right_panel, bg="#080808")
        control_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        # Action Tool Buttons Row
        tools_row = tk.Frame(control_frame, bg="#080808")
        tools_row.pack(fill=tk.X, pady=(0, 6))

        self.btn_mic = tk.Button(
            tools_row,
            text="🎤 Mic",
            command=self.toggle_mic,
            bg="#111827",
            fg="#38bdf8",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            width=8,
            cursor="hand2"
        )
        self.btn_mic.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_cam = tk.Button(
            tools_row,
            text="📷 Camera",
            command=self.capture_camera,
            bg="#111827",
            fg="#38bdf8",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            width=9,
            cursor="hand2"
        )
        self.btn_cam.pack(side=tk.LEFT, padx=4)

        btn_interrupt = tk.Button(
            tools_row,
            text="🛑 Interrupt",
            command=self.on_interrupt,
            bg="#991b1b",
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            width=10,
            cursor="hand2"
        )
        btn_interrupt.pack(side=tk.LEFT, padx=4)

        lbl_img_status = tk.Label(tools_row, textvariable=self.get_img_var(), font=("Segoe UI", 8), fg="#10b981", bg="#080808")
        lbl_img_status.pack(side=tk.RIGHT, padx=5)

        # Text Input & Send Row
        input_row = tk.Frame(control_frame, bg="#080808")
        input_row.pack(fill=tk.X)

        self.entry_msg = tk.Entry(
            input_row,
            bg="#000000",
            fg="#ffffff",
            insertbackground="#00ffcc",
            font=("Segoe UI", 11),
            relief=tk.FLAT,
            highlightbackground="#00ffcc",
            highlightthickness=1
        )
        self.entry_msg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=5)
        self.entry_msg.bind("<Return>", lambda e: self.send_message())

        btn_send = tk.Button(
            input_row,
            text="Send ⚡",
            command=self.send_message,
            bg="#00ffcc",
            fg="#000000",
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT,
            width=9,
            cursor="hand2"
        )
        btn_send.pack(side=tk.RIGHT)

    def get_img_var(self):
        if not hasattr(self, "_img_var"):
            self._img_var = tk.StringVar(value="")
        return self._img_var

    # --- 3D CANVAS METHODS ---
    def init_3d_canvas(self):
        """Draw default 3D mesh representation on the canvas."""
        self.render_3d_view()

    def render_3d_view(self):
        self.canvas_3d.delete("all")
        info = self.threed_engine.render_to_canvas(self.canvas_3d, width=320, height=270)
        self.lbl_3d_info.config(
            text=f"Model: {info['model_name']} | Type: {info['format']}\n"
                 f"Vertices: {info['vertices']} | Faces: {info['faces']}"
        )

    def rotate_3d(self, dx, dy, dz):
        self.threed_engine.rotate(dx, dy, dz)
        self.render_3d_view()

    def load_cube_mesh(self):
        self.threed_engine.active_shape = "cube"
        self.threed_engine.load_cube()
        self.render_3d_view()
        self.update_status("• Loaded default Cube 3D mesh into canvas.")

    def load_pyramid_mesh(self):
        self.threed_engine.active_shape = "pyramid"
        self.threed_engine.load_pyramid()
        self.render_3d_view()
        self.update_status("• Loaded Pyramid 3D mesh into canvas.")

    def import_3d_file(self):
        file_path = filedialog.askopenfilename(
            title="Select 3D Model File",
            filetypes=[("3D Files", "*.obj *.stl *.gltf *.ply"), ("All Files", "*.*")]
        )
        if file_path:
            res = self.threed_engine.load_file(file_path)
            self.render_3d_view()
            self.update_status(f"• Loaded 3D File: {os.path.basename(file_path)}")
            self.log_chat("System", f"3D Model loaded: {res['name']} ({res['format']}) with {res['vertices_count']} vertices.")

    # --- CHATBOT & INTERACTION METHODS ---
    def update_status(self, msg):
        self.txt_status.insert(tk.END, msg + "\n")
        self.txt_status.see(tk.END)

    def log_chat(self, sender, message):
        tag = "laiba"
        if sender == "You":
            tag = "user"
        elif sender == "System":
            tag = "sys"

        self.chat_display.insert(tk.END, f"{sender}: ", tag)
        self.chat_display.insert(tk.END, f"{message}\n\n")
        self.chat_display.see(tk.END)

    def send_message(self):
        user_text = self.entry_msg.get().strip()
        img_path = self.selected_image_path
        self.selected_image_path = None
        self.get_img_var().set("")

        if not user_text and not img_path:
            return

        self.entry_msg.delete(0, tk.END)

        if img_path:
            self.log_chat("You", f"[Image Attached: {os.path.basename(img_path)}] {user_text}")
        else:
            self.log_chat("You", user_text)

        # Process message in background thread to prevent GUI freezing
        threading.Thread(target=self._process_message_thread, args=(user_text, img_path), daemon=True).start()

    def _process_message_thread(self, text, img_path):
        response = self.chatbot.process_message(text, img_path)
        self.root.after(0, lambda: self.log_chat("Laiba", response))

    def toggle_mic(self):
        self.is_listening = not self.is_listening
        if self.is_listening:
            self.btn_mic.config(bg="#0284c7", fg="#ffffff")
            self.log_chat("System", "🎤 Listening... Speak now (Voice Input active).")
            # Simulate speech input demo
            self.root.after(2000, self._simulate_voice_capture)
        else:
            self.btn_mic.config(bg="#111827", fg="#38bdf8")
            self.log_chat("System", "🎤 Voice Input standby.")

    def _simulate_voice_capture(self):
        if self.is_listening:
            voice_sample = "Laiba, rotate 3D view and show current version status"
            self.entry_msg.delete(0, tk.END)
            self.entry_msg.insert(0, voice_sample)
            self.btn_mic.config(bg="#111827", fg="#38bdf8")
            self.is_listening = False
            self.log_chat("System", f"🎤 Captured Voice: \"{voice_sample}\"")

    def capture_camera(self):
        """Simulate or trigger camera image snapshot for Gemini Vision processing."""
        file_path = filedialog.askopenfilename(
            title="Select Image or Camera Snapshot",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All Files", "*.*")]
        )
        if file_path:
            self.selected_image_path = file_path
            self.get_img_var().set(f"📷 Attached: {os.path.basename(file_path)[:15]}")
            self.log_chat("System", f"📷 Camera Snapshot selected: {os.path.basename(file_path)}")
        else:
            # Create a mock camera snapshot image if no file chosen
            mock_path = os.path.join(os.getcwd(), "camera_snapshot.jpg")
            try:
                from PIL import Image, ImageDraw
                img = Image.new('RGB', (400, 300), color=(15, 23, 42))
                d = ImageDraw.Draw(img)
                d.text((20, 140), "Laiba Camera Vision Snapshot", fill=(0, 255, 204))
                img.save(mock_path)
                self.selected_image_path = mock_path
                self.get_img_var().set("📷 Camera Snapshot Ready")
                self.log_chat("System", f"📷 Captured Camera Frame saved to '{mock_path}'.")
            except (OSError, ValueError, ImportError):
                messagebox.showinfo("Camera Engine", "Camera snapshot triggered. Select an image file to process with Gemini vision.")

    def on_interrupt(self):
        res = self.chatbot.trigger_interrupt()
        self.log_chat("System", f"🛑 {res}")

    def on_check_update(self):
        info = self.self_updater.check_for_updates()
        msg = f"Version: {info['current_version']}\nLatest: {info['latest_version']}\nChangelog: {info['changelog']}"
        messagebox.showinfo("Self-Update Engine Status", msg)
        self.update_status(f"• Update check completed: v{info['current_version']} active.")

    def on_zip_and_share(self):
        res = self.chatbot.export_project_zip()
        self.log_chat("System", f"📦 {res}")
        self.update_status("• Project zip created for WhatsApp distribution.")
        messagebox.showinfo("WhatsApp Zip Exporter", res)


def main():
    root = tk.Tk()
    LaibaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
