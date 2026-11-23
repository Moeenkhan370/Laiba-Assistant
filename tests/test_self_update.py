import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engines.self_update import SelfUpdateEngine


class SelfUpdateTests(unittest.TestCase):

    def test_unconfigured_update_url(self):
        engine = SelfUpdateEngine("1.0.0", "")
        self.assertEqual(engine.check_for_updates()["status"], "not_configured")

    def test_detects_newer_version(self):
        engine = SelfUpdateEngine("1.0.0", "https://example.com/update.json")
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps({
            "version": "1.1.0",
            "changelog": "Security improvements",
            "apk_url": "https://example.com/laiba.apk",
            "sha256": "0" * 64
        }).encode()
        with patch("engines.self_update.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = response
            result = engine.check_for_updates()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["update_available"])

    def test_rejects_invalid_version(self):
        engine = SelfUpdateEngine("1.0.0", "https://example.com/update.json")
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"version":"invalid"}'
        with patch("engines.self_update.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = response
            result = engine.check_for_updates()
        self.assertEqual(result["status"], "error")

    def test_rejects_non_object_manifest(self):
        engine = SelfUpdateEngine("1.0.0", "https://example.com/update.json")
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'["invalid"]'
        with patch("engines.self_update.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = response
            result = engine.check_for_updates()
        self.assertEqual(result["status"], "error")

    def test_verifies_file_sha256(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.apk"
            path.write_bytes(b"Laiba test APK")
            digest = hashlib.sha256(b"Laiba test APK").hexdigest()
            self.assertTrue(SelfUpdateEngine.verify_file(path, digest)[0])
            self.assertFalse(SelfUpdateEngine.verify_file(path, "0" * 64)[0])

    def test_rejects_missing_digest(self):
        self.assertFalse(SelfUpdateEngine.verify_file("missing.apk", "")[0])

    def test_update_state_resets_after_check(self):
        engine = SelfUpdateEngine("1.0.0", "https://example.com/update.json")
        with patch("engines.self_update.urllib.request.urlopen", side_effect=OSError("offline")):
            engine.check_for_updates()
        self.assertFalse(engine.is_checking)


    def test_download_apk_verifies_digest(self):
        payload = b"Laiba verified APK"
        digest = hashlib.sha256(payload).hexdigest()
        response = MagicMock()
        response.geturl.return_value = "https://example.com/app.apk"
        response.read.side_effect = [payload, b""]
        response.__enter__.return_value = response
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "app.apk"
            with patch("engines.self_update.urllib.request.build_opener") as build:
                build.return_value.open.return_value = response
                result = SelfUpdateEngine("1.0.0", timeout=3).download_apk(
                    "https://example.com/app.apk", digest, target
                )
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(result["sha256"], digest)

    def test_download_apk_rejects_wrong_digest(self):
        response = MagicMock()
        response.geturl.return_value = "https://example.com/app.apk"
        response.read.side_effect = [b"untrusted", b""]
        response.__enter__.return_value = response
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "app.apk"
            with patch("engines.self_update.urllib.request.build_opener") as build:
                build.return_value.open.return_value = response
                with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                    SelfUpdateEngine().download_apk(
                        "https://example.com/app.apk", "0" * 64, target
                    )
            self.assertFalse(target.exists())



    def test_update_state_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            engine = SelfUpdateEngine(current_version="1.0.2", state_path=str(path))
            engine.save_update_state({"status": "pending", "target_version": "1.0.3"})
            self.assertEqual(engine.load_update_state()["status"], "pending")

    def test_pending_update_confirms_new_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            engine = SelfUpdateEngine(current_version="1.0.2", state_path=str(path))
            engine.mark_update_pending("1.0.3", str(Path(directory) / "update.apk"), "a" * 64)
            self.assertEqual(engine.resolve_update_state("1.0.3")["status"], "confirmed")

    def test_pending_update_marks_failed_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            engine = SelfUpdateEngine(current_version="1.0.2", state_path=str(path))
            engine.mark_update_pending("1.0.3", str(Path(directory) / "update.apk"), "a" * 64)
            self.assertEqual(engine.resolve_update_state("1.0.2")["status"], "failed")


    def test_corrupt_update_state_recovers_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("{invalid json", encoding="utf-8")
            engine = SelfUpdateEngine(current_version="1.0.2", state_path=str(path))
            result = engine.load_update_state()
            self.assertEqual(result["status"], "failed")
            self.assertIn("invalid", result["reason"].lower())


    def test_rejects_https_url_with_embedded_credentials(self):
        with self.assertRaises(ValueError):
            SelfUpdateEngine._https_url(
                "https://user:password@example.com/update.json",
                "Manifest URL"
            )

    def test_accepts_normal_https_url(self):
        self.assertEqual(
            SelfUpdateEngine._https_url(
                "https://example.com/update.json", "Manifest URL"
            ),
            "https://example.com/update.json"
        )

if __name__ == "__main__":
    unittest.main()
