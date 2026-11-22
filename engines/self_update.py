"""Honest update checker: fetches a configured JSON manifest; never self-installs APKs."""
import hashlib
import json
import os
import re
import urllib.request
from urllib.parse import urlparse
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
        value = str(value).strip()
        if not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
            raise ValueError("Invalid version format: {}".format(value))
        return tuple(int(part) for part in value.lstrip("v").split("."))

    @staticmethod
    def _https_url(value, field_name):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("{} must be a non-empty HTTPS URL.".format(field_name))
        parsed = urlparse(value.strip())
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise ValueError("{} must use HTTPS.".format(field_name))
        return value.strip()

    def check_for_updates(self):
        if not self.update_url:
            return {"status": "not_configured", "update_available": False,
                    "current_version": self.version, "latest_version": None,
                    "changelog": "No update manifest URL is configured."}
        self.is_checking = True
        try:
            manifest_url = self._https_url(self.update_url, "Manifest URL")
            request = urllib.request.Request(
                manifest_url,
                headers={"User-Agent": "LaibaAssistant-Updater/1.0"}
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise RuntimeError(
                        "Manifest server returned HTTP {}".format(response.status)
                    )
                raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("Manifest exceeds the 1 MB size limit.")
            manifest = json.loads(raw.decode("utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("Manifest must be a JSON object.")

            latest = manifest.get("version")
            if not latest:
                raise ValueError("Manifest is missing 'version'.")
            current_tuple = self._version_tuple(self.version)
            latest_tuple = self._version_tuple(latest)

            apk_url = manifest.get("apk_url")
            if apk_url is not None:
                apk_url = self._https_url(apk_url, "APK URL")

            sha256 = manifest.get("sha256")
            if sha256 is not None:
                if not isinstance(sha256, str) or not re.fullmatch(
                    r"[0-9a-fA-F]{64}", sha256
                ):
                    raise ValueError("Manifest SHA-256 must contain exactly 64 hex characters.")

            available = latest_tuple > current_tuple
            return {
                "status": "ok",
                "update_available": available,
                "current_version": self.version,
                "latest_version": latest,
                "changelog": str(manifest.get("changelog", "No changelog provided.")),
                "download_url": apk_url,
                "sha256": sha256,
                "signature": manifest.get("signature")
            }
        except Exception as exc:
            return {
                "status": "error",
                "update_available": False,
                "current_version": self.version,
                "latest_version": None,
                "changelog": "Update check failed: {}".format(exc)
            }
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
