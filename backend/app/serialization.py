from __future__ import annotations

from .models import Finding, ReviewContext, ReviewJob, ReviewState, Severity


def finding_to_dict(finding: Finding) -> dict:
    return {
        "id": finding.id,
        "title": finding.title,
        "message": finding.message,
        "severity": finding.severity.value,
        "category": finding.category,
        "file_path": finding.file_path,
        "line_start": finding.line_start,
        "line_end": finding.line_end,
        "recommendation": finding.recommendation,
        "source": finding.source,
        "evidence": finding.evidence,
    }


def finding_from_dict(data: dict) -> Finding:
    return Finding(
        id=data["id"],
        title=data["title"],
        message=data["message"],
        severity=Severity(data["severity"]),
        category=data["category"],
        file_path=data.get("file_path"),
        line_start=data.get("line_start"),
        line_end=data.get("line_end"),
        recommendation=data.get("recommendation"),
        source=data.get("source", "static"),
        evidence=data.get("evidence"),
    )


def context_to_dict(context: ReviewContext) -> dict:
    return {
        "provider": context.provider,
        "repository": context.repository,
        "pull_request_number": context.pull_request_number,
        "title": context.title,
        "base_branch": context.base_branch,
        "head_branch": context.head_branch,
        "author": context.author,
        "diff": context.diff,
        "files_changed": list(context.files_changed),
        "metadata": dict(context.metadata),
    }


def context_from_dict(data: dict) -> ReviewContext:
    return ReviewContext(
        provider=data.get("provider", "local-git"),
        repository=data.get("repository", "local"),
        pull_request_number=data.get("pull_request_number"),
        title=data.get("title", "Untitled review"),
        base_branch=data.get("base_branch", "main"),
        head_branch=data.get("head_branch", "HEAD"),
        author=data.get("author"),
        diff=data.get("diff", ""),
        files_changed=list(data.get("files_changed", [])),
        metadata=dict(data.get("metadata", {})),
    )


def job_to_dict(job: ReviewJob) -> dict:
    return {
        "job_id": job.job_id,
        "state": job.state.value,
        "progress": job.progress,
        "message": job.message,
        "findings": [finding_to_dict(item) for item in job.findings],
        "markdown_comment": job.markdown_comment,
        "metadata": dict(job.metadata),
    }


def job_from_dict(data: dict) -> ReviewJob:
    return ReviewJob(
        job_id=data["job_id"],
        state=ReviewState(data.get("state", ReviewState.PENDING.value)),
        progress=data.get("progress", 0),
        message=data.get("message", "Queued"),
        findings=[finding_from_dict(item) for item in data.get("findings", [])],
        markdown_comment=data.get("markdown_comment", ""),
        metadata=dict(data.get("metadata", {})),
    )
