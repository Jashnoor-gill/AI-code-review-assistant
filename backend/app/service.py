from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapters import GitHubAdapter, GitLabAdapter, LocalGitAdapter
from .llm import MockReviewModel, ReviewModel, HuggingFaceReviewModel, LocalLlamaModel, OpenAIReviewModel
from .models import ReviewContext, ReviewJob, ReviewState
from .pipeline import ReviewPipeline
from .storage import ReviewStore


def _normalize_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


@dataclass(slots=True)
class ReviewService:
    store: ReviewStore
    model: ReviewModel
    pipeline: ReviewPipeline | None = None
    local_adapter: LocalGitAdapter | None = None
    github_adapter: GitHubAdapter | None = None
    gitlab_adapter: GitLabAdapter | None = None

    def __post_init__(self) -> None:
        if self.pipeline is None:
            self.pipeline = ReviewPipeline(scanner=__import__("app.scanner", fromlist=["StaticRuleScanner"]).StaticRuleScanner(), model=self.model)
        self.local_adapter = LocalGitAdapter()
        self.github_adapter = GitHubAdapter()
        self.gitlab_adapter = GitLabAdapter()

    def _build_context(self, payload: dict[str, Any]) -> ReviewContext:
        provider = payload.get("provider", "local-git")
        reference = payload.get("reference", payload.get("diff", ""))
        if provider == "github":
            self.github_adapter.token = payload.get("token")
            return self.github_adapter.fetch_context(reference, payload)
        if provider == "gitlab":
            self.gitlab_adapter.token = payload.get("token")
            return self.gitlab_adapter.fetch_context(reference, payload)
        return self.local_adapter.fetch_context(reference, payload)

    def create_review(self, payload: dict[str, Any]) -> ReviewJob:
        context = self._build_context(payload)
        context.metadata.update(_normalize_metadata(payload))
        context.metadata["provider"] = context.provider
        context.metadata["repository"] = context.repository
        context.metadata["title"] = context.title

        job = self.pipeline.run(context)
        job.metadata = {
            "provider": context.provider,
            "repository": context.repository,
            "title": context.title,
            "context": payload,
        }
        self.store.upsert_job(job, context.provider, context.repository, context.title)
        self.store.append_event(job.job_id, "created", "Review completed")
        return job

    def get_job(self, job_id: str) -> ReviewJob | None:
        return self.store.load_job(job_id)

    def list_jobs(self) -> list[ReviewJob]:
        return self.store.list_jobs()

    def approve_job(self, job_id: str) -> ReviewJob | None:
        job = self.store.update_state(job_id, ReviewState.POSTED, "Approved and posted")
        return job

    def reject_job(self, job_id: str, reason: str = "Rejected by reviewer") -> ReviewJob | None:
        job = self.store.update_state(job_id, ReviewState.REJECTED, reason)
        return job

    def to_review_payload(self, job: ReviewJob) -> dict[str, Any]:
        from .serialization import job_to_dict

        return job_to_dict(job)


def build_default_service(store: ReviewStore) -> ReviewService:
    # Prefer Hugging Face if API key is provided, then local Llama, then OpenAI, then Mock
    from . import llm as _llm
    hf_key = _llm.os.environ.get("HUGGINGFACE_API_KEY")
    llama_path = _llm.os.environ.get("LLAMA_MODEL_PATH")
    openai_key = _llm.os.environ.get("OPENAI_API_KEY")
    if hf_key:
        model = HuggingFaceReviewModel(api_key=hf_key)
    elif llama_path:
        model = LocalLlamaModel(model_path=llama_path)
    elif openai_key:
        model = OpenAIReviewModel(api_key=openai_key)
    else:
        model = MockReviewModel()
    return ReviewService(store=store, model=model)
