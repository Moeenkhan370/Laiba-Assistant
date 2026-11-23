"""Honest update checker: fetches a configured JSON manifest; never self-installs APKs."""
import hashlib
import json
import os
import re
import ssl
import tempfile
import urllib.request
import certifi
from urllib.parse import urlparse
from config import CURRENT_CONFIG


class SelfUpdateEngine:
    def __init__(self, current_version=None, update_url=None, timeout=12, state_path=None):
        self.version = current_version or CURRENT_CONFIG.get("VERSION", "1.0.0")
        self.update_url = CURRENT_CONFIG.get("UPDATE_SERVER_URL", "") if update_url is None else update_url
        self.timeout = timeout
        self.is_checking = False
        self.auto_update_enabled = False
        self.state_path = state_path

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
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("{} must use a valid HTTPS URL without embedded credentials.".format(field_name))
        return value.strip()

    @staticmethod
    def _ssl_context():
        """Use certifi CA roots with SSL verification enabled."""
        return ssl.create_default_context(cafile=certifi.where())

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
            with urllib.request.urlopen(request, timeout=self.timeout, context=self._ssl_context()) as response:
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

            available = latest_tuple > current_tuple
            apk_url = manifest.get("apk_url")
            sha256 = manifest.get("sha256")
            if available:
                apk_url = self._https_url(apk_url, "APK URL")
                if not isinstance(sha256, str) or not re.fullmatch(
                    r"[0-9a-fA-F]{64}", sha256
                ):
                    raise ValueError(
                        "A valid 64-character SHA-256 digest is required."
                    )
            elif apk_url is not None:
                apk_url = self._https_url(apk_url, "APK URL")
            if sha256 is not None and (
                not isinstance(sha256, str)
                or not re.fullmatch(r"[0-9a-fA-F]{64}", sha256)
            ):
                raise ValueError("Manifest SHA-256 must contain exactly 64 hex characters.")

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

    def download_apk(self, url, expected_sha256, destination,
                     max_bytes=512 * 1024 * 1024):
        url = self._https_url(url, "APK URL")
        if not isinstance(expected_sha256, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", expected_sha256
        ):
            raise ValueError("A valid SHA-256 digest is required.")

        class HTTPSRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                if urlparse(newurl).scheme.lower() != "https":
                    raise ValueError("HTTPS downgrade redirect rejected.")
                return super().redirect_request(
                    req, fp, code, msg, headers, newurl
                )

        destination = os.path.abspath(os.fspath(destination))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        temporary = None
        digest = hashlib.sha256()
        total = 0
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "LaibaAssistant-Updater/1.0"}
            )
            opener = urllib.request.build_opener(
                HTTPSRedirectHandler,
                urllib.request.HTTPSHandler(context=self._ssl_context())
            )
            with opener.open(request, timeout=self.timeout) as response:
                if urlparse(response.geturl()).scheme.lower() != "https":
                    raise ValueError("Insecure final download URL.")
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=os.path.dirname(destination),
                    prefix=".laiba-update-", suffix=".part", delete=False
                ) as output:
                    temporary = output.name
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("APK exceeds download size limit.")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())

            actual = digest.hexdigest()
            if actual.lower() != expected_sha256.lower():
                raise ValueError("APK SHA-256 mismatch; installation blocked.")
            os.replace(temporary, destination)
            temporary = None
            return {"path": destination, "sha256": actual, "bytes": total}
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

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

    def save_update_state(self, state):
        if not self.state_path:
            raise ValueError("Update state path is not configured.")
        directory = os.path.dirname(os.path.abspath(self.state_path))
        os.makedirs(directory, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".update-state-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(state, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.state_path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)

    def load_update_state(self):
        if not self.state_path or not os.path.isfile(self.state_path):
            return {"status": "idle"}
        try:
            with open(self.state_path, encoding="utf-8") as stream:
                state = json.load(stream)
            if not isinstance(state, dict):
                raise ValueError("Invalid update state.")
            return state
        except (OSError, ValueError, json.JSONDecodeError):
            return {"status": "failed", "reason": "Update state file is invalid."}

    def mark_update_pending(self, target_version, apk_path, sha256):
        if not target_version or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", str(target_version)):
            raise ValueError("Invalid target version.")
        self.save_update_state({
            "status": "pending",
            "current_version": self.version,
            "target_version": str(target_version),
            "apk_path": os.path.abspath(apk_path),
            "sha256": str(sha256).lower()
        })

    def resolve_update_state(self, current_version=None):
        state = self.load_update_state()
        if state.get("status") != "pending":
            return state
        current = self._version_tuple(current_version or self.version)
        target = self._version_tuple(state.get("target_version", ""))
        state["status"] = "confirmed" if current == target else "failed"
        state["installed_version"] = str(current_version or self.version)
        if state["status"] == "failed":
            state["reason"] = "App resumed without the target version; installation was cancelled or unsuccessful."
        self.save_update_state(state)
        return state

    def apply_update_patch(self, *args, **kwargs):
        return "Automatic source patching is disabled. Review and confirm changes through FileModifierEngine."

    def start_background_updater(self, callback_on_update=None):
        return "Background updates are not started automatically; Android background limits and user consent apply."

    def upgrade_engine_capability(self, *args, **kwargs):
        return "Engine self-modification is disabled for safety. Use reviewed, backed-up file changes."
