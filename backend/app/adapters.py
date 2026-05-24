from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .models import ReviewContext


class SourceAdapter(Protocol):
    provider: str

    def fetch_context(self, reference: str, payload: dict[str, Any] | None = None) -> ReviewContext:
        raise NotImplementedError


def normalize_diff(diff_text: str) -> str:
    return diff_text.replace("\r\n", "\n").strip()


def _looks_like_diff(text: str) -> bool:
    return text.lstrip().startswith("diff --git") or "@@" in text or text.lstrip().startswith("---")


def _read_url(url: str, headers: dict[str, str] | None = None) -> str:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def _git_diff(repo_path: Path, base_branch: str, head_branch: str) -> str:
    command = ["git", "-C", str(repo_path), "diff", "--no-color", f"{base_branch}...{head_branch}"]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return completed.stdout.strip() or completed.stderr.strip()


def _parse_reference(reference: str) -> tuple[str | None, str | None, int | None]:
    parsed = urlparse(reference)
    if parsed.netloc.endswith("github.com"):
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 4 and parts[2] == "pull":
            return f"{parts[0]}/{parts[1]}", "github", int(parts[3])
    if parsed.netloc.endswith("gitlab.com"):
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 5 and parts[3] == "-" and parts[4] == "merge_requests":
            return f"{parts[0]}/{parts[1]}", "gitlab", int(parts[5])
    return None, None, None


@dataclass(slots=True)
class LocalGitAdapter:
    provider: str = "local-git"

    def fetch_context(self, reference: str, payload: dict[str, Any] | None = None) -> ReviewContext:
        payload = payload or {}
        diff_path = Path(reference)
        if diff_path.is_dir():
            diff_text = _git_diff(diff_path, payload.get("base_branch", "main"), payload.get("head_branch", "HEAD"))
        elif diff_path.exists():
            diff_text = diff_path.read_text(encoding="utf-8")
        elif _looks_like_diff(reference):
            diff_text = reference
        else:
            diff_text = payload.get("diff", reference)
        return ReviewContext(
            provider=self.provider,
            repository=payload.get("repository", "local"),
            pull_request_number=payload.get("pull_request_number"),
            title=payload.get("title", "Local diff review"),
            base_branch=payload.get("base_branch", "main"),
            head_branch=payload.get("head_branch", "HEAD"),
            author=payload.get("author"),
            diff=normalize_diff(diff_text),
            files_changed=list(payload.get("files_changed", [])),
            metadata={"source": "local", **payload.get("metadata", {})},
        )


@dataclass(slots=True)
class GitHubAdapter:
    provider: str = "github"
    api_base: str = "https://api.github.com"
    token: str | None = None

    def fetch_context(self, reference: str, payload: dict[str, Any] | None = None) -> ReviewContext:
        payload = payload or {}
        repository = payload.get("repository")
        pull_request_number = payload.get("pull_request_number")
        if repository is None or pull_request_number is None:
            parsed_repository, _, parsed_number = _parse_reference(reference)
            repository = repository or parsed_repository or reference
            pull_request_number = pull_request_number or parsed_number

        diff_text = payload.get("diff", "")
        if not diff_text and repository and pull_request_number:
            headers = {"Accept": "application/vnd.github.v3.diff", "User-Agent": "ai-code-review-assistant"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            try:
                diff_text = _read_url(f"{self.api_base}/repos/{repository}/pulls/{pull_request_number}", headers=headers)
            except URLError:
                diff_text = f"# Unable to fetch GitHub PR diff for {repository}#{pull_request_number}"
        return ReviewContext(
            provider=self.provider,
            repository=repository or reference,
            pull_request_number=pull_request_number,
            title=payload.get("title", "GitHub pull request"),
            base_branch=payload.get("base_branch", "main"),
            head_branch=payload.get("head_branch", "feature"),
            author=payload.get("author"),
            diff=normalize_diff(diff_text),
            files_changed=list(payload.get("files_changed", [])),
            metadata={"source": "github", "reference": reference, **payload.get("metadata", {})},
        )

    def post_comment(self, repository: str, pull_request_number: int, body: str) -> bool:
        """Post a comment to the specified PR. Returns True on 2xx response."""
        if not repository or not pull_request_number:
            return False
        url = f"{self.api_base}/repos/{repository}/issues/{pull_request_number}/comments"
        headers = {"Content-Type": "application/json", "User-Agent": "ai-code-review-assistant"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        payload = json.dumps({"body": body}).encode("utf-8")
        try:
            req = Request(url, data=payload, headers=headers, method="POST")
            with urlopen(req, timeout=20) as resp:
                return 200 <= resp.getcode() < 300
        except Exception:
            return False


@dataclass(slots=True)
class GitLabAdapter:
    provider: str = "gitlab"
    api_base: str = "https://gitlab.com/api/v4"
    token: str | None = None

    def fetch_context(self, reference: str, payload: dict[str, Any] | None = None) -> ReviewContext:
        payload = payload or {}
        repository = payload.get("repository")
        pull_request_number = payload.get("pull_request_number")
        if repository is None or pull_request_number is None:
            parsed_repository, _, parsed_number = _parse_reference(reference)
            repository = repository or parsed_repository or reference
            pull_request_number = pull_request_number or parsed_number

        diff_text = payload.get("diff", "")
        if not diff_text and repository and pull_request_number:
            headers = {"User-Agent": "ai-code-review-assistant"}
            if self.token:
                headers["PRIVATE-TOKEN"] = self.token
            try:
                project = quote(repository, safe="")
                diff_text = _read_url(f"{self.api_base}/projects/{project}/merge_requests/{pull_request_number}/changes", headers=headers)
                try:
                    parsed = json.loads(diff_text)
                    changes = parsed.get("changes", [])
                    diff_text = "\n\n".join(change.get("diff", "") for change in changes)
                except json.JSONDecodeError:
                    pass
            except URLError:
                diff_text = f"# Unable to fetch GitLab MR diff for {repository}!{pull_request_number}"
        return ReviewContext(
            provider=self.provider,
            repository=repository or reference,
            pull_request_number=pull_request_number,
            title=payload.get("title", "GitLab merge request"),
            base_branch=payload.get("base_branch", "main"),
            head_branch=payload.get("head_branch", "feature"),
            author=payload.get("author"),
            diff=normalize_diff(diff_text),
            files_changed=list(payload.get("files_changed", [])),
            metadata={"source": "gitlab", "reference": reference, **payload.get("metadata", {})},
        )

    def post_comment(self, repository: str, merge_request_iid: int, body: str) -> bool:
        """Post a comment to a GitLab merge request. Returns True on success."""
        if not repository or not merge_request_iid:
            return False
        project = quote(repository, safe="")
        url = f"{self.api_base}/projects/{project}/merge_requests/{merge_request_iid}/notes"
        headers = {"Content-Type": "application/json", "User-Agent": "ai-code-review-assistant"}
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token
        payload = json.dumps({"body": body}).encode("utf-8")
        try:
            req = Request(url, data=payload, headers=headers, method="POST")
            with urlopen(req, timeout=20) as resp:
                return 200 <= resp.getcode() < 300
        except Exception:
            return False
