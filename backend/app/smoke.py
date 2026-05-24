from __future__ import annotations

import json

import tempfile
import threading
import time
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

from .server import create_server
from .service import build_default_service
from .storage import ReviewStore


def _request(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    temp_dir = tempfile.mkdtemp()
    try:
        store = ReviewStore(Path(temp_dir) / "reviews.sqlite3")
        service = build_default_service(store)
        server = create_server(port=0)
        server.RequestHandlerClass.server = server  # type: ignore[attr-defined]
        server._service_override = service  # type: ignore[attr-defined]

        from . import server as server_module

        server_module.get_service.cache_clear()  # type: ignore[attr-defined]
        server_module.get_service = lambda: service  # type: ignore[assignment]

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            time.sleep(0.1)
            host, port = server.server_address
            health = _request(f"http://{host}:{port}/api/health")
            assert health["status"] == "ok"

            job = _request(
                f"http://{host}:{port}/api/reviews",
                method="POST",
                payload={
                    "provider": "local-git",
                    "title": "Smoke test",
                    "repository": "local",
                    "diff": "diff --git a/app.py b/app.py\n@@ -1 +1 @@\n-print('hi')\n+eval(user_input)\n",
                },
            )
            assert job["job_id"]
            assert job["findings"]

            approved = _request(f"http://{host}:{port}/api/jobs/{job['job_id']}/approve", method="POST", payload={})
            assert approved["state"] == "posted"
        finally:
            server.shutdown()
            server.server_close()
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            # On Windows the sqlite file can be briefly locked; ignore cleanup errors in smoke
            pass

    print("smoke test passed")


if __name__ == "__main__":
    main()
