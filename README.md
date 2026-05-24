# AI Code Review Assistant

This workspace now contains the source repos you provided plus a unified starter project that pulls the strongest patterns into one clean structure.

## What was carried over

- Security-first review flow from `SecureAgent`: deterministic rules first, semantic review second.
- Adapter-based ingestion from `codedog`: separate GitHub, GitLab, and local diff sources.
- Strict prompt contracts and structured output handling from `ai-code-review-cli`, `codedog`, `CodeSage`, and `Prism`.
- Streaming / job-oriented workflow ideas from `Agentic-Code-Review-Assistant` and webhook-driven review posting from `CodeSage`.

## Current scaffold

- `backend/app/models.py`: core data models for diffs, findings, and review jobs.
- `backend/app/adapters.py`: source adapters for GitHub, GitLab, and local git.
- `backend/app/scanner.py`: deterministic static checks.
- `backend/app/prompts.py`: prompt builder with strict output contract.
- `backend/app/llm.py`: semantic review interface with Hugging Face as the default provider, plus local Llama, OpenAI, and a safe mock provider.
- `backend/app/pipeline.py`: scan -> review -> merge -> markdown formatting.
- `backend/app/server.py`: HTTP server for the API and static frontend.
- `backend/app/storage.py`: SQLite persistence for reviews and events.
- `backend/app/service.py`: orchestration layer for creating, approving, and rejecting reviews.
- `backend/app/smoke.py`: end-to-end smoke test for the backend API.
- `frontend/`: static browser UI for submitting and reviewing findings.

## How to run the demo

From `backend`:

```bash
python -m app.demo
```

To run the full app:

```bash
cd backend
python -m app.server
```

Then open `http://127.0.0.1:8000`.

To run the smoke test:

```bash
cd backend
python -m app.smoke
```

## Environment variables

Copy `backend/.env.example` to `backend/.env` for local development and fill in secrets. The project will load `.env` automatically if `python-dotenv` is installed.

Important variables:
- `AI_CODE_REVIEW_TOKEN`: API token used by clients to call protected endpoints.
- `AI_CODE_REVIEW_REQUIRE_API_TOKEN`: `true` to enforce token requirement (recommended for staging/production).
- `HUGGINGFACE_API_KEY`, `HUGGINGFACE_MODEL`, `HUGGINGFACE_API_BASE`: Hugging Face provider config.
- `LLAMA_MODEL_PATH`: Path to a local ggml model to enable local Llama inference.
- `OPENAI_API_KEY`, `OPENAI_MODEL`: optional OpenAI fallback config.
- `GITHUB_TOKEN`, `GITLAB_TOKEN`: tokens used to post comments back to PRs/MRs.

Security notes
--------------
- Never commit `.env` to source control. Add `backend/.env` to `.gitignore`.
- Use a secrets manager in CI / production (GitHub Actions secrets, Azure Key Vault, AWS Secrets Manager).
- Create low-privilege tokens for posting comments and rotate them regularly.
- If you set `AI_CODE_REVIEW_REQUIRE_API_TOKEN=true`, also set `AI_CODE_REVIEW_TOKEN`; the server prints a startup warning when the token is missing.

## Hugging Face setup

If you want Hugging Face to power reviews, set these in `backend/.env`:

```env
HUGGINGFACE_API_KEY=hf_your_token_here
HUGGINGFACE_MODEL=Qwen/Qwen2.5-Coder-7B-Instruct
HUGGINGFACE_API_BASE=https://api-inference.huggingface.co/models
```

Then run:

```bash
cd backend
python -m app.smoke
```

## Token guide

See [backend/TOKEN_GUIDE.md](backend/TOKEN_GUIDE.md) for the minimum GitHub token permissions and where to paste each value.

## Next step

If you want, I can turn this scaffold into a real FastAPI + Next.js app next, using the same pattern set.