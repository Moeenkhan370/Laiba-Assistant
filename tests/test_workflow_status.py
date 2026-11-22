import unittest
from engines.command_router import CommandRouter

class WorkflowStatusTests(unittest.TestCase):
    def test_build_status_commands(self):
        router = CommandRouter()
        for command in ("build status", "check build", "apk status", "بلڈ اسٹیٹس"):
            self.assertEqual(router.route(command), "build_status")

if __name__ == "__main__":
    unittest.main()
