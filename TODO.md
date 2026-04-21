# TODO — easy-fints HTTP API

This file lists open points, suggested next steps, and decisions to make for the HTTP API adapter around `python-fints`.

Priority legend
- High: must-have before exposing this to untrusted networks
- Medium: important improvements for reliability, testing, and operator experience
- Low: nice-to-have features or future polish

## Current status

Already implemented:

- FastAPI endpoints for `/accounts`, `/balance`, `/transactions`, `/transfer`, `/transfer/retry-with-name`, and `/confirm`
- dedicated `DELETE /sessions/{session_id}` cancel endpoint for active confirmation sessions
- read-only `GET /sessions/{session_id}` endpoint for active session inspection
- explicit confirmation/session states for `awaiting_tan`, `awaiting_decoupled`, and `awaiting_vop`
- auth-free API design with request-driven credentials/config and no profile abstraction
- SEPA single transfer flow with field validation, TAN resume, VoP handling, retry with corrected recipient name, instant payment, and scheduled execution dates
- normalized unsupported transfer product errors for instant/scheduled transfer capability issues
- structured `transfer_overview` payload in non-final transfer challenge responses and final `200` transfer responses
- configurable session inactivity TTL via `FINTS_SESSION_TTL_SECONDS`
- graceful shutdown closes active FinTS clients via FastAPI lifespan handlers
- request-driven `POST /readiness` probe for bank/server reachability via anonymous FinTS bank-info lookup
- response models and OpenAPI-visible schemas for the main endpoints
- manual TAN/VoP helper scripts and workflow documentation
- transaction normalization through dedicated mapping modules under `easy_fints/transaction_mapping/`
- opt-in transaction debug logging with `FINTS_DEBUG_LEVEL` and `FINTS_DEBUG_FAIL_ONLY`

Not implemented yet:

- optional deployment hardening for exposed environments


---

## High priority

- TLS and deployment: run behind TLS (reverse proxy) and require HTTPS for production.


## Medium priority

- Observability: structured logging, request IDs, and basic Prometheus metrics (request count, active sessions, TANs issued).


## Low priority / nice-to-have

- Rate limiting per IP or API key.


## Decisions / questions (need your input)

- Credentials/config handling is intentionally request-driven:
  - no server-side profile model
  - no persistent credential store
  - no server-managed user/account records
  - only short-lived runtime session state in memory while an active confirm flow is in progress

## Implementation suggestions / design notes

- Sessions & resume flow:
  - Keep sessions process-local and in memory only.
  - Do not introduce profile storage, credential persistence, or server-managed account metadata.

- Security:
  - Never store raw PINs in logs or plaintext repositories.
  - Keep the server stateless with respect to persistent user data; only ephemeral in-memory runtime state for active confirmations is acceptable.
  - Avoid persisting live FinTS dialog state, pending TAN objects, or raw client objects in central storage unless there is a very strong reason and compensating controls.
  - Keep the core API auth-free for easy integration, and prefer external protection layers such as network isolation, reverse proxy auth, mTLS, or VPN if deployment requires access control.
  - Enforce HTTPS, use short-lived sessions for TANs, and add rate-limiting where exposure warrants it.
  - Treat `logs/debug.log` as sensitive when `FINTS_DEBUG_LEVEL=record_raw` is enabled.
