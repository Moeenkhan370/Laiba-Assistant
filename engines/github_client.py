"""GitHub API client. Never send the token to Gemini."""
import requests
import base64
from urllib.parse import quote

class GitHubClient:
    API = "https://api.github.com"

    def __init__(self, token, repository, branch):
        self.token = str(token).strip()
        self.repository = str(repository).strip()
        self.branch = str(branch).strip()
        if not self.token or "/" not in self.repository:
            raise ValueError("Invalid GitHub token or repository.")

    def request(self, endpoint, params=None):
        response = requests.get(
            self.API + endpoint,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Laiba-Assistant"
            },
            params=params, timeout=(8, 20)
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("message", "Request failed")
            except Exception:
                detail = "Request failed"
            raise RuntimeError("GitHub HTTP {}: {}".format(response.status_code, detail))
        return response.json()

    def check_access(self):
        account = self.request("/user")
        self.request("/repos/" + self.repository)
        workflows = self.request(
            "/repos/" + self.repository + "/actions/workflows",
            {"per_page": 100}
        )
        count = len(workflows.get("workflows", []))
        return {
            "ok": True,
            "message": "Connected as @{}. Repository accessible; {} workflow(s) found.".format(
                account.get("login", "GitHub user"), count
            )
        }

    def fetch_repository_files(self, max_files=500, max_blob_bytes=50000):
        """Read eligible text files from the configured branch; never write to GitHub."""
        branch = quote(self.branch, safe="")
        base = "/repos/" + self.repository
        ref = self.request(base + "/git/ref/heads/" + branch)
        tree_sha = ref["object"]["sha"]
        tree = self.request(base + "/git/trees/" + tree_sha, {"recursive": "1"})
        allowed = {
            ".py", ".md", ".json", ".txt", ".yaml", ".yml",
            ".toml", ".ini", ".cfg", ".kv", ".spec", ".sh",
            ".xml", ".gradle", ".properties"
        }
        blocked = {".git", ".laiba_backups", "__pycache__", "venv", ".venv", "bin"}
        secret_names = {".env", "laiba_config.json", "secrets.json", "credentials.json"}
        files = {}
        for item in tree.get("tree", []):
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            parts = path.split("/")
            if (Path(path).suffix.lower() not in allowed
                    or any(x in blocked or x.startswith(".") for x in parts[:-1])
                    or parts[-1].lower() in secret_names
                    or item.get("size", 0) > max_blob_bytes):
                continue
            blob = self.request(base + "/git/blobs/" + item["sha"])
            try:
                raw = base64.b64decode(blob.get("content", ""))
                files[path] = raw.decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                continue
            if len(files) >= max_files:
                break
        return files

    def list_workflows(self):
        return self.request(
            "/repos/" + self.repository + "/actions/workflows",
            {"per_page": 100}
        )

    def list_workflow_runs(self):
        return self.request(
            "/repos/" + self.repository + "/actions/runs",
            {"branch": self.branch, "per_page": 20}
        )
