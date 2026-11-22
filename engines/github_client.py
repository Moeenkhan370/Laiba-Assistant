"""GitHub API client. Never send the token to Gemini."""
import requests

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
