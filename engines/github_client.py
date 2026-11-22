"""GitHub API client. Never send the token to Gemini."""
import requests
import base64
from pathlib import Path
from urllib.parse import quote

class GitHubClient:
    API = "https://api.github.com"

    def __init__(self, token, repository, branch):
        self.token = str(token).strip()
        self.repository = str(repository).strip()
        self.branch = str(branch).strip()
        if not self.token or "/" not in self.repository:
            raise ValueError("Invalid GitHub token or repository.")

    def request(self, endpoint, params=None, method="GET", json_body=None):
        response = requests.request(
            method,
            self.API + endpoint,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Laiba-Assistant"
            },
            params=params, json=json_body, timeout=(8, 20)
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("message", "Request failed")
            except Exception:
                detail = "Request failed"
            raise RuntimeError("GitHub HTTP {}: {}".format(response.status_code, detail))
        return response.json()

    def check_access(self):
        base = "/repos/" + self.repository
        account = self.request("/user")
        repository = self.request(base)
        branch = quote(self.branch, safe="")
        ref = self.request(base + "/git/ref/heads/" + branch)
        commit = self.request(base + "/git/commits/" + ref["object"]["sha"])
        self.request(base + "/git/trees/" + commit["tree"]["sha"])
        workflows = self.request(
            base + "/actions/workflows", {"per_page": 100}
        )
        permissions = repository.get("permissions") or {}
        push_access = bool(permissions.get("push"))
        return {
            "ok": True,
            "account": account.get("login", "unknown"),
            "repository": self.repository,
            "branch": self.branch,
            "read_verified": True,
            "account_push_access": push_access,
            "token_write_verified": False,
            "workflow_count": len(workflows.get("workflows", [])),
            "message": (
                "Read access verified for @{} on {} branch; "
                "account push access: {}. Token write permission is not "
                "claimed because no remote write test was performed."
            ).format(
                account.get("login", "GitHub user"),
                self.branch,
                "available" if push_access else "unavailable"
            )
        }

    def fetch_repository_files(self, max_files=2000, max_blob_bytes=100000):
        """Read eligible text files from the configured branch; never write to GitHub."""
        branch = quote(self.branch, safe="")
        base = "/repos/" + self.repository
        ref = self.request(base + "/git/ref/heads/" + branch)
        commit = self.request(base + "/git/commits/" + ref["object"]["sha"])
        tree_sha = commit["tree"]["sha"]
        tree = self.request(base + "/git/trees/" + tree_sha, {"recursive": "1"})
        if tree.get("truncated"):
            raise RuntimeError("GitHub returned an incomplete repository tree; refusing partial analysis.")
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
                    or any(
                        x in blocked or
                        (x.startswith(".") and not (
                            parts[0] == ".github" and
                            len(parts) > 2 and parts[1] == "workflows"
                        ))
                        for x in parts[:-1]
                    )
                    or parts[-1].lower() in secret_names
                    or parts[-1].lower().startswith((".env.", "secret", "credential"))
                    or Path(parts[-1]).suffix.lower() in {
                        ".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"
                    }
                    or (parts[-1].startswith(".") and not (
                        len(parts) > 2 and parts[0] == ".github"
                        and parts[1] == "workflows"
                    ))
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

    def commit_files(self, changes, message, approved=False):
        """Atomically commit multiple approved text-file changes to the configured branch."""
        if approved is not True:
            raise PermissionError("Explicit user approval is required.")
        if not isinstance(changes, list) or not changes:
            raise ValueError("At least one file change is required.")

        entries = []
        seen = set()
        for item in changes:
            if not isinstance(item, dict):
                raise ValueError("Invalid file change.")
            path = str(item.get("path", "")).replace("\\\\", "/")
            parts = path.split("/")
            if (not path or path.startswith("/") or
                    any(part in ("", ".", "..") for part in parts) or
                    any(part.startswith(".") for part in parts) or
                    not isinstance(item.get("content"), str)):
                raise ValueError("Unsafe path or invalid file content.")
            if path in seen:
                raise ValueError("Duplicate file path.")
            seen.add(path)
            blob = self.request(
                "/repos/" + self.repository + "/git/blobs",
                method="POST",
                json_body={"content": item["content"], "encoding": "utf-8"}
            )
            entries.append({
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": blob["sha"]
            })

        branch = quote(self.branch, safe="")
        base = "/repos/" + self.repository
        ref = self.request(base + "/git/ref/heads/" + branch)
        parent_sha = ref["object"]["sha"]
        parent = self.request(base + "/git/commits/" + parent_sha)

        tree = self.request(
            base + "/git/trees",
            method="POST",
            json_body={"base_tree": parent["tree"]["sha"], "tree": entries}
        )
        commit = self.request(
            base + "/git/commits",
            method="POST",
            json_body={
                "message": str(message)[:200],
                "tree": tree["sha"],
                "parents": [parent_sha]
            }
        )
        self.request(
            base + "/git/refs/heads/" + branch,
            method="PATCH",
            json_body={"sha": commit["sha"], "force": False}
        )
        return {
            "status": "success",
            "commit": commit["sha"],
            "files": sorted(seen),
            "branch": self.branch
        }

    def dispatch_workflow(self, workflow_id, approved=False):
        if approved is not True:
            raise PermissionError("Explicit user approval is required.")
        if not str(workflow_id).strip():
            raise ValueError("Workflow ID is required.")
        return self.request(
            "/repos/" + self.repository + "/actions/workflows/"
            + quote(str(workflow_id), safe="") + "/dispatches",
            method="POST",
            json_body={"ref": self.branch}
        )

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
