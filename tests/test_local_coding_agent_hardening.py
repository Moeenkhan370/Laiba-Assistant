
import tempfile
import unittest
from pathlib import Path
from local_coding_agent import LocalCodingAgent


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scans_selected_hidden_project_folders(self):
        p = self.root / ".github"
        p.mkdir()
        (p / "workflow.py").write_text("def deploy(): pass\n", encoding="utf-8")
        (self.root / ".hidden").mkdir()
        (self.root / ".hidden" / "skip.py").write_text("x=1\n", encoding="utf-8")
        agent = LocalCodingAgent(self.root)
        result = agent.scan()
        self.assertIn(".github/workflow.py", result["files"])
        self.assertNotIn(".hidden/skip.py", result["files"])

    def test_large_file_is_warning_not_crash(self):
        (self.root / "large.py").write_text("x" * 200, encoding="utf-8")
        agent = LocalCodingAgent(self.root)
        agent.MAX_FILE_BYTES = 100
        result = agent.scan()
        self.assertNotIn("large.py", result["files"])
        self.assertTrue(any(x["kind"] == "file_size_limit"
                            for x in result["warnings"]))

    def test_detects_extra_static_risks(self):
        (self.root / "risks.py").write_text(
            "import yaml\n"
            "x = (value is 1)\n"
            "yaml.load(data)\n"
            "requests.get(url, verify=False)\n",
            encoding="utf-8")
        agent = LocalCodingAgent(self.root)
        agent.scan()
        kinds = {x["kind"] for x in agent.analyze()["findings"]}
        for kind in ("identity_literal", "unsafe_yaml_load",
                     "tls_verification_disabled"):
            self.assertIn(kind, kinds)

    def test_detects_duplicate_definition_and_unreachable_code(self):
        (self.root / "dupes.py").write_text(
            "def same(): pass\n"
            "def same(): pass\n"
            "def later():\n"
            "    return 1\n"
            "    value = 2\n", encoding="utf-8")
        agent = LocalCodingAgent(self.root)
        agent.scan()
        kinds = {x["kind"] for x in agent.analyze()["findings"]}
        self.assertIn("duplicate_definition", kinds)
        self.assertIn("unreachable_code", kinds)

    def test_feature_search_matches_identifier_words(self):
        (self.root / "voice.py").write_text(
            "class VoiceConversationEngine:\n"
            "    def start_call(self): pass\n", encoding="utf-8")
        agent = LocalCodingAgent(self.root)
        agent.scan()
        result = agent.find_feature_locations("conversation")
        self.assertTrue(any(x["path"] == "voice.py" for x in result))

    def test_context_includes_local_import_dependency(self):
        (self.root / "core.py").write_text(
            "def important_helper():\n    return 42\n", encoding="utf-8")
        (self.root / "main.py").write_text(
            "from core import important_helper\n"
            "def run_feature():\n    return important_helper()\n",
            encoding="utf-8")
        agent = LocalCodingAgent(self.root)
        agent.scan()
        agent.analyze()
        result = agent.build_context("run feature", max_chars=3000)
        self.assertIn("dependency: core.py", result["context"])
        self.assertIn("important_helper", result["context"])

    def test_report_exposes_scan_warnings(self):
        agent = LocalCodingAgent(self.root)
        agent.warnings = [{"kind": "test_warning", "message": "notice"}]
        self.assertEqual(agent.report()["warnings"][0]["kind"], "test_warning")


if __name__ == "__main__":
    unittest.main()
