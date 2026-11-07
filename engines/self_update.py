"""Honest update checker: fetches a configured JSON manifest; never self-installs APKs."""
import hashlib
import json
import os
import urllib.request
from config import CURRENT_CONFIG


class SelfUpdateEngine:
    def __init__(self, current_version=None, update_url=None, timeout=12):
        self.version = current_version or CURRENT_CONFIG.get("VERSION", "1.0.0")
        self.update_url = update_url or CURRENT_CONFIG.get("UPDATE_SERVER_URL", "")
        self.timeout = timeout
        self.is_checking = False
        self.auto_update_enabled = False

    @staticmethod
    def _version_tuple(value):
        try:
            return tuple(int(part) for part in str(value).strip().lstrip("v").split("."))
        except ValueError:
            return ()

    def check_for_updates(self):
        if not self.update_url:
            return {"status": "not_configured", "update_available": False,
                    "current_version": self.version, "latest_version": None,
                    "changelog": "No update manifest URL is configured."}
        self.is_checking = True
        try:
            request = urllib.request.Request(self.update_url, headers={"User-Agent": "LaibaAssistant-Updater/1.0"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise RuntimeError("Manifest server returned HTTP {}".format(response.status))
                manifest = json.loads(response.read(1024 * 1024).decode("utf-8"))
            latest = manifest.get("version")
            if not latest:
                raise ValueError("Manifest is missing 'version'.")
            available = self._version_tuple(latest) > self._version_tuple(self.version)
            return {"status": "ok", "update_available": available,
                    "current_version": self.version, "latest_version": latest,
                    "changelog": str(manifest.get("changelog", "No changelog provided.")),
                    "download_url": manifest.get("apk_url"),
                    "sha256": manifest.get("sha256"),
                    "signature": manifest.get("signature")}
        except Exception as exc:
            return {"status": "error", "update_available": False,
                    "current_version": self.version, "latest_version": None,
                    "changelog": "Update check failed: {}".format(exc)}
        finally:
            self.is_checking = False

    @staticmethod
    def verify_file(path, expected_sha256):
        if not expected_sha256:
            return False, "Manifest has no SHA-256 digest."
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        valid = digest.hexdigest().lower() == expected_sha256.lower()
        return valid, "SHA-256 verified." if valid else "SHA-256 mismatch."

    def apply_update_patch(self, *args, **kwargs):
        return "Automatic source patching is disabled. Review and confirm changes through FileModifierEngine."

    def start_background_updater(self, callback_on_update=None):
        return "Background updates are not started automatically; Android background limits and user consent apply."

    def upgrade_engine_capability(self, *args, **kwargs):
        return "Engine self-modification is disabled for safety. Use reviewed, backed-up file changes."
