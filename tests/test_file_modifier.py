import tempfile
import unittest
from pathlib import Path

from engines.file_modifier import FileModifierEngine


class FileModifierEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = FileModifierEngine(self.root)
        (self.root / "sample.txt").write_text(
            "first\nsecond\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_write_requires_confirmation(self):
        result = self.engine.write_file("new.txt", "hello")
        self.assertIn("Confirmation required", result)
        self.assertFalse((self.root / "new.txt").exists())

    def test_write_creates_file_and_replacement_backup(self):
        result = self.engine.write_file("sample.txt", "changed\n", confirm=True)
        self.assertTrue(result.startswith("Success:"))
        self.assertEqual(
            (self.root / "sample.txt").read_text(encoding="utf-8"),
            "changed\n"
        )
        backups = list(self.engine.backup_dir.rglob("sample.txt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "first\nsecond\n")

    def test_invalid_python_does_not_replace_original(self):
        original = (self.root / "sample.py")
        original.write_text("VALUE = 1\n", encoding="utf-8")
        result = self.engine.write_file(
            "sample.py", "def broken(:\n", confirm=True
        )
        self.assertIn("Error writing file", result)
        self.assertEqual(original.read_text(encoding="utf-8"), "VALUE = 1\n")

    def test_path_traversal_is_rejected(self):
        outside = self.root.parent / "outside.txt"
        result = self.engine.write_file("../outside.txt", "bad", confirm=True)
        self.assertIn("Error writing file", result)
        self.assertFalse(outside.exists())

    def test_sensitive_paths_are_blocked(self):
        for name in (".env", ".env.local", ".git/config",
                     ".laiba_backups/secret.txt", "secrets/data.txt"):
            result = self.engine.write_file(name, "secret", confirm=True)
            self.assertIn("Error writing file", result)

    def test_append_to_missing_file_does_not_create_it(self):
        result = self.engine.append_to_file("missing.txt", "new", confirm=True)
        self.assertIn("Error appending", result)
        self.assertFalse((self.root / "missing.txt").exists())

    def test_append_preserves_existing_content(self):
        result = self.engine.append_to_file(
            "sample.txt", "third\n", confirm=True
        )
        self.assertTrue(result.startswith("Success:"))
        self.assertEqual(
            (self.root / "sample.txt").read_text(encoding="utf-8"),
            "first\nsecond\nthird\n"
        )

    def test_modify_line_changes_only_first_match(self):
        (self.root / "sample.txt").write_text(
            "apple\napple\n", encoding="utf-8"
        )
        result = self.engine.modify_line(
            "sample.txt", "apple", "orange", confirm=True
        )
        self.assertTrue(result.startswith("Success:"))
        self.assertEqual(
            (self.root / "sample.txt").read_text(encoding="utf-8"),
            "orange\napple\n"
        )

    def test_modify_line_missing_match_changes_nothing(self):
        before = (self.root / "sample.txt").read_text(encoding="utf-8")
        result = self.engine.modify_line(
            "sample.txt", "absent", "replacement", confirm=True
        )
        self.assertIn("target text not found", result)
        self.assertEqual(
            (self.root / "sample.txt").read_text(encoding="utf-8"),
            before
        )

    def test_delete_requires_confirmation_and_keeps_backup(self):
        result = self.engine.delete_file("sample.txt")
        self.assertIn("Confirmation required", result)
        self.assertTrue((self.root / "sample.txt").exists())

        result = self.engine.delete_file("sample.txt", confirm=True)
        self.assertTrue(result.startswith("Success:"))
        self.assertFalse((self.root / "sample.txt").exists())
        self.assertEqual(
            len(list(self.engine.backup_dir.rglob("sample.txt"))), 1
        )

    def test_restore_last_backup(self):
        self.engine.write_file("sample.txt", "new version\n", confirm=True)
        result = self.engine.restore_last_backup(
            "sample.txt", confirm=True
        )
        self.assertIn("Restored latest backup", result)
        self.assertEqual(
            (self.root / "sample.txt").read_text(encoding="utf-8"),
            "first\nsecond\n"
        )

    def test_restore_requires_confirmation(self):
        result = self.engine.restore_last_backup("sample.txt")
        self.assertIn("Confirmation required", result)

    def test_list_dir_hides_backup_and_git_directories(self):
        (self.root / ".git").mkdir()
        entries = self.engine.list_dir(".")
        self.assertIn("sample.txt", entries)
        self.assertNotIn(".git", entries)
        self.assertNotIn(".laiba_backups", entries)

    def test_file_size_limit_is_enforced(self):
        limited = FileModifierEngine(self.root, max_file_bytes=4)
        result = limited.write_file("large.txt", "12345", confirm=True)
        self.assertIn("size limit", result)
        self.assertFalse((self.root / "large.txt").exists())

    def test_symlink_outside_project_is_rejected(self):
        outside = self.root.parent / "outside-laiba.txt"
        outside.write_text("safe", encoding="utf-8")
        link = self.root / "outside-link.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks are unavailable in this environment")

        result = self.engine.write_file(
            "outside-link.txt", "unsafe", confirm=True
        )
        self.assertIn("Error writing file", result)
        self.assertEqual(outside.read_text(encoding="utf-8"), "safe")


if __name__ == "__main__":
    unittest.main()
