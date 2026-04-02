# TODO — python-fints FastAPI wrapper

This file lists open points, suggested next steps, and decisions to make for the FastAPI wrapper around `python-fints`.

Priority legend
- High: must-have before exposing this to untrusted networks
- Medium: important improvements for reliability, testing, and operator experience
- Low: nice-to-have features or future polish


---

## High priority

- Authentication & Authorization: require and validate credentials for all endpoints (at minimum an `API_KEY` or token). Protect `/confirm` especially.
- Replace in-memory sessions with a multi-process safe store (Redis) and a single worker or queue to resume operations. The current in-memory `_sessions` works only for single-process dev.
- TLS and deployment: run behind TLS (reverse proxy) and require HTTPS for production.
- Money transfer support: add a transfer endpoint to initiate SEPA credit transfers with strict validation, confirmation preview, and TAN-based authorization/resume flow.


## Medium priority

- Docker + docker-compose: provide a `Dockerfile` and `docker-compose.yml` with Redis for sessions for easy local and CI testing.
- Observability: structured logging, request IDs, and basic Prometheus metrics (request count, active sessions, TANs issued).
- Robust session lifecycle: make session TTL configurable via env var, provide endpoints to query/cancel sessions, ensure graceful shutdown closes active FinTS clients.


## Low priority / nice-to-have

- Rate limiting per IP or API key.
- Add a health/readiness probe that reflects ability to reach configured bank endpoints (optional separate check).


## Quick wins (recommended order)

1. Add a minimal API key auth dependency in `src/fastapi_app.py` (env var `API_KEY`) and protect all endpoints.
2. Add `response_model` using small Pydantic models (or convert serializable dataclasses to pydantic) so `/docs` lists correct schema.


## Decisions / questions (need your input)

- How should credentials be handled in production?
  - Option A: clients send PIN in each request (current behavior — not recommended)
  - Option B: clients register a profile (server stores encrypted credentials) and call endpoints by `profile_id` + optional PIN/TAN challenge only
  - Option C: integrate with an external secrets manager (Vault / KMS)

- Multi-process deployment: do you plan to run multiple uvicorn workers or multiple containers? If yes, we'll need Redis or a shared worker pattern for sessions.

- Authentication method: prefer a simple API key for now, or should I implement OAuth2 / JWT / mTLS?

- Session TTL: default 5 minutes OK or do you want another value?


## Implementation suggestions / design notes

- Sessions & resume flow:
  - Store minimal resume descriptor (callable or operation name + args) and reconstruct or persist enough state to resume the operation on the worker that holds the FinTS client.
  - Prefer a dedicated worker process that manages FinTS clients and only accepts resume/confirm operations from the API process via a queue or RPC.

- Security:
  - Never store raw PINs in logs or plaintext repositories.
  - Enforce HTTPS, use short-lived sessions for TANs, and add rate-limiting.


## Suggested next PRs (small, actionable)

- PR 1: Add simple API key auth and wire it to all endpoints.
- PR 2: Add basic Pydantic response models for account and transaction schemas and wire `response_model` into routes.
