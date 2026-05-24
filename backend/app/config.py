from __future__ import annotations

import os
from pathlib import Path


def _clean(value: str | None, default: str = "") -> str:
	return (value or default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
	return _clean(os.environ.get(name), "true" if default else "false").lower() in ("1", "true", "yes")

# Optionally load a .env file for local development if python-dotenv is installed
try:
	from dotenv import load_dotenv  # type: ignore

	_env_path = Path(__file__).resolve().parents[2] / ".env"
	if _env_path.exists():
		load_dotenv(str(_env_path))
except Exception:
	pass


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_DIR = Path(os.environ.get("AI_CODE_REVIEW_DATA", ROOT_DIR / "data"))
DB_PATH = DATA_DIR / "reviews.sqlite3"
API_TOKEN = _clean(os.environ.get("AI_CODE_REVIEW_TOKEN"))
HOST = _clean(os.environ.get("AI_CODE_REVIEW_HOST"), "127.0.0.1")
PORT = int(_clean(os.environ.get("AI_CODE_REVIEW_PORT"), "8000"))
REQUIRE_API_TOKEN = _env_bool("AI_CODE_REVIEW_REQUIRE_API_TOKEN")
GITHUB_WEBHOOK_SECRET = _clean(os.environ.get("GITHUB_WEBHOOK_SECRET"))
GITLAB_WEBHOOK_SECRET = _clean(os.environ.get("GITLAB_WEBHOOK_SECRET"))


def validate_security_config() -> list[str]:
	warnings: list[str] = []
	if REQUIRE_API_TOKEN and not API_TOKEN:
		warnings.append("AI_CODE_REVIEW_REQUIRE_API_TOKEN is enabled but AI_CODE_REVIEW_TOKEN is empty.")
	return warnings
