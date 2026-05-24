from __future__ import annotations

from dataclasses import dataclass
import os
import json
import time
import urllib.request
import urllib.error
from typing import Any, Optional

from .models import Finding, ReviewContext, Severity


_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _retry(operation, attempts: int = 3, delay_seconds: float = 0.5):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if attempt < attempts - 1:
                time.sleep(delay_seconds * (attempt + 1))
    if last_error is not None:
        raise last_error


def _extract_json_text(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        if text.startswith("{"):
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                return text[start : end + 1]
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return None


def _coerce_finding_item(item: Any, fallback_id: str) -> Finding | None:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title", "")).strip()
    message = str(item.get("message", "")).strip()
    if not title or not message:
        return None

    severity_value = str(item.get("severity", "low")).lower()
    if severity_value not in {severity.value for severity in Severity}:
        severity_value = Severity.LOW.value

    file_path = item.get("file_path")
    if file_path is not None:
        file_path = str(file_path)

    line_start = item.get("line_start")
    if line_start is not None:
        try:
            line_start = int(line_start)
        except (TypeError, ValueError):
            line_start = None

    line_end = item.get("line_end")
    if line_end is not None:
        try:
            line_end = int(line_end)
        except (TypeError, ValueError):
            line_end = None

    recommendation = item.get("recommendation")
    if recommendation is not None:
        recommendation = str(recommendation).strip() or None

    evidence = item.get("evidence")
    if evidence is not None:
        evidence = str(evidence)

    category = str(item.get("category", "general")).strip() or "general"

    return Finding(
        id=str(item.get("id", fallback_id)),
        title=title[:160],
        message=message,
        severity=Severity(severity_value),
        category=category,
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        recommendation=recommendation,
        source="semantic",
        evidence=evidence,
    )


def _parse_findings(raw: str, prefix: str) -> list[Finding]:
    json_text = _extract_json_text(raw)
    if not json_text:
        return []

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        for key in ("findings", "items", "results"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                data = candidate
                break
        else:
            return []

    if not isinstance(data, list):
        return []

    findings: list[Finding] = []
    for index, item in enumerate(data):
        finding = _coerce_finding_item(item, f"{prefix}-{index + 1}")
        if finding is not None:
            findings.append(finding)
    return findings


def _request_with_retry(request: urllib.request.Request, timeout: int) -> Optional[str]:
    def _attempt() -> Optional[str]:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            if error.code in _RETRYABLE_STATUS_CODES:
                raise
            return None

    try:
        return _retry(_attempt)
    except Exception:
        return None


class ReviewModel:
    def review(self, prompt: str, context: ReviewContext) -> list[Finding]:
        raise NotImplementedError


@dataclass(slots=True)
class MockReviewModel(ReviewModel):
    """Safe fallback that proves the pipeline without calling a real provider."""

    def review(self, prompt: str, context: ReviewContext) -> list[Finding]:
        if "TODO" in context.diff:
            return [
                Finding(
                    id="semantic-1",
                    title="Follow-up work left in diff",
                    message="The diff contains a TODO marker that may indicate unfinished logic.",
                    severity=Severity.LOW,
                    category="maintainability",
                    file_path=None,
                    line_start=None,
                    line_end=None,
                    recommendation="Replace TODO markers with a tracked issue or complete the change before merge.",
                    source="semantic",
                    evidence="TODO",
                )
            ]
        return []


@dataclass(slots=True)
class OpenAIReviewModel(ReviewModel):
    api_key: Optional[str] = None
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1/chat/completions"

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        self.model = os.environ.get("OPENAI_MODEL", self.model)

    def _call_api(self, prompt: str) -> Optional[str]:
        if not self.api_key:
            return None
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert code reviewer. Return JSON only: a top-level array of findings."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 1500,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        body = _request_with_retry(req, timeout=30)
        if not body:
            return None
        try:
            parsed = json.loads(body)
        except Exception:
            return None
        choices = parsed.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message", {}).get("content") or choices[0].get("text")
        return message

    def review(self, prompt: str, context: ReviewContext) -> list[Finding]:
        raw = self._call_api(prompt)
        if not raw:
            return []

        # Try to extract JSON from model output
        return _parse_findings(raw, "semantic")


@dataclass(slots=True)
class HuggingFaceReviewModel(ReviewModel):
    api_key: Optional[str] = None
    model: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    base_url: str = "https://api-inference.huggingface.co/models"

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("HUGGINGFACE_API_KEY")
        self.model = os.environ.get("HUGGINGFACE_MODEL", self.model)
        self.base_url = os.environ.get("HUGGINGFACE_API_BASE", self.base_url)

    def _call_api(self, prompt: str) -> Optional[str]:
        if not self.api_key:
            return None
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 1500,
                "temperature": 0.0,
                "return_full_text": False,
            },
            "options": {
                "wait_for_model": True,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}/{self.model}"
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        body = _request_with_retry(req, timeout=90)
        if not body:
            return None
        try:
            parsed = json.loads(body)
        except Exception:
            return body
        if isinstance(parsed, list) and parsed:
            first = parsed[0]
            if isinstance(first, dict):
                return first.get("generated_text") or first.get("summary_text") or first.get("text")
            if isinstance(first, str):
                return first
        if isinstance(parsed, dict):
            return parsed.get("generated_text") or parsed.get("summary_text") or parsed.get("text")
        return body

    def review(self, prompt: str, context: ReviewContext) -> list[Finding]:
        raw = self._call_api(prompt)
        if not raw:
            return []

        return _parse_findings(raw, "semantic")


@dataclass(slots=True)
class LocalLlamaModel(ReviewModel):
    """Local Llama model runner.

    Behavior:
    - Prefer the `llama_cpp` Python binding (pip package `llama-cpp-python`) when available.
    - Fallback to invoking a local `llama.cpp` binary (e.g. `main`/`main.exe`) via subprocess.

    Required manual steps (brief):
    1. Obtain a Llama-compatible ggml model and place its path in the environment var `LLAMA_MODEL_PATH`.
    2. Either install `llama-cpp-python` (`pip install llama-cpp-python`) OR build `llama.cpp` and ensure the `main` executable is on PATH.

    Notes:
    - Running large models locally may require a GPU and substantial RAM; quantized ggml models run on CPU but with lower quality/throughput.
    - The class returns the model's raw text output and attempts to parse JSON findings like the OpenAI adapter.
    """

    model_path: Optional[str] = None
    max_tokens: int = 512
    temperature: float = 0.0

    def __post_init__(self) -> None:
        self.model_path = self.model_path or os.environ.get("LLAMA_MODEL_PATH")
        # Try to import the Python binding lazily
        self._use_binding = False
        self._client = None
        try:
            from llama_cpp import Llama  # type: ignore

            if self.model_path:
                self._client = Llama(model_path=self.model_path)
                self._use_binding = True
        except Exception:
            self._use_binding = False

    def _call_binding(self, prompt: str) -> Optional[str]:
        if not self._client:
            return None
        try:
            # llama-cpp-python exposes a create method returning a dict with 'choices'
            resp = self._client.create(prompt=prompt, max_tokens=self.max_tokens, temperature=self.temperature)
            # Try common response shapes
            if isinstance(resp, dict):
                choices = resp.get("choices") or []
                if choices and isinstance(choices, list):
                    text = choices[0].get("text") or choices[0].get("message", {}).get("content")
                    return text
                # newer bindings may return 'content' directly
                return resp.get("content") or resp.get("text")
        except Exception:
            return None
        return None

    def _call_subprocess(self, prompt: str) -> Optional[str]:
        import subprocess
        import shutil

        if not self.model_path:
            return None
        # Find an executable (main, main.exe or llama)
        candidates = ["main", "main.exe", "llama"]
        exe = None
        for c in candidates:
            path = shutil.which(c)
            if path:
                exe = path
                break
        if not exe:
            return None
        # Call the binary with arguments. Behavior depends on the particular build of llama.cpp.
        # We pass the prompt directly with -p; if your binary expects different args, adjust here.
        cmd = [exe, "-m", self.model_path, "-p", prompt, "--n_predict", str(self.max_tokens), "--temp", str(self.temperature)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            out = proc.stdout or proc.stderr
            return out
        except Exception:
            return None

    def _call_local(self, prompt: str) -> Optional[str]:
        if self._use_binding:
            out = self._call_binding(prompt)
            if out is not None:
                return out
        # fallback to subprocess
        return self._call_subprocess(prompt)

    def review(self, prompt: str, context: ReviewContext) -> list[Finding]:
        raw = self._call_local(prompt)
        if not raw:
            return []
        return _parse_findings(raw, "local-llama")
