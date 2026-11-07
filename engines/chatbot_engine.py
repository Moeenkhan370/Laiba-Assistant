"""Laiba central brain. Uses Gemini REST so no desktop-only SDK is required."""
import json
import os
import re
import zipfile
from pathlib import Path
from urllib.parse import quote
import requests
from config import CURRENT_CONFIG, save_config
from engines.command_router import CommandRouter
from engines.file_modifier import FileModifierEngine
from engines.self_update import SelfUpdateEngine
from engines.threed_engine import ThreeDEngine


class ChatbotEngine:
    def __init__(self, project_root=None):
        self.project_root = Path(project_root or Path(__file__).resolve().parents[1]).resolve()
        self.api_key = str(CURRENT_CONFIG.get("GEMINI_API_KEY", "")).strip()
        self.model_name = CURRENT_CONFIG.get("GEMINI_MODEL", "gemini-2.0-flash")
        self.api_base = CURRENT_CONFIG.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta")
        self.timeout = int(CURRENT_CONFIG.get("GEMINI_TIMEOUT", 30))
        self.is_speaking = False
        self.is_listening = False
        self.interrupt_flag = False
        self.file_modifier = FileModifierEngine(str(self.project_root))
        self.self_updater = SelfUpdateEngine()
        self.threed_engine = ThreeDEngine()
        self.router = CommandRouter()
        self.chat_history = []
        self.session = requests.Session()

    def init_gemini(self):
        return bool(self.api_key)

    def set_api_key(self, key):
        key = str(key or "").strip().strip('"').strip("'")
        key = re.sub(r"\\s+", "", key)

        if not key:
            return "API key is empty. Nothing was changed."

        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            return "Invalid API key format. Check the copied key and try again."

        old_key = self.api_key
        old_config_key = CURRENT_CONFIG.get("GEMINI_API_KEY", "")

        self.api_key = key
        CURRENT_CONFIG["GEMINI_API_KEY"] = key

        if not save_config(CURRENT_CONFIG):
            self.api_key = old_key
            CURRENT_CONFIG["GEMINI_API_KEY"] = old_config_key
            return "API key could not be saved. Previous settings restored."

        return "API key saved successfully. Now test the Gemini connection."

    def test_api_connection(self):
        if not self.api_key:
            return {"ok": False, "message": "Gemini API key is not configured."}
        try:
            url = "{}/models/{}".format(self.api_base.rstrip("/"), quote(self.model_name, safe="-"))
            response = self.session.get(url, params={"key": self.api_key}, timeout=self.timeout)
            if response.ok:
                return {"ok": True, "message": "Gemini model endpoint is reachable."}
            return {"ok": False, "message": "Gemini returned HTTP {}: {}".format(response.status_code, self._safe_error(response))}
        except requests.RequestException as exc:
            return {"ok": False, "message": "Network error: {}".format(exc)}

    @staticmethod
    def _safe_error(response):
        try:
            data = response.json()
            return str(data.get("error", {}).get("message", "Request failed"))[:500]
        except Exception:
            return "Request failed"

    def trigger_interrupt(self):
        self.interrupt_flag = True
        self.is_speaking = False
        return "Laiba response interruption requested. Speech playback must be stopped by the active audio service."

    def create_whatsapp_zip(self, output_path=None):
        export_dir = self.project_root / "exports"
        export_dir.mkdir(exist_ok=True)
        destination = Path(output_path).resolve() if output_path else export_dir / "Laiba_Project_Export.zip"
        if self.project_root == destination or self.project_root in destination.parents:
            if destination.exists(): destination.unlink()
        ignored_dirs = {".git", "__pycache__", ".pytest_cache", ".buildozer", "bin", "venv", ".venv", "env", "exports", ".laiba_backups"}
        ignored_names = {"laiba_config.json", ".env", "secrets.json"}
        ignored_suffixes = {".pyc", ".pyo", ".pyd", ".apk", ".aab", ".keystore"}
        try:
            with zipfile.ZipFile(str(destination), "w", zipfile.ZIP_DEFLATED) as archive:
                for root, dirs, files in os.walk(str(self.project_root)):
                    dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
                    for name in files:
                        path = Path(root) / name
                        if name in ignored_names or path.suffix.lower() in ignored_suffixes or name.endswith(".zip"):
                            continue
                        if path == destination or ".laiba_backups" in path.parts:
                            continue
                        archive.write(str(path), str(path.relative_to(self.project_root)))
            with zipfile.ZipFile(str(destination), "r") as archive:
                bad = archive.testzip()
                if bad: raise RuntimeError("ZIP integrity check failed at {}".format(bad))
            return {"status": "success", "zip_path": str(destination), "message": "Project ZIP created and integrity-checked: {}".format(destination)}
        except Exception as exc:
            return {"status": "error", "message": "ZIP export failed: {}".format(exc)}

    def export_project_zip(self):
        return self.create_whatsapp_zip()

    def handle_buildozer_commands(self, query):
        if any(term in query.lower() for term in ("build apk", "buildozer", "package apk")):
            return "Build from the project root with: buildozer android debug. This project includes a Buildozer spec; successful APK creation still depends on a compatible ARM64/Ubuntu toolchain."
        return None

    def _gemini(self, prompt, image_path=None):
        if not self.api_key:
            return "Gemini is not connected. Add an API key in Laiba settings before using online AI."
        url = "{}/models/{}:generateContent".format(self.api_base.rstrip("/"), quote(self.model_name, safe="-"))
        parts = [{"text": prompt}]
        if image_path:
            image = Path(image_path)
            if not image.is_file(): return "Image file was not found."
            mime = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
            import base64
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(image.read_bytes()).decode("ascii")}})
        history = self.chat_history[-12:]
        contents = list(history) + [{"role": "user", "parts": parts}]
        payload = {"system_instruction": {"parts": [{"text": "You are Laiba, a helpful assistant. Understand Urdu, Roman Urdu, English, and mixed language. Never claim a device action succeeded unless it was actually executed."}]}, "contents": contents, "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024}}
        try:
            response = self.session.post(url, params={"key": self.api_key}, json=payload, timeout=self.timeout)
            if not response.ok:
                return "Gemini API error (HTTP {}): {}".format(response.status_code, self._safe_error(response))
            data = response.json()
            answer = "".join(p.get("text", "") for p in data.get("candidates", [{}])[0].get("content", {}).get("parts", []))
            if not answer: return "Gemini returned an empty response."
            self.chat_history.extend([{"role": "user", "parts": [{"text": prompt}]}, {"role": "model", "parts": [{"text": answer}]}])
            self.chat_history = self.chat_history[-24:]
            return answer
        except requests.Timeout:
            return "Gemini request timed out. Please try again."
        except requests.RequestException as exc:
            return "Network error while contacting Gemini: {}".format(str(exc).replace(self.api_key, "[REDACTED]") if self.api_key else str(exc))
        except (ValueError, KeyError, IndexError) as exc:
            return "Could not parse Gemini response: {}".format(exc)

    def process_message(self, user_text, image_path=None):
        text = str(user_text or "").strip()
        if not text and not image_path: return "Please type or say something."
        self.interrupt_flag = False
        intent = self.router.route(text)
        if intent == "update_check":
            info = self.self_updater.check_for_updates()
            return "Update check: {}\nCurrent: {}\nLatest: {}\n{}".format(info["status"], info["current_version"], info.get("latest_version") or "unknown", info["changelog"])
        if intent == "zip_export":
            return self.create_whatsapp_zip()["message"]
        if intent == "3d_status":
            stats = self.threed_engine.model_stats
            return "3D engine ready. Model: {}; vertices: {}; faces: {}. Supported loaders: OBJ, STL, ASCII PLY. GLTF/GLB are not yet supported.".format(stats.get("file"), stats.get("vertices"), stats.get("faces"))
        if intent == "file_list":
            return "Project files: {}".format(", ".join(self.file_modifier.list_dir(".")))
        if intent == "open_link":
            return "Opening apps and websites requires the Android intent bridge; that integration is not yet enabled in this build."
        build = self.handle_buildozer_commands(text)
        if build: return build
        return self._gemini(text or "Please analyze this image.", image_path)
