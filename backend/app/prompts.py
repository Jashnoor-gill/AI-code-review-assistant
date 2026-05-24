from __future__ import annotations

from .models import Finding, ReviewContext


def build_review_prompt(context: ReviewContext, static_findings: list[Finding]) -> str:
    static_section = "\n".join(
        f"- [{finding.severity}] {finding.title}: {finding.message}"
        for finding in static_findings
    ) or "- None"

    return f"""You are an expert code reviewer.

Review the pull request using these rules:
- Focus on bugs, security risks, performance bottlenecks, and maintainability issues.
- Return JSON only.
- Each finding must include: title, message, severity, category, file_path, line_start, line_end, recommendation, evidence.
- Use the severities: low, medium, high, critical.
- Do not invent file paths or lines that are not supported by the diff.

Repository: {context.repository}
Title: {context.title}
Base branch: {context.base_branch}
Head branch: {context.head_branch}

Static findings already detected:
{static_section}

Diff:
{context.diff}
"""
