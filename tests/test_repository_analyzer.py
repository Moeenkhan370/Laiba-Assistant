import tempfile
import unittest
from pathlib import Path

from engines.development_engine import DevelopmentEngine


class FakeGitHub:
    branch = "laiba-self-development"

    def fetch_repository_files(self):
        return {
            "main.py": (
                "from pkg.mod import Thing\n"
                "class App:\n"
                "    def run(self):\n"
                "        return Thing()\n"
            ),
            "pkg/mod.py": (
                "class Thing:\n"
                "    pass\n"
                "def helper():\n"
                "    return 1\n"
            ),
            "README.md": "# Laiba\n"
        }


class RepositoryAnalyzerTests(unittest.TestCase):

    def test_reads_all_files_and_builds_ast_dependency_map(self):
        calls = []

        def generate(prompt):
            calls.append(prompt)
            if "Create one consolidated" in prompt:
                return "Consolidated bug report generated."
            return "Batch reviewed."

        with tempfile.TemporaryDirectory() as folder:
            engine = DevelopmentEngine(
                folder,
                ai_generate=generate,
                github_client=FakeGitHub()
            )

            report = engine.analyze_repository(
                "Analyze the complete repository"
            )

        self.assertIn("Text files analyzed: 3", report)
        self.assertIn("CLASS 2:App", report)
        self.assertIn("FUNCTION 3:run", report)
        self.assertIn("main.py -> pkg.mod -> pkg/mod.py", report)
        self.assertIn("Consolidated bug report generated.", report)
        self.assertGreaterEqual(len(calls), 2)

    def test_splits_large_file_into_multiple_batches(self):
        calls = []

        class LargeGitHub:
            branch = "laiba-self-development"

            def fetch_repository_files(self):
                return {
                    "large.txt": "Laiba source analysis line\n" * 1800
                }

        def generate(prompt):
            calls.append(prompt)
            return "Reviewed."

        with tempfile.TemporaryDirectory() as folder:
            engine = DevelopmentEngine(
                folder,
                ai_generate=generate,
                github_client=LargeGitHub()
            )
            report = engine.analyze_repository()

        self.assertIn("Analysis batches:", report)
        self.assertGreaterEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
