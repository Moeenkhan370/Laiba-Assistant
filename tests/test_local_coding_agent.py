import tempfile
import unittest
from pathlib import Path

from local_coding_agent import LocalCodingAgent

class LocalCodingAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "engines").mkdir()
        (self.root / "engines" / "voice.py").write_text(
            "class VoiceEngine:\n"
            "    def listen(self):\n"
            "        return True\n"
            "def start_call():\n"
            "    try:\n"
            "        eval('1 + 1')\n"
            "    except:\n"
            "        pass\n",
            encoding="utf-8"
        )
        (self.root / "main.py").write_text(
            "from engines.voice import VoiceEngine\n"
            "app = VoiceEngine()\n",
            encoding="utf-8"
        )
        (self.root / ".env").write_text("SECRET=hidden", encoding="utf-8")
        (self.root / "credentials.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_scans_without_secret_files(self):
        agent = LocalCodingAgent(self.root)
        result = agent.scan()
        self.assertIn("main.py", result["files"])
        self.assertNotIn(".env", result["files"])
        self.assertNotIn("credentials.json", result["files"])

    def test_ast_symbols_and_dependencies(self):
        agent = LocalCodingAgent(self.root)
        agent.scan()
        report = agent.analyze()
        self.assertIn("VoiceEngine", str(report["symbols"]))
        self.assertTrue(any(x["target"] == "engines/voice.py"
                            for x in report["dependencies"]))

    def test_finds_static_risk_locations(self):
        agent = LocalCodingAgent(self.root)
        agent.scan()
        report = agent.analyze()
        kinds = {x["kind"] for x in report["findings"]}
        self.assertIn("dynamic_execution", kinds)
        self.assertIn("broad_exception", kinds)

    def test_feature_search_and_context_have_line_numbers(self):
        agent = LocalCodingAgent(self.root)
        agent.scan()
        agent.analyze()
        result = agent.analyze_feature("voice listen call")
        self.assertTrue(result["feature_locations"])
        self.assertIn("engines/voice.py", result["relevant_context"]["context"])
        self.assertIn("2:", result["relevant_context"]["context"])

    def test_reports_syntax_error(self):
        (self.root / "broken.py").write_text("def bad(:\n", encoding="utf-8")
        agent = LocalCodingAgent(self.root)
        agent.scan()
        report = agent.analyze()
        self.assertTrue(any(x["kind"] == "syntax_error"
                            and x["path"] == "broken.py"
                            for x in report["findings"]))


    def test_nested_ast_scope_and_async_mapping(self):
        (self.root / "nested.py").write_text(
            "class Outer:\n"
            "    class Inner:\n"
            "        async def run(self):\n"
            "            def helper(): pass\n",
            encoding="utf-8"
        )
        agent = LocalCodingAgent(self.root)
        agent.scan()
        report = agent.analyze()
        symbols = report["symbols"]["nested.py"]["symbols"]
        self.assertTrue(any(x.get("parent") == "Outer" for x in symbols))
        self.assertTrue(any(x.get("kind") == "async_function" and
                            x.get("parent") == "Outer.Inner" for x in symbols))

if __name__ == "__main__":
    unittest.main()
