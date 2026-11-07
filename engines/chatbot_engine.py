"""Laiba central brain. Uses Gemini REST so no desktop-only SDK is required."""
import json
import os
import mimetypes
import re
import zipfile
import time
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
        self.model_name = CURRENT_CONFIG.get("GEMINI_MODEL", "gemini-3.8-flash")
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

        self.history_file = None
        try:
            from kivy.app import App
            app = App.get_running_app()
            if app and app.user_data_dir:
                self.history_file = Path(app.user_data_dir) / "gemini_history.json"
        except Exception:
            self.history_file = self.project_root / "gemini_history.json"

        self.load_chat_history()

    def load_chat_history(self):
        if not self.history_file:
            return
        try:
            if self.history_file.is_file():
                data = json.loads(self.history_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.chat_history = data[-24:]
        except Exception as exc:
            print("[LAIBA] History load error:", exc)
            self.chat_history = []

    def save_chat_history(self):
        if not self.history_file:
            return
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            safe_history = []
            for item in self.chat_history[-24:]:
                safe_item = {"role": item.get("role"), "parts": []}
                for part in item.get("parts", []):
                    if "text" in part:
                        safe_item["parts"].append({"text": part["text"]})
                    elif "inline_data" in part:
                        safe_item["parts"].append({
                            "text": "[Image was attached in this conversation]"
                        })
                safe_history.append(safe_item)

            temporary = self.history_file.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(safe_history, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            temporary.replace(self.history_file)
        except Exception as exc:
            print("[LAIBA] History save error:", exc)

    def clear_chat_history(self):
        self.chat_history = []
        self.save_chat_history()
        return "Gemini conversation history cleared."

    def init_gemini(self):
        return bool(self.api_key)

    def set_api_key(self, key):
        key = re.sub(r"\s+", "", str(key or "").strip().strip('"').strip("'"))

        if not key:
            return "API key is empty. Nothing was changed."

        if any(ord(ch) < 32 or ord(ch) == 127 for ch in key):
            return "API key contains hidden control characters. Copy it again."

        old_key = self.api_key
        old_config_key = CURRENT_CONFIG.get("GEMINI_API_KEY", "")
        old_model = self.model_name
        old_config_model = CURRENT_CONFIG.get("GEMINI_MODEL", "")

        self.api_key = key

        try:
            available_model = None
            errors = []

            for model in ("gemini-3.8-flash", "gemini-3.5-flash"):
                url = "{}/models/{}".format(
                    self.api_base.rstrip("/"), quote(model, safe="-")
                )
                response = self._request_with_retry("GET",
                    url, params={"key": key}, timeout=self.timeout
                )

                if response.ok:
                    try:
                        data = response.json()
                        methods = data.get("supportedGenerationMethods", [])
                        if methods and "generateContent" not in methods:
                            errors.append(model + ": generateContent unavailable")
                            continue
                    except ValueError:
                        pass

                    available_model = model
                    break

                errors.append("{}: HTTP {}".format(model, response.status_code))

            if not available_model:
                self.api_key = old_key
                return "No supported Gemini model found. Previous key retained. " + "; ".join(errors)

            self.model_name = available_model
            CURRENT_CONFIG["GEMINI_API_KEY"] = key
            CURRENT_CONFIG["GEMINI_MODEL"] = available_model

            if not save_config(CURRENT_CONFIG):
                self.api_key = old_key
                self.model_name = old_model
                CURRENT_CONFIG["GEMINI_API_KEY"] = old_config_key
                CURRENT_CONFIG["GEMINI_MODEL"] = old_config_model
                return "Settings could not be saved. Previous settings restored."

            return "API key saved. Automatically selected " + available_model

        except requests.RequestException as exc:
            self.api_key = old_key
            self.model_name = old_model
            return "Gemini connection failed. Previous key retained: " + str(exc)

    def test_api_connection(self):
        if not self.api_key:
            return {"ok": False, "message": "Gemini API key is not configured."}
        try:
            url = "{}/models/{}".format(
                self.api_base.rstrip("/"), quote(self.model_name, safe="-")
            )
            response = self._request_with_retry("GET",
                url, params={"key": self.api_key}, timeout=self.timeout
            )
            if response.ok:
                return {"ok": True, "message": "Connected using " + self.model_name}
            return {
                "ok": False,
                "message": "Gemini returned HTTP {}: {}".format(
                    response.status_code, self._safe_error(response)
                )
            }
        except requests.RequestException:
            return {"ok": False, "message": "Gemini network connection failed."}

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

    def _request_with_retry(self, method, url, **kwargs):
        retry_statuses = {429, 500, 502, 503, 504}

        for attempt in range(3):
            try:
                response = self.session.request(method, url, **kwargs)

                if response.status_code not in retry_statuses or attempt == 2:
                    return response

                response.close()

            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    raise

            time.sleep(1 + attempt)

        raise requests.RequestException("Request failed after retries.")

    def _gemini(self, prompt, image_path=None):
        if not self.api_key:
            return "Gemini is not connected. Add an API key in Laiba settings before using online AI."
        url = "{}/models/{}:generateContent".format(self.api_base.rstrip("/"), quote(self.model_name, safe="-"))
        parts = [{"text": prompt}]
        if image_path:
            image = Path(image_path)
            if not image.is_file():
                return "Image file was not found."

            mime, _ = mimetypes.guess_type(str(image))
            if mime not in {"image/jpeg", "image/png", "image/webp"}:
                return "Unsupported image format. Use JPG, PNG, or WEBP."

            try:
                image_bytes = image.read_bytes()
                if len(image_bytes) > 20 * 1024 * 1024:
                    return "Image is too large. Maximum size is 20 MB."

                import base64
                parts.append({
                    "inline_data": {
                        "mime_type": mime,
                        "data": base64.b64encode(image_bytes).decode("ascii")
                    }
                })
            except OSError as exc:
                return "Could not read image: {}".format(exc)
        history = self.chat_history[-12:]
        contents = list(history) + [{"role": "user", "parts": parts}]
        payload = {"system_instruction": {"parts": [{"text": "You are Laiba, a helpful assistant. Understand Urdu, Roman Urdu, English, and mixed language. Never claim a device action succeeded unless it was actually executed."}]}, "contents": contents, "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024}}
        try:
            response = self._request_with_retry("POST", url, params={"key": self.api_key}, json=payload, timeout=self.timeout)
            if not response.ok:
                return "Gemini API error (HTTP {}): {}".format(response.status_code, self._safe_error(response))
            data = response.json()
            answer = "".join(p.get("text", "") for p in data.get("candidates", [{}])[0].get("content", {}).get("parts", []))
            if not answer: return "Gemini returned an empty response."
            self.chat_history.extend([
                {"role": "user", "parts": parts},
                {"role": "model", "parts": [{"text": answer}]}
            ])
            self.chat_history = self.chat_history[-24:]
            self.save_chat_history()
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
