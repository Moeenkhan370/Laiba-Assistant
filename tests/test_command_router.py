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


if __name__ == "__main__":
    unittest.main()
