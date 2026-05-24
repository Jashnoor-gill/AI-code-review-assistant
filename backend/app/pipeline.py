from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .llm import ReviewModel
from .models import Finding, ReviewContext, ReviewJob, ReviewState, Severity
from .prompts import build_review_prompt
from .scanner import StaticRuleScanner
import re


def _slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "job"


def _severity_rank(severity: Severity) -> int:
    order = {
        Severity.LOW: 1,
        Severity.MEDIUM: 2,
        Severity.HIGH: 3,
        Severity.CRITICAL: 4,
    }
    return order[severity]


def _deduplicate(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str | None, int | None, str]] = set()
    result: list[Finding] = []
    for finding in findings:
        key = (finding.title, finding.file_path, finding.line_start, finding.source)
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result


def _group_by_category(findings: list[Finding]) -> dict[str, list[Finding]]:
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.category].append(finding)
    return dict(grouped)


def format_markdown_review(context: ReviewContext, findings: list[Finding]) -> str:
    if not findings:
        return f"## Review for {context.title}\n\nNo issues detected."

    grouped = _group_by_category(findings)
    sections: list[str] = [f"## Review for {context.title}"]
    for category, category_findings in sorted(grouped.items()):
        sections.append(f"\n### {category.title()}")
        for finding in sorted(category_findings, key=lambda item: _severity_rank(item.severity), reverse=True):
            location = ""
            if finding.file_path:
                location = f" ({finding.file_path}:{finding.line_start or '?'}{f'-{finding.line_end}' if finding.line_end and finding.line_end != finding.line_start else ''})"
            sections.append(
                f"- **{finding.title}** [{finding.severity}]{location}\n"
                f"  - {finding.message}\n"
                f"  - Recommendation: {finding.recommendation or 'Review manually.'}"
            )
    return "\n".join(sections)


@dataclass(slots=True)
class ReviewPipeline:
    scanner: StaticRuleScanner
    model: ReviewModel

    def run(self, context: ReviewContext) -> ReviewJob:
        job = ReviewJob(job_id=f"review-{context.provider}-{_slugify(context.title)}", state=ReviewState.RUNNING, progress=10, message="Scanning diff")

        static_findings = self.scanner.scan(context)
        job.progress = 45
        job.message = "Running semantic review"

        prompt = build_review_prompt(context, static_findings)
        semantic_findings = self.model.review(prompt, context)

        merged = _deduplicate(static_findings + semantic_findings)
        job.findings = merged
        job.markdown_comment = format_markdown_review(context, merged)
        job.progress = 100
        job.state = ReviewState.NEEDS_APPROVAL if merged else ReviewState.POSTED
        job.message = "Review complete"
        return job
