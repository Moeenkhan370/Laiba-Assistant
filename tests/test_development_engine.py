import json
import tempfile
import unittest
from unittest.mock import patch
import engines.development_engine as development_module
from pathlib import Path

from engines.development_engine import DevelopmentEngine


class DevelopmentEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def engine_for(self, path, content):
        payload = {"summary": "Test change", "changes": [{"path": path, "content": content}]}
        return DevelopmentEngine(
            self.root,
            ai_generate=lambda prompt: json.dumps(payload)
        )

    def test_requires_approval_and_creates_backup(self):
        engine = self.engine_for("sample.py", "VALUE = 2\n")
        proposal = engine.create_proposal("Improve sample")
        self.assertEqual(proposal["status"], "proposal")
        self.assertEqual((self.root / "sample.py").read_text(), "VALUE = 1\n")
        pending = engine.apply_proposal(proposal["proposal_id"])
        self.assertEqual(pending["status"], "confirmation_required")
        result = engine.apply_proposal(proposal["proposal_id"], confirm=True)
        self.assertEqual(result["status"], "success")
        self.assertEqual((self.root / "sample.py").read_text(), "VALUE = 2\n")
        self.assertTrue(Path(result["backup"]).is_dir())

    def test_rejects_path_traversal(self):
        engine = self.engine_for("../outside.py", "VALUE = 2\n")
        self.assertEqual(engine.create_proposal("unsafe change")["status"], "error")

    def test_rejects_invalid_python(self):
        engine = self.engine_for("sample.py", "def broken(:\n")
        self.assertEqual(engine.create_proposal("bad syntax")["status"], "error")

    def test_redacts_google_key_and_secret_assignment(self):
        sample = 'GEMINI_API_KEY = "AIza123456789012345678901234"\npassword=verysecret\n'
        redacted = DevelopmentEngine._redact_sensitive(sample)
        self.assertNotIn("AIza123456789012345678901234", redacted)
        self.assertNotIn("verysecret", redacted)


    def test_redacts_bearer_and_access_tokens(self):
        samples = [
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
            'access_token="SECRET123456"',
        ]
        for sample in samples:
            redacted = DevelopmentEngine._redact_sensitive(sample)
            self.assertNotIn("abcdefghijklmnopqrstuvwxyz123456", redacted)
            self.assertNotIn("SECRET123456", redacted)

    def test_rolls_back_when_second_file_write_fails(self):
        (self.root / "second.py").write_text("VALUE = 1\n", encoding="utf-8")
        payload = {"summary": "Rollback test", "changes": [
            {"path": "sample.py", "content": "VALUE = 2\n"},
            {"path": "second.py", "content": "VALUE = 2\n"},
        ]}
        engine = DevelopmentEngine(
            self.root, ai_generate=lambda _: json.dumps(payload)
        )
        proposal = engine.create_proposal("Test rollback")
        self.assertEqual(proposal["status"], "proposal", proposal)

        original_replace = development_module.os.replace
        calls = [0]

        def fail_second(src, dst):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError("simulated write failure")
            return original_replace(src, dst)

        with patch.object(development_module.os, "replace", side_effect=fail_second):
            result = engine.apply_proposal(proposal["proposal_id"], confirm=True)

        self.assertEqual(result["status"], "error")
        self.assertEqual((self.root / "sample.py").read_text(), "VALUE = 1\n")
        self.assertEqual((self.root / "second.py").read_text(), "VALUE = 1\n")

if __name__ == "__main__":
    unittest.main()
