# Local semantic review gateway

`review_server.py` is the MacBook Pro side of the cost-aware review path:

1. GitHub deterministic CI remains authoritative for static/runtime checks.
2. GitHub-hosted Actions sends a bounded semantic prompt to this gateway.
3. The gateway runs the fixed `Qwen3-Coder-Next Q3_K_XL` model in LM Studio.
4. GitHub-hosted Actions independently falsifies the local draft with free-tier
   Gemma 4 26B A4B.
5. Any local outage, malformed draft, Gemma rejection/quota error, or high-risk
   policy gate falls back to Vertex Gemini 3.7 Flash.

The gateway is intentionally **not** a self-hosted GitHub Actions runner. The
repository is public, so PR-controlled workflow code must never obtain shell
execution on a developer workstation. The gateway exposes only a bounded text
inference operation for one fixed local model; it has no checkout, file-read,
tool-call, arbitrary-command, or arbitrary-model API.

## Runtime contract

- HTTP origin binds only to `127.0.0.1:8765`.
- A Cloudflare Tunnel exposes the authenticated `/v1/review` endpoint.
- `/healthz` contains no repository or credential data.
- The bearer token is stored outside the repository with mode `0600` and is
  mirrored to the GitHub Actions `LOCAL_REVIEW_TOKEN` repository secret.
- Requests above the configured prompt/body limits are rejected.
- LM Studio loads `qwen_qwen3-coder-next` at 32K context with a short TTL so the
  ~36 GiB model is not permanently resident when review traffic stops.
- The service logs request metadata only, never prompt bodies or credentials.

If the MacBook is asleep/offline, GitHub's local-review HTTP step fails closed
and the existing Vertex path remains available. No merge/CI decision depends on
the workstation being online.
