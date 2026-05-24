# Token Guide

This project uses Hugging Face as the default model provider.

## Hugging Face token

Add this to `backend/.env`:

```env
HUGGINGFACE_API_KEY=hf_your_token_here
HUGGINGFACE_MODEL=Qwen/Qwen2.5-Coder-7B-Instruct
HUGGINGFACE_API_BASE=https://api-inference.huggingface.co/models
```

Recommended Hugging Face scopes
- Use the token that can make inference calls.
- Do not enable extra permissions unless you need to manage endpoints.
- If you no longer need the old token, revoke it and create a new one.

## GitHub token

Only needed if you want the assistant to post comments back to GitHub.

Add this to `backend/.env`:

```env
GITHUB_TOKEN=gh_your_token_here
GITHUB_WEBHOOK_SECRET=your_webhook_secret
```

Minimum GitHub fine-grained token permissions for this app
- Contents: Read & write
- Pull requests: Read & write
- Issues: Read & write
- Metadata: Read
- Webhooks: Create and manage if you want the app to register webhooks

## GitLab token

Only needed if you want GitLab comment posting or webhook support.

Add this to `backend/.env`:

```env
GITLAB_TOKEN=glpat_your_token_here
GITLAB_WEBHOOK_SECRET=your_webhook_secret
```

## API token for this app

If you want to protect the HTTP API itself, set:

```env
AI_CODE_REVIEW_TOKEN=your_local_service_token
AI_CODE_REVIEW_REQUIRE_API_TOKEN=true
```

If `AI_CODE_REVIEW_REQUIRE_API_TOKEN=true` and `AI_CODE_REVIEW_TOKEN` is empty, the server prints a warning at startup and protected endpoints will reject requests.

## Quick reminder

Never commit `backend/.env`.
