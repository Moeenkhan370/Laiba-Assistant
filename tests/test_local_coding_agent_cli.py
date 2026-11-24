import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from local_coding_agent.cli import main


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "voice.py").write_text(
            "class VoiceEngine:\\n"
            "    def listen(self):\\n"
            "        return True\\n",
            encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, command, output, request=None):
        args = [command, "--root", str(self.root),
                "--output", output]
        if request is not None:
            args += ["--request", request]
        stream = StringIO()
        with redirect_stdout(stream):
            main(args)
        return stream.getvalue()

    def test_feature_saves_json_and_prints_compact_summary(self):
        text = self.run_cli("feature", "feature.json", "voice listen")
        saved = self.root / "feature.json"
        self.assertTrue(saved.is_file())
        data = json.loads(saved.read_text(encoding="utf-8"))
        self.assertIn("feature_locations", data)
        self.assertIn("Report saved:", text)
        self.assertNotIn('"relevant_context"', text)

    def test_context_saves_json_without_dumping_context(self):
        text = self.run_cli("context", "context.json", "voice listen")
        data = json.loads(
            (self.root / "context.json").read_text(encoding="utf-8")
        )
        self.assertIn("context", data)
        self.assertIn("Characters:", text)
        self.assertNotIn("--- voice.py ---", text)

    def test_analyze_saves_report(self):
        text = self.run_cli("analyze", "analysis.json")
        data = json.loads(
            (self.root / "analysis.json").read_text(encoding="utf-8")
        )
        self.assertIn("symbols", data)
        self.assertIn("Python parsed:", text)

    def test_output_cannot_escape_project_root(self):
        with self.assertRaises(SystemExit):
            self.run_cli("feature", "../outside.json", "voice")


if __name__ == "__main__":
    unittest.main()
