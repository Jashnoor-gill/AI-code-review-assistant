from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Finding, ReviewContext, Severity


@dataclass(slots=True)
class ScanRule:
    pattern: re.Pattern[str]
    title: str
    message: str
    severity: Severity
    category: str
    recommendation: str


DEFAULT_RULES = [
    ScanRule(
        pattern=re.compile(r"\beval\s*\("),
        title="Dynamic code execution",
        message="eval() can execute attacker-controlled input.",
        severity=Severity.CRITICAL,
        category="security",
        recommendation="Replace dynamic evaluation with an explicit parser or allowlist.",
    ),
    ScanRule(
        pattern=re.compile(r"subprocess\.(run|Popen)\(.*shell\s*=\s*True", re.DOTALL),
        title="Shell execution with shell=True",
        message="Running a shell command with shell=True increases injection risk.",
        severity=Severity.HIGH,
        category="security",
        recommendation="Pass arguments as a list and avoid shell expansion.",
    ),
    ScanRule(
        pattern=re.compile(r"(api_key|secret|token|password)\s*=\s*['\"]?[A-Za-z0-9_\-]{8,}", re.IGNORECASE),
        title="Possible hardcoded credential",
        message="A value that looks like a credential is hardcoded in the diff.",
        severity=Severity.HIGH,
        category="security",
        recommendation="Move secrets to environment variables or a secret manager.",
    ),
    ScanRule(
        pattern=re.compile(r"\.unwrap\(|\.get\(\)\s*!|assert\s+false", re.IGNORECASE),
        title="Unsafe failure handling",
        message="This pattern can hide a crash path or make the failure mode brittle.",
        severity=Severity.MEDIUM,
        category="reliability",
        recommendation="Handle the error explicitly and return a structured failure.",
    ),
]


class StaticRuleScanner:
    def __init__(self, rules: list[ScanRule] | None = None) -> None:
        self.rules = rules or DEFAULT_RULES

    def scan(self, context: ReviewContext) -> list[Finding]:
        findings: list[Finding] = []
        lines = context.diff.splitlines()
        for line_number, line in enumerate(lines, start=1):
            for rule in self.rules:
                if rule.pattern.search(line):
                    findings.append(
                        Finding(
                            id=f"static-{len(findings) + 1}",
                            title=rule.title,
                            message=rule.message,
                            severity=rule.severity,
                            category=rule.category,
                            file_path=None,
                            line_start=line_number,
                            line_end=line_number,
                            recommendation=rule.recommendation,
                            source="static",
                            evidence=line.strip(),
                        )
                    )
        return findings
