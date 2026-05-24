from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import ReviewJob, ReviewState
from .serialization import job_from_dict, job_to_dict


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ReviewStore:
    db_path: Path

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_jobs (
                    job_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    repository TEXT NOT NULL,
                    state TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_events (
                    source TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(source, event_id)
                )
                """
            )
            connection.commit()

    def upsert_job(self, job: ReviewJob, provider: str, repository: str, title: str) -> ReviewJob:
        payload = json.dumps(job_to_dict(job), ensure_ascii=True)
        timestamp = _utc_now()
        with self._connect() as connection:
            existing = connection.execute("SELECT created_at FROM review_jobs WHERE job_id = ?", (job.job_id,)).fetchone()
            created_at = existing[0] if existing else timestamp
            connection.execute(
                """
                INSERT INTO review_jobs(job_id, provider, repository, state, title, payload, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    provider = excluded.provider,
                    repository = excluded.repository,
                    state = excluded.state,
                    title = excluded.title,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (job.job_id, provider, repository, job.state.value, title, payload, created_at, timestamp),
            )
            connection.commit()
        return job

    def load_job(self, job_id: str) -> ReviewJob | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM review_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return job_from_dict(json.loads(row[0]))

    def list_jobs(self, limit: int = 50) -> list[ReviewJob]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM review_jobs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [job_from_dict(json.loads(row[0])) for row in rows]

    def update_state(self, job_id: str, state: ReviewState, message: str | None = None) -> ReviewJob | None:
        job = self.load_job(job_id)
        if job is None:
            return None
        job.state = state
        if message is not None:
            job.message = message
        self.upsert_job(job, job.metadata.get("provider", "local"), job.metadata.get("repository", "local"), job.metadata.get("title", job.job_id))
        self.append_event(job_id, state.value, message or state.value)
        return job

    def append_event(self, job_id: str, event_type: str, message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO review_events(job_id, event_type, message, created_at) VALUES(?, ?, ?, ?)",
                (job_id, event_type, message, _utc_now()),
            )
            connection.commit()

    def claim_webhook_event(self, source: str, event_id: str) -> bool:
        """Return True the first time a webhook delivery is seen, False for duplicates."""
        if not source or not event_id:
            return True
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO webhook_events(source, event_id, created_at) VALUES(?, ?, ?)",
                (source, event_id, _utc_now()),
            )
            connection.commit()
            return cursor.rowcount > 0
