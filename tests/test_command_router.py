import unittest
from engines.command_router import CommandRouter


class NaturalIntentRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = CommandRouter()

    def test_build_status_in_everyday_english(self):
        samples = (
            "Laiba, is my build complete?",
            "APK ban gayi?",
            "Check whether the latest build is ready",
            "GitHub Actions ka kya status hai?",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(self.router.route(sample), "build_status")

    def test_self_development_in_everyday_language(self):
        samples = (
            "Laiba improve your own code",
            "self update engine pe kaam karo",
            "is engine ko behtar banao",
            "اپنی کوڈنگ بہتر کرو",
            "اس انجن پر کام کرو",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(self.router.route(sample), "development_propose")

    def test_update_check_is_distinct_from_self_development(self):
        self.assertEqual(
            self.router.route("koi naya update aya hai?"), "update_check"
        )
        self.assertEqual(
            self.router.route("work on your self update engine"),
            "development_propose"
        )

    def test_explicit_approval_only(self):
        self.assertEqual(self.router.route("yes do it"), "chat")
        self.assertEqual(
            self.router.route("approve proposal 1730000000-a1b2c3d4"),
            "development_apply"
        )

    def test_existing_routes_remain_available(self):
        self.assertEqual(
            self.router.route("show latest 5 commits"), "github_commits"
        )
        self.assertEqual(
            self.router.route("list repository files"), "github_file_list"
        )
        self.assertEqual(
            self.router.route("read file engines/chatbot_engine.py"),
            "github_file_read"
        )

    def test_ordinary_chat_stays_chat(self):
        self.assertEqual(self.router.route("hello Laiba"), "chat")


    def test_all_remaining_router_intents(self):
        cases = {
            "find bugs in this code": "bug_analysis",
            "export zip": "zip_export",
            "show me a cube": "3d_status",
            "list files": "file_list",
            "open youtube": "open_link",
            "run workflow android.yml": "workflow_dispatch",
            "approve workflow android.yml": "workflow_approve",
            "check for updates": "update_check",
            "check updates": "update_check",
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(self.router.route(phrase), expected)

    def test_urdu_and_mixed_language_routes(self):
        cases = {
            "بگز تلاش کرو": "bug_analysis",
            "اپڈیٹس چیک": "update_check",
            "فائل کھولو": "github_file_read",
            "زپ بناؤ": "zip_export",
            "یوٹیوب کھولو": "open_link",
            "بلڈ اسٹیٹس": "build_status",
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(self.router.route(phrase), expected)

    def test_approval_requires_explicit_identifier(self):
        self.assertEqual(self.router.route("approve workflow"), "chat")
        self.assertEqual(self.router.route("run workflow"), "chat")
        self.assertEqual(self.router.route("yes, do it"), "chat")

    def test_empty_and_whitespace_input_are_safe(self):
        self.assertEqual(self.router.route(""), "chat")
        self.assertEqual(self.router.route("   "), "chat")
        self.assertEqual(self.router.route(None), "chat")


if __name__ == "__main__":
    unittest.main()
