# Simulated FinTS Backend Use Cases

## Goal

Track the high-level use cases for a simulated FinTS backend that can drive the REST wrapper without talking to a real bank.

The simulated backend should help us verify:

- request validation
- session lifecycle
- `/transfer` and `/confirm` flow control
- TAN / decoupled / VoP handling
- capability errors for unsupported transfer products
- stable integration behavior across different software stacks

## Scope

This document tracks behavioral use cases, not the low-level implementation.

The simulation should behave like a deterministic FinTS backend from the point of view of:

- `PyFinIntegrationClient`
- FastAPI endpoints
- helper scripts
- API consumers

## Principles

- No real bank access is required.
- Scenarios must be deterministic and repeatable.
- The simulation should cover both happy paths and failure paths.
- The simulation should model stateful confirm flows, not only static one-shot responses.
- The simulation should stay high-level enough that different internal implementations are possible.

## Core Use Cases

| ID | Use case | Expected high-level behavior | Priority | Status |
|---|---|---|---|---|
| UC-01 | Accounts without confirmation | `POST /accounts` returns a normal `200` response | High | Planned |
| UC-02 | Accounts with TAN requirement | `POST /accounts` returns `409 tan_required`, then `/confirm` completes successfully | High | Verified |
| UC-03 | Transactions with decoupled confirmation | `POST /transactions` returns `awaiting_decoupled`, repeated `/confirm` reaches final success | High | Verified |
| UC-04 | Transfer happy path | `POST /transfer` returns final `200` without follow-up confirmation | High | Verified |
| UC-05 | Transfer with TAN | `POST /transfer` returns `tan_required`, `/confirm` returns final transfer result | High | Planned |
| UC-06 | Transfer with decoupled confirmation | `POST /transfer` returns `confirmation_pending` or `tan_required` with `awaiting_decoupled`, `/confirm` loops until success | High | Planned |
| UC-07 | Transfer with VoP exact match | transfer enters `awaiting_vop`, user approves, flow finishes successfully | High | Verified |
| UC-08 | Transfer with VoP close match and retry-with-name | transfer enters `awaiting_vop`, user retries with corrected name, same session continues, flow resumes | High | Verified |
| UC-09 | Transfer with VoP rejected by user | user does not approve VoP, session can be cancelled or left to expire | Medium | Planned |
| UC-10 | Transfer overview propagation | `transfer_overview` appears in non-final transfer responses and final `200` transfer responses | High | Verified |
| UC-11 | Instant payment supported | `instant_payment=true` behaves like a supported transfer product | High | Planned |
| UC-12 | Instant payment unsupported | API returns `422 unsupported_transfer_product` instead of a generic error | High | Verified |
| UC-13 | Scheduled transfer supported | `execution_date=YYYY-MM-DD` creates a dated transfer flow that can finish successfully | High | Planned |
| UC-14 | Scheduled transfer unsupported | API returns a normalized unsupported-product error when the bank/simulator rejects dated transfers | High | Verified |
| UC-15 | Cancel active session | `DELETE /sessions/{session_id}` closes the active session and later `/confirm` returns `404` | High | Verified |
| UC-16 | Inspect active session | `GET /sessions/{session_id}` returns state, next action, expiry, and optional transfer overview | High | Verified |
| UC-17 | Session expiry | expired sessions are pruned and later `/confirm` or `/sessions/{id}` returns `404` | High | Verified |
| UC-18 | Shutdown cleanup | active simulated sessions are closed cleanly on app shutdown | Medium | Verified |
| UC-19 | Unknown session operation safety | invalid or corrupted session state fails safely with an explicit API error | Medium | Planned |
| UC-20 | Repeated confirm safety | duplicate or late `/confirm` calls after completion/cancel/expiry fail predictably | Medium | Planned |

## Suggested Scenario Sets

### Read scenarios

- accounts success
- accounts TAN required
- balance success
- transactions decoupled

### Transfer scenarios

- standard transfer success
- TAN-required transfer
- decoupled transfer
- VoP exact match
- VoP close match with retry
- instant payment supported
- instant payment unsupported
- scheduled transfer supported
- scheduled transfer unsupported

### Session scenarios

- inspect active session
- cancel active session
- session expiry
- shutdown cleanup

## Out of Scope for the First Simulation

- real PSD2 or bank certificate handling
- real FinTS message encoding and transport
- real account data persistence
- full performance benchmarking
- multi-bank behavior parity in one step

## Open Design Decision

The simulated backend should probably be introduced as an interchangeable backend/adapter rather than as a separate HTTP service.

That would keep:

- local development simple
- tests fast
- scenario injection deterministic

## Tracking Notes

- Keep this file at use-case level.
- Put technical design details in code, tests, or a separate implementation note later.
- Link each implemented scenario to one or more verification checks in `VERIFICATION.md`.
- The automated simulated checks currently live in:
  [tests/test_api_read_flows.py](/home/bomay/git/python-fints-REST-wrapper/tests/test_api_read_flows.py),
  [tests/test_api_transfer_flows.py](/home/bomay/git/python-fints-REST-wrapper/tests/test_api_transfer_flows.py),
  and [tests/test_api_session_lifecycle.py](/home/bomay/git/python-fints-REST-wrapper/tests/test_api_session_lifecycle.py).
