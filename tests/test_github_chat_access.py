import base64
import unittest
from unittest.mock import Mock
from engines.command_router import CommandRouter
from engines.github_client import GitHubClient


class GitHubChatAccessTests(unittest.TestCase):
    def test_commit_and_file_read_routes(self):
        router = CommandRouter()
        self.assertEqual(router.route("show latest 5 commits"), "github_commits")
        self.assertEqual(router.route("list repository files"), "github_file_list")
        self.assertEqual(router.route("read file engines/chatbot_engine.py"), "github_file_read")

    def test_list_commits_uses_configured_branch(self):
        client = GitHubClient("test-token", "owner/repo", "dev")
        client.request = Mock(return_value=[{"sha": "abc"}])
        self.assertEqual(client.list_commits(5), [{"sha": "abc"}])
        client.request.assert_called_once_with(
            "/repos/owner/repo/commits", {"sha": "dev", "per_page": 5}
        )

    def test_read_file_decodes_text(self):
        client = GitHubClient("test-token", "owner/repo", "dev")
        content = base64.b64encode(b"print('Laiba')").decode()
        client.request = Mock(return_value={
            "type": "file", "size": 14, "content": content
        })
        self.assertEqual(client.read_file("engines/demo.py"), "print('Laiba')")

    def test_read_file_rejects_traversal(self):
        client = GitHubClient("test-token", "owner/repo", "dev")
        with self.assertRaises(ValueError):
            client.read_file("../secrets.json")


if __name__ == "__main__":
    unittest.main()
