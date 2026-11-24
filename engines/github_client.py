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


    def fetch_repository_files(
        self, max_files=None, max_blob_bytes=5 * 1024 * 1024
    ):
        """Fetch every eligible text file without silently truncating analysis."""
        branch = quote(self.branch, safe="")
        base = "/repos/" + self.repository

        ref = self.request(base + "/git/ref/heads/" + branch)
        commit = self.request(
            base + "/git/commits/" + ref["object"]["sha"]
        )
        tree = self.request(
            base + "/git/trees/" + commit["tree"]["sha"],
            {"recursive": "1"}
        )

        if tree.get("truncated"):
            raise RuntimeError(
                "GitHub returned an incomplete repository tree."
            )

        allowed = {
            ".py", ".md", ".json", ".txt", ".yaml", ".yml",
            ".toml", ".ini", ".cfg", ".kv", ".spec", ".sh",
            ".xml", ".gradle", ".properties", ".backup", ".java"
        }
        blocked = {
            ".git", ".laiba_backups", "__pycache__",
            "venv", ".venv", "bin"
        }
        secret_names = {
            ".env", "laiba_config.json", "secrets.json",
            "credentials.json"
        }

        files = {}
        total_bytes = 0

        for item in tree.get("tree", []):
            if item.get("type") != "blob":
                continue

            path = item.get("path", "")
            parts = path.split("/")
            if not path or len(parts) == 0:
                continue

            name = parts[-1].lower()
            workflow = (
                len(parts) > 2
                and parts[0] == ".github"
                and parts[1] == "workflows"
            )

            if Path(path).suffix.lower() not in allowed:
                continue

            if any(part in blocked for part in parts[:-1]):
                continue

            if any(
                part.startswith(".") and not workflow
                for part in parts[:-1]
            ):
                continue

            if name in secret_names:
                continue

            if name.startswith((".env.", "secret", "credential")):
                continue

            if Path(name).suffix.lower() in {
                ".pem", ".key", ".p12", ".pfx",
                ".keystore", ".jks"
            }:
                continue

            size = int(item.get("size", 0))

            if size > max_blob_bytes:
                raise RuntimeError(
                    "Repository file exceeds analysis limit: " + path
                )

            if total_bytes + size > 50 * 1024 * 1024:
                raise RuntimeError(
                    "Repository text exceeds the 50 MB safety limit."
                )

            blob = self.request(
                base + "/git/blobs/" + item["sha"]
            )

            try:
                raw = base64.b64decode(
                    blob.get("content", "")
                )
                content = raw.decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                # Binary content is not source text.
                continue

            total_bytes += len(raw)
            files[path] = content

            if max_files is not None and len(files) >= max_files:
                break

        return files


    def list_commits(self, per_page=5):
        per_page = int(per_page)
        if not 1 <= per_page <= 20:
            raise ValueError("Commit count must be between 1 and 20.")
        return self.request(
            "/repos/" + self.repository + "/commits",
            {"sha": self.branch, "per_page": per_page}
        )

    def list_repository_files(self):
        base = "/repos/" + self.repository
        branch = quote(self.branch, safe="")
        ref = self.request(base + "/git/ref/heads/" + branch)
        commit = self.request(base + "/git/commits/" + ref["object"]["sha"])
        tree = self.request(
            base + "/git/trees/" + commit["tree"]["sha"],
            {"recursive": "1"}
        )
        if tree.get("truncated"):
            raise RuntimeError("GitHub returned an incomplete repository tree.")
        allowed = {
            ".py", ".md", ".json", ".txt", ".yaml", ".yml",
            ".toml", ".ini", ".cfg", ".kv", ".spec", ".sh",
            ".xml", ".gradle", ".properties", ".backup", ".java"
        }
        blocked = {".git", ".laiba_backups", "__pycache__", "venv", ".venv", "bin"}
        secrets = {".env", "laiba_config.json", "secrets.json", "credentials.json"}
        result = []
        for item in tree.get("tree", []):
            path = item.get("path", "")
            parts = path.split("/")
            if item.get("type") != "blob" or not path:
                continue
            if Path(path).suffix.lower() not in allowed:
                continue
            if parts[-1].lower() in secrets or parts[-1].lower().startswith(
                (".env.", "secret", "credential")
            ):
                continue
            if any(part in blocked for part in parts[:-1]):
                continue
            if any(
                part.startswith(".") and not (
                    parts[0] == ".github" and len(parts) > 2
                    and parts[1] == "workflows"
                )
                for part in parts
            ):
                continue
            result.append(path)
        return sorted(result)

    def read_file(self, path, max_bytes=5 * 1024 * 1024):
        path = str(path or "").strip().replace("\\\\", "/")
        parts = path.split("/")
        allowed = {
            ".py", ".md", ".json", ".txt", ".yaml", ".yml",
            ".toml", ".ini", ".cfg", ".kv", ".spec", ".sh",
            ".xml", ".gradle", ".properties", ".backup", ".java"
        }
        if (
            not path or path.startswith("/") or
            any(part in ("", ".", "..") for part in parts) or
            Path(path).suffix.lower() not in allowed or
            parts[-1].lower() in {
                ".env", "laiba_config.json", "secrets.json", "credentials.json"
            } or
            parts[-1].lower().startswith((".env.", "secret", "credential"))
        ):
            raise ValueError("Unsafe or unsupported repository file path.")
        endpoint = (
            "/repos/" + self.repository + "/contents/"
            + quote(path, safe="/")
        )
        data = self.request(endpoint, {"ref": self.branch})
        if data.get("type") != "file" or int(data.get("size", 0)) > max_bytes:
            raise ValueError("File is not readable or exceeds the size limit.")
        raw = base64.b64decode(data.get("content", ""))
        if len(raw) > max_bytes:
            raise ValueError("Decoded file exceeds the size limit.")
        return raw.decode("utf-8")

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
            workflow_path = (
                len(parts) > 2
                and parts[0] == ".github"
                and parts[1] == "workflows"
            )
            hidden_path = any(
                part.startswith(".") and not (workflow_path and index == 0)
                for index, part in enumerate(parts)
            )
            if (not path or path.startswith("/") or
                    any(part in ("", ".", "..") for part in parts) or
                    hidden_path or
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
