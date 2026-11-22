import unittest
from unittest.mock import patch
from engines.github_client import GitHubClient


class GitHubCommitTests(unittest.TestCase):
    def setUp(self):
        self.client = GitHubClient("test-token", "owner/repo", "laiba-self-development")

    def test_requires_explicit_approval(self):
        with self.assertRaises(PermissionError):
            self.client.commit_files([{"path": "app.py", "content": "X=1"}], "test")

    def test_rejects_unsafe_paths(self):
        for path in ("../secret.py", "/root/file.py", ".env", "folder/../x.py"):
            with self.assertRaises(ValueError):
                self.client.commit_files(
                    [{"path": path, "content": "X=1"}], "test", approved=True
                )

    def test_creates_single_commit_for_multiple_files(self):
        responses = [
            {"sha": "blob1"},
            {"sha": "blob2"},
            {"object": {"sha": "parent1"}},
            {"tree": {"sha": "tree0"}},
            {"sha": "tree1"},
            {"sha": "commit1"},
            {},
        ]
        with patch.object(self.client, "request", side_effect=responses) as request:
            result = self.client.commit_files([
                {"path": "app.py", "content": "X=1"},
                {"path": "config.py", "content": "Y=2"},
            ], "Approved Laiba update", approved=True)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["commit"], "commit1")
        self.assertEqual(len(result["files"]), 2)
        self.assertEqual(request.call_count, 7)
        self.assertEqual(request.call_args_list[-1].kwargs["method"], "PATCH")
        self.assertFalse(request.call_args_list[-1].kwargs["json_body"]["force"])


if __name__ == "__main__":
    unittest.main()
