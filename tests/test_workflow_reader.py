import unittest
from pathlib import Path
from engines.development_engine import DevelopmentEngine

class WorkflowReaderTests(unittest.TestCase):
    def test_discovers_android_workflow(self):
        engine = DevelopmentEngine(".")
        files = engine.inspect_project()
        self.assertIn(".github/workflows/android.yml", files)

    def test_reads_workflow_content(self):
        engine = DevelopmentEngine(".")
        context = engine._project_context()
        self.assertIn(".github/workflows/android.yml", context)

if __name__ == "__main__":
    unittest.main()
