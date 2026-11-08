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
        self.model_name = CURRENT_CONFIG.get("GEMINI_MODEL", "")
        self.model_candidates = CURRENT_CONFIG.get("GEMINI_MODEL_CANDIDATES", [])
        self.api_base = CURRENT_CONFIG.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta")
        self.timeout = int(CURRENT_CONFIG.get("GEMINI_TIMEOUT", 30))
        self.is_speaking = False
        self.is_listening = False
        self.interrupt_flag = False
        self.file_modifier = FileModifierEngine(str(self.project_root))
        self.self_updater = SelfUpdateEngine()
        self.threed_engine = ThreeDEngine()
        self.router = CommandRouter()
        from engines.reminder_bridge import ReminderBridge
        self.reminder_bridge = ReminderBridge()
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

    def discover_flash_models(self, key=None):
        key = key or self.api_key
        if not key:
            return []

        models = []
        page_token = None

        for _ in range(10):
            params = {"key": key, "pageSize": 100}
            if page_token:
                params["pageToken"] = page_token

            response = self._request_with_retry(
                "GET", self.api_base.rstrip("/") + "/models",
                params=params, timeout=self.timeout
            )
            if not response.ok:
                raise requests.RequestException(
                    "ListModels HTTP {}: {}".format(
                        response.status_code, self._safe_error(response)
                    )
                )

            data = response.json()
            for item in data.get("models", []):
                name = str(item.get("name", "")).replace("models/", "")
                methods = item.get("supportedGenerationMethods", [])
                lower = name.lower()

                if ("flash" in lower and
                    "generateContent" in methods and
                    not any(x in lower for x in (
                        "tts", "live", "transcribe", "translate",
                        "image", "embedding"
                    ))):
                    models.append(name)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        def version_key(name):
            return tuple(int(x) for x in re.findall(r"[0-9]+", name))

        return sorted(set(models), key=version_key, reverse=True)

    def set_api_key(self, key):
        key = re.sub(r"\\s+", "", str(key or "").strip().strip('"').strip("'"))
        if not key:
            return "API key is empty. Nothing was changed."

        old_key = self.api_key
        old_model = self.model_name
        old_candidates = self.model_candidates
        old_config = dict(CURRENT_CONFIG)

        try:
            candidates = self.discover_flash_models(key)
            if not candidates:
                return "No accessible Flash model supporting generateContent was found."

            self.api_key = key
            self.model_candidates = candidates
            self.model_name = ""

            CURRENT_CONFIG["GEMINI_API_KEY"] = key
            CURRENT_CONFIG["GEMINI_MODEL"] = ""
            CURRENT_CONFIG["GEMINI_MODEL_CANDIDATES"] = candidates

            if not save_config(CURRENT_CONFIG):
                CURRENT_CONFIG.clear()
                CURRENT_CONFIG.update(old_config)
                self.api_key = old_key
                self.model_name = old_model
                self.model_candidates = old_candidates
                return "Settings could not be saved. Previous settings restored."

            return "API key saved. Automatic Flash selection enabled. Found {} compatible models.".format(len(candidates))

        except Exception as exc:
            self.api_key = old_key
            self.model_name = old_model
            self.model_candidates = old_candidates
            return "Gemini model discovery failed: {}".format(str(exc)[:400])

    def test_api_connection(self):
        if not self.api_key:
            return {"ok": False, "message": "Gemini API key is not configured."}
        try:
            candidates = self.discover_flash_models()
            if not candidates:
                return {"ok": False, "message": "No compatible Flash models found."}
            self.model_candidates = candidates
            return {
                "ok": True,
                "message": "Gemini connected. {} compatible Flash models discovered.".format(len(candidates))
            }
        except Exception as exc:
            return {"ok": False, "message": "Gemini discovery failed: {}".format(str(exc)[:300])}

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
            return "Gemini is not connected. Add an API key in Laiba settings."

        parts = [{"text": prompt}]
        if image_path:
            image = Path(image_path)
            if not image.is_file():
                return "Image file was not found."
            mime, _ = mimetypes.guess_type(str(image))
            if mime not in {"image/jpeg", "image/png", "image/webp"}:
                return "Unsupported image format. Use JPG, PNG, or WEBP."
            try:
                import base64
                image_bytes = image.read_bytes()
                if len(image_bytes) > 20 * 1024 * 1024:
                    return "Image is too large. Maximum size is 20 MB."
                parts.append({
                    "inline_data": {
                        "mime_type": mime,
                        "data": base64.b64encode(image_bytes).decode("ascii")
                    }
                })
            except OSError as exc:
                return "Could not read image: {}".format(exc)

        try:
            candidates = self.model_candidates
            if not candidates:
                candidates = self.discover_flash_models()
                self.model_candidates = candidates

            if not candidates:
                return "No compatible Gemini Flash models are available."

            history = self.chat_history[-12:]
            contents = list(history) + [{"role": "user", "parts": parts}]
            payload = {
                "system_instruction": {"parts": [{
                    "text": "You are Laiba, a helpful assistant. Understand Urdu, Roman Urdu, English, and mixed language. Never claim a device action succeeded unless it was actually executed."
                }]},
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1024
                }
            }

            errors = []
            for model in candidates:
                url = "{}/models/{}:generateContent".format(
                    self.api_base.rstrip("/"), quote(model, safe="-")
                )
                try:
                    response = self._request_with_retry(
                        "POST", url, params={"key": self.api_key},
                        json=payload, timeout=self.timeout
                    )
                    if not response.ok:
                        errors.append("{}: HTTP {}".format(model, response.status_code))
                        continue

                    data = response.json()
                    answer = "".join(
                        p.get("text", "")
                        for p in data.get("candidates", [{}])[0]
                        .get("content", {}).get("parts", [])
                    )
                    if not answer:
                        errors.append("{}: empty response".format(model))
                        continue

                    self.model_name = model
                    CURRENT_CONFIG["GEMINI_MODEL"] = ""
                    CURRENT_CONFIG["GEMINI_MODEL_CANDIDATES"] = self.model_candidates
                    save_config(CURRENT_CONFIG)

                    self.chat_history.extend([
                        {"role": "user", "parts": parts},
                        {"role": "model", "parts": [{"text": answer}]}
                    ])
                    self.chat_history = self.chat_history[-24:]
                    self.save_chat_history()
                    print("[LAIBA] Active Gemini model:", model)
                    return answer

                except requests.RequestException as exc:
                    errors.append("{}: {}".format(model, str(exc)[:120]))
                    continue
                except (ValueError, KeyError, IndexError) as exc:
                    errors.append("{}: invalid response".format(model))
                    continue

            return "All discovered Gemini Flash models failed. " + "; ".join(errors[:8])

        except requests.RequestException as exc:
            return "Gemini network/discovery error: {}".format(
                str(exc).replace(self.api_key, "[REDACTED]")
            )

    def process_message(self, user_text, image_path=None):
        text = str(user_text or "").strip()
        if not text and not image_path: return "Please type or say something."
        self.interrupt_flag = False
        intent = self.router.route(text)
        if intent == "reminder_schedule":
            from engines.reminder_parser import parse_reminder
            reminder, error = parse_reminder(text)
            if error:
                return error
            title, message, time_ms, repeat_ms = reminder
            result = self.reminder_bridge.schedule(
                title, message, time_ms, repeat_ms
            )
            if result:
                return "جی، یاددہانی لگا دی ہے۔ مقررہ وقت پر آپ کو اطلاع دوں گی۔"
            return "معذرت، یاددہانی محفوظ نہیں ہو سکی۔ Android میں Laiba کی اجازتیں چیک کریں۔"
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
