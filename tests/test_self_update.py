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
            "changelog": "Security improvements"
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


if __name__ == "__main__":
    unittest.main()
