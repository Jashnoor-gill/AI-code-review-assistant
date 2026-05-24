from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    NEEDS_APPROVAL = "needs_approval"
    REJECTED = "rejected"
    POSTED = "posted"
    FAILED = "failed"


@dataclass(slots=True)
class Finding:
    id: str
    title: str
    message: str
    severity: Severity
    category: str
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    recommendation: str | None = None
    source: str = "static"
    evidence: str | None = None


@dataclass(slots=True)
class ReviewContext:
    provider: str
    repository: str
    pull_request_number: int | None
    title: str
    base_branch: str
    head_branch: str
    author: str | None
    diff: str
    files_changed: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReviewJob:
    job_id: str
    state: ReviewState = ReviewState.PENDING
    progress: int = 0
    message: str = "Queued"
    findings: list[Finding] = field(default_factory=list)
    markdown_comment: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
