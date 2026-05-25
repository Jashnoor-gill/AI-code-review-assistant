from __future__ import annotations

import json
import os
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import hmac
from urllib.parse import urlparse

from .config import API_TOKEN, DB_PATH, FRONTEND_DIR, HOST, PORT, validate_security_config
from .serialization import job_to_dict
from .service import build_default_service
from .storage import ReviewStore
from .adapters import GitHubAdapter, GitLabAdapter


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Token")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(encoded)


def _text_response(handler: BaseHTTPRequestHandler, status: int, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
    encoded = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(encoded)


def _read_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def _read_raw_body(handler: BaseHTTPRequestHandler) -> tuple[bytes, dict[str, Any]]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return b"", {}
    raw = handler.rfile.read(length)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception:
        parsed = {}
    return raw, parsed


def _retry(operation, attempts: int = 3, delay_seconds: float = 0.5):
    import time

    last_error = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if attempt < attempts - 1:
                time.sleep(delay_seconds * (attempt + 1))
    if last_error is not None:
        raise last_error


def _is_same_origin_request(handler: BaseHTTPRequestHandler) -> bool:
    host = handler.headers.get("Host", "")
    fetch_site = handler.headers.get("Sec-Fetch-Site", "")
    if fetch_site in ("same-origin", "same-site") and host:
        return True
    for header_name in ("Origin", "Referer"):
        header_value = handler.headers.get(header_name, "")
        if not header_value:
            continue
        parsed = urlparse(header_value)
        if parsed.netloc and parsed.netloc == host:
            return True
    return False


def _require_token(handler: BaseHTTPRequestHandler) -> bool:
    # If REQUIRE_API_TOKEN is False, do not require a token (useful for local dev).
    from .config import REQUIRE_API_TOKEN

    if not REQUIRE_API_TOKEN:
        return True
    if _is_same_origin_request(handler):
        return True
    if not API_TOKEN:
        _json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": "Server requires an API token but none is configured"})
        return False
    token = handler.headers.get("Authorization", "")
    header_token = handler.headers.get("X-API-Token", "")
    if hmac.compare_digest(token, f"Bearer {API_TOKEN}") or hmac.compare_digest(header_token, API_TOKEN):
        return True
    _json_response(handler, HTTPStatus.UNAUTHORIZED, {"error": "Missing or invalid API token"})
    return False


@lru_cache(maxsize=1)
def get_service():
    return build_default_service(ReviewStore(DB_PATH))


class ReviewRequestHandler(BaseHTTPRequestHandler):
    server_version = "AIReviewAssistant/0.1"

    def do_OPTIONS(self) -> None:
        _json_response(self, HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self._serve_frontend_file(FRONTEND_DIR / "index.html", "text/html; charset=utf-8")
            return
        if self.path == "/app.js":
            self._serve_frontend_file(FRONTEND_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if self.path == "/styles.css":
            self._serve_frontend_file(FRONTEND_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if self.path == "/api/health":
            _json_response(self, HTTPStatus.OK, {"status": "ok"})
            return
        if self.path == "/api/jobs":
            jobs = [job_to_dict(job) for job in get_service().list_jobs()]
            _json_response(self, HTTPStatus.OK, {"jobs": jobs})
            return
        if self.path.startswith("/api/jobs/"):
            job_id = self.path.split("/api/jobs/", 1)[1]
            job = get_service().get_job(job_id)
            if job is None:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Job not found"})
                return
            _json_response(self, HTTPStatus.OK, job_to_dict(job))
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path.startswith("/api/") and not _require_token(self):
            return

        if self.path == "/api/reviews":
            payload = _read_body(self)
            job = get_service().create_review(payload)
            _json_response(self, HTTPStatus.CREATED, job_to_dict(job))
            return
        if self.path.startswith("/api/jobs/") and self.path.endswith("/approve"):
            job_id = self.path.split("/api/jobs/", 1)[1].rsplit("/approve", 1)[0]
            job = get_service().approve_job(job_id)
            if job is None:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Job not found"})
                return
            # Optionally post the review comment back to the provider (GitHub/GitLab)
            payload = _read_body(self)
            token = payload.get("token") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GITLAB_TOKEN")
            try:
                job_dict = job_to_dict(job)
                meta = job_dict.get("metadata", {})
                provider = meta.get("provider")
                repo = meta.get("repository")
                context = meta.get("context") or {}
                pr_number = context.get("pull_request_number") or job_dict.get("metadata", {}).get("pull_request_number")
                comment_body = job_dict.get("markdown_comment") or job_dict.get("message") or "Code review posted."
                if provider == "github" and repo and pr_number:
                    gh = GitHubAdapter()
                    gh.token = token
                    gh.post_comment(repo, pr_number, comment_body)
                if provider == "gitlab" and repo and pr_number:
                    gl = GitLabAdapter()
                    gl.token = token
                    gl.post_comment(repo, pr_number, comment_body)
            except Exception:
                pass
            _json_response(self, HTTPStatus.OK, job_to_dict(job))
            return
        if self.path.startswith("/api/jobs/") and self.path.endswith("/reject"):
            job_id = self.path.split("/api/jobs/", 1)[1].rsplit("/reject", 1)[0]
            payload = _read_body(self)
            job = get_service().reject_job(job_id, payload.get("reason", "Rejected by reviewer"))
            if job is None:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Job not found"})
                return
            _json_response(self, HTTPStatus.OK, job_to_dict(job))
            return
        # Webhook endpoints are intentionally unauthenticated by API token.
        if self.path == "/webhook/github":
            return self.do_POST_webhook_github()
        if self.path == "/webhook/gitlab":
            return self.do_POST_webhook_gitlab()
        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST_webhook_github(self) -> None:
        raw, payload = _read_raw_body(self)
        # Verify GitHub signature if secret configured
        from .config import GITHUB_WEBHOOK_SECRET
        sig_header = self.headers.get("X-Hub-Signature-256", "")
        if GITHUB_WEBHOOK_SECRET:
            import hmac
            import hashlib

            if not sig_header.startswith("sha256="):
                _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Missing signature"})
                return
            signature = sig_header.split("=", 1)[1]
            mac = hmac.new(GITHUB_WEBHOOK_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(mac, signature):
                _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Invalid signature"})
                return
        # Basic GitHub webhook handling: create a review on PR open/synchronize
        try:
            event_id = self.headers.get("X-GitHub-Delivery", "")
            service = get_service()
            if not service.store.claim_webhook_event("github", event_id):
                _json_response(self, HTTPStatus.OK, {"status": "duplicate"})
                return
            repo = payload.get("repository", {}).get("full_name")
            pr = payload.get("pull_request")
            if repo and pr:
                number = pr.get("number")
                # enqueue a review request
                _retry(
                    lambda: service.create_review({"provider": "github", "repository": repo, "pull_request_number": number, "token": os.environ.get("GITHUB_TOKEN")}),
                )
        except Exception:
            pass
        _json_response(self, HTTPStatus.ACCEPTED, {"status": "ok"})

    def do_POST_webhook_gitlab(self) -> None:
        raw, payload = _read_raw_body(self)
        try:
            # Verify GitLab token if configured
            from .config import GITLAB_WEBHOOK_SECRET
            header_token = self.headers.get("X-Gitlab-Token", "")
            if GITLAB_WEBHOOK_SECRET and header_token != GITLAB_WEBHOOK_SECRET:
                _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Invalid GitLab webhook token"})
                return
            event_id = self.headers.get("X-Gitlab-Event-UUID", "") or self.headers.get("X-Request-Id", "")
            service = get_service()
            if not service.store.claim_webhook_event("gitlab", event_id):
                _json_response(self, HTTPStatus.OK, {"status": "duplicate"})
                return
            repo = payload.get("project", {}).get("path_with_namespace")
            mr = payload.get("object_attributes")
            if repo and mr:
                iid = mr.get("iid")
                _retry(
                    lambda: service.create_review({"provider": "gitlab", "repository": repo, "pull_request_number": iid, "token": os.environ.get("GITLAB_TOKEN")}),
                )
        except Exception:
            pass
        _json_response(self, HTTPStatus.ACCEPTED, {"status": "ok"})

    def _serve_frontend_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Frontend file missing"})
            return
        _text_response(self, HTTPStatus.OK, path.read_text(encoding="utf-8"), content_type)

    def log_message(self, format: str, *args: Any) -> None:
        return


def create_server(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), ReviewRequestHandler)


def main() -> None:
    for warning in validate_security_config():
        print(f"Warning: {warning}")
    server = create_server()
    print(f"Serving on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
