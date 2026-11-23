import unittest
from engines.chatbot_engine import ChatbotEngine


class DynamicIntentTests(unittest.TestCase):

    def test_everyday_commands_reach_classifier(self):
        samples = (
            "check the project",
            "find bugs in this code",
            "read this file",
            "اپنا کوڈ بہتر کرو",
            "اس فائل کو پڑھو",
            "APK check karo",
            "اس پر کام کرو",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(
                    ChatbotEngine._should_classify_intent(None, sample)
                )

    def test_contextual_followup_reaches_classifier(self):
        engine = ChatbotEngine.__new__(ChatbotEngine)
        engine.chat_history = [
            {"role": "user", "parts": [{"text": "Check repository"}]}
        ]
        self.assertTrue(engine._should_classify_intent("isko check karo"))
        self.assertTrue(engine._should_classify_intent("اب اس پر کام کرو"))

    def test_ordinary_chat_does_not_force_classification(self):
        engine = ChatbotEngine.__new__(ChatbotEngine)
        engine.chat_history = []
        self.assertFalse(engine._should_classify_intent("hello Laiba"))
        self.assertFalse(engine._should_classify_intent("how are you?"))

    def test_classifier_accepts_development_intent(self):
        engine = ChatbotEngine.__new__(ChatbotEngine)
        engine.chat_history = []
        engine._gemini = lambda *a, **k: (
            '{"intent":"development_propose","confidence":0.95}'
        )
        self.assertEqual(
            engine._classify_natural_intent("improve your engine"),
            "development_propose"
        )

    def test_classifier_accepts_bug_analysis(self):
        engine = ChatbotEngine.__new__(ChatbotEngine)
        engine.chat_history = []
        engine._gemini = lambda *a, **k: (
            '{"intent":"bug_analysis","confidence":0.94}'
        )
        self.assertEqual(
            engine._classify_natural_intent("find project bugs"),
            "bug_analysis"
        )

    def test_classifier_rejects_execution_authority(self):
        engine = ChatbotEngine.__new__(ChatbotEngine)
        engine.chat_history = []
        engine._gemini = lambda *a, **k: (
            '{"intent":"workflow_dispatch","confidence":1.0}'
        )
        self.assertEqual(
            engine._classify_natural_intent("run it"), "chat"
        )

    def test_classifier_rejects_low_confidence(self):
        engine = ChatbotEngine.__new__(ChatbotEngine)
        engine.chat_history = []
        engine._gemini = lambda *a, **k: (
            '{"intent":"build_status","confidence":0.30}'
        )
        self.assertEqual(
            engine._classify_natural_intent("check it"), "chat"
        )


if __name__ == "__main__":
    unittest.main()
